#!/usr/bin/env python3
"""Rewrite chexc so no commit carries formatter churn, via three-way merge.

For each file at each commit:
    B  = upstream base content (original formatting)
    B' = clang-format-15(B)          -- what our old whole-file fmt turned B into
    H  = the commit's content        -- formatted, with our semantic edits
    result = git merge-file --ours H B' B

Both sides of diff(B',H) are formatted, so that diff is purely semantic; merging it onto
the UNFORMATTED B reinstates upstream layout everywhere we did not edit. Conflicts (a
region both reformatted and edited) resolve to ours, i.e. our formatted version — correct,
since that region genuinely changed.

Gate: the result must be token-identical to the input tree per file, ignoring include
ORDER (clang-format sorted includes; restoring upstream order is intended). Refs are only
moved after every file passes. The tree WILL differ from the old head, so the caller must
rebuild and run the full gate before pushing.
"""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from denoise_format import toks  # noqa: E402

REPO = "/home/penguin/Projs/effects-research/cangjie/cangjie_compiler"
BRANCH = "chexc"
BACKUP = "chexc-concentrated-fmt"
FORMATTABLE = (".cpp", ".h", ".inc")

def git(*a, input=None, env=None):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(["git", "-C", REPO, *a], input=input, env=e,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"git {' '.join(a)} failed:\n{r.stderr}")
    return r.stdout.strip()

def blob(rev, path):
    r = subprocess.run(["git", "-C", REPO, "show", f"{rev}:{path}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None

def sig(text):
    """(sorted include set, token stream without includes) — include ORDER ignored."""
    lines = text.splitlines(keepends=True)
    # set, not multiset: clang-format dedupes repeated includes, and restoring an
    # upstream duplicate is a no-op under include guards. A genuinely LOST include
    # still fails this check.
    inc = sorted({re.sub(r"\s+", " ", x.strip())
                  for x in lines if x.lstrip().startswith("#include")})
    rest = [x for x in lines if not x.lstrip().startswith("#include")]
    return inc, toks(rest)

def main():
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("worktree dirty")
    base = git("merge-base", "origin/main", BRANCH)
    head = git("rev-parse", BRANCH)
    commits = git("rev-list", "--reverse", f"{base}..{BRANCH}").split()
    union = sorted({p for c in commits
                    for p in git("diff-tree", "--no-commit-id", "--name-only", "-r", c).split()
                    if p.endswith(FORMATTABLE) and not p.startswith("third_party/")})
    print(f"base {base[:10]}  head {head[:10]}  {len(commits)} commits  {len(union)} files")

    tmp = tempfile.mkdtemp(prefix="denoise3-", dir="/tmp/claude-1000")
    os.makedirs(f"{tmp}/w")
    subprocess.run(["cp", os.path.join(REPO, ".clang-format"), f"{tmp}/w/"], check=True)

    # formatted base (B') for every file, one container run
    base_txt, ext = {}, {}
    for p in union:
        b = blob(base, p)
        if b is None:
            continue
        base_txt[p] = b
        ext[p] = os.path.splitext(p)[1]
        with open(f"{tmp}/w/{p.replace('/', '@')}{ext[p]}", "w") as f:
            f.write(b)
    r = subprocess.run(["sg", "docker", "-c",
                        f"docker run --rm -i --cpus=8 -v {tmp}/w:/w -w /w cangjie-dev "
                        "bash -c 'ls | grep -v clang-format | xargs -P 8 -n 16 clang-format-15 -i'"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"formatting base failed:\n{r.stderr}")
    fbase = {p: open(f"{tmp}/w/{p.replace('/', '@')}{ext[p]}").read() for p in base_txt}
    print(f"formatted {len(fbase)} base files")

    cache, idx = {}, f"{tmp}/index"
    env = {"GIT_INDEX_FILE": idx}
    conflicts_total = 0

    def tree_for(rev):
        nonlocal conflicts_total
        git("read-tree", rev, env=env)
        for p in union:
            ls = git("ls-tree", rev, "--", p, env=env)
            if not ls:
                continue
            mode, _t, oid = ls.split()[0:3]
            if oid in cache:
                new = cache[oid]
            else:
                if p not in base_txt:            # added by the branch: leave as-is
                    new = oid
                else:
                    h = blob(rev, p)
                    for nm, txt in (("H", h), ("Bf", fbase[p]), ("B", base_txt[p])):
                        with open(f"{tmp}/{nm}", "w") as f:
                            f.write(txt)
                    m = subprocess.run(
                        ["git", "merge-file", "--ours", "-p", f"{tmp}/H", f"{tmp}/Bf", f"{tmp}/B"],
                        capture_output=True, text=True)
                    if m.returncode < 0:
                        sys.exit(f"merge-file crashed on {p}")
                    res = m.stdout
                    conflicts_total += res.count("<<<<<<<")
                    if sig(res) != sig(h):
                        sys.exit(f"SIGNATURE MISMATCH in {p} at {rev[:10]} — aborting")
                    new = git("hash-object", "-w", "--stdin", input=res)
                cache[oid] = new
            if new != oid:
                git("update-index", "--cacheinfo", f"{mode},{new},{p}", env=env)
        return git("write-tree", env=env)

    parent, mapping, dropped = base, [], 0
    for c in commits:
        tree = tree_for(c)
        if tree == git("rev-parse", f"{parent}^{{tree}}"):
            dropped += 1
            print(f"  (dropped, empty) {git('log', '-1', '--format=%s', c)[:60]}")
            continue
        meta = git("log", "-1", "--format=%an%x00%ae%x00%aD%x00%cn%x00%ce%x00%cD", c).split("\x00")
        msg = subprocess.run(["git", "-C", REPO, "log", "-1", "--format=%B", c],
                             capture_output=True, text=True).stdout
        parent = git("commit-tree", tree, "-p", parent, input=msg, env={
            "GIT_AUTHOR_NAME": meta[0], "GIT_AUTHOR_EMAIL": meta[1], "GIT_AUTHOR_DATE": meta[2],
            "GIT_COMMITTER_NAME": meta[3], "GIT_COMMITTER_EMAIL": meta[4], "GIT_COMMITTER_DATE": meta[5]})
        mapping.append((c, parent))
        print(f"{c[:10]} -> {parent[:10]}  old:[{git('diff', '--shortstat', f'{c}^', c)}]  "
              f"new:[{git('diff', '--shortstat', f'{parent}^', parent)}]")

    print(f"\nconflict markers produced: {conflicts_total} (must be 0)")
    if conflicts_total:
        sys.exit("conflicts present — aborting")
    print(f"dropped {dropped} empty commit(s)")
    print(f"branch total: old [{git('diff', '--shortstat', base, head)}]")
    print(f"              new [{git('diff', '--shortstat', base, parent)}]")
    git("branch", "-f", BACKUP, head)
    with open(f"{tmp}/map.txt", "w") as f:
        for o, n in mapping:
            f.write(f"{o} {n}\n")
    print(f"\nbackup {BACKUP} -> {head[:10]}; map {tmp}/map.txt")
    print(f"new head {parent}\nADOPT WITH:  git -C {REPO} reset --hard {parent}")

if __name__ == "__main__":
    main()
