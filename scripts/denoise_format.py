#!/usr/bin/env python3
"""Restore upstream formatting everywhere the branch did not semantically change code.

Our old whole-file `fmt` reformatted entire files, so the branch diff against upstream is
full of hunks that only rewrap/realign pre-existing code. This computes, per file, a
"de-noised" version: start from HEAD's content and revert every diff block that is
token-identical to the base (i.e. pure formatting), keeping blocks that carry real edits.

Safety property: de-noising never changes tokens, only whitespace/comment layout, so the
de-noised tree is token-equivalent to the input tree. Callers must still build and test.
"""
import difflib
import re
import subprocess
import sys

REPO = "/home/penguin/Projs/effects-research/cangjie/cangjie_compiler"
FORMATTABLE = (".cpp", ".h", ".inc")

def git(*a, text=True):
    r = subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=text)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr}")
    return r.stdout

def toks(lines):
    """Token stream insensitive to every difference clang-format is allowed to make:
    whitespace, comments, macro line-continuations, string-literal splitting, and a
    trailing comma before a closing bracket."""
    s = "".join(lines)
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
        elif c == "\\" and i + 1 < n and s[i + 1] in "\r\n":
            i += 1                                   # macro line-continuation
        elif s.startswith("//", i):
            j = s.find("\n", i)
            i = n if j < 0 else j
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "\"'":
            j, buf = i + 1, []
            while j < n and s[j] != c:
                if s[j] == "\\" and j + 1 < n:
                    buf.append(s[j:j + 2]); j += 2
                else:
                    buf.append(s[j]); j += 1
            kind = "STR" if c == '"' else "CHR"
            # adjacent literals concatenate: "ab" == "a" "b"
            if out and out[-1][0] == kind:
                out[-1] = (kind, out[-1][1] + "".join(buf))
            else:
                out.append((kind, "".join(buf)))
            i = j + 1
        else:
            m = re.match(r"[A-Za-z_]\w*|\d[\w.]*", s[i:])
            if m:
                out.append(("TOK", m.group())); i += len(m.group())
            else:
                out.append(("TOK", c)); i += 1
    return [t for k, t in enumerate(out)
            if not (out[k] == ("TOK", ",") and k + 1 < len(out)
                    and out[k + 1][1] in "}])")]

def denoise(base_lines, head_lines):
    """head with pure-formatting blocks reverted to base. Returns (lines, reverted_blocks)."""
    sm = difflib.SequenceMatcher(None, base_lines, head_lines, autojunk=False)
    out, reverted = [], 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.extend(base_lines[i1:i2])
        elif toks(base_lines[i1:i2]) == toks(head_lines[j1:j2]):
            out.extend(base_lines[i1:i2])   # pure formatting -> keep upstream layout
            reverted += 1
        else:
            out.extend(head_lines[j1:j2])   # real change -> keep ours
    return out, reverted

def files_changed(base, rev):
    out = git("diff", "--name-only", base, rev)
    return [p for p in out.split("\n")
            if p.endswith(FORMATTABLE) and not p.startswith("third_party/")]

def content(rev, path):
    r = subprocess.run(["git", "-C", REPO, "show", f"{rev}:{path}"],
                       capture_output=True, text=True)
    return r.stdout.splitlines(keepends=True) if r.returncode == 0 else None

def main():
    base, rev = sys.argv[1], sys.argv[2]
    total_before = total_after = 0
    rows = []
    for p in files_changed(base, rev):
        b, h = content(base, p), content(rev, p)
        if b is None or h is None:
            continue
        d, nrev = denoise(b, h)
        if toks(d) != toks(h):
            raise SystemExit(f"TOKEN LOSS in {p} — aborting")
        before = sum(1 for _ in difflib.unified_diff(b, h, n=0) if _[0] in "+-" and not _.startswith(("+++", "---")))
        after = sum(1 for _ in difflib.unified_diff(b, d, n=0) if _[0] in "+-" and not _.startswith(("+++", "---")))
        total_before += before
        total_after += after
        rows.append((before - after, before, after, nrev, p))
    rows.sort(reverse=True)
    print(f"{'saved':>7} {'before':>7} {'after':>6} {'blocks':>7}  file")
    for saved, before, after, nrev, p in rows[:18]:
        print(f"{saved:>7} {before:>7} {after:>6} {nrev:>7}  {p}")
    print(f"\nTOTAL changed lines: {total_before} -> {total_after} "
          f"({100*(total_before-total_after)//max(total_before,1)}% is pure formatting)")

if __name__ == "__main__":
    main()
