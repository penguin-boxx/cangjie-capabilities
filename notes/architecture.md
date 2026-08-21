# Architecture sketch: checked exceptions (the implicit capability passing design, extensible to the convenience features)

Goal: implement the base design (the implicit capability passing design) with stage separation that later accommodates
capability parameter inference ("Capability parameter inference"), conversions ("Exception conversions"), aliases ("Capability list aliases"), captures ("Capability capturing"),
and Modal escape analysis ("Escape analysis") without restructuring.

## Load-bearing observations from the proposal

1. "Generics": capability lists of argument functions are excluded from generic type-argument
   inference. "Overloading": overload resolution ignores capability lists. "Capability argument inference": capabilities are
   witnesses only; which one is chosen is unobservable. Together: **core type checking never
   needs the result of capability resolution** — capability checking can run after Sema.
2. "Phase ordering" pipeline: `types → modes → capability parameters → capability arguments`.
   Capability-parameter inference ("Capability parameter inference") is a distinct phase; capability-argument checking
   ("Capability argument inference") runs last. No fixpoint: inference is one bottom-up SCC pass; cycles among
   inference-eligible decls are errors ("Recursion").
3. Capabilities are fully erased ("Implicit capability passing design", "ABI and reflection"): they never become params, args, mangled names,
   or CHIR. The cjo must carry `throws` lists (cross-package checking), so serialization
   happens from signature data, not from materialized params.

## Why not the colleague's staging

His prototype resolves implicits eagerly inside `TypeCheckCall` (diagnostics interleaved with
type checking), integrates implicit lists into Ty unification/JoinAndMeet, mutates interned
FuncTys in place after cjo-save, and mangles implicits into symbols. Each of these blocks
inference: an unresolved capability at a call is *not yet an error* if the enclosing callable
may infer it; unification over capability lists is row-typing "Generics" forbids; ABI must not see
capabilities at all. See notes/prototype-study.md — we reuse his scope/introduction machinery
shapes, not his staging.

## Components

### A. Front-end representation (Parse/AST)
- `throws E1, E2` clause on callables: soft-keyword parse (Peek().Value()=="throws"), stored
  as a clause node on FuncBody/decl (position-carrying, for diagnostics & tooling). Must work
  for functions, methods, ctors, prop accessors (move past the prop early-return), operators,
  extensions, interface methods; order with `where` arbitrary ("Capability parameters in declarations" rule 4); `throws ()` legal.
- Functional types `(A) throws (E1,E2) -> R`: clause node on FuncType; paren-vs-functype
  lookahead after `)` extended to `throws` (colleague's `ParseTypeWithParen` pattern).
- `main() throws ...` allowed.
- AST checker rules: no `...` in functional types (grammar exists only when "Interaction with an explicit throws" lands);
  reject `throws` entries that are concrete unchecked types later ("Capability parameters in declarations" rule 5 — needs
  UncheckedException, defer until "Unchecked exceptions").

### B. Signature elaboration (PreCheck)
- Elaborate clause → canonical capability list `CapList` (list of Ty, subtypes of Exception;
  type params allowed) attached to:
  - decl signatures (FuncDecl-level table or field), and
  - `FuncTy.capTys` for functional types.
- FuncTy identity: capTys participate in interning identity (distinct types), BUT:
  - overload duplicate check uses signature-modulo-caps comparison ("Overloading"),
  - type-argument inference/unification ignores capTys entirely ("Generics") and must not reject
    on differing lengths,
  - JoinAndMeet: subsumption-aware (use set rules; do not bail like his invariant version).
- Subtyping (TypeManager): `F2 <: F1` iff usual param/result variance AND
  ∀ c2 ∈ caps(F2). ∃ c1 ∈ caps(F1). CanThrow<c1> <: CanThrow<c2> (i.e. c2 <: c1 by
  contravariance) — permutation/length-insensitive ("Functional types").
- Override/redefinition rule ("Overriding and redefinition"): in inheritance checker, pointwise subsumption of the
  override's list against the original's (reuse his hook + generic mapping, swap predicate).
  Constructors exempt.
- Lambda literals: capability list comes ONLY from expected type ("First-class functions"/"Which declarations are inferred"). Propagate
  during checking (his ChkLamBody pattern), storing the list on the literal's FuncTy.

### C. CapabilityCheck pass (new module, runs after type checking of a package)
Self-contained; owns all "Capability argument inference" diagnostics. Per callable body, walk the typed AST maintaining
a supply stack and checking demands:

- Supplies (scopes, "Capability argument inference"): callable's own CapList; try-block per-catch-pattern types
  (E1|E2 → two entries; try-with-resources initializers inside; catch/finally OUTSIDE);
  literal's CapList for its body. Later: captures ("Capability capturing"), conversion boundaries ("Exception conversions").
- Demands: `throw e` → CanThrow<type(e)> (skip unchecked later); call site → callee FuncTy's
  capTys after generic substitution (use the call's solved instantiation, his ApplySubstPack
  point); default-value exprs checked against the callee's own scope ("Capability argument inference"); field
  initializers per "Capability argument inference" special rules.
- Resolution: demand satisfied iff ∃ supply S in stack with S <: required (first match; no
  ambiguity concept). Miss → (later: conversions "Exception conversions") → diagnostic in proposal's wording.
- The pass never mutates types and emits no demands into them — pure check.

Extensibility slots:
- "Capability parameter inference" inference: a pre-step of this pass. Build intra-package call graph over
  inference-eligible decls (non-public, no authoritative clause), SCC condensation,
  bottom-up: infer list = union of residual demands of the body (same demand/supply walker
  run in "collect" mode instead of "error" mode). Write inferred lists into decl signatures,
  then run the checking step uniformly. Walker is shared; only the miss-handler differs
  (collect vs report). This is the key seam: **the demand walker must be parameterizable
  over its miss-handler from day one.**
- "Exception conversions" conversions: alternative miss-handler step before erroring; synthesizes conversion
  info for later desugar.
- "Capability list aliases" aliases: clause elaboration in B expands aliases; C unchanged.
- "Escape analysis" escape analysis: separate mode-system concern; C only marks which try introduced which
  capability (region ids) for it to consume later.

### D. Serialization (cjo)
- Decl CapLists and FuncTy capTys serialized (his FuncTyInfo.implicitTypes pattern: [uint32]
  type refs appended to tables — flatbuffers-compatible). Inferred lists are serialized too
  (they're part of the in-package truth; exported surface is explicit-only by "Which declarations are inferred").
- Loader reconstructs CapLists into signatures/FuncTys. No param-list loading, no
  ownerFunc/default-arg wiring (nothing is materialized). Cover all three loaders:
  ASTLoader, ReferenceLoader, IncrementalLoader.

### E. Erasure / back-end
- Nothing to do by construction: capabilities never exist as params/args/values. Mangler
  ignores capTys (no changes needed — verify with a test that two same-name decls differing
  in caps are already rejected by "Overloading" so no symbol collision can arise). CHIR untouched.
- CanThrow: prefer compiler-known intrinsic marker type (proposal "Type of exception capabilities" NOTE) — avoids stdlib
  bootstrap dance entirely. It only needs to exist as a Ty for subtyping of capability
  entries; likely we can even avoid a dedicated Ty and store exception Tys directly in
  CapLists, applying contravariance in the subsumption predicate. Decide at implementation.

## Phase map (target pipeline)

```
parse → macro-expand → sema type check (uses B: subtyping/lambda/override rules)
      → [mode inference — Modal, when present; capability-BLIND, see below]
      → CapabilityCheck pass:
           ["Capability parameter inference" inference over SCCs — later]
           per-body demand/supply checking ("Capability argument inference" diagnostics)
           records capability capture sets per literal
      → [capability-region escape check — Modal "try-scoped capability regions"; consumes modes + capture sets,
         produces neither]
      → MANGLING (untouched) → SAVE_CJO (writes CapLists) → CHIR → codegen (untouched)
```

## Modes vs capabilities: the circularity and its resolution

Authoritative sources: `Modal CangJie updated.md` (symlinked in repo root; esp. "Mode of
Function Objects", "Try-catch-finally Expressions") and checked-exceptions proposal "Escape analysis".
Relevant Modal facts:
- A function object's mode reflects its captures: `~local` lambdas capture only `~local`;
  `local?` lambdas may also capture `local?`. **Capturing `local!` is banned outright, and
  no function object has mode `local!`** — only a `local?` alias of a `local!` value may be
  captured. So mode CHECKING of a lambda consumes its capture list.
- Regions are per-function-invocation; no surface construct scopes a region to a block.
  `exclave` is banned inside try/catch. `throw` requires `~local`; catch binds `~local`
  (so modes constrain only capabilities, never exception objects).

The circularity (user-raised, concrete): a literal capturing a `CanThrow<E> @ local!`
capability must become region-bound ("First-class functions"). Which capabilities a literal captures is
decided by capability ARGUMENT resolution; under "Capability parameter inference", demands additionally depend on
capability PARAMETER inference. If lambda mode checking consumed capability captures, we'd
get: modes → capability params → capture sets → modes. Worse, "Capability capturing" rule 4 (capability
access through `local?` receivers) makes capability checking read receiver modes — so
putting capabilities inside Modal's ordinary value rules (proposal "try-scoped capability regions" path (a), real
try-scoped regions in Modal proper) yields a genuine cycle:
capability args need modes (receiver rule) AND modes need capability capture sets.

Resolution = proposal "try-scoped capability regions" **path (b), phantom capabilities** — which we adopt not only for
the reasons "try-scoped capability regions" gives (erasure, no ask on Modal authors) but because it is what makes the
pipeline LINEARIZABLE at all:

1. **Modal analysis is capability-blind.** Capabilities are phantom: excluded from lambda
   capture lists as far as mode rules are concerned; the `local!`-capture ban does not see
   them. Modes are computed/checked from ordinary values only. ("Phase ordering" supports this: the
   capability's own `@ local!` is fixed by desugaring, never inferred.)
2. **Capability analysis (params → args) runs after modes**, reads modes where its rules
   need them ("Capability capturing" rule 4 — modes are final by then), never writes them.
3. **The escape guarantee is a dedicated capability-scope check** ("try-scoped capability regions"(b)) after argument
   resolution. Per literal/capturing-instance: recorded capability captures + their try
   associations. Intra-function: no use after the try closes, no assignment to variables
   declared outside it (this part needs no modes at all — it is "Checking without Modal CangJie"'s degraded check).
   Cross-function: the value's mode must be `local?`-capped — enforced as a CHECK against
   the capability-blind Modal result (a capability-capturing value whose mode/usage lets it
   leave the function is reported at the offending point; per "try-scoped capability regions"(b) `local?` is exactly
   the mode Modal can handle for such captures today, via the alias rule).
4. **No mode rewriting.** We never retro-restrict an inferred/declared mode because of a
   capability capture; violations are errors. No precision loss: a program where the
   restriction would matter is one that lets a capability escape its handler.

Pipeline (linear; the forbidden edge is "Modal results depend on capability results"):
types → modes (capability-blind) → capability parameters ("Capability parameter inference", mode-independent) →
capability arguments (records captures) → capability-scope check (reads modes + captures).

Per "try-scoped capability regions"'s own caveat: these dedicated rules are defined as an implementation of
try-scoped-region SEMANTICS (path (a)), so that if capabilities later materialize
(evidence-passing effect handlers, "effect handlers"), the lowering changes but not which programs
type-check. The linearity argument above is an additional, load-bearing reason to keep it
this way — record it in the proposal's "Open questions (Escape analysis)" open-questions resolution.

PR-1735 prototype study (notes/pr1735-study.md) CONFIRMS this resolution and sharpens it:
the prototype itself never infers a lambda's mode from captures — mode comes from the
expected type only (LambdaExpr.cpp:356-359 in mr-1735), captures are validated post-hoc in
a separate pass (CheckModalType, TypeChecker.cpp:2044). So the cycle is absent in the
Modal prototype's architecture too, and our phantom filter reduces to two concrete edits
when Modal lands: exempt capability-typed targets in CheckCapture (mirroring its Copy
early-return) or make CanThrow mode-transparent in IsModalSubtype; and insert our
capability-scope check as a sibling pass right after CheckModalType, on the pre-desugar
AST (desugar-synthesized lambdas are never modal-checked — both checks must see the same
AST). Modes participate in Ty interning and mangling there, so retro-restricting a mode is
structurally impossible anyway — "no mode rewriting" is forced, not merely chosen.
`exclave` is an explicit escape edge our check must model (banned in try/catch but not in
finally). To keep the implicit capability passing design unblocked, the base design ships without Modal: CapabilityCheck
records capture sets + try associations from day one, and the "Checking without Modal CangJie" intra-function check
runs on them mode-free.

## Modes vs capabilities — status 2026-08-21

The resolution above was written before a line of the pass existed. Here is what of it is
built, what the author's 2026-08-20 question ("imagine Modal has landed — modes of functional
types must describe captured capabilities; isn't that a problem?") sharpened, and what is
implementable now.

### Built / not built

| Stage of the linear pipeline | Status |
|---|---|
| types, capability-blind | built — capability lists never enter unification or overload resolution; `FuncTy::capTys` is in interning identity but not in `typeArgs` |
| capability parameters (inference), mode-independent | built — SCC + Kleene iteration over the miss-handler seam |
| capability arguments (demand/supply check) | built — pure check; supplies from clauses, `catch`, literals' expected types, class captures, `handle` |
| **recording capability capture sets per literal / instance** | **not built** — the checker discharges a literal's demands against its expected-type list and discards which capabilities the body actually used |
| **capability-scope check** (no use after the `try`, no assignment outward; result-value escape) | **not built** — ruling 10: no escape analysis before Modal. Both canonical escapes of "try-scoped capability regions" are accepted today |
| mode cap at `local?` for capturing values | not applicable pre-Modal (no modes exist) |

Consequence: the guarantee is weaker than "Checking without Modal CangJie" describes — the
degraded mode's intra-function checks are specified but absent.

### What the question sharpened

1. **The framing "modes depend on captures" is true but weaker than it sounds.** Capturing a
   capability can only *cap* a value's mode at `local?` — binary, monotone, never a richer
   function of the capture set. That is why check-and-cap (discover captures → lower →
   propagate region-boundness through captures and stores → re-validate the lowered values'
   uses) fits a pipeline as a third stage. The Modal prototype (PR-1735) makes rewriting
   structurally impossible anyway: modes participate in interning and mangling, so "no mode
   rewriting; violations are errors" is forced, not chosen.
2. **The one genuine break is mode-dependent overloading.** Modal methods overload on the
   receiver-mode specifier, selected by submode. A cap that arrives after overload resolution
   can invalidate the chosen overload; re-resolving would silently change which code runs.
   Sound rule: **reject**, with a diagnostic that names the capability capture ("this literal
   captures `CanThrow<E>` and is region-bound; the call requires an unrestricted receiver —
   handle `E` inside, or declare it"). Accepting such programs needs a (modes, captures)
   fixpoint; recommendation: don't.
3. **Under evidence passing the argument changes.** Effect capabilities become real
   runtime values; D17's shared `performs`/`throws` list must split, and the phantom rules
   must already enforce exactly what real regions would — the proposal's "(b) implements
   (a)'s semantics" contract. Our check-and-cap stage must be written against that
   contract from the start.
4. **Negotiations the design cannot avoid** (the proposal's own "Open questions"): the
   forwarding rule — read literally it rejects every capability propagation step; unwinding
   × regions (`finally`, `exclave`); invoking `local?`/`local!` function values; `for-in` over
   `local!` iterators (now required by the capturing-iterator stdlib ruling).

### Implementable now: the intra-function stage

The capture-set recording and the intra-function scope check need **no modes**: the checker
already walks every literal body with a supply stack, so recording which supplied
capabilities a body demanded (rather than discarding it), tagging each with the `try` that
supplied it, and then checking (i) no use of the capturing value after that `try` closes and
(ii) no assignment of it to a variable declared outside the `try` — including flow through
the `try` expression's own result value — is a self-contained third stage. It would reject
both canonical escapes today and is exactly the half of path (b) that "Checking without
Modal CangJie" promises. Cross-function escape stays Modal's. Proposed as the next compiler
milestone; tracked as I4 in `gap-analysis.md`.

**Update, 2026-08-21 evening — effects join the base design.** The revision that rewrote the
escape-analysis section also moved effect requirements into the base design as a section of their
own: `perform` needs a handler exactly as `throw` needs one, `CanPerform<C>` is the analogue of
`CanThrow<E>`, and every rule of the capability-passing and escape sections applies under the
substitution `throw`→`perform`, `catch`→`handle`, exception type→command type. That settles what
had been our own extension (D17: one capability list carrying both kinds, kept apart by the
disjoint `Exception`/`Command` roots) and adds one architectural constraint we did not have:
effects live on the **effect-handler feature's axis**, not the exception-checking level, so the
capability pass now runs whenever handlers are enabled — reporting effect misses as errors at
every exception level, and exception misses not at all when checking is off. The four differences
the text lists (no inference, no unchecked commands or escape hatch, no `performs` on `main`, no
pessimistic cast reading for commands since there is no top command type) are all in place.

**Update, 2026-08-21 evening.** The escape-analysis section was rewritten and now states the
semantics normatively instead of sketching an extension: every capability has an **origin**
(the region of the `try-catch` that introduced it), carriers have **origin sets** that unions
of joins and stores propagate, and a **flow condition** says a value may flow only into
storage whose lifetime is contained in every region of its set — with explicit rules for the
try-region lifetime (closed before `catch`/`finally` run), forwarding of capability arguments,
the call boundary (a `local?`/`local!` result inherits the union of the origins the call site
supplied), and `spawn`. Phantom capabilities are now the adopted strategy, not the
recommended one. This turns I4 from "design a check" into "implement rules 1–6", and two of
them fall out of machinery the checker already has: the supply stack gives origins, and the
demand walk gives the carrier set. The call-boundary rule is the one genuinely new piece —
it is conservative by design (a region-bound result unrelated to the callee's requirements is
tied to them all the same), so a first implementation can follow it literally. The
cast rule of the ABI section is the other half of the same story and is implemented: a cast
preserves origin sets rather than laundering them.

## Open implementation questions (resolve during detailed planning)

1. Where CapLists live for decls: new field on FuncBody/FuncTy vs side table keyed by decl.
   Field is simpler & serializes naturally; side table keeps Node.h churn minimal.
2. Interning: confirm no code path relies on FuncTy Hash/== collapsing cap-differing types
   (overload dup-check must compare modulo caps explicitly).
3. Diagnostics ordering: capability errors after type errors — confirm acceptable UX.
4. LSP/cjd (CjdCompilerInstance) integration of the new pass.
5. Incremental compilation: capability-list changes must invalidate dependents (ASTHasher
   must include clauses).
