# Architecture sketch: checked exceptions (§3.1–3.8, extensible to §6.x)

Goal: implement the base design (§3.1–3.8) with stage separation that later accommodates
capability parameter inference (§6.2), conversions (§8.10), aliases (§6.1), captures (§3.9),
and Modal escape analysis (§4) without restructuring.

## Load-bearing observations from the proposal

1. §3.6: capability lists of argument functions are excluded from generic type-argument
   inference. §3.7: overload resolution ignores capability lists. §3.3: capabilities are
   witnesses only; which one is chosen is unobservable. Together: **core type checking never
   needs the result of capability resolution** — capability checking can run after Sema.
2. §6.2.3 pipeline: `types → modes → capability parameters → capability arguments`.
   Capability-parameter inference (§6.2) is a distinct phase; capability-argument checking
   (§3.3) runs last. No fixpoint: inference is one bottom-up SCC pass; cycles among
   inference-eligible decls are errors (§6.2.4).
3. Capabilities are fully erased (§3, §3.10): they never become params, args, mangled names,
   or CHIR. The cjo must carry `throws` lists (cross-package checking), so serialization
   happens from signature data, not from materialized params.

## Why not the colleague's staging

His prototype resolves implicits eagerly inside `TypeCheckCall` (diagnostics interleaved with
type checking), integrates implicit lists into Ty unification/JoinAndMeet, mutates interned
FuncTys in place after cjo-save, and mangles implicits into symbols. Each of these blocks
inference: an unresolved capability at a call is *not yet an error* if the enclosing callable
may infer it; unification over capability lists is row-typing §3.6 forbids; ABI must not see
capabilities at all. See notes/prototype-study.md — we reuse his scope/introduction machinery
shapes, not his staging.

## Components

### A. Front-end representation (Parse/AST)
- `throws E1, E2` clause on callables: soft-keyword parse (Peek().Value()=="throws"), stored
  as a clause node on FuncBody/decl (position-carrying, for diagnostics & tooling). Must work
  for functions, methods, ctors, prop accessors (move past the prop early-return), operators,
  extensions, interface methods; order with `where` arbitrary (§3.2 rule 4); `throws ()` legal.
- Functional types `(A) throws (E1,E2) -> R`: clause node on FuncType; paren-vs-functype
  lookahead after `)` extended to `throws` (colleague's `ParseTypeWithParen` pattern).
- `main() throws ...` allowed.
- AST checker rules: no `...` in functional types (grammar exists only when §6.2.5 lands);
  reject `throws` entries that are concrete unchecked types later (§3.2 rule 5 — needs
  UncheckedException, defer until §6.3).

### B. Signature elaboration (PreCheck)
- Elaborate clause → canonical capability list `CapList` (list of Ty, subtypes of Exception;
  type params allowed) attached to:
  - decl signatures (FuncDecl-level table or field), and
  - `FuncTy.capTys` for functional types.
- FuncTy identity: capTys participate in interning identity (distinct types), BUT:
  - overload duplicate check uses signature-modulo-caps comparison (§3.7),
  - type-argument inference/unification ignores capTys entirely (§3.6) and must not reject
    on differing lengths,
  - JoinAndMeet: subsumption-aware (use set rules; do not bail like his invariant version).
- Subtyping (TypeManager): `F2 <: F1` iff usual param/result variance AND
  ∀ c2 ∈ caps(F2). ∃ c1 ∈ caps(F1). CanThrow<c1> <: CanThrow<c2> (i.e. c2 <: c1 by
  contravariance) — permutation/length-insensitive (§3.4).
- Override/redefinition rule (§3.8): in inheritance checker, pointwise subsumption of the
  override's list against the original's (reuse his hook + generic mapping, swap predicate).
  Constructors exempt.
- Lambda literals: capability list comes ONLY from expected type (§3.5/§6.2.1). Propagate
  during checking (his ChkLamBody pattern), storing the list on the literal's FuncTy.

### C. CapabilityCheck pass (new module, runs after type checking of a package)
Self-contained; owns all §3.3 diagnostics. Per callable body, walk the typed AST maintaining
a supply stack and checking demands:

- Supplies (scopes, §3.3): callable's own CapList; try-block per-catch-pattern types
  (E1|E2 → two entries; try-with-resources initializers inside; catch/finally OUTSIDE);
  literal's CapList for its body. Later: captures (§3.9), conversion boundaries (§8.10).
- Demands: `throw e` → CanThrow<type(e)> (skip unchecked later); call site → callee FuncTy's
  capTys after generic substitution (use the call's solved instantiation, his ApplySubstPack
  point); default-value exprs checked against the callee's own scope (§3.3); field
  initializers per §3.3 special rules.
- Resolution: demand satisfied iff ∃ supply S in stack with S <: required (first match; no
  ambiguity concept). Miss → (later: conversions §8.10) → diagnostic in proposal's wording.
- The pass never mutates types and emits no demands into them — pure check.

Extensibility slots:
- §6.2 inference: a pre-step of this pass. Build intra-package call graph over
  inference-eligible decls (non-public, no authoritative clause), SCC condensation,
  bottom-up: infer list = union of residual demands of the body (same demand/supply walker
  run in "collect" mode instead of "error" mode). Write inferred lists into decl signatures,
  then run the checking step uniformly. Walker is shared; only the miss-handler differs
  (collect vs report). This is the key seam: **the demand walker must be parameterizable
  over its miss-handler from day one.**
- §8.10 conversions: alternative miss-handler step before erroring; synthesizes conversion
  info for later desugar.
- §6.1 aliases: clause elaboration in B expands aliases; C unchanged.
- §4 escape analysis: separate mode-system concern; C only marks which try introduced which
  capability (region ids) for it to consume later.

### D. Serialization (cjo)
- Decl CapLists and FuncTy capTys serialized (his FuncTyInfo.implicitTypes pattern: [uint32]
  type refs appended to tables — flatbuffers-compatible). Inferred lists are serialized too
  (they're part of the in-package truth; exported surface is explicit-only by §6.2.1).
- Loader reconstructs CapLists into signatures/FuncTys. No param-list loading, no
  ownerFunc/default-arg wiring (nothing is materialized). Cover all three loaders:
  ASTLoader, ReferenceLoader, IncrementalLoader.

### E. Erasure / back-end
- Nothing to do by construction: capabilities never exist as params/args/values. Mangler
  ignores capTys (no changes needed — verify with a test that two same-name decls differing
  in caps are already rejected by §3.7 so no symbol collision can arise). CHIR untouched.
- CanThrow: prefer compiler-known intrinsic marker type (proposal §3.1 NOTE) — avoids stdlib
  bootstrap dance entirely. It only needs to exist as a Ty for subtyping of capability
  entries; likely we can even avoid a dedicated Ty and store exception Tys directly in
  CapLists, applying contravariance in the subsumption predicate. Decide at implementation.

## Phase map (target pipeline)

```
parse → macro-expand → sema type check (uses B: subtyping/lambda/override rules)
      → [mode inference — Modal, when present; capability-BLIND, see below]
      → CapabilityCheck pass:
           [§6.2 inference over SCCs — later]
           per-body demand/supply checking (§3.3 diagnostics)
           records capability capture sets per literal
      → [capability-region escape check — Modal §4.3; consumes modes + capture sets,
         produces neither]
      → MANGLING (untouched) → SAVE_CJO (writes CapLists) → CHIR → codegen (untouched)
```

## Modes vs capabilities: the circularity and its resolution

Authoritative sources: `Modal CangJie updated.md` (symlinked in repo root; esp. "Mode of
Function Objects", "Try-catch-finally Expressions") and checked-exceptions proposal §4.
Relevant Modal facts:
- A function object's mode reflects its captures: `~local` lambdas capture only `~local`;
  `local?` lambdas may also capture `local?`. **Capturing `local!` is banned outright, and
  no function object has mode `local!`** — only a `local?` alias of a `local!` value may be
  captured. So mode CHECKING of a lambda consumes its capture list.
- Regions are per-function-invocation; no surface construct scopes a region to a block.
  `exclave` is banned inside try/catch. `throw` requires `~local`; catch binds `~local`
  (so modes constrain only capabilities, never exception objects).

The circularity (user-raised, concrete): a literal capturing a `CanThrow<E> @ local!`
capability must become region-bound (§3.5). Which capabilities a literal captures is
decided by capability ARGUMENT resolution; under §6.2, demands additionally depend on
capability PARAMETER inference. If lambda mode checking consumed capability captures, we'd
get: modes → capability params → capture sets → modes. Worse, §3.9 rule 4 (capability
access through `local?` receivers) makes capability checking read receiver modes — so
putting capabilities inside Modal's ordinary value rules (proposal §4.3 path (a), real
try-scoped regions in Modal proper) yields a genuine cycle:
capability args need modes (receiver rule) AND modes need capability capture sets.

Resolution = proposal §4.3 **path (b), phantom capabilities** — which we adopt not only for
the reasons §4.3 gives (erasure, no ask on Modal authors) but because it is what makes the
pipeline LINEARIZABLE at all:

1. **Modal analysis is capability-blind.** Capabilities are phantom: excluded from lambda
   capture lists as far as mode rules are concerned; the `local!`-capture ban does not see
   them. Modes are computed/checked from ordinary values only. (§6.2.3 supports this: the
   capability's own `@ local!` is fixed by desugaring, never inferred.)
2. **Capability analysis (params → args) runs after modes**, reads modes where its rules
   need them (§3.9 rule 4 — modes are final by then), never writes them.
3. **The escape guarantee is a dedicated capability-scope check** (§4.3(b)) after argument
   resolution. Per literal/capturing-instance: recorded capability captures + their try
   associations. Intra-function: no use after the try closes, no assignment to variables
   declared outside it (this part needs no modes at all — it is §5.5's degraded check).
   Cross-function: the value's mode must be `local?`-capped — enforced as a CHECK against
   the capability-blind Modal result (a capability-capturing value whose mode/usage lets it
   leave the function is reported at the offending point; per §4.3(b) `local?` is exactly
   the mode Modal can handle for such captures today, via the alias rule).
4. **No mode rewriting.** We never retro-restrict an inferred/declared mode because of a
   capability capture; violations are errors. No precision loss: a program where the
   restriction would matter is one that lets a capability escape its handler.

Pipeline (linear; the forbidden edge is "Modal results depend on capability results"):
types → modes (capability-blind) → capability parameters (§6.2, mode-independent) →
capability arguments (records captures) → capability-scope check (reads modes + captures).

Per §4.3's own caveat: these dedicated rules are defined as an implementation of
try-scoped-region SEMANTICS (path (a)), so that if capabilities later materialize
(evidence-passing effect handlers, §8.2), the lowering changes but not which programs
type-check. The linearity argument above is an additional, load-bearing reason to keep it
this way — record it in the proposal's §4.4 open-questions resolution.

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
finally). To keep §3.1–3.8 unblocked, the base design ships without Modal: CapabilityCheck
records capture sets + try associations from day one, and the §5.5 intra-function check
runs on them mode-free.

## Open implementation questions (resolve during detailed planning)

1. Where CapLists live for decls: new field on FuncBody/FuncTy vs side table keyed by decl.
   Field is simpler & serializes naturally; side table keeps Node.h churn minimal.
2. Interning: confirm no code path relies on FuncTy Hash/== collapsing cap-differing types
   (overload dup-check must compare modulo caps explicitly).
3. Diagnostics ordering: capability errors after type errors — confirm acceptable UX.
4. LSP/cjd (CjdCompilerInstance) integration of the new pass.
5. Incremental compilation: capability-list changes must invalidate dependents (ASTHasher
   must include clauses).
