#!/usr/bin/env python3
"""Rewrite cangjie_compiler's chexc history to isolate whole-file clang-format churn.

Problem: cj.py's fmt used to reformat WHOLE files changed vs origin/main, so feature
commits carry many hunks that merely reformat pre-existing upstream code (cj.py now
formats changed lines only; this script cleans up the history the old behavior left).

Approach: normalize every touched formattable file to its clang-format-15 form at EVERY
commit, and put the base-side normalization into one style commit at the branch root.
Every inter-commit diff is then a diff between co-formatted trees, so formatting churn
disappears from feature commits — including the two files where a commit deliberately
carried a hand-minimized diff and a later sweep re-churned them (first-touch bookkeeping
cannot handle those; format-everywhere can). clang-format-15 is idempotent on its own
output, and the branch HEAD is already format-clean, so the FINAL TREE IS BYTE-IDENTICAL
— verified at the end; a differing final tree aborts before any ref moves.

Formatting runs inside the cangjie-dev container (clang-format-15 — the exact version
that produced the churn; the host's clang-format differs and would not cancel it).

Effects: creates branch backup `chexc-whole-file-fmt` at the old head, moves `chexc` to
the rewritten chain, writes an old->new SHA map to scratch. Does NOT push.
"""
import os
import subprocess
import sys
import tempfile

ROOT = "/home/penguin/Projs/effects-research/cangjie"
REPO = os.path.join(ROOT, "cangjie_compiler")
BRANCH = "chexc"
BACKUP = "chexc-whole-file-fmt"
FORMATTABLE = (".cpp", ".h", ".inc")

def git(*args, input=None, env=None, strip=True):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(["git", "-C", REPO, *args], input=input, env=e,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr}")
    return r.stdout.strip() if strip else r.stdout

def formattable(path):
    return path.endswith(FORMATTABLE) and not path.startswith("third_party/")

def main():
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("worktree dirty — commit or stash first")
    base = git("merge-base", "origin/main", BRANCH)
    head = git("rev-parse", BRANCH)
    print(f"base {base[:12]}  head {head[:12]}")

    if git("diff", "--diff-filter=DR", "--name-only", base, BRANCH):
        sys.exit("branch deletes/renames files — this script does not handle that")

    commits = git("rev-list", "--reverse", f"{base}..{BRANCH}").splitlines()
    touched = {c: [p for p in git("diff-tree", "--no-commit-id", "--name-only",
                                  "-r", c).splitlines() if formattable(p)]
               for c in commits}
    union = sorted({p for ps in touched.values() for p in ps})
    print(f"{len(commits)} commits, {len(union)} formattable files touched")

    # ---- collect unique blobs to format: (oid, ext) at base and at each commit ----
    need = {}  # oid -> ext
    def note(rev, path):
        out = subprocess.run(["git", "-C", REPO, "rev-parse", f"{rev}:{path}"],
                             capture_output=True, text=True)
        if out.returncode == 0:
            need.setdefault(out.stdout.strip(), os.path.splitext(path)[1])
    for p in union:
        note(base, p)
    for c in commits:
        for p in touched[c]:
            note(c, p)
    print(f"{len(need)} unique blobs to format")

    # ---- format all blobs in one container run ----
    tmp = tempfile.mkdtemp(prefix="fmt15-", dir="/tmp/claude-1000")
    os.makedirs(f"{tmp}/blobs")
    cf = os.path.join(REPO, ".clang-format")
    subprocess.run(["cp", cf, f"{tmp}/.clang-format"], check=True)
    for oid, ext in need.items():
        with open(f"{tmp}/blobs/{oid}{ext}", "w") as f:
            f.write(git("cat-file", "blob", oid, strip=False))
    dr = subprocess.run(
        ["sg", "docker", "-c",
         f"docker run --rm -i --cpus=8 -v {tmp}:/fmt -w /fmt cangjie-dev "
         "bash -c 'ls blobs | sed s,^,blobs/, | xargs -P 8 -n 32 clang-format-15 -i'"],
        capture_output=True, text=True)
    if dr.returncode != 0:
        sys.exit(f"container formatting failed:\n{dr.stderr}")
    fmt_oid = {}   # original oid -> formatted oid (hash-object -w), identity if unchanged
    for oid, ext in need.items():
        with open(f"{tmp}/blobs/{oid}{ext}") as f:
            content = f.read()
        new = git("hash-object", "-w", "--stdin", input=content)
        fmt_oid[oid] = new
    changed = sum(1 for a, b in fmt_oid.items() if a != b)
    print(f"{changed}/{len(need)} blobs change under clang-format-15")

    # ---- tree surgery helpers ----
    idx = f"{tmp}/index"
    env = {"GIT_INDEX_FILE": idx}
    def rewrite_tree(rev, paths):
        git("read-tree", rev, env=env)
        for p in paths:
            ls = git("ls-tree", rev, "--", p, env=env)
            if not ls:
                continue
            mode, _type, oid = ls.split()[0:3]
            new = fmt_oid.get(oid, oid)
            if new != oid:
                git("update-index", "--cacheinfo", f"{mode},{new},{p}", env=env)
        return git("write-tree", env=env)

    # ---- style root commit ----
    style_tree = rewrite_tree(base, union)
    parent = base
    mapping = []
    if style_tree != git("rev-parse", f"{base}^{{tree}}"):
        parent = git("commit-tree", style_tree, "-p", base, input=(
            "style: clang-format-15 sweep of files later touched by chexc\n\n"
            "Mechanical, no semantic change. Concentrates the whole-file formatting\n"
            "churn that cj.py's old fmt spread across every feature commit; the\n"
            "feature commits that follow are pure semantic diffs against this.\n\n"
            "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>\n"))
        print(f"style commit {parent[:12]}")

    # ---- rewrite the chain ----
    for c in commits:
        tree = rewrite_tree(c, union)
        meta = git("log", "-1", "--format=%an%x00%ae%x00%aD%x00%cn%x00%ce%x00%cD", c).split("\x00")
        msg = git("log", "-1", "--format=%B", c, strip=False)
        parent = git("commit-tree", tree, "-p", parent, input=msg, env={
            "GIT_AUTHOR_NAME": meta[0], "GIT_AUTHOR_EMAIL": meta[1], "GIT_AUTHOR_DATE": meta[2],
            "GIT_COMMITTER_NAME": meta[3], "GIT_COMMITTER_EMAIL": meta[4], "GIT_COMMITTER_DATE": meta[5]})
        mapping.append((c, parent))
        old_st = git("diff", "--shortstat", f"{c}^", c)
        new_st = git("diff", "--shortstat", f"{parent}^", parent)
        print(f"{c[:10]} -> {parent[:10]}\n    old: {old_st}\n    new: {new_st}")

    # ---- the safety gate: final tree must be byte-identical ----
    if git("rev-parse", f"{head}^{{tree}}") != git("rev-parse", f"{parent}^{{tree}}"):
        sys.exit("FINAL TREE DIFFERS — aborting before touching any ref")
    print("final tree identical — verified")

    git("branch", "-f", BACKUP, head)
    git("branch", "-f", BRANCH, parent)
    with open(f"{tmp}/sha-map.txt", "w") as f:
        for old, new in mapping:
            f.write(f"{old} {new}\n")
    print(f"backup at {BACKUP}; {BRANCH} moved; sha map: {tmp}/sha-map.txt")
    print("NOT pushed — inspect, then: git push capabilities +chexc chexc-whole-file-fmt")

if __name__ == "__main__":
    main()
