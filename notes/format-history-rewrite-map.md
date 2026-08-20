# chexc format-history rewrite — 2026-08-20

Old head `85c06a22` preserved as branch `chexc-whole-file-fmt`. Final tree is
**byte-identical** to the old head, so every gate run against it still holds.
The new root commit `5ab6d939` (`style: clang-format-15 sweep`) was proven
token-identical to its parent across all 51 files, modulo whitespace, comments
(clang-format adds `// namespace`) and trailing commas before a closing brace.

Include ORDER was deliberately excluded from the rewrite (`--sort-includes=0`):
`src/Parse/ASTChecker.cpp` carries one include-order deviation in the real head,
and reordering includes is semantic, not formatting.

| old | new | commit |
|---|---|---|
| 8125feac3c | ff0d051b98 | feat(chexc): experimental checked exceptions — flag, token |
| 3585be92be | cc196a0c50 | feat(chexc): capability lists in types — elaboration, subt |
| 517ddc3ca8 | 7b877052dd | feat(chexc): capability argument checking — CapabilityChec |
| b987f87c12 | 95622d3ec4 | feat(chexc): unchecked exceptions and class capturing (pro |
| 37cae377fd | 21c4498c03 | feat(chexc): capability parameter inference (proposal 6.3) |
| 3734b4ff47 | b9e8c24d62 | feat(chexc): capability list aliases (proposal 6.1) |
| 858edc6884 | 33ba75a676 | fix(chexc): audit batch 1 — soft keywords, captures scopin |
| 6c3e898e36 | f9a0910aae | fix(chexc): audit batch 2 — capability lists lost through  |
| 5ae78b5ec9 | 579ce0e1d0 | fix(chexc): audit batch 3 — generic substitution and overr |
| f04f595993 | 1c94b2c38a | feat(chexc): assumption imports (proposal 5.2.2) |
| a4e995a0d2 | 247a7d02cc | feat(chexc): capability lists cross package boundaries (pr |
| ede5af34b2 | afa7adc7bf | feat(chexc): effect requirement checking, 'performs' claus |
| ec3a5a1e1f | 9c1ec8dca5 | fix(chexc): review findings F1-F5; clause changes now spre |
| 2fbd93edd1 | d4358dce4c | fix(chexc): the Error hierarchy never demands a capability |
| 85c06a229d | 0c664a4836 | fix(chexc): assumption-import changes invalidate the incre |
