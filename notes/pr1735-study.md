# Study: Modal local-mode prototype (gitcode PR #1735, commit f3f89d712d, branch mr-1735)

Base: old `dev` branch (edcbf064). 226 files, +7312/−1698. Core: 6 new files, notably
`src/Sema/TypeCheckModal.cpp` (1205 lines — the entire checker) and `AST/ModalInfo.h`.
All references below are into the mr-1735 commit (read via `git show f3f89d712d:<path>`).

## Headline for our design

**A lambda's mode is never inferred from its captures.** It comes from the expected type
only (`ChkLamExpr`, LambdaExpr.cpp:356-359 — sole input `target.Modal()`), defaults to
`@~local` in synthesis position, and captures are validated AFTERWARDS against the fixed
mode in a separate post-typecheck pass (`ModalTypeChecker::CheckCapture`,
TypeCheckModal.cpp:739-756; driven from `PostTypeCheck`, TypeChecker.cpp:2044). Flow is
strictly: expected type → lambda mode → (later) capture-legality check. **The circularity
we feared is absent, and the architecture actively supports keeping it absent.**

## Facts we build on

- Syntax: modes are atomic tokens `@~local` / `@local!` / `@local?` (Tokens.inc:179-182,
  single-token lexing with backtracking, Lexer.cpp:1626-1677); type-suffix position;
  `this @mode` receiver via new ThisParam node; `exclave` as modifier + expression;
  `@MakeCopy` structs. No `demode` in this prototype.
- Representation: `ModalInfo` is an immutable field on every `Ty` (Types.h:427-433),
  **participates in interning identity, hashing, and mangling** (BaseMangler.cpp:175-189).
  Retroactively changing a mode is NOT a local edit — changes Ty identity, symbol names,
  overload selection. Strongest argument for capability-blind mode determination.
- Lattice: `~local(01) <: local?(11)`, `local!(10) <: local?(11)`; `local?` is TOP
  (may-be-either), not bottom. Restriction to local! is an incomparable move from ~local,
  not a join (C6).
- Copy short-circuit: `IsModalSubtype` returns true unconditionally for Copy types
  (TypeManager.cpp:1243-1251); `CheckCapture` early-returns for Copy targets
  (TypeCheckModal.cpp:742-744). Ready-made "mode-transparent" hatch.
- Regions: strictly per-function-activation. CHIR StartRegion/EndRegion at entry/exits,
  `needsRegion` per-function bool. **No block/try-scoped region construct exists**;
  try-scoped capability regions would be a new granularity (but CHIR's depth-counted
  region checker could nest). For ERASED capabilities no CHIR region is needed at all.
- Modes are inside type checking (fused types+modes phase), not a separate phase; only
  VALIDATION (`CheckModalType`) is a separate pass at PostTypeCheck (TypeChecker.cpp:2044),
  after captureKind computation, before DESUGAR_AFTER_SEMA.
- C4 pitfall: lambdas synthesized by DESUGAR_AFTER_SEMA (incl. effect-handler try lambdas)
  are never modal-checked. Our capability check should sit immediately after CheckModalType
  on the same pre-desugar AST so both checks see the same lambdas.
- Prototype gaps (don't inherit): partial instantiation hard-disabled; CHIR devirt
  disabled; `LambdaExpr::needsRegion` uninitialized + not cloned; zero end-to-end tests.

## Integration seams (P-points, full table in the agent transcript)

- P1/P2 (leave untouched): LambdaExpr.cpp:356-359 (check-mode lambda mode from target) and
  SynLamExpr — no capability data may flow here; this is where the cycle would bite.
- P3/P5 (the phantom filter): either early-return capability-typed targets in CheckCapture
  (mirroring the Copy early-return) or make CanThrow mode-transparent in IsModalSubtype
  (TypeManager.cpp:1243-1251) — the cheapest global bypass; modes then ignore capabilities
  everywhere at once.
- P4: `CheckCaptures` walker (TypeCheckModal.cpp:758-786) is the natural template/place to
  COLLECT capability captures (def-site vs use-site via ScopeManager).
- P6: insert our capability-scope check right after CheckModalType at TypeChecker.cpp:2044
  (when Modal exists; until then our own pass placement per implementation plan M3).
- P7: replicate the SHAPE of IsExternalLocal (TypeCheckModal.cpp:184-225) for try-scopes:
  "is this capability reference external to the innermost enclosing try?"
- P8: don't touch needsRegion/CHIR — erased capabilities need no runtime region.
- P9: **exclave is an explicit escape edge** our capability check must handle: it switches
  allocation/region to the caller and reclassifies internality; Modal bans it inside
  try/catch but NOT inside finally — our check treats exclave boundaries explicitly.
- P10: our pass needs its own analogues of CheckCallExpr/CheckAssignExpr for "capability-
  carrying value passed/stored".

## Soundness note

Capability-blind modes + separate capability check is sound because try-regions nest
strictly inside function regions: "doesn't escape its try" implies "doesn't escape the
function", so the finer discipline can never permit what the coarser forbids — except via
exclave (P9), which must be an explicit edge in our check.

## Consequence for the usability cost

The prototype's cost ("synthesis-position lambdas default to ~local; capability-capturing
ones would need ascription") mostly dissolves under phantom capabilities: Modal never sees
capability captures, so a synthesis-position literal capturing only capabilities stays
`~local` for Modal; OUR check enforces the try-scope discipline (use-before-try-close,
no assignment out of the try) and errors only on actual escape attempts. No ascription
burden in the common case.
