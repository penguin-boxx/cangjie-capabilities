# notes/ — index

Living documents (update these):
- `gap-analysis.md` — **the** proposal ↔ implementation gap document. Part I: what the
  implementation must change. Part II: what the proposal must change (errata, design
  tensions, open readings to rule, stdlib rulings needed). Part III: resolved, kept for lessons.
- `architecture.md` — pipeline design, the modes-vs-capabilities resolution, the built/not-built
  status, and the five implementation questions with the answers the implementation gave them.
- `autonomous-decisions.md` — decisions D1–D18 with rationale; the "why" behind the code.
- `conversions-adapt-plan.md` — implementation plan for the two extensions (now outside the
  base design; priority below Part I of the gap analysis).
- `stdlib-exception-inventory.md` — classification data for the stdlib migration.
- `caplist-design.md` — why capability lists are canonicalized at producer boundaries rather
  than at interning, the four sites, and what is deliberately left alone (C16).

Reference (rarely changes):
- `format-history-rewrite-map.md` — old→new SHA map for the two `chexc` history rewrites.
- `prototype-study.md`, `pr1735-study.md` — studies of the colleague's prototype and the
  Modal PR that shaped the staging decisions.
- `test-baseline.md` — the upstream baseline established before any change, the feature's own
  twelve test groups, the current gate numbers, and which suite catches which class of defect.

Historical execution plans (superseded; kept for provenance, not maintained):
- `implementation-plan.md` (holds author rulings 1–14), `handoff-plan.md`, `batch2-guide.md`.

Convention: cite proposal sections by **title**, never by number.
