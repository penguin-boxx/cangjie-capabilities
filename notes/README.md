# notes/ — index and working rules

## The documents

- `gap-analysis.md` — **the** proposal ↔ implementation gap document. Part I: what the
  implementation must change. Part II: what the proposal must change (errata, design tensions,
  open readings to rule, stdlib rulings needed). Part III: resolved, kept for the lessons.
- `architecture.md` — pipeline design, the modes-vs-capabilities resolution, the built/not-built
  status, the key facts about how the feature is wired into the compiler, and the five
  implementation questions with the answers the implementation gave them.
- `autonomous-decisions.md` — the author's rulings 1–14 and the decisions D1–D18 taken without
  consultation, each with its rationale; the "why" behind the code.
- `property-clauses-design.md` — the design for clauses on properties (E-19/I31): the two ruled
  forms, where the clause lives in the AST, how it is distributed, and what it costs.
- `caplist-design.md` — why capability lists are canonicalized at producer boundaries rather than
  at interning, the four sites, and what is deliberately left alone.
- `test-baseline.md` — the upstream baseline established before any change, the feature's own test
  groups, the current gate numbers, and which suite catches which class of defect.
- `conversions-adapt-plan.md` — plan for the two extensions; outside the current tier by ruling.
- `stdlib-exception-inventory.md` — classification data for the stdlib migration.

Reference, rarely changes:

- `format-history-rewrite-map.md` — old→new SHA map for the two `chexc` history rewrites.
- `prototype-study.md`, `pr1735-study.md` — studies of the colleague's prototype and of the Modal
  PR that shaped the staging decisions.

Convention: cite proposal sections by **title**, never by number — the numbering changes.

## Working rules

### Repos, branches, remotes

All under `/home/penguin/Projs/effects-research/cangjie/`; development branch `chexc` everywhere,
remote name `capabilities`:

| repo | contents | remote |
|---|---|---|
| `cangjie_compiler` | the compiler | `github.com/penguin-boxx/cangjie-compiler-capabilities` |
| `cangjie_test` | LLT suites (ours: `testsuites/LLT/compiler/CheckedExceptions/`) | `…/cangjie-test-capabilities` |
| `cangjie_runtime` | runtime + stdlib | `…/cangjie-runtime-capabilities` |
| `cangjie_stdx` | stdx | `…/cangjie-stdx-capabilities` |

Never commit to `main`. Push `chexc` after every commit. `cangjie_runtime` and `cangjie_stdx` track
`main` locally and push as `HEAD:chexc`. A clone must be unshallowed (`git fetch --unshallow
origin`) before its first push — shallow packs are rejected.

### Build and test

Everything runs in docker via `cj.py`; nothing is installed on the host.

- `./cj.py build compiler` — incremental compiler build (ccache warm). Slow: ~10–20 min.
- `./cj.py build std` / `./cj.py build stdx` — stdlib and stdx, both at `warn` (the flags are in
  `cj.py`; building std without them fails at parse, since the stdlib carries clauses).
- `./cj.py test compiler` — ctest unit tests, 49/49. MacroTest compiles against the installed SDK,
  so std must be rebuilt after a compiler change or it fails spuriously.
- `./cj.py test llt --filter <paths…> -j N` — LLT groups; see `test-baseline.md` for which suite
  catches what, and for the current expected numbers.
- `./cj.py fmt <repo>` — clang-format over branch-changed files. Takes a **repo directory**, not a
  component name.
- `./cj.py sh -- '<cmd>'` — any command in the build container. Each invocation is a fresh
  container: `/tmp` does not survive, write to `/work/logs/`.

### Process

1. **Builds are very slow.** Batch every edit of a cycle; run `fmt` **before** the build, never
   after; one build per cycle; run every suite against that build.
2. **Probe before believing.** A rule the text states and the code seems to implement is worth six
   lines of CangJie to check — three of five suspected gaps in the 2026-08-23 re-read were not
   gaps, and two real ones were places where reasoning had replaced reading.
3. **A passing test is evidence only if it discriminates.** Assert locations, not just messages;
   check that the test fails against the unfixed compiler when that is cheap to arrange.
4. **Verified-only commits, review-sized**, `feat(chexc)`/`test(chexc)`/`fix(chexc)` prefixes, gate
   numbers in the body. Never commit a failing test — a reproducer for an open defect belongs in
   `gap-analysis.md`, not in the suite.
5. **Update `gap-analysis.md` in the same round**: close what you fixed, record what you found,
   and write the questions you could not answer into it rather than blocking on them.
6. **Never start implementation without the author's go-ahead.** Rulings settle what is right, not
   that the work starts now.
7. **Out of scope by ruling:** escape analysis of any kind (regions, carrier tracking — they belong
   to Modal), and anything outside proposal sections 3, 5 and 6 plus the obvious std/stdx
   annotations. Diagnostics never mention `@ local!` while Modal is absent.
