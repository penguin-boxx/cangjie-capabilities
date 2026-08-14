# Study: Wizzerinus' implicits prototype (`wizzerinus-cjc-implicits`)

Source: branch `diploma/implicits-updated-new` (base `new-main`, upstream main @ 2026-06-17).
Delta: 101 files, +1689/−241 (~700 lines are mechanical churn from a `GetFunctionTy`
signature change; real implementation ≈600 lines / ~20 files).
Regression suite: `wizzerinus-implicits-regression` (harness.py + 20 test dirs).

## Mental model of his design

General **implicit values passed at runtime** (not erased capabilities):

- `func f(a: A) using (x: X, y: Y): R` — implicit parameter list (second `FuncParamList` on `FuncBody`).
- `with (e1, e2) { … }` — introduces implicit values for the block (`ImplicitWithExpr`).
- `(A) using (X) -> R` — functional type with implicit params (`FuncTypeUsing` on `FuncType`).
- Call sites: Sema walks a stack of implicit scopes (innermost first), unique subtype match
  required, materializes a `RefExpr` into `CallExpr::implicitlyAssignedArgs`.
- New pipeline stage `DESUGAR_AFTER_CJO` (between SAVE_CJO and CHIR) merges implicit
  params/args into the ordinary ones (AST + `FuncTy`) — implicits become real leading
  runtime parameters. Mangling includes them (`$_` prefix) so they affect ABI.
- Checked exceptions layered on top: stdlib `struct Throws<E>`; `try/catch (e: E)` synthesizes
  `let throwDecl$i = Throws<E>()` + pushes an implicit scope. Runtime values, zero erasure.

## Key file/line map (in wizzerinus-cjc-implicits/)

Scope stack (the core idea, ~10 lines):
- `include/cangjie/AST/ASTContext.h:73-81,210` — `ImplicitValue{ty, valueDecl}`, `ImplicitScope`, `implicitScopes` stack
- `src/Sema/ScopeManager.cpp:266-278` — Enter/Exit/FetchImplicitScope

Resolution at call sites:
- `src/Sema/TypeCheckCall.cpp:2876-2963` — `ValidateImplicitContext` (ApplySubstPack first;
  innermost-out walk; 1 match → take, >1 → error, 0 → outward; miss → `sema_missing_throws_cap`
  for `Throws<X>` with helpful notes, else `sema_implicit_not_found`)
- Hook points: `PostCheckCallExpr` (:2862), `CheckNonNormalCall` (:3047)

Capability introduction:
- `src/Sema/TypeCheckExpr/TryExpr.cpp:22-79` — try-catch pushes scope (catch/finally OUTSIDE — matches §3.3);
  `:358` `GenerateTryExprCaughtTypes` returns `std::optional<vector<Ty>>` (empty ≠ error; try/finally!)
- `src/Sema/TypeChecker.cpp:482-520` — `EnterImplicitScopeForFuncBody` + `SynthesizeWithUsing`/`CheckWithUsing`
  wrapping the 5 `Synthesize(ctx, fb.body)` call-sites
- `src/Sema/TypeCheckExpr/LambdaExpr.cpp:470-495` — lambda capability list inferred from expected type (§3.5)

Parsing:
- `src/Parse/ParseDecl.cpp:2317-2324` — `using` clause in `ParseFuncBody` after params, before `:`.
  NOTE: prop accessors early-return before this → must move for our §3.2 (props need throws)
- `src/Parse/ParseType.cpp:211-300` — `ParseFuncTypeUsing`; funcType-vs-parenType decided by
  one-token lookahead after `)` (this is our `(A) throws (E) -> R` ambiguity solution)
- `using` is a soft keyword via `Peek().Value() == "using"` — no lexer changes; same trick works for `throws`
- `with` was already a reserved token (`Tokens.inc:130`); `throws` is NOT a token today

Subtyping (his: invariant+positional — we must replace with set subsumption):
- `src/Sema/TypeManager.cpp:889-920` — IsFuncSubtype/IsFuncParametersSubtype
- `src/Sema/JoinAndMeet.cpp:193-199`, `src/Sema/LocalTypeArgumentSynthesis.cpp:463-486` (bidirectional
  unification of implicit tys — our §3.6 forbids this)
- `src/AST/Types.cpp:113,1122` — FuncTy Hash/== include implicitParamTys (we need the OPPOSITE per §3.7)

Override checking:
- `src/Sema/InheritanceChecker/StructInheritanceChecker.cpp:1414-1428` — right hook + generic mapping;
  his rule is "identical lists", ours is pointwise subsumption (§3.8) — swap predicate only

cjo serialization:
- `schema/ModuleFormat.fbs:75,596` — `FuncBody.implicitParamList`, `FuncTyInfo.implicitTypes:[uint32]`
- `src/Modules/ASTSerialization/ASTWriter.cpp:1117-1132,1374-1378`; `ReferenceLoader.cpp:352-394`;
  `ExprLoader.cpp:496-498`; `IncrementalLoader.cpp:67-74` (has a copy-paste BUG at :71: reads
  `paramList` instead of `implicitParamList`)
- We only need `FuncTyInfo`-style type lists, not param lists → half the loader churn disappears

Diagnostics: `include/cangjie/Basic/DiagRefactor/DiagnosticSema.def:424-437` (13 new diags;
`sema_missing_throws_cap` has the good UX pattern: error + "in scope" note + "how to fix" note)

Erasure counter-example:
- `src/Sema/Desugar/DesugarAfterCjo.cpp` (178 lines) + `src/CHIR/.../TranslateCallExpr.cpp:746-750`
  (DCE hack) + mangler changes (`MangleUtils.h:64`, `BaseMangler.cpp:1101,1153`) — all exists ONLY
  because his implicits are runtime values. Our erased design deletes this entire layer.

## What we reuse vs invert (proposal §3.1–3.8)

REUSE (structure/code):
1. Scope stack + Enter/Exit wrappers (drop valueDecl → just `Ptr<Ty>`).
2. Try-catch scope introduction incl. optional-caught-types + E1|E2 handling; drop `Throws<E>()` synthesis.
3. Function-body scope wrapping (the exact 5 call-sites).
4. Lambda inference from expected type (drop synthesized FuncParams).
5. Resolution hook points + ApplySubstPack; simplify body to a yes/no subtype check, first match wins.
6. Functional-type grammar surgery incl. paren-lookahead; rename to throws clause (bare type list).
7. Decl-clause parse position (move before prop early-return; allow either order with `where`).
8. Override-check hook + generic-mapping preamble; swap predicate to subsumption.
9. `FuncTyInfo.implicitTypes`-style cjo field for capability type lists.
10. Regression harness as-is (fix CJC_PATH), re-derive the 20 scenarios for capabilities.

INVERT (his decisions that contradict our proposal):
1. Runtime values → full erasure: no implicitlyAssignedArgs/FuncArgs, no param merging, no CHIR/DCE
   hacks, no mangling changes (mangler simply ignores capTys; erase after SAVE_CJO or never
   materialize beyond FuncTy).
2. FuncTy identity: Hash/== must EXCLUDE capability lists (§3.7) — so capabilities likely live
   outside interned Ty identity (side member not hashed, or per-decl side table). Design decision
   he never faced.
3. Subtyping: invariant/positional → set-based subsumption ∀c2∃c1. c2 <: c1 (contravariant CanThrow).
4. Ambiguity: his duplicate/subtype-relation errors disappear (§3.3: any suitable capability works;
   stop at first match). Delete CheckTypesAreDistinct analog.
5. Generic inference: do NOT unify capability lists (§3.6); also don't reject on differing lengths.
6. `Throws` as stdlib struct → `CanThrow` as compiler-known intrinsic (kills bootstrap dance,
   reference guard, GetCoreDecl asserts).
7. `main` with capabilities is ALLOWED in our design (§3.2); he forbids it.
8. Unnamed capabilities: no symbol-table entries, no unused-var warnings.

## Pitfall checklist (from his fix commits)

- New AST node/field ⇒ update 7+ visitors: Walker, Clone, PartialInstantiation, PrintNode,
  ASTChecker, ASTHasher, Collector, InitializationChecker. Silent miscompiles if missed.
- Scope-introducing nodes need Collector two-part treatment (Collector.cpp:666 exclusion).
- Desugar of block constructs must SPLICE statements, not nest Blocks (value propagation).
- try/finally has zero catch patterns — empty caught-list ≠ failure (std::optional).
- Type checking runs MULTIPLE times over the same node — make transforms idempotent;
  pure scope push/pop (our design) sidesteps this.
- Synthesized nodes need begin/end/curFile copied from a real node.
- Default-param helper functions: check default-value exprs against the callee's own capability
  scope (§3.3); no param-list surgery needed in erased design.
- `Synthesize` yields ideal literal types — `ReplaceIdealTy` before use.
- `ASTKind.inc` order encodes subtype ranges — placement matters.
- Post-CJO transforms must also apply to imported packages; IncrementalLoader is a third,
  easily-forgotten loader.
- Avoid changing `GetFunctionTy` signature (≈700-line churn tax across FFI/Mock code) — additive API.
- §3.7 (overloads can't differ by caps) and "no ABI impact" are the same coin — enforcing the
  former is what makes the latter safe.

## Regression scenarios to re-derive for capabilities (his 20 tests)

ideal_ty, implicitly, di, scopes, missing_capability, constructor, optional_parameters, override,
misc_diagnostics, invalid_overload, overload_by_functional_type, lambda_inference,
infer_generic_by_implicit, generic_resolution, ffi, macro, modules, exceptions_capturing,
exceptions_wrong, const_throw.

Harness: `python harness.py '<glob>'`; per-test dir: main.cj + errors.json (order-insensitive
diag match) + output.log (stdout match) + optional run.py driver; CJC_PATH/EXTRA_LD in common.py
point at `../dist/` — adjust to our SDK output.
