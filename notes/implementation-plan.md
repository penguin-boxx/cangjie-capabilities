# Implementation plan: proposal §3.1–3.8 (base checked exceptions)

> **Historical (superseded 2026-08-30).** The original milestone plan (M0–M4). Kept for one
> reason that still matters: it holds the author's rulings 1–14 with their context, which nothing
> else records in full. The plan itself was overtaken — the milestones landed, the batch plans
> that followed (A–E, then R1–R5) are in `gap-analysis.md` I.0 and Part III.

Inputs: `Checked exceptions for CangJie.md` §3.1–3.8, notes/architecture.md (stage separation,
inference-ready), notes/prototype-study.md (colleague's prototype), anchor verification against
our checkout (upstream main @ 098c1b26a1, 2026-08-14).

Feature gate: like effect handlers — `GlobalOptions::enableEH` pattern (Option.h:594) behind
`--experimental`. Add `enableCheckedExceptions` (working flag name: `--enable-chexc`); the
`throws` keyword is an `EXPERIMENTAL_TOKEN` that lexes as identifier unless enabled
(Token.h:56 IsExperimental, Lexer.cpp:309-318 pattern used by PERFORM/RESUME/THROWING/HANDLE).

Upstream context to respect: an experimental algebraic-effects feature already lives in tree
(TryExpr::handlers/tryLambda, PERFORM/RESUME/THROWING/HANDLE tokens,
src/Sema/Desugar/AfterTypeCheck/EffectHandlers.cpp lowering try/handle to stdx.effect frames).
Our changes must coexist: capability scopes read `te.catchPatterns` only, and the
CapabilityCheck pass must tolerate handler-bearing TryExpr (skip or treat like normal try —
decide in M3; proposal §16 extension goal says effect handlers are the future direction).

## Milestones

### M0 — Scaffolding (small)
- Driver/lexer: `enableCheckedExceptions` option (experimental-gated); `THROWS` EXPERIMENTAL_TOKEN
  ("throws"); lexer contextual enabling alongside PERFORM et al. (Lexer.cpp:309-318).
- Sanity test: flag off → `throws` remains a valid identifier everywhere (add lexer unittest).

### M0 — DONE (2026-08-14). Files touched:
- include/cangjie/Lex/Tokens.inc (EXPERIMENTAL_TOKEN THROWS), include/cangjie/Option/Option.h
  (enableChexc), include/cangjie/Option/Options.inc (--enable-chexc), src/Option/
  OptionAction.cpp, src/Lex/{LexerImpl.h,LexerImpl.cpp,Lexer.cpp} + include/cangjie/Lex/
  Lexer.h (chexcEnabled gate + SetChexcEnabled), src/Parse/{ParserImpl.h,ParserImpl.cpp} +
  include/cangjie/Parse/Parser.h (SetChexcEnabled wired in SetCompileOptions).
- Gating model: `throws` lexes as IDENTIFIER unless enableChexc — so all clause grammar is
  inert without the flag by construction (the flag-off guards in the test suite pin this).

### M1 — Parsing + AST (§3.2 decl clauses, §3.4 type syntax)

M1 concrete edit list (anchors verified on our main):
- AST: `ThrowsClause : Node` (throwsPos, optional paren positions, vector<OwnedPtr<Type>>
  capTypes, hasEllipsis flag parsed-then-rejected for types); ASTKind entry OUTSIDE the
  Type subtype range. Fields: `FuncBody::throwsClause`, `FuncType::throwsClause`.
- Parser decls (ParseDecl.cpp:2260 ParseFuncBody): after return type (~:2285..2296),
  accept clause and generic constraints in either order (§3.2 rule 4) — loop over
  {throws-clause, where-block}. Prop accessors: extend ParsePropMemberBody (:2239).
- Parser types (ParseType.cpp): ParseTypeWithParen :211 — after `)`, THROWS also selects
  func-type path (parse clause, then require ARROW); ParseFuncType :246 return-type path
  unchanged (right associativity free). Clause grammar: `throws (T {, T})` | `throws T`
  (single-type sugar; bare type parse stops before `->` since func types need parenthesized
  params). `throws ()` = empty list.
- Grammar note: after `throws`, `(` always opens the LIST (never a paren type / func type
  entry) — matches proposal §10 which reserves parenthesized form for the list.
- Visitors for new node/fields: Walker, Clone, PrintNode, ASTChecker, ASTHasher (clause
  must affect incremental hash), Collector, PartialInstantiation. Macro NodeFormat: defer
  (M6), ensure ASTChecker rejects clause inside macro-reparse if it crashes otherwise.
- Diagnostics (DiagnosticParser.def): expected exception type after throws; expected `->`
  after clause in type; `...` not allowed in functional types; clause not allowed here.
- Sema neutrality: M1 leaves clause semantically inert (PreCheck ignores it); full
  compile of clause-bearing code must still succeed (positive tests exercise this).
AST:
- `ThrowsClause` node: `throwsPos`, optional parens positions, `vector<OwnedPtr<Type>> capTypes`.
  Attach: `FuncBody::throwsClause` (covers funcs/methods/ctors/prop accessors/operators) and
  `FuncType::throwsClause`. ASTKind placement: NOT inside the Type range unless it derives from
  Type (pitfall: ASTKind.inc ranges).
- Visitor checklist (from prototype pitfalls): Walker, Clone, PrintNode, ASTChecker, ASTHasher
  (incremental hashing must see clauses!), Collector, PartialInstantiation. Macro NodeFormat
  serialization: defer to M6 (macros emitting throws), keep compile-error stub meanwhile.
Parser:
- Decls: in `ParseFuncBody` (ParseDecl.cpp:2260): after return type (~:2294), accept clause in
  either order with generic constraints (§3.2 rule 4: `where`/`throws` arbitrary order).
  Move/prop handling: accept clause on `get()`/`set()` before `ParsePropMemberBody` early
  return (:2274). `throws ()` empty clause is legal. `main() throws ...` allowed.
- Types: `(A) throws (E1,E2) -> R` and single-type `throws E ->` sugar. Extend
  `ParseTypeWithParen` (:206-224) lookahead: after `)`, contextual `throws` also selects the
  func-type path; parse clause then require `->` (reuse `parse_expected_arrow_in_func_type`).
  Right-associativity: clause binds to the arrow it precedes (§3.4).
- Reject `...` marker in functional types (parse it only to diagnose per §3.4/§6.2.5, or leave
  for later — decide: parse-and-reject gives better errors).
Tests: parser unittests (ParserTest) + PrintNode round-trip; negative cases (clause on
variables, missing arrow, etc.).

### M1 implementation notes (from the implementing agent's report, 2026-08-14):
- ThrowsClause node before FuncType in Node.h; THROWS_CLAUSE between FUNC_PARAM_LIST and
  FUNC_BODY in ASTKind.inc; 5 new parser diagnostics; all 7 visitors + ASTHasher covers
  clause in HashMemberSignature (API-surface relevant).
- DEVIATION: THROWS_CLAUSE added to ASTTypeValidator::ignoreKinds (clause types are not
  sema-elaborated in M1, same treatment as GENERIC_CONSTRAINT). **M2 must remove it from
  ignoreKinds once capTypes are elaborated in PreCheck.**
- Options.inc carries clang-format off/on guards (hand-laid table).
- neg_bad_positions pins the natural parse error (no dedicated "clause not allowed here"
  diagnostic; var decls end at their type, so `throws` errors naturally).
- No LLT case yet pins parse_expected_exception_type_after_throws /
  parse_duplicate_throws_clause — add cases in M2 test batch.

### M2 author rulings (2026-08-14, user-confirmed):
1. §3.7 = overload-resolution rule only: cap-differing FuncTys are DISTINCT interned types;
   only overload machinery compares modulo caps.
2. Join = union of capability lists; meet = entries subsumed by both lists.
3. C FFI: `throws` banned on both foreign funcs and CFunc types (dedicated diagnostic);
   revisit at §5.2 interop if needed.

### M2 — Types & signatures (§3.1, §3.4 semantics, §3.6, §3.7, §3.8)
Representation decision (architecture.md): store exception Tys directly as `FuncTy::capTys`
(no user-visible CanThrow type; §3.1 intrinsic NOTE). Contravariance is applied inside the
subsumption predicate.
- `FuncTy`: new `capTys` member via ctor; update Hash (Types.cpp:103), operator== (:1105),
  String() (:758) → prints `throws (...)`. Keep `paramTys` const style: capTys const too.
  `GetFunctionTy` (TypeManager.h:76): additive — new defaulted parameter or overload; do NOT
  change existing call sites (700-line churn tax). Mind `noCast` flag added upstream.
- PreCheck (`GetTyFromASTType` for FuncType; `PreSetDeclType` for decls): elaborate clauses →
  capTys. Entries must be subtypes of Exception (type params allowed, §3.6); dedicated
  diagnostic otherwise. CFunc/@C rejection (follow prototype's sema_implicits_cfunc precedent —
  check §5/interop sections before finalizing).
- Subtyping (§3.4): `IsFuncSubtype`/`IsFuncParametersSubtype` (TypeManager.cpp:882/:896),
  `IsFuncTySubType` (:1973, cjnative-#ifdef), `JoinOrMeetFuncTy` (JoinAndMeet.cpp:182):
  set-subsumption — `F2 <: F1` iff ∀c2∈caps(F2) ∃c1∈caps(F1): c2 <: c1 (note direction:
  suitable = handler-side type is supertype). Join/meet: union/intersection semantics —
  derive precise rule from subsumption; start conservative (join = union of caps, meet =
  caps satisfying both) with tests.
- Generic inference (§3.6): `UnifyFuncTy` (LocalTypeArgumentSynthesis.cpp:462, Tracked<FuncTy>
  wrappers): IGNORE capTys entirely; must not reject on differing lengths.
- Overloading (§3.7): decl-conflict check — find the declaration-duplicate path (Collector/
  Sema redefinition checking) and compare signatures modulo capTys; `RemoveShadowedFunc`
  (TypeCheckCall.cpp:1736) is already params-only. Argument-position rule: function types
  differing only in capTys are "same type" for overload resolution — locate candidate-type
  comparison and apply caps-stripped equality there.
- Override (§3.8): `CheckImplementationRelation` (StructInheritanceChecker.cpp:1358): add caps
  subsumption after `AreReturnTypesCompatible` (:1389); use
  `typeManager.GenerateGenericMappingFromGeneric(*parentFunc, *childFunc)` (:1370) for generic
  substitution. Constructors exempt. Diagnostic per §3.8.
Tests: Sema unittests (TypeCheckerTest pattern) for subtyping matrix, overload rejection,
override matrix, generic-inference neutrality.

### M3+ author rulings (2026-08-14, user-confirmed):
1. M3 is all-checked (every Exception needs a capability under the flag); §6.3
   UncheckedException follows immediately as its own small milestone (std.core class +
   throw-site exemption + §3.2 rule 5).
2. ROADMAP REORDERED by author: M3 (§3.3/§3.5 checking) → §6.3 unchecked → **§3.9 class
   capturing** → §6.2 capability parameter inference → M4 cjo serialization (cross-package)
   → §5.5 escape checks. (Supersedes the original M4-next ordering.)
3. Diagnostics omit `@ local!` until Modal lands: "Cannot find a capability for `E`
   (of type `CanThrow<E>`) in the current scope. Required by `f(...)` on N:M."
4. Effects feature (try/handle): NOT considered for now — no design/test surface; handle
   clauses introduce no capabilities simply by omission.
5. spawn: ban capability capture with the simplest sound implementation — spawn bodies
   start with an EMPTY capability scope stack (outer capabilities unreachable).

### M3+ author rulings, round 2 (2026-08-14, user-confirmed):
8. Warn mode: attach the severity to the existing key — `--enable-chexc[=error|warn]`
   via option kind FLAG_WITH_ARG (bare = error; committed tests stay valid). Register
   capability diagnostics under a `chexc` warn group so `-Woff chexc` composes when in
   warn mode.
9. §6.3 classification principle: contract/state → unchecked (inventory file for
   line-by-line review prepared during M3). §6.2.6: `...` stays banned on public decls.
10. **NO hand-written escape analysis before Modal lands** (author ruling, supersedes
    §5.5's intra-function check for the prototype): no use-after-try or
    assignment-out-of-try checks for ANY capability carrier — literals or capturing
    instances. Pre-Modal, capability checking is purely lexical/scope-based; the escape
    guarantee arrives wholesale with Modal integration. M3 and §3.9 drop all carrier
    value-tracking; do not write tests for escape cases until Modal.

### §3.9 pre-Modal rulings (2026-08-14, user-confirmed):
11. Until Modal lands: EVERY constructor of a capturing class demands the captured
    capabilities at its call site, and EVERY method/prop body gets them in scope
    (§3.9 rules 3/4 are mode-driven and take over when Modal arrives; no escape
    guarantee pre-Modal per ruling 10). Rule 5 (subclass isolation) and the
    field-initializer rules are mode-independent and implemented as written.
12. Primary constructors are banned on capturing classes NOW (forward-compatible
    with Modal's ~local-primary argument). `captures` allowed on structs; a
    capturing struct is structurally non-Copyable per §3.9.
Red-first tests committed under CheckedExceptions/captures/ (3 pos + 3 neg).

### Later-stage directives (user, 2026-08-14):
6. **Stdlib warn-mode cleanup**: compile the stdlib with checking in WARN mode and fix all
   obvious exception-checking warnings (stdlib edits on cangjie_runtime chexc, pushed to
   the runtime GitHub repo); warnings needing design decisions go to a file for the user
   (notes/gap-analysis.md (Part I.5)). Consequences: M3 builds a warn-mode switch from
   day one (--chexc-warn: capability diagnostics as warnings, or per-package severity —
   decide in M3). Sequencing assumption (correct me if wrong): cleanup runs AFTER §6.3
   (else every internal runtime-error throw warns) and ideally after §6.2 inference
   (non-public stdlib decls then need no explicit clauses — far fewer edits). So:
   M3 → §6.3 → §3.9 → §6.2 → stdlib cleanup → …
7. **Effect-handler checking comes after the stdlib cleanup** (supersedes ruling 4's
   "not considered" as a LATER milestone, not never): integrate checking with the in-tree
   try/handle+perform/resume feature per proposal §8 — needs a §8 read + design round with
   the author before implementation.

### M3 — Lambda inference + CapabilityCheck pass (§3.3, §3.5)
- §3.5 (Sema-side): lambda capability list from expected type only. Hook `ChkLamExpr`
  (LambdaExpr.cpp:401-409): when tgtTy has capTys, build the lambda's FuncTy with them
  (mirror the existing retType smuggling channel; `ChkLamBody` currently takes no target).
  No synthesized params (erased design). No expected type → empty list.
- CapabilityCheck pass (new: src/Sema/CapabilityCheck/): new CompileStage between SEMA and
  DESUGAR_AFTER_SEMA (enum CompilerInstance.h:43 + performMap insertion CompilerInstance.cpp:
  190-204; integer-index loop makes order = enum order). Runs before effect/try desugars
  destroy TryExpr structure, before GENERIC_INSTANTIATION.
  - Supply stack walker over each callable body: decl clause caps; try blocks — one cap per
    catch-pattern type (`ChkTryExprCatchPatterns` result shape, TryExpr.cpp:287; E1|E2 → two);
    catch/finally OUTSIDE; try-with-resources initializers INSIDE (:20); lambda bodies get
    the literal's FuncTy capTys.
  - Demands: `ThrowExpr` → thrown type (unchecked exemption comes with §6.3 — for now all
    Exceptions checked under the flag); `CallExpr` → resolved callee FuncTy capTys with
    instantiation applied (verify what ce.ty/resolvedFunction hold post-Sema; fall back to
    the PostCheckCallExpr hook at TypeCheckCall.cpp:2856 to RECORD demands if post-pass
    reconstruction proves unreliable — recording keeps staging clean either way);
    function-value calls (CheckNonNormalCall path) → the value's FuncTy capTys.
  - §3.3 special contexts: default-value exprs checked against callee's own scope; instance
    field initializers must be satisfiable by every ctor's scope (defer full rule to §3.9
    captures milestone if ctor scopes are trivial now); static/top-level initializers have no
    scope.
  - Resolution: demand satisfied iff ∃ supply S: demanded <: S. First match; no ambiguity.
  - Miss-handler interface (THE §6.2 seam): `onMiss(demand) -> report | collect`. Base: report
    with proposal's message ("Cannot find a capability for `E` (of type `CanThrow<E> @ local!`)
    in the current scope. Required by `f(42)` on N:M."). Mode/`local!` wording kept even though
    modes aren't implemented — it matches the proposal; revisit if confusing pre-Modal.
- LSP/cjd: CjdCompilerInstance stage handling (no-op like his PerformDesugarAfterCjo, or run
  pass for diagnostics in IDE — start with run-for-diagnostics).
Tests: the scenario matrix (below).

### M4 — Serialization (§3.10.2 subset)
- ModuleFormat.fbs `FuncTyInfo` (fbs:591): append `capTypes:[uint32]` (flatbuffers-compatible
  append-at-end). Since decl types ARE FuncTys with capTys, this covers decls and functional
  types uniformly — no FuncBody field needed (unlike prototype).
- ASTWriter `SaveFuncTy` (ASTWriter.cpp:1105; mind the SaveType side-effect ordering hazard),
  ReferenceLoader `SetTypeTy<FuncTy>` (:368) + LoadTypeArgs-for-vector helper,
  IncrementalLoader (cached decl types; NOTE prototype bug: use the right list),
  ASTHasher already covers clause (M1) for incremental invalidation.
- Cross-package test: package A exports `throws` decls; package B imports, checks demands and
  functional-type subtyping across the boundary.

### M5 — Erasure verification (§3.10.1)
Nothing to implement (capabilities never materialize); verify:
- Mangled symbols identical with/without clauses (nm diff on a test lib).
- cjo round-trip preserves capTys; CHIR/codegen paths untouched by construction.
- Flag-off compile of flag-on-compiled cjo? (cross-flag import behavior — define: capTys in
  cjo are ignored when flag off; test.)

### Tests — written FIRST, in cangjie_test (per user direction)

Location: `cangjie_test/testsuites/LLT/compiler/CheckedExceptions/<area>/`, following the
LLT conventions observed in the suite:
- single-file cases: `<name>.cj` with `// EXEC:`/`// EXEC-PIPE-N:` directives (template
  vars %compiler %cmp_opt %n %output %run %f) + `/* SCAN */` block of expected diagnostics
  (matched by `compare %f`); negative tests encode exact error text.
- multi-file/cross-package cases: `<name>.info` driver with `// DEPENDENCE:` lines.
- Our EXEC lines add `--experimental --enable-chexc` (exact flag spelling fixed in M0).
Areas mirror milestones: `parse/` (M1), `types/` (M2: subtyping matrix f1/f2/f3, overload,
override, generics incl. §3.6 negatives), `check/` (M3: discharge, propagation,
multi-exception, hierarchy contravariance, scope nesting, ctors, prop accessors, main,
lambda inference, higher-order capture, diagnostics wording), `modules/` (M4 cross-package),
`erasure/` (M5), `coexist/` (effects-feature flag combos; flag-off `throws`-as-identifier).
Scenario matrix cross-checked against the colleague's 20 regression scenarios
(notes/prototype-study.md) — the capability analogue of each.

Workflow per milestone (M0..M5):
1. Write the milestone's test cases in cangjie_test FIRST (they fail or are inert).
2. Implement until the milestone's group passes: `./cj.py test llt --filter
   compiler/CheckedExceptions/<area>`.
3. Regression gate before declaring the milestone done:
   - `./cj.py fmt --check` clean (project .clang-format via clang-format-15 in the image;
     `./cj.py fmt` rewrites changed files),
   - `./cj.py test compiler` (ctest 49/49),
   - affected LLT groups (M1/M2: compiler/Parser compiler/Sema; M3: + compiler/CHIR smoke;
     M4: + compiler/Modules compiler/IncrementalCompilation; each: our CheckedExceptions/),
   - periodically (at least M1, M3, M5): full baseline `compiler/ Runtime/ API/` vs
     notes/test-baseline.md.
4. Commit tests (cangjie_test branch `chexc`) and implementation (cangjie_compiler branch
   `chexc`) together per milestone.

The wizzerinus harness stays as a secondary tool if pydantic-style diagnostics matching
proves useful; primary tests live in cangjie_test.

## Modes / Modal CangJie (PR #1735) — phase-ordering constraint

See notes/architecture.md "Modes vs capabilities" for the circularity analysis and the
resolution (mode inference capability-blind; capability analysis after modes, read-only on
them; escape guarantee as a separate capability-region check; no mode downgrades).
Implementation consequences now:
- M3's CapabilityCheck records per-literal capability capture sets from day one — the data
  the future region check (and §5.5 degraded intra-function check) consumes.
- Nothing in M0–M5 may make Sema/type/mode results depend on capability resolution.
- After the PR-1735 study lands, add to this plan: where its lambda-mode computation would
  have to filter out capability captures, and whether try-blocks can host regions (§4.3).

## Sizing / order

M0+M1 first (parser/AST is prerequisite for everything; ~2-4 days of focused work).
M2 next — the subtyping/overload/override cluster is self-contained and unit-testable.
M3 is the core novelty (scope walker + pass registration); M4/M5 mechanical. Tests for
each milestone are written before its implementation, as above.

## Open questions (carry into implementation)

1. Post-Sema demand reconstruction vs demand recording at PostCheckCallExpr — decide by
   reading what CallExpr retains after Sema (ce.ty instantiation state). Recording is the
   fallback; keep it behind the same module API either way.
2. Join/meet exact rule for capTys (union for join?) — derive from subsumption + tests.
3. Interaction with effect handlers' TryExpr (handlers/tryLambda): capability scopes from
   catchPatterns only; do handle-clauses discharge anything? (Proposal §8 extension territory —
   for now: no.)
4. `@Frozen`/const functions & clause (const_throw scenario from prototype).
5. Diagnostics wording: include `@ local!` before Modal integration?
6. Where decl-redefinition (same signature modulo caps) is actually checked — locate exact
   function during M2.

### Final pre-M4 rulings (2026-08-14, user-confirmed):
13. Stdlib warn-mode cleanup: WHOLE stdlib in one pass (not incremental by package).
14. Modal strategy: wait for upstream Modal; our layer stays Modal-ready (phantom
    design + documented integration points from the PR-1735 study). No revival of
    mr-1735 by us; escape guarantees land with upstream Modal.
