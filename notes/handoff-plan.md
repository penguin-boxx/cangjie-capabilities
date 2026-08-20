# Checked exceptions for CangJie — detailed implementation handoff plan

Audience: an AI implementation model continuing this project. Follow this document
literally. When something is ambiguous or contradicts observed reality, STOP and ask
the author (the user) — do not invent semantics. The proposal author is the user.

## 0. Ground rules (read fully before any work)

### 0.1 Repos, branches, remotes
All under `/home/penguin/Projs/effects-research/cangjie/`:
- `cangjie_compiler` — the compiler. Branch `chexc` (M0–M3 committed). Remote
  `capabilities` = github.com/penguin-boxx/cangjie-compiler-capabilities.
- `cangjie_runtime` — runtime + stdlib (`runtime/`, `stdlib/`). Branch `chexc` (clean,
  no chexc commits yet). Remote `capabilities` = …/cangjie-runtime-capabilities.
- `cangjie_test` — LLT suites. Branch `chexc`. Remote `capabilities` =
  …/cangjie-test-capabilities. Our tests: `testsuites/LLT/compiler/CheckedExceptions/`
  {parse (11 cases, green), types (10, green), scopes (7, green), captures (6, RED),
  unchecked (4, RED), inference (5, RED)} — red groups are the targets of upcoming tasks.
- NEVER commit to `main` anywhere. Push `chexc` to `capabilities` after every commit.
- A git stash `partial-6.4-3.9-agent-work` exists in cangjie_compiler: an aborted
  partial attempt at Tasks 1–2 (parse-layer `captures` work). You MAY consult it
  (`git stash show -p 'stash@{0}'`) but implement deliberately; do not blind-apply.

### 0.2 Build & test commands (docker under the hood; never install on the host)
From the workdir root:
- `./cj.py build compiler` — incremental compiler build (ccache warm). SLOW even so.
- `./cj.py build std` — stdlib rebuild + SDK refresh (needed only when stdlib changes).
- `./cj.py test compiler` — compiler unittests (ctest). Expect 49/49.
  IMPORTANT: MacroTest compiles against the installed SDK, so after any compiler build the
  stdlib must be rebuilt (`./cj.py build std`) before ctest will pass — otherwise MacroTest
  fails spuriously with "Send exit stg false". Do this once per milestone gate, not per
  iteration.
- `./cj.py test llt --filter <paths...> -j N` — LLT groups.
  Full regression gate: `./cj.py test llt --filter compiler/Parser compiler/Sema -j 8`
  → must be 3934/3934 (baseline: notes/test-baseline.md; singleton fails near
  timeouts are load-flakes — retest at -j4 before investigating).
- `./cj.py fmt && ./cj.py fmt --check` — clang-format-15 over branch-changed files.
- `./cj.py sh -- '<cmd>'` — arbitrary command in the build container.

### 0.3 Iron process rules
1. BUILDS ARE VERY SLOW. Batch ALL edits for a cycle; run `fmt` BEFORE the build
   (never after — a post-build format forces a second build); ONE build per cycle;
   run every test suite against that single build. Never rebuild without new edits.
2. Red tests first: each task's tests are already committed (red). Implementation
   drives them green. If you must edit a test beyond its `// ASSERT:` lines, the only
   valid reason is that the test itself violates the proposal — explain in the commit.
3. Verified-only commits, review-sized: full gate before any implementation commit.
   Commit message style: see `git -C cangjie_compiler log` (feat(chexc)/test(chexc)
   prefixes, gate tallies in body, Co-Authored-By line as in previous commits).
4. Gate (every task): fmt --check clean; build(s) EXIT 0; ctest 49/49; ALL
   CheckedExceptions groups at their expected state; Parser/Sema LLT 3934/3934.
   For stdlib-touching tasks add: `./cj.py test llt --filter API/std -j 8` compared
   against notes/test-baseline.md's known exclusions.
5. After each task: update notes/gap-analysis.md (the inconsistency
   ledger) — close items you fixed, add any new deviation with its rationale.
6. FORBIDDEN, always: escape analysis of any kind (author ruling — waits for Modal);
   changing `TypeManager::GetFunctionTy`'s existing signature; touching mangling or
   CHIR for capabilities (erasure is by-construction: capTys are not in typeArgs);
   any effect-handlers (`handle`/`perform`/`resume`) special-casing; new escape-y
   value tracking. Diagnostics never mention `@ local!` (pre-Modal ruling).
7. The canonical docs: the proposal `Checked exceptions for CangJie.md` (symlink in
   workdir root) is normative; notes/implementation-plan.md holds ALL author rulings
   (numbered 1–14 across several blocks — read every rulings block); notes/
   architecture.md explains the phase design; notes/pr1735-study.md and
   notes/prototype-study.md are background.

### 0.4 Key architecture facts (established M0–M3; do not re-litigate)
- Flag: `--enable-checked-exceptions[=error|warn]` (FLAG_WITH_ARG), alias
  `--enable-chexc[=…]`; requires `--experimental`. `GlobalOptions::enableChexc` +
  `chexcSeverity` (CS_ERROR/CS_WARN). `throws`/`captures`-style keywords are
  EXPERIMENTAL_TOKENs lexed as identifiers unless the flag is on (Lexer.cpp keyword
  map, gated on `chexcEnabled`).
- AST: `ThrowsClause : Node` (ASTKind THROWS_CLAUSE), fields `FuncBody::throwsClause`,
  `FuncType::throwsClause`. Any new AST node/field must update ALL visitors: Walker,
  Clone, PrintNode, ASTChecker, ASTHasher (incl. member-signature hash), Collector,
  PartialInstantiation — and ASTKind.inc's SIZE column + unittests/Utils/
  CastASTTests.cpp count (CreateTest.CheckASTSize tells you exact numbers on failure).
- Types: `FuncTy::capTys` — const member, part of interning identity/Hash/==, NOT in
  typeArgs (that is what erases capabilities from CHIR/codegen). Additive
  `GetFunctionTy(paramTys, retTy, cfg = {}, capTys = {})`. `TyInstantiator`,
  `ReplaceThisTy`, `SubstituteTypeArgs`, alias substitution all carry capTys.
  Subtyping: `TypeManager::IsCapTysSubsumed(sub, super)` = ∀c2∈sub ∃c1∈super c2<:c1,
  wired in IsFuncSubtype/IsFuncTySubType. Join/meet in JoinAndMeet.cpp: join = union
  with redundancy pruning; meet = entries covered by every operand list. §3.6:
  UnifyFuncTy never touches capTys. §3.7: `TypeManager::EraseCapTys` inside
  IsFuncParameterTypesIdentical makes all overload/dup/shadow machinery compare
  modulo caps. §3.8: override subsumption in StructInheritanceChecker
  (CheckThrowsClauseCompatible, generic-mapped, ctors exempt).
- Checking: `CAPABILITY_CHECK` compile stage (CompilerInstance.h enum, between SEMA
  and DESUGAR_AFTER_SEMA; performMap entry in CompilerInstance.cpp; no-op unless
  enableChexc; error mode stops the pipeline like Sema errors, warn mode proceeds).
  Module: include/cangjie/Sema/CapabilityCheck.h +
  src/Sema/CapabilityCheck/CapabilityCheck.cpp (~410 lines; its header comment
  documents the rule set — READ IT FIRST). Interface:
  `CapabilityDemand{exceptionTy, demandSite, requiredBy}`,
  `CapabilityMissHandler{HandleMiss}` (abstract — the §6.2 seam),
  `ReportCapabilityMissHandler` (diag; error-or-warning),
  `CheckCapabilities(TypeManager&, const ImportManager&, Package&, handler)`.
  Supplies: FuncBody clause caps (TypeCheckUtil::GetFuncBodyCapTys); LambdaExpr's
  FuncTy capTys; TryExpr manual walk (push per-catch-pattern caps; resourceSpec +
  tryBlock inside; catch/finally OUTSIDE; wildcard → core Exception); SpawnExpr task
  runs with an EMPTY stack. Demands: ThrowExpr thrown static type; CallExpr via
  `ce.baseFunc->GetTy()` as FuncTy (already instantiated — covers generic/ctor/
  operator/function-value calls); FuncParam default values in the callee's own scope
  (synthesized desugarDecl clones skipped); instance field initializers must satisfy
  every ctor's scope; static/top-level initializers have no scope. Resolution:
  innermost-out, `TypeManager::IsSubtype(demanded, S)`, first match.
- Diagnostics: sema_chexc_missing_capability(_warn) — "Cannot find a capability for
  '%s' (of type 'CanThrow<%s>') in the current scope" + "required by %s" hint; warn
  variant in warn group `chexc` (DiagnosticWarnGroupKind.def) so `-Woff chexc` works.
- Known cosmetic facts: diagnostics print Ty names like `Class-AException`; tests pin
  these exact strings.

---

## TASK 1 — §6.3 UncheckedException

Target: `compiler/CheckedExceptions/unchecked` 4/4 (now 1/4 vacuous-pass).
Proposal: §6.3 (grep "### 6.4" in the proposal) + §3.2 rule 5.
Author rulings: 1 (M3 was all-checked; this task ends that), 9 (classification
principle; the re-parenting sweep is Task 5's job, NOT this one — the user's review
of notes/stdlib-exception-inventory.md is still pending).

Steps:
1. Stdlib (cangjie_runtime, branch chexc): add to std.core —
   `public open class UncheckedException <: Exception { ... }`.
   Find the existing exception classes: `grep -rn "open class Exception" 
   cangjie_runtime/stdlib/std/core/` (exception.cj or similar). Mirror the ctor
   surface of `Exception` (empty + message ctor), doc comment style of neighbors.
2. Compiler — helper: `bool IsUncheckedException(TypeManager&, const ImportManager&,
   Ty&)` — true iff the ty is a class ty whose decl chain reaches the std.core decl
   named "UncheckedException". Look up via ImportManager core-decl API (precedent:
   the effects feature's `GetCoreDecl<StructDecl>("Throws")` in
   src/Sema/TypeCheckExpr/TryExpr.cpp — copy its bootstrap tolerance: helper returns
   false when std.core lacks the class, e.g. while compiling std.core itself).
   Place it in the CapabilityCheck module (it is the only consumer, plus one PreCheck
   site below).
3. Exemption point 1 — THROW_EXPR: in CapabilityCheck.cpp where ThrowExpr produces a
   demand, skip when IsUncheckedException(thrown type).
4. Exemption point 2 — call demands: where CallExpr capTys entries become demands,
   skip entries whose INSTANTIATED type is unchecked (this is what makes
   `safeThrow<RequestException>()` capability-free — test unchecked_generic_ok.cj).
5. §3.2 rule 5 — clause validation: in the clause-entry validation
   (`ChkThrowsClauseTypes`, src/Sema/TypeChecker.cpp ~:205 area), reject CONCRETE
   types that are unchecked with a NEW dedicated diagnostic (suggested id
   sema_chexc_unchecked_in_clause: "unchecked exception type '%s' may not appear in
   a 'throws' clause"). Type parameters remain allowed even if instantiable to
   unchecked (the exemption in step 4 handles them).
6. Order of operations (build economy): make ALL compiler edits; fmt; build compiler
   ONCE; then edit stdlib; `./cj.py build std` ONCE (this uses the new cjc and
   refreshes the SDK); then run tests.
7. Tests: drive unchecked/ to 4/4. Tighten unchecked_in_clause_neg.cj's ASSERT to
   the new diagnostic text. All other groups stay at their state (captures/ and
   inference/ remain red — do NOT touch them here).
8. Gate per §0.3 rule 4 INCLUDING the API/std group run (stdlib changed).
9. Commits: (a) cangjie_runtime — the class (one commit, its own gate note);
   (b) cangjie_compiler — exemptions + rule 5; (c) cangjie_test — ASSERT pin.
   Push all three repos. Update the gaps ledger (close A7).

Pitfalls: std.core must still compile with the flag OFF (exemptions only run under
enableChexc, but the CLASS is unconditional — additive, so safe). If an API/std test
declares its own `UncheckedException` name, investigate the clash before renaming
anything (unlikely; check with grep in cangjie_test).

## TASK 2 — §3.9 class capturing (pre-Modal semantics)

Target: `compiler/CheckedExceptions/captures` 6/6 (now 1/6 vacuous).
Proposal: §3.9 (lines ~849–922). Author rulings: 10 (NO escape analysis — capturing
instances are NOT tracked), 11 (pre-Modal: EVERY ctor captures, EVERY body covered),
12 (primary ctors banned on capturing classes; `captures` allowed on structs).
The stash contains a partial parse-layer attempt — consult, don't blind-apply.

Steps:
1. Token: EXPERIMENTAL_TOKEN CAPTURES ("captures") in Tokens.inc after THROWS; add to
   the Lexer.cpp keyword map; gate under the SAME `chexcEnabled` (no new option).
   Update ASTKind/size tests only if you add a node kind (see step 2).
2. AST: REUSE the ThrowsClause node type (it is exactly a positioned type list) as a
   new field `capturesClause` on ClassDecl and StructDecl (find their struct defs in
   include/cangjie/AST/Node.h; if they share a suitable base for body/where handling,
   attach at the shared level). No new ASTKind needed. Visitors: Walker, Clone,
   PrintNode, ASTChecker, ASTHasher (MUST enter the member-signature/API hash),
   Collector, PartialInstantiation — grep each for `throwsClause` and mirror.
3. Parse (src/Parse/ParseDecl.cpp, class/struct decl paths): accept `captures` clause
   with a bare comma-separated type list; position relative to the superclass list
   and `where` block arbitrary (mirror how the decl throws/where ordering loop works
   in ParseFuncBody). Reject `...` in it. Reuse the throws-clause sub-parser
   (`ParseThrowsClause(true)`) — rename/generalize if needed.
4. Sema validation: entries must be subtypes of core Exception (reuse
   ChkThrowsClauseTypes on the captures clause); concrete UNCHECKED entries rejected
   (same rule-5 diagnostic family as Task 1). PRIMARY constructor on a capturing
   class/struct → new diagnostic (suggested: "a class with a 'captures' clause must
   declare explicit 'init' constructors"). Detect primary ctor presence at the decl
   level (PrimaryCtorDecl child) BEFORE desugaring hides it.
5. CapabilityCheck integration (all in CapabilityCheck.cpp):
   a. SUPPLIES: for members of a class/struct WITH capturesClause, push the captures
      cap list (elaborated Tys) around: every method body, every prop accessor body,
      every init ctor body, and include it in the instance-field-initializer
      every-ctor predicate. The class's OWN clause only — rule 5: never inherited.
      (CheckMembers already centralizes member dispatch; add the push there.)
   b. DEMANDS: in HandleCall, when the callee is a constructor of a capturing class,
      demand each captured cap at the call site. Cover: direct `C(...)` calls,
      `super(...)` calls from subclass ctors (demand the SUPERclass's captures), and
      delegating `this(...)` calls (same class's captures are in scope from (a), so
      they self-satisfy — verify, don't special-case blindly).
      How to find the constructed class from a CallExpr: the resolved FuncDecl's
      outerDecl / the ce.resolvedFunction — inspect how M3's HandleCall gets callee
      info and extend.
   c. Where do elaborated captures Tys live? Recommended: elaborate clause →
      `std::vector<Ptr<Ty>>` once in PreCheck-adjacent code and cache on the decl
      (mirror how GetFuncBodyCapTys elaborates throws clauses); do NOT re-elaborate
      per call site.
6. cjo: same silent-drop posture as throws clauses (verify exporting a capturing
   class does not crash; note in gaps ledger C11).
7. Tests: drive captures/ 6/6; ASSERT tightening for the two new diagnostics.
   captures_struct.cj notes: struct copy duplicates the capability — under rulings
   10/11 nothing extra to implement (no tracking); the test just runs.
8. Gate; commits: compiler + test; push; gaps-ledger update (A3/A4 remain, note
   implemented shape).

Pitfalls: PRIMARY_CTOR_DECL is desugared during Sema — ban it before desugar.
ASTHasher omission = silent incremental-compilation bugs (the hash MUST change when
a captures clause changes). Do not let the captures supplies leak into nested
LOCAL functions declared inside methods?? They DO see enclosing scopes lexically
(M3 behavior for try/clause scopes) — keep captures consistent with that: lexical.

## TASK 3 — §6.2 capability parameter inference

Target: `compiler/CheckedExceptions/inference` 5/5 (now 2/5: public_neg legitimately
green, poly_recursion_neg vacuous).
Proposal: §6.2 ENTIRE section, re-read carefully — esp. 6.3.1 (eligibility), 6.3.2
(what is inferred, incl. the discharge rule), 6.3.4 (least fixpoint + the
no-evolving-list-as-conversion-target monotonicity rule + POLYMORPHIC RECURSION
rejection), 6.3.5 (`...` and `throws ()`).

Steps:
1. Parser unlock: `...` in DECL clauses only (ParseThrowsClause currently
   diagnoses it everywhere; keep the functional-type rejection). Store
   `hasEllipsis` on ThrowsClause. ASTHasher must include it.
2. Eligibility (6.3.1): a callable is inference-eligible iff it has NO clause (or a
   clause ending in `...`) AND is not exported surface: not `public`, not `protected`,
   not an interface method decl; accessors/secondary ctors follow the enclosing
   decl's visibility. Literals are NEVER body-inferred (their caps come from expected
   type — already M2). Determine CangJie default visibility semantics from the code
   (grep Modifier handling) — do not guess: verify what unannotated top-level means.
3. New pre-step in the CAPABILITY_CHECK stage (before the report run), same module:
   a. Collect the intra-package call graph over eligible callables: reuse the M3
      walker in a COLLECT mode — implement `CollectingMissHandler` (the existing
      CapabilityMissHandler seam) that records residual demands instead of
      diagnosing. You need per-callable granularity: expose the pass's per-decl
      entry (CheckCallable/CheckInitializer are file-private — add a public
      `CheckDecl(decl, handler)` or equivalent).
   b. Call-graph edges: calls from an eligible callable to OTHER eligible callables
      (only intra-package, only calls whose callee decl is known). Non-eligible
      callees contribute their (authoritative) capTys as ordinary demands.
   c. SCC condensation (Tarjan; write it locally, ~60 lines), process SCCs bottom-up
      in reverse topological order. Within an SCC: Kleene-iterate the equations
      `C(f) = local(f) ∪ ⋃ callsites (C(callee) ∖ discharged-at-site)` from empty
      sets until stable. `discharged-at-site` = the supply stack at that call site
      (the collect walker must record demands WITH their discharge context — the
      simplest correct shape: a demand is residual iff no ENCLOSING supply covers
      it; for intra-SCC calls, record the call site's supply stack so the callee's
      evolving list can be filtered through it each iteration).
   d. Explicit-clause members of a cycle are constants (checked as written).
      `throws A, ...` = constant A ∪ evolving inferred part.
   e. POLYMORPHIC RECURSION check (6.3.4): on SCC call edges, if the type-argument
      substitution maps a type parameter to a non-variable type CONTAINING that
      parameter (occurs check), and that parameter appears in any throws-relevant
      position in the cycle, reject with a dedicated diagnostic naming the growing
      instantiation; require explicit clauses. Only inspect parameters that occur
      in demand types.
   f. Write results: attach the inferred list to the decl the same way explicit
      clauses land (rebuild the decl's FuncTy with capTys via GetFunctionTy — types
      are interned; also update GetFuncBodyCapTys's source so the report run sees
      supplies). THEN run the normal report pass over the whole package.
4. `throws ()` is already authoritative-empty (M2 elaborates it) — verify inference
   skips such decls (they have a clause).
5. Monotonicity rule (6.3.4, conversions): conversions (§8.10) do not exist yet;
   leave a NORMATIVE comment at the miss-resolution point that when conversions
   arrive they must not target any in-flight SCC member's list.
6. Tests: inference/ 5/5. infer_recursion.cj's pong MUST infer {B} only (partial
   discharge — this distinguishes the fixpoint from naive union; if it infers
   {A, B} your discharge recording is wrong). Also re-run ALL other groups: inference
   must not change any (they all use explicit clauses or none + public).
7. Gate; commit compiler + any ASSERT pins; push; gaps ledger: close C4 (decl `...`),
   B7 note "implemented".

Pitfalls: the walker runs per-decl with fresh state — ensure collect mode composes
(no shared mutable stack between callables). Iteration order determinism: process
SCC members in declaration order for reproducible diagnostics. Do NOT run inference
when severity is warn?? — inference runs regardless of severity (it determines
lists; severity only affects reporting).

## TASK 4 — cjo serialization / package metadata (§3.10.2 subset)

Closes gaps C1, C2, C3, C11. Proposal §3.10.2. Do AFTER Task 3 (inferred lists are
serialized like explicit ones — they're intra-package truth; exported surface is
explicit-only by 6.3.1, but same-package incremental caching needs them).

Steps:
1. schema/ModuleFormat.fbs: append `capTypes:[uint32]` to `table FuncTyInfo` (~:591;
   flatbuffers append-at-end is backward compatible). Also a field for decl-level
   captures clause metadata on the class table (list of type refs) — find ClassDecl's
   table.
2. Writer: src/Modules/ASTSerialization/ASTWriter.cpp `SaveFuncTy` (~:1105) — write
   capTys IN CANONICAL FORM (C3/§3.10.2 rule 1): expand nothing (no aliases yet),
   drop entries covered by a more general entry (use IsSubtype), drop duplicates,
   sort the remaining antichain deterministically (by mangled/ToString name; generic
   parameters all kept). CAUTION in SaveFuncTy: SaveType has side effects — compute
   each offset in its own statement (existing comment explains).
3. Loaders (ALL THREE): ReferenceLoader.cpp `SetTypeTy<FuncTy>` (~:368) reads the
   vector back into GetFunctionTy's capTys param; ASTLoader decl paths; and
   IncrementalLoader.cpp (cached decl types — the prototype study warns of a
   copy-paste hazard here: use the RIGHT list). Captures clause: reload into the
   decl field so CapabilityCheck sees it for imported classes.
4. Cross-flag semantics (§3.10.2 rules 2–3): record the package's checking level
   (off/warn/error) in the metadata header (find the package-level table); on
   import: lists from any-level package are used as-is; packages recorded "off"
   yield empty lists. (Full §5.2 interop defaults are NOT this task — only the
   metadata plumbing; note remaining §5.2 work in the gaps ledger D section.)
5. Tests: new LLT dir `CheckedExceptions/modules/` with a run.py driver (copy the
   pattern from an existing modules-style test, e.g. the colleague's suite
   `wizzerinus-implicits-regression/tests/modules/run.py` as reference): package A
   (staticlib) exports `throws` decls + a capturing class; package B imports —
   verify (a) missing-capability error crossing the boundary, (b) functional-type
   subtyping across it, (c) override checking against an imported base, (d) a
   flag-off-compiled A read as empty lists. Commit tests RED first (run.py driver
   that currently shows caps NOT crossing), then implement, then green.
6. Canonicalization also fixes C3 for METADATA only — in-memory order-sensitivity
   stays (harmless). Gate + commits (compiler, test) + push + ledger.

## TASK 5 — stdlib one-pass warn-mode cleanup (§5.3 / directive 6)

PREREQUISITE: the user's review of notes/stdlib-exception-inventory.md (18 UNCERTAIN
items). If still pending, ASK — do not guess UNCERTAIN classifications. The
re-parenting sweep applies the reviewed verdicts.

Steps:
1. Re-parent: for every class the inventory marks unchecked, change its base to
   UncheckedException in cangjie_runtime/stdlib (one mechanical commit; the
   hierarchy conflicts flagged in the inventory — e.g. IllegalFormatException under
   IllegalArgumentException — follow the user's per-item verdicts).
2. Build std with checking: add a chexc-warn configuration to the std build
   (`--enable-checked-exceptions=warn` must reach cjc for std packages — find where
   stdlib build.py assembles cjc flags; add an opt-in env/flag so normal builds are
   unaffected). Collect ALL warnings to a file.
3. Triage every warning: (a) obvious fixes — add `throws` clauses to non-public
   helpers ONLY where inference doesn't cover them (inference exists by now — most
   internal warnings should vanish via §6.2), add clauses to public API where the
   checked exception is clearly part of the contract, add local try/catch where the
   code already handles-and-continues; (b) anything requiring API judgment (public
   signature changes, wrap-vs-propagate decisions, §8.10-conversion-shaped patterns)
   goes to notes/gap-analysis.md (Part I.5) — one entry per item: location,
   warning, options, recommendation. Do NOT make public-API judgment calls yourself.
4. Whole stdlib in ONE pass (author ruling 13) — iterate until the warn build's
   chexc warning count is zero-or-documented.
5. Gate: everything from §0.3 rule 4 + `API/std` + `API/stdx` LLT groups (stdx group
   needs CANGJIE_STDX_PATH — cj.py handles it) — stdlib behavior must not change
   (erasure guarantees ABI; test failures here mean a semantic slip, investigate).
6. Commits: runtime repo (re-parent; cleanup), notes file for the user; push.

## TASK 6 — macro NodeFormat serialization (gap C5)

Small. schema/NodeFormat.fbs: add ThrowsClause table + fields on FuncBody/FuncType
(+ capturesClause on class/struct tables); writers in src/Macro/NodeSerialization.cpp
/ ExprSerialization.cpp; loader side in the macro reparse path. Reference: the
colleague's fork did exactly this for its clause (`git -C wizzerinus-cjc-implicits
diff new-main..diploma/implicits-updated-new -- schema/NodeFormat.fbs
src/Macro/NodeSerialization.cpp`). Test: LLT case where a macro emits a decl with a
throws clause via quote (copy the shape of the colleague's `macro` test). Note
Tokens.inc's header comment: stdlib/ast/AnyKind.cj may need a matching update —
check what `libast` exposes for tokens (the API/std/libast tests will tell).

## TASK 7 — IDE/cjd capability diagnostics (gap C9)

CjdCompilerInstance currently no-ops PerformCapabilityCheck. Implement run-for-
diagnostics: execute the pass in the cjd pipeline (diagnostics only; ensure the LSP
diagnostic collection includes the chexc kinds). Verify with the LSP-oriented
unittests (TypeCheckForLSP paths) that nothing crashes on incomplete ASTs — the
pass must tolerate broken/partial nodes (guard on Ty::IsTyCorrect everywhere; M3
already does — extend the discipline to captures/inference code).

## TASK 8 — Effects §8 integration (DESIGN FIRST — do not implement)

Author directive: after Task 5. This is a DESIGN round with the user, not an
implementation task. Prepare and present: (1) §8/§8.2 close-read summary; (2) how
`try/handle` should interact with capability scopes (do handle clauses discharge
anything? does `perform` demand a capability-like evidence?); (3) whether checked
exceptions and effects share the capability machinery under evidence passing
(§8.2 materialization — the ABI-epoch caveat of §3.10); (4) what the in-tree
experimental effects implementation (EffectHandlers.cpp lowering to stdx.effect
frames) constrains; (5) a proposed test matrix. STOP after presenting; implement
only after explicit author rulings.

## Ambient / backlog (pick up opportunistically, never block on them)
- Diagnostics polish (gaps C7/C8): dedicated §3.6 inference-failure wording; unify
  Ty-name vs source-text printing.
- C10: drop or keep the `--enable-chexc` alias — author's call.
- §6.1 aliases and §8.10 conversions: unscheduled; §8.10 interacts with §6.2's
  monotonicity rule (see Task 3 step 5's comment) — bring to the author before
  starting.
- Modal integration: WAITING on upstream (ruling 14). When it lands: phantom-filter
  seams are documented in notes/pr1735-study.md (P1–P10) — capability-blind
  CheckCapture, our pass after CheckModalType, exclave as an escape edge, restore
  §5.5 checks and the `@ local!` diagnostic wording (gaps A1/A2/A3).
- Inventory review (user): 18 UNCERTAIN items — prerequisite of Task 5 only.

## Per-task loop (checklist)
1. Read the task's proposal section + rulings + relevant gap entries. 2. Red tests
exist? (Tasks 1–3: yes, committed.) If a task lacks tests (4–7): WRITE THEM FIRST,
verify red, commit+push them with a message explaining the red state. 3. Batch all
edits. 4. `./cj.py fmt && ./cj.py fmt --check`. 5. Build (compiler; std only if
stdlib changed). 6. Run: target group; ALL CheckedExceptions groups; ctest;
Parser/Sema LLT; (+API groups when stdlib touched). 7. Iterate 3–6 (each iteration:
fmt before build). 8. Update notes/gap-analysis.md. 9. Commit
per-repo, review-sized, gate tallies in message. 10. Push `chexc` to `capabilities`
on every touched repo. 11. Report: files+rationale, tallies, deviations (explicitly
flag ANY spec interpretation you had to make — the author reads these).

---

# ADDENDUM (2026-08-15): the four author-requested features

Order (author-confirmed): §6.2 inference → §6.1 aliases → §5.2.2 assumption imports →
cjo serialization → §8.10 conversions (branch `chexc-conversions`) → §8.11 adapt (branch
`chexc-adapt`). Decisions and their rationale: notes/autonomous-decisions.md.
Red tests for all four are COMMITTED (13 cases): CheckedExceptions/{aliases,assume,
conversions,adapt}.

## TASK A — §6.1 capability list aliases (→ chexc)

Target: `compiler/CheckedExceptions/aliases` 4/4.
Spec: proposal §6.1 (grep "### 6.1"). Decisions D2, D3.

Anchors researched:
- Alias types are `TypeAliasTy` (include/cangjie/AST/Types.h:952); `TypeManager::
  ObtainsAliasType` / `ObtainsAliasTypeOfRefType` (src/Sema/TypeManager.cpp:2526) resolve
  an alias RefType to its target ty. Tuple target ⇒ `TupleTy` (Types.h:639).
- Clause elaboration sites (where the expansion belongs): `TypeCheckUtil::
  GetFuncBodyCapTys` and `GetDeclCapturesCapTys` (src/Sema/TypeCheckUtil.cpp), plus
  `PreCheck.cpp GetTyFromASTType(FuncType&)` for functional types, and the validator
  `ChkThrowsClauseTypes` (src/Sema/TypeChecker.cpp ~:196).
Steps: after a clause entry's Ty is elaborated, if it resolves (through aliases) to a
TupleTy, splice its element tys into the capability list, recursively, with a visited set
over TypeAliasDecls for cycle detection (dedicated diagnostic on cycle). Validate elements
with the existing per-entry rules AFTER expansion (so `alias_neg.cj` reports on elements).
Keep the alias usable as an ordinary tuple type elsewhere — do not change ObtainsAliasType.

## TASK B — §5.2.2 assumption imports (→ chexc)

Target: `compiler/CheckedExceptions/assume` 3/3 (multi-package: see the DEPENDENCE/EXEC
lines in the tests; a support package legacy_db.pkg.cj is compiled without the flag).
Spec: proposal §5.2.2 (line ~1098). Decisions D4, D5, D6.

Anchors researched:
- `ImportSpec` already carries `annotations` (include/cangjie/AST/Node.h:2962-2966).
- Annotation kinds: `AnnotationKind` (Node.h:536); name→kind map `NAME_TO_ANNO_KIND`
  (include/cangjie/Parse/Parser.h ~:50); per-kind parsing switch in
  src/Parse/ParseAnnotations.cpp (~:360, see the WHEN and DEPRECATED cases);
  `ASTChecker.cpp:132` and `ASTHasher.cpp:817` have per-kind switches to extend.
Steps: add `ASSUME_THROWS` kind + "AssumeThrows" mapping; parse a bracketed TYPE list
(like the clause parser — reuse ParseThrowsClause's element parsing, or parse args and
resolve RefExprs as types); bare form ⇒ `Exception`. Elaborate the list once (aliases
apply, TASK A). Store per imported package name in the package context. In
CapabilityCheck::HandleCall, when the callee decl's `fullPackageName` matches an assumed
package, demand the assumed list too (D6: only direct calls into that package). Diagnostic
mentions the assumption's origin (D5). Never serialize (consumer-local).

## TASK C — cjo serialization (→ chexc) — see TASK 4 above, unchanged, but note:
inferred lists (§6.2) are intra-package truth; exported surface is explicit-only by
§6.2.1, so serialize capTys as they stand after inference, in canonical form (§3.10.2
rule 1). Also serialize `captures` clauses (§3.9 classes are exported).

## TASK D — §8.10 exception conversions (→ NEW BRANCH `chexc-conversions`)

Target: `compiler/CheckedExceptions/conversions` 4/4. Spec §8.10 entirely (§8.10.1 rules
1–6 are the test matrix). Decisions D7–D11.
Requires: `Convertible<From, To>` interface in std.core (runtime repo) + a SETTABLE
`Exception.cause` (author ruling; `suppressed` deferred — record as a gap).
Shape: CapabilityCheck records conversion sites (pure check, D7); a new desugar step in
DESUGAR_AFTER_SEMA synthesizes `try { e } catch (eFrom: From) { let eTo =
To.convertFrom(eFrom); if (eTo.cause is None) { eTo.cause = eFrom }; throw eTo }`.
Rule 6 needs demands tagged with their origin (storage vs call) — add a DemandKind to the
CapabilityDemand struct when implementing §3.9 captures demands (they are the storage ones).

## TASK E — §8.11 adapt (→ NEW BRANCH `chexc-adapt`, on top of D)

Target: `compiler/CheckedExceptions/adapt` 2/2. Spec §8.11. Decision D12.
NOTE: the proposal explicitly defers this feature; it is built at author request as an
experimental extension. Synthesize a capturing class (reusing §3.9), forwarding methods,
`captures` = union of forwarded `throws` lists; result demands those at the adapt site.
