# chexc history rewrites — 2026-08-20

Two rewrites, both preserving semantics exactly. Branch diff vs upstream went from
**3472+/743−** to **2925+/73−**: every hunk that merely reformatted pre-existing
upstream code is gone, and the deletions that remain are real.

| branch | head | what it is |
|---|---|---|
| `chexc` | `0754bfdb` | current — formatter churn removed |
| `chexc-concentrated-fmt` | `0c664a48` | rewrite 1: churn concentrated in one style commit |
| `chexc-whole-file-fmt` | `85c06a22` | original history as first written |

## How rewrite 2 worked

Per file per commit: `git merge-file --ours HEAD_version clang-format(base) base`.
Both sides of `diff(clang-format(base), HEAD)` are formatted, so that diff is purely
semantic; replaying it onto the *unformatted* base restores upstream layout everywhere
we did not edit. Zero conflicts across all 16 commits.

Gates: per-file token+include signature before any ref moved; whole-tree semantic
equivalence vs the backup (49 files differ textually, 0 semantically); build clean;
**LLT 5961/5961**; **ctest 49/49**.

Deliberate exceptions, each verified:
- Include ORDER is restored to upstream (clang-format had sorted it) — order is not formatting.
- Two upstream duplicate `#include`s that clang-format had deduped are restored
  (`ConstantsUtils.h`, `StructInheritanceChecker.cpp`); harmless under include guards.
- One merge-introduced duplicate (`TypeCheckUtil.cpp`) was found by a scan of all 63
  touched files and removed in `0754bfdb`.
- `NAME_TO_ANNO_KIND` reflows as a whole construct because we add an entry to it:
  9 lines, accepted so `cj.py fmt --check` stays meaningful.

Recurrence is prevented: `cj.py fmt` now formats only changed lines (`git diff -U0`
ranges), so no future commit accumulates whole-file churn.

## SHA map (original → current)

| original | current | commit |
|---|---|---|
| 8125feac3c | 286d87c0c4 | feat(chexc): experimental checked exceptions — flag, token |
| 3585be92be | 49adf8d73a | feat(chexc): capability lists in types — elaboration, subt |
| 517ddc3ca8 | 24930a55e9 | feat(chexc): capability argument checking — CapabilityChec |
| b987f87c12 | 635c3ae72b | feat(chexc): unchecked exceptions and class capturing (pro |
| 37cae377fd | 596efafd90 | feat(chexc): capability parameter inference (proposal 6.3) |
| 3734b4ff47 | d4f09ef0e4 | feat(chexc): capability list aliases (proposal 6.1) |
| 858edc6884 | f03bab140d | fix(chexc): audit batch 1 — soft keywords, captures scopin |
| 6c3e898e36 | 8234ca7e00 | fix(chexc): audit batch 2 — capability lists lost through  |
| 5ae78b5ec9 | d54a90a3ef | fix(chexc): audit batch 3 — generic substitution and overr |
| f04f595993 | 078c0093f4 | feat(chexc): assumption imports (proposal 5.2.2) |
| a4e995a0d2 | ccb5dad88e | feat(chexc): capability lists cross package boundaries (pr |
| ede5af34b2 | 91745cb9b7 | feat(chexc): effect requirement checking, 'performs' claus |
| ec3a5a1e1f | 666a619545 | fix(chexc): review findings F1-F5; clause changes now spre |
| 2fbd93edd1 | c06d090df9 | fix(chexc): the Error hierarchy never demands a capability |
| 85c06a229d | 75b042a3b9 | fix(chexc): assumption-import changes invalidate the incre |
