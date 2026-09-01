# Proposal ↔ implementation gap analysis

**Single source of truth** for what separates the `chexc` prototype from the proposal, and
the proposal from a stabilizable design. Two parts: what the **implementation** must change,
what the **proposal** must change. A short third part keeps resolved items whose lessons
still matter. Updated at every milestone gate.

State: compiler `cd0b3f4f`, runtime `3caa943`, stdx `4eb1cd8`,
tests `0e131d8a` — the four commits the umbrella pins; proposal as revised **2026-08-30 17:54** (chapter 5 rewritten: the
`--enable-checked-effects` axis with `@AssumePerforms` and `unsafeCanPerform`, the escape hatch
renamed `unsafeCanThrow`, free clause order in declarations, the sibling-catch rule for `resume
throwing`, `where`-bounds in the semantic form). Sections 3, 5 and 6 were re-audited against the prototype
on 2026-08-23 by probing; the plan to close what is left is I.0.

This document consolidates and replaces: `handoff-plan.md`, `implementation-plan.md` and
`batch2-guide.md` (merged into `README.md`, `architecture.md`, `autonomous-decisions.md` and this
file on 2026-08-30, then deleted), `proposal-implementation-gaps.md` (ledger A–F),
`proposal-update-review-2026-08-20.md`, `production-gap-analysis.md`, `author-questions.md`,
`stdlib-migration-questions.md`, `audit-report.md`, `code-review-2026-08-15.md` — all in
git history. Decisions (D1–D18) stay in `autonomous-decisions.md`; the extension plan stays
in `conversions-adapt-plan.md`; the stdlib classification data stays in
`stdlib-exception-inventory.md`.

---

# Part I — What the implementation must change

## I.0 The plan (2026-08-30 evening): the chapter-5 revision and its review

The R-plan below is done in full. A second external review arrived against `5de33983`, targeted at
chapter 5 and the **new text revision of 2026-08-30 17:54**; every implementation claim it makes
was probed or code-read, and **all twelve were confirmed** — an unusually accurate review. Its
Modal sections are out of scope by the standing ruling. The batches, awaiting the author's
go-ahead per batch:

| Batch | Contents | Size |
|---|---|---|
| **S1 — quick correctness** | I32 generic-`Error` exemption; I44 plural effect message says `CanPerform`; I43 fabricate only `E`; I45 one shared inference-eligibility predicate (the `...` incremental gap); I35a completion compares content, not size; I35b instantiate entries at reference sites | S, 1 build |
| **S2 — text sync, small** | I38 free clause order in declarations; I42 rename to `unsafeCanThrow` (compiler constant + std.core + tests); I37 `resume throwing` discharged by the try's own catches | S–M, 1 build + std |
| **S3 — `where`-bound coverage** | I36: the semantic form uses bounds already in the open generic form | S–M |
| **S4 — the checked-effects axis** | I39 `--enable-checked-effects off/warn/error` + its warn group + metadata effect level + unchecked-effects boundary; I40 `@AssumePerforms`; I41 `unsafeCanPerform`. Vehicle question: this is where D17's single `capTys` vector stops being tenable — kind-aware severity, filtering, metadata and printing all want `throwsTys`/`performsTys` split (closes C16/C17 too). **Design note first** | L |
| **S5 — inference completion** | I35: replace the formation-site reading with completed capability components on expression types plus a replay of capability-sensitive constraints (the review's §7.4/7.5). Closes the **confirmed soundness hole** (a value formed under a discharging `try`, stored outward, called after — compiles at `error`, leaks at run time) and retires artifact C15's inferred half. **Design note first** | L |
| **S6 — inference reach** | I33 field initializers feed every inference-eligible constructor; I34 the `for-in` iterator protocol demands (synthesize like the implicit `close()`) | M |

### The decision-free ordering (2026-08-31, chapters 3/5/6)

The S-batches above, reordered and completed by the author's request into a queue where **nothing
waits on a ruling**: every item is fully specified by the current text, by an already-given
ruling, or is implementation-internal. Sub-choices that exist are recorded with the recommended
default and are reversible. Each batch ends with the standard gate (fmt → build → targeted groups
→ std at `warn` → commit/push → this file) plus the extra suites named per batch.

**Landed 2026-08-31: T1 through T4**, each on its own gate (the batch's own groups, then the
extra suites named in its row). The queue below keeps the full contents for the record; what is
left is T5 — begun, and in the working tree only — then T6, T7 and T8. Closed rows are marked in I.2.

| # | Contents | Size | Extra gate |
|---|---|---|---|
| ~~**T1**~~ = S1 | Quick correctness: I32 generic-`Error` exemption (provable relation to the roots, bounds included); I44 plural `CanPerform`; I43 fabricate only `E`; I45 one shared eligibility predicate (`...` incremental gap); I35a content-compare in completion; I35b instantiate entries at reference sites | S | IncrementalCompilation (I45) |
| ~~**T2**~~ = S2 | Text sync: I38 free declaration clause order; I42 rename → `unsafeCanThrow` (constant, std.core file, tests); I37 `resume throwing` discharged by the try's own catches — mechanism: a resume-only injection supply pushed for handler bodies, consumed by `RESUME_EXPR` demands alone, so ordinary `throw` in a handler stays outside the try's scope | S–M | Macro suite (parser), std build (rename) |
| ~~**T3**~~ = S3 | I36 `where`-bound coverage in the open form: `IsSubtype` over a `GenericsTy` entry must consult declared upper bounds where normalization runs (investigate whether the loss is in `IsSubtype` or in normalization running before constraints attach) | S–M | full `compiler/Sema` (type identity) |
| ~~**T4**~~ = S6 | Inference reach: I33 field initializers contribute to every inference-eligible constructor (collect each initializer's residual demands into every ctor's equation, mirroring the explicit-clause path); I34 `for-in` demands — synthesize `iterator()`/`next()` effective lists at `FOR_IN_EXPR`, the implicit-`close()` pattern | M | — |
| **T5** = S5 *(in progress: the completer and the replay exist in the working tree, ungated and uncommitted; the pinned compiler does not carry them)* | **Inference completion** (closes the confirmed `error`-level leak): after `CompleteInferredCapabilityTypes`, complete the capability components of expression types — references, bound methods, inferred variable types, returns, joins, invariant containers, generated wrappers — and replay capability-sensitive subtype/equality checks recorded during Sema; retire `DemandInferredOnValue` and artifact C15's inferred half. Internal design note first (`inference-completion-design.md`); semantics is the text's own (the list rides the type, the call pays) | L | full `compiler/Sema` + serialization + IncrementalCompilation |
| **T6** = S4 | **The checked-effects axis**: `--enable-checked-effects off/warn/error`, effect severity and the `checked-effects` warn group, metadata effect level, unchecked-effects boundary (`performs` reads empty without the flag), `@AssumePerforms` (no bare form), `unsafeCanPerform`; `performs_without_chexc.cj` flips to the new semantics. Vehicle: the `throwsTys`/`performsTys` split (D17 revisited — implementation-internal), which also closes C16 (printing) and C17 (inert-gate kinds). Internal design note first | L | effect groups + stdx build + serialization |
| **T7** = I31 | Property clauses, on the ruling and the two recorded recommendations (Q14 distribution, Q15 distributed-only metadata; both reversible): `PropDecl::throwsClause`/`::performsClause` + visitor sweep, bodyless accessors where bodyless methods are legal, distribution in `ParsePropBody` and `AddSetterGetterInProp`, then the `std.net` socket interfaces — the annotation this was for. Independent of T5/T6; can run in any slot | M | Macro suite (parser), std build |
| **T8** | Cleanup tail: split `CapabilityCheck.cpp` into checking/inference/assumptions/completion units (pure refactor, after T5/T6 so it moves final code); inference instrumentation (SCC count/size, iterations, re-walked nodes — the review's numbers, behind a flag or the profile recorder); incremental v2 (persist inferred fingerprints, invalidate actual dependents instead of full rollback) | M | full targeted set |

**Excluded, because they wait on the author:** every text item (`proposal-shortcomings.md`), the
Q-STD rulings and everything they block (stdlib batch 3a, the zlib/tar/http/tls stdx rings), E-4,
E-17/E-19 text sides, I5/I7, and all of chapter 4 / Modal.

## I.0-done The plan (2026-08-30): section 3 conformance + the reviewer's findings

Supersedes the 2026-08-23 batch plan (A/B/C done, D out of scope, E partly ruled — history in
Part III). Ordered by value per build; every batch ends with: fmt → compiler build → targeted
groups (`compiler/CheckedExceptions`, `compiler/Sema/effect`) → std build at `warn` → commit/push
→ this file. Nothing starts without the author's go-ahead per batch.

**The mechanism behind Q11, established by reading the solver** (`LocalTypeArgumentSynthesis::
FindSolution`): the language reports *unable to infer* only for a variable with **no constraints
at all** (`NO_CONSTRAINT` → "no information known for type variable"); a `where T <: Exception`
bound seeds an upper bound into the constraint set, and a bounded-but-otherwise-unconstrained
variable is **solved to its bound** by the general machinery. So `g(0, f)` compiling is ordinary
language behavior, not a capability-feature anomaly — and the ruled restoration must be a
dedicated post-resolution check, never a solver change (which would break ordinary
`where`-bounded code).

| Batch | Contents | Size | Builds |
|---|---|---|---|
| ~~R1 — the rulings~~ | **done** (compiler `51825163`): Q11 rejection, Q10 inert clauses, I29 closed by reading | — | — |
| ~~R2 — Q8: `close()` demand~~ | **done** (same commit): each resource's effective `close` list demanded in the try's scope | — | — |
| ~~R3 — I30: canonical `CapList`~~ | **done** (compiler `667b9a1c`): normalization at the four producer boundaries; C16 stays recorded, see the design note | — | — |
| ~~R4 — I28: incremental inferred lists~~ | **done** (compiler `ac3856ef`): feature-gated rollback when an inference-eligible declaration is recompiled; v2 (persist lists, invalidate actual dependents) recorded | — | — |
| ~~R5 — review tails~~ | **done** except two recorded items: meet tests, the ABI/erasure symbol test, the stale header. The `capTysInert` kind split (EH-on/chexc-off) and the optional file split of `CapabilityCheck.cpp` stay open — see I.3 | — | — |

**R1 details.**
- *Q11/I20*: helper `CollectClauseOnlyTyVars` in TypeCheckUtil — a callee type parameter is
  clause-only when the full walk (the `CollectUsedTyVarsInto` shape: typeArgs + `capTys`) sees it
  but the erased walk (`Ty::GetGenericTyArgs`, typeArgs only) does not. Hook at post-resolution
  call finalization (after the winning candidate is fixed — NOT inside per-candidate solving,
  which would perturb overload resolution); no explicit type argument for such a parameter →
  `sema_unable_to_infer_generic_func` plus a dedicated note: *"type parameter 'T' occurs only in
  capability lists, which take no part in type-argument inference; write it explicitly"*.
  Constructors of generic capturing classes covered if the same hook sees them, else recorded.
  Tests: the text's example verbatim as a neg; the `throws T, G`-callee variant flips from
  demand-at-bound to unable-to-infer; explicit args stay legal (`generics_higher_order.cj`).
  Verification probe: upstream-general `func p<T>(x: Int64) where T <: Exception; p(0)` —
  document whether the language accepts it (expected: yes, solved to bound), pinning that our
  new error is deliberately stricter for clause-only parameters exactly as the text demands.
- *Q10/I18*: unstash `q10-draft` (capTys dropped at the `GetFunctionTy` funnel when BOTH features
  are off; set in the CompilerInstance ctor before imports load), restore the two parked tests
  (`scopes/off_ignores_throws.cj`, `serialization/xpkg_off_consumer.cj`), add a `.cjo` assertion
  that an off package records no `throws` lists. Residue recorded: the EH-on/chexc-off combo keeps
  exception entries until R5's kind split.
- *I29*: no code. Ledger close (composition exists only as `@Inner` inside `quote` → a dynamic
  cascade; bodies are checked statically, the root is the compiler's contract; no static edge
  through `quote` exists) + erratum E-18: §5.3.1's non-public-macro sentence is vacuous — the
  compiler mandates `public` on every macro declaration.

**R2 details.** In the `TRY_EXPR` case of the walker, for each resource of a try-with-resources:
resolve the resource type's `close()` member, take its effective list (declared `FuncTy::capTys` ∪
`inferred[close]`, instantiated through the resource's type mapping — reuse the
`GetInstantiatedAccessorCapTys` shape), and demand each entry **inside the try's pushed scope**
(the probe of 2026-08-30 confirmed the desugaring puts closing inner to the catches, so the try's
own capabilities are the right suppliers). Tests at `warn` (a clause-bearing `close` over
clause-free `Resource.close` is tolerated there); the `error`-level test lands with batch 3a's
interface ruling (Q-STD-9a).

**R3 details.** Design note first (`notes/caplist-design.md`). Normalization = dedupe +
coverage-drop + drop concrete unchecked entries (uses the `uncheckedExceptionTy` the manager now
holds), applied at PRODUCER boundaries — never at interning, where the 2026-08-22 attempt broke 17
tests: (1) clause elaboration (declaration types in `TypeChecker.cpp`/`PreCheck.cpp:1824`, the
functional-type-node site), (2) the `FuncTy` branch of `GetInstantiatedTy` (placeholder-guarded —
`NormalizeCapTys` already returns placeholder lists unchanged), (3) the loader
(`ReferenceLoader.cpp:380`), (4) `CompleteInferredCapabilityTypes`. Joins/meets already normalize.
Closes: Box-invariance identity, the printed semantic form, the unchecked-instantiation identity
residue. Gate: full `compiler/Sema` (3,934) + serialization + CheckedExceptions + std and stdx
builds. C16 decided during design: if entries carry an elaboration-computed kind bit, the printed
form splits `performs`/`throws` here; otherwise C16 stays recorded.

**R4 details.** v1, sound and simple: persist each eligible declaration's inferred list in the
incremental cache (keyed by raw mangle; values as stable normalized type identities); after
inference, compare with the cache — any change escalates the round to a full-package recompile,
logged in the incremental decision log; the no-change case keeps today's incrementality. The
precise dependent-set version stays a recorded v2. Tests: the `incr_inferred.cj` reproducer from
Part III returns as a real test, plus a no-change case asserting the incremental path via the
decision log. Gate: `compiler/IncrementalCompilation` (1,944) + CheckedExceptions.

**R5 details.** (1) meet test — the text's own `k = if (cond) { p } else { q }` example; (2)
ABI/erasure regression — clause-bearing and clause-free twins compiled, `nm` symbol lists compared
byte-identical; (3) stale comment sweep (the checker header still says effects are ignored); (4)
kind classification for `capTysInert` (EH-on/chexc-off drops exception entries, keeps commands;
`SetCommandDecl` beside `SetUncheckedExceptionTy`; loader-side residue recorded); (5) optional,
last: split `CapabilityCheck.cpp` (~1,500 lines) into checking/inference/assumption units — pure
refactor, deferred behind R3/R4 to avoid dragging conflicts.

**Out of scope by the author's rulings:** captures lifetime, regions, `resume with` flow, the
closed-build verifier (Modal); LSP/cjd (C9), the fixer and the lints (I.4 tooling); the
`throws`/`performs` storage split (D17 — revisited at evidence passing).

## I.1 Base-design conformance (the proposal says it; we don't do it)

| # | Gap | Proposal section | Effort |
|---|---|---|---|
| I4 | **No capability-region check** — rules 1–6 of "Capability regions", resumptions as carriers, `resume with` as a flow boundary. Both canonical escapes are accepted today. **Deferred by the author (2026-08-23): regions are a Modal CangJie requirement, not this tier's.** Kept here because the text still states them for the base design — either the text scopes them to Modal, or this stays a permanent divergence | Capability regions; Effect requirements rules 4, 6 | — (not to be implemented) |
| I31 | **A property cannot declare what its accessors throw where it matters most — in an interface** (E-19). Ruled 2026-08-30: support a clause on a bodyless accessor and a clause on the property itself, distributed to accessors without one. Design, plan and two open sub-questions in `property-clauses-design.md`; the expensive part is a new `PropDecl` field and its visitor sweep. Closes the `std.net` socket properties, the only real cases in std and stdx | Capability parameters in declarations, rule 1; Overriding and redefinition | M: 1–2 compiler builds + std |
| ~~I32~~ | *(closed 2026-08-31, T1: the `IsClass()` gate is gone from `Demand()`, so a bound-provable relation to either root exempts a generic. Tests `unchecked/error_generic.cj` + `_neg.cj` — the negative half needed a type parameter only, `Error`'s constructors not being exported outside std.core.)* **A generic `T <: Error` demands a capability.** The `Error`-hierarchy exemption fires only for `ty->IsClass()`; `throw e` with `E <: Error` demands `CanThrow<Generics-E>` (probed). Classify by provable relation to the two roots, generic upper bounds included | Capability requirement at `throw`, rule 1 | S |
| ~~I33~~ | *(closed 2026-08-31, T4: `CollectFieldInitializerDemands()` walks each initializer in the constructor's own scope, so its residual demands enter every inference-eligible ctor's equation. Test `inference/infer_field_initializer.cj`.)* **Field initializers do not feed constructor inference.** A clause-free `init` evaluating a throwing initializer errors at the initializer instead of inferring the requirement into every inference-eligible constructor (probed: construction under a matching `try` still rejected) | What is inferred, point 3 | M |
| ~~I34~~ | *(closed 2026-08-31, T4: `DemandForInProtocol()` synthesizes the `iterator()`/`next()` lists at `FOR_IN_EXPR` via `FindNullaryMember`. `forInKind` turned out to be unusable here — CHIR sets it, so it reads INVALID at capability-check time; the subject's own members decide instead. Tests `scopes/forin_protocol.cj` + `_neg.cj`.)* **`for-in` demands nothing.** The pass runs before desugar, the iterator-protocol calls do not exist yet, and no `FOR_IN_EXPR` case synthesizes them — a `throws ()` function iterating a throwing iterator compiles silently at `warn` (probed; at `error` the interface wall masks it). Same shape and fix as the implicit `close()` | What is inferred, point 2 | M |
| I35 | *(OPEN on the pinned compiler; T5 is written but not gated, so the hole below is still live there — the confirmed `error`-level leak. `CapabilityTypeCompleter` finishes the capability component of the expression types naming an inferred declaration (instantiating through `expr.instTys`) and of the bindings they initialize; `CapabilitySubtypeReplay` re-checks the four capability-sensitive positions type check judged while the lists were empty — declared-type binding, assignment, argument, `return` — reporting `sema_chexc_inferred_list_not_admitted`. `DemandInferredOnValue` and both call sites are gone. The probe now fails at the assignment, which is where the text puts it; scope and the deferred round (joins, aggregates, wrappers) are in `inference-completion-design.md`.)* **Inferred lists never reach expression types — and the formation-site reading has a confirmed soundness hole.** `var g: () -> Unit`; inside `try { g = risky }` the formation demand is discharged by the try; `g()` after it demands nothing; **compiles at `error`, uncaught at run time** (probed). Sub-items landable early: (a) `CompleteInferredCapabilityTypes` compares sizes, so `throws Derived, ...` inferring `Base` keeps the stale type — probed, the revealed type still says `Derived`; (b) `DemandInferredOnValue` demands uninstantiated entries — `risky<Int64>` demands `GenExc<Generics-T>` (probed). The full fix is completion + replay of capability-sensitive constraints (review §7.4/7.5) | First-class functions; Phase ordering | L (a, b are S) |
| ~~I36~~ | *(closed 2026-08-31, T3 — and the cause was not where the row guessed. `IsSubtype` has a persistent cache outliving phases; normalization at clause elaboration asked about a `GenericsTy` before its bounds were attached, got `false`, and that answer stood for the whole compilation. `NormalizeCapTys` now never compares a bound-less generic entry, keeping it verbatim. Test `types/where_bound_coverage.cj`; lesson in Part III.)* **`where`-bound coverage is not applied in the open form.** New rule: `E <: IOException` makes `throws (E, IOException)` the list `{IOException}` already before instantiation; probed — `Box` invariance still splits the two | Capability parameters in declarations, rule 2 (revised) | S–M |
| ~~I37~~ | *(closed 2026-08-31, T2: `DemandInjected()` plus a `resumeSupplies` stack pushed for handler bodies and consumed by `RESUME_EXPR` demands alone, so an ordinary `throw` in a handler still sees only the enclosing scopes. Test `performs/resume_throwing_sibling.cj`.)* **`resume throwing` ignores the try's own catches.** New rule 5 resolves against the `try`'s catch clauses AND the enclosing scopes; the text's own positive example errors (probed). Needs a resume-only injection supply, not a general reopening of the try scope to the handler body | Effect requirements, rule 5 (revised) | S–M |
| ~~I38~~ | *(closed 2026-08-31, T2: `parse_performs_clause_after_throws` no longer fires for declarations; functional types keep `performs` first. Test `performs/performs_order_free.cj`, which had to route its `return` through a helper — `return` is not allowed inside a `try/handle` block.)* **Declaration clause order is still fixed.** The revision lets `where`/`performs`/`throws` order freely in declarations (functional types keep `performs` first); the parser still diagnoses `performs` after `throws`, and `performs_order_neg.cj` pins the old rule | Keyword scheme; Capability parameters in declarations | S |
| I39 | **The checked-effects axis is absent.** No `--enable-checked-effects off/warn/error`, no effect severity or `checked-effects` warn group, no effect trust level in metadata, no unchecked-effects boundary (a package without the flag must read as `performs`-empty). Today effect errors ride `--enable-eh` unconditionally — `performs_without_chexc.cj` pins the now-wrong behaviour | Effect requirements, rule 2; Compatibility | L (with S4's split) |
| I40 | **`@AssumePerforms` is absent** (no bare form — no top command type) | Assumption imports (revised) | S–M after I39 |
| I41 | **`unsafeCanPerform` is absent** | The escape hatch; Effect requirements rule 2 | S after I39 |
| ~~I42~~ | *(closed 2026-08-31, T2: `UNSAFE_CAN_THROW`, `std/core/unsafe_can_throw.cj` and every test renamed.)* **The escape hatch bears the rejected name.** The text ruled `unsafeCanThrow` (naming rationale added — `unsafeAssumeHandled` is kind-ambiguous); compiler constant, std.core declaration and tests all say the old name | The escape hatch | S |
| ~~I43~~ | *(closed 2026-08-31, T1: only the first type parameter.)* `FabricatedCapabilities` fabricates for **every** generic parameter of the intrinsic, not only `E` — harmless for the current signature, wrong the moment the twin lands | The escape hatch | S |
| ~~I44~~ | *(closed 2026-08-31, T1.)* The **plural** missing-capability message still prints `Handler<C>`; the singular was renamed to `CanPerform` | Effect requirements | trivial |
| ~~I45~~ | *(closed 2026-08-31, T1: `Sema::IsInferenceEligible(const FuncDecl&)` is now the single definition, exported from `CapabilityCheck.h`; the incremental frontend's copy delegates to it.)* **Inference eligibility exists twice.** The incremental frontend's copy treats any `throwsClause` as authoritative, but `throws ...` / `throws A, ...` stay inference-eligible — a body edit of such a declaration can again leave callers on a stale contract. One shared predicate | Interaction with an explicit `throws`; the I28 fix | S |
| I5 | Diagnostic omits the mode (`CanThrow<E>` not `CanThrow<E> @ local!`) | Capability argument inference | trivial at Modal integration (ruling 3) |
| I7 | CLI takes the level as `--enable-checked-exceptions=warn`; the text spells it as a separate argument. **Deliberate for now**: the bare form is used everywhere and the option table has no "optional separate value" kind | Compatibility - checked and unchecked code | S once the option kinds allow it |

**Audited and conforming** (implicit capability passing, rule by rule, 2026-08-21): the
intrinsic's contravariance and non-denotability; clause placement on functions, instance and
static methods, primary and secondary constructors, interface and extension methods, property
accessors, operators, `main` (and the bans on foreign/`CFunc`/whole-`prop` clauses); entries
including nested parenthesized lists, aliases, `Exception`-bounded type parameters, `throws ()`
as a whole list; requirement sites; all four scope introducers (including wildcard `catch (_)`
as `Exception` and try-with-resources initializers) and all the exclusions — finalizers,
`catch`/`finally` blocks, default parameter values against the callable's own scope,
instance field initializers against every constructor, top-level and static initializers;
innermost-first resolution with no ambiguity error for several suitable entries in one scope;
capabilities-are-not-values; functional-type syntax, subtyping, joins and meets; literal lists
from the expected type only; generics (capability inference after type-argument inference,
capability lists out of type-argument inference); overloading by recursively erased signatures,
for functions, methods and constructors; override and redefinition including statics and
generic substitution; capturing — construction-site obligation, alias entries, `where`-order,
subclass opacity, statics and finalizers excluded from the captures scope, structs, primary-
constructor ban, rejection on interfaces and enums; runtime erasure. Plus, since the fixes of
Part III: several clauses of one kind unioning, the empty-list rules, the finalizer exclusions,
the `...` ban on exported declarations, and the pessimistic reading of cast targets.

**Audited and conforming in sections 5 and 6** (2026-08-21): the unchecked/checked split and the
capability requirement at `throw` (including `Error` staying outside tracking and `catch` of an
unchecked type); the unchecked-entry rule for concrete types, type parameters, and now their
bounds; alias rules — recursive expansion, cycles rejected, nesting and flattening, single-type
aliases, and a tuple not being an exception type (`f<(A, B)>()` is rejected by ordinary
subtyping); which declarations are inferred, now by **effective** visibility; what is inferred
(throws, calls, implicit invocations, default-parameter expressions, field initializers into
every constructor, per-site discharge); the phase order; recursion by least fixpoint with
polymorphic recursion rejected; the explicit-clause interaction — authoritative lists, `...`,
`throws ()` — and the marker's bans; the effect rules of "Effect requirements" except the
diagnostic (I14): no inference, no unchecked commands, no `main` clause, commands in `captures`,
`performs` before `throws`, clause unions, and effects checked wherever handlers are enabled;
assumption imports — package scope, alias expansion, union across imports, bare form, empty form
rejected, participation in inference; and the boundary rules that fall out of functional-type
subtyping.

**Audited and conforming, 2026-08-23 additions** (probed against the revision that added them):
**multiplatform matching** — a platform declaration matches its common one only when the lists
are equal up to normalization (a differing list fails to match; a covered entry, an alias versus
its expansion, and a reordering all match); **mixed-kind `captures`** with checking off — the
command entry is demanded at construction whenever the effect-handler feature is on, and the
type stays capturing; the `captures` entry grammar (nested lists, aliases, `()`); and the
inferred-override re-check that "an inferred override requiring more than the overridden list is
an error" asks for.

## I.2 Deliberate pre-Modal deviations (author rulings; revisit at Modal integration)

| # | Proposal | Implementation | Ruling |
|---|---|---|---|
| A2 | degraded mode includes intra-function escape checks | none — purely lexical checking | 10: no hand-written escape analysis before Modal (now superseded by I4's plan) |
| A3 | captures only in `this @ local!` constructors; body coverage depends on receiver modes | EVERY constructor captures; EVERY method/prop body covered | 11 |
| A4 | primary-constructor ban on capturing classes derives from modes | enforced directly | 12, forward-compatible |
| A5 | spawn safety from Modal's spawn rule | lexical: spawn body starts with an empty capability stack | 5 — **now proposal text** (Lazy computations and `spawn`) |
| A8 | (unstated) | `throws` banned on foreign functions and CFunc types | M2 round; the text could state it |
| A9 | per-package error/warn level recorded in metadata | per-invocation flag + `chexc` warn group | 8; levels arrive with metadata (I.5) |

## I.3 Implementation artifacts not sanctioned by the proposal

- **C15** An assumption import pays for a covariant function value **where the value crosses the
  package boundary**, not where it is finally called. The text puts the assumed list on the type;
  doing that faithfully needs the imported declarations' types rewritten at load time, since
  rewriting an expression's type does not reach the variable or field it flows into. The
  difference is a false positive for a value taken and never called, never a missed obligation.
- **C5 (narrowed by probe, 2026-08-23)** Macro `NodeFormat` has no `ThrowsClause`, but a
  declaration **does** keep its clause through a macro: `parseDecl(input).toTokens()` re-emits it
  and the call site still demands the capability (probed). What is missing is the std.ast *API* —
  a macro cannot read a declaration's clause, nor attach one to a node it builds programmatically.
  Fixing that means the schema, the generated `NodeFormat_generated.cj`, and new `std.ast`
  members, in that order.
- **C6** `CanThrow` does not exist as a type; entries live directly in `FuncTy::capTys`. Working as intended (strongest form of the intrinsic NOTE in "Type of exception capabilities"); revisit only if effects materialization needs a real type.
- **C17** `capTysInert` (the Q10 gate) drops the whole list when both features are off, which is
  right, but the EH-on/chexc-off combination keeps exception entries too: the gate cannot tell the
  kinds apart without a `Command` root in the type manager, beside the `UncheckedException` one it
  now holds. Small and self-contained; nothing observes it today, since effect-only builds are
  rare and exception entries there impose nothing.
- **C16** `FuncTy` printing folds both capability kinds into one `throws (...)` — a command entry
  prints under `throws`, though the syntax of "Functional types" and "Effect requirements" keeps
  `performs` before `throws` as two clauses. Cosmetic until evidence passing, but every diagnostic
  that prints a functional type shows a spelling the parser would reject (review, 2026-08-30).
- **C7/C8** Diagnostics: generic inference failure shows the uninstantiated capability row with no dedicated message; override/clause diagnostics print raw `Class-X` names.
- **C9** LSP/cjd compiler instance no-ops the pass — no IDE diagnostics.
- **C10** `--enable-chexc` alias retained beside the canonical flag.
- **C11** ASTWriter exports generic/inline bodies without clause nodes (silent; no crash observed).
- **C13 — two regressions behind one symptom (found 2026-08-21).** The full-tree run turned up
  826 failures; 126 of them were ours, and they had *two* causes, not one.
  *(a) Token ordinals — fixed.* `THROWS` and `CAPTURES` were added to the experimental block of
  `Tokens.inc`, which sits before the table's last three entries, so `ILLEGAL`, `DOUBLE_COLON`
  and `FEATURES` shifted by +2 (`DOUBLE_COLON` 165 where upstream and every golden say 163).
  Macro token round-trips broke: 4 `Macro/annotation`, 1 `Macro/expr`, 3 `unittest` power-assert
  `invalid_syntax`. Both tokens turned out to be **dead** — the lexer never produced them, since
  the soft keywords are recognized by spelling (`SeeingChexcClause`) — so they were deleted
  outright and the table is now byte-identical to upstream. All 8 cases pass.
  *(b) SDK skew — the 118 remaining.* `API/stdx/syntax` (106) and `API/std/libast` (12) fail
  because `std.ast`'s and `stdx.syntax`'s **native FFI shims** are compiled against the compiler
  headers and were last built on 08-15 and 08-14, while our AST changes moved node layouts
  (`ASTKind.inc` records the sizes: `Annotation` 512→520, `ClassDecl` 840→848, `FuncType`
  488→512, `FuncBody` 448→464) and inserted `THROWS_CLAUSE` before `FUNC_BODY`. The stale shim
  reads the new frontend's nodes at the old offsets and reports "parsing program error". Not a
  code defect: the required rebuild cadence. Fix is to rebuild std and stdx after any change to
  the AST node set or the parser headers.
  **Lesson:** a table whose indices cross an ABI is append-only, and dead entries in it are not
  free; and `compiler/`-only gates cannot see either failure mode — the library suites must run
  whenever the lexer, the AST node set, or the parser headers change.
- **C14** *(closed 2026-08-23: the golden lists `--enable-chexc`, its two severities and the `chexc` warning group; `compiler/Driver/options/help` is 5/5.)*
- **C7 (widened)** Capability diagnostics print `Class-X` for class types — `Cannot find a capability for 'Class-AException' (of type 'CanThrow<Class-AException>')`. Not ours to fix locally: stock `cjc` prints the same form everywhere (`expected 'Int64', found 'Class-A'`), so the model message in "Capability argument inference", which spells the source name, describes a compiler-wide diagnostic style CangJie does not have. Either the message is illustrative, or the type printer changes globally.
- **MF2 half** *(closed 2026-08-30, then RETIRED 2026-08-31 by T5. The formation-site demand was a stopgap for inferred lists, and it was the leak: forming the value inside a discharging `try` paid the list there, and the call afterwards paid nothing. T5 completes the expression type instead, so inferred and declared lists behave alike — the list rides the type, the call pays.)*
- **R6** 118 `GetFunctionTy` call sites do not visibly pass a capability list. Most are capability-free by construction; nothing but an audit separates them from latent drop sites (the reconstruction defect class, Part III).

## I.4 Production-readiness (prototype → shippable)

Ranked; effort S/M/L/XL.

1. **Modal integration — XL, critical path.** See Part II D-0 for the precise shape: the pipeline survives as check-and-cap, the one genuine break is mode-dependent overloading, and the open Modal negotiations (forwarding rule, unwinding, `local?` invocation, `for-in` over `local!`) are listed in the proposal's own "Open questions".
2. **Make the reconstruction defect class unrepresentable — L.** Remove `GetFunctionTy`'s defaulted capability parameter (or introduce a `FuncSig` value) so omission is a compile error; burn down the 118 sites once.
3. **Split the shared `performs`/`throws` list — M–L.** D17 is valid only while both kinds are phantom; evidence passing makes `Handler<C>` a real value (separate list, lowering, schema, ABI).
4. **Inference results beside the AST — M.** `InferredCapabilities` + completed decl types + uncompleted expression types works with one consumer; LSP/CHIR/refactoring need one query API or full completion.
5. **cjo feature gate — M.** An old compiler reading a new cjo silently drops capability metadata. Also unimplemented from "Package metadata": per-package level and ABI epoch, without which the whole-build guarantee is not diagnosable.
6. **Diagnostic provenance — M.** Inference makes requirements non-local; the fixpoint keeps no derivation. Design it into the collecting handler, don't bolt it on.
7. **Performance — unmeasured.** Kleene iteration re-walks bodies per round (quadratic on large SCCs); per-demand scope scans; three whole-package walks that could fuse. Benchmark at stdlib scale before optimizing.
8. **Toolchain integration — L–XL collectively.** LSP quick-fixes off the miss-handler seam; `.cj.d` declaration files; macros (C5); **cjfmt has never seen `throws`/`performs`/`captures`/`@AssumeThrows` and will mangle migrated stdlib**; CJMP common/specific merging untested; Java-interop exception mapping undesigned.
9. **Spec fold-back — S, organizational.** ~35 normative micro-decisions (D1–D18, rulings 1–14, ratified interpretations B1–B7) live only in the notes; the text must absorb them before stabilization.

Ratified interpretations the text should state (B-table, kept here so they survive the ledger's removal): cap-differing FuncTys are distinct interned types but all overload/duplicate/shadow machinery compares modulo caps · after `throws`, `(` always opens the capability list · `catch (_)` supplies `CanThrow<Exception>` · `throws` accepted before and after `where` · declarations accept bare and parenthesised lists, functional types only parenthesised (plus single-type sugar) · join = union with redundancy pruning, meet = entries covered by every operand · polymorphic recursion detected by an occurs check over SCC call-edge substitutions.

## I.5 Stdlib work items

Rulings now in text (Standard library and toolchain impact; Standard library migration):

- **Batch 3a — stream interfaces declare `throws IOException`**, in-memory implementations override narrower. Clears the 6 deliberate fs/io residual warnings. **Blocked by erratum E-4**: `ContentFormatException` is not under `IOException`, so the ruling as written cannot cover std.io's own content errors — needs the author's pick (re-parent recommended).
- **Batch 3b — IO-backed iterators become capturing classes** (StringReader's iterator types capture `ContentFormatException`); construction-site obligations move. Costs documented in D-1.
- **Batch 2 (classified obvious, not yet annotated):** `std.regex` (ruled checked), `std.time`, `std.process`, `std.database.sql`, `std.net` specific socket types, plus `std.convert` and `encoding.*` now named in the text.
- **Shipping policy:** "a module ships either unannotated or `error`-clean; `warn` is a development state" — our `cj.py` warn ratchet is the development state; per-module `error` flips are the target.
- Remove the hand clause on `walkFuncWrapper` once I2 lands.

Stdlib rulings still needed from the author (recommendations inline):
- **Q-STD-1 std.ast** (2,800 warnings, 67% of all): `FlatBuffersException`/`ASTException`/`ParseASTException` → recommend **unchecked** (framework data-integrity), optionally keeping `ParseASTException` checked.
- **Q-STD-2 raw `throw Exception(...)`** (net 242, unittest 192, others): annotating `throws Exception` is uninformative; needs per-package specific types — API design. For std.net the specific types already exist.
- **Q-STD-3 std.reflect** (254): split — lookup failures checked, misuse types unchecked, `ReflectException` stays checked as umbrella; re-parents the hierarchy, so it's a call.
- **Q-STD-4** runtime/env/unittest.common small sets: `MemoryInfo`/`ProfilingInfo` lean checked; `EnvException` inventory-UNCERTAIN; `DataModel`/`Json` in unittest.common → recommend unchecked as framework machinery.
- **Q-STD-9 — the SPI-interface question, which is what the whole migration keeps hitting.**
  Four of the open stdlib items are one question wearing different hats: an interface in `std`
  declares no clause, and its implementations elsewhere throw. `Iterator.next` with
  `ContentFormatException` (E-4), `Resource.close` (E-16), `ToString.toString` in
  `stdx.encoding.json` (Q-STD-8), and now `std.crypto.digest.Digest.write`/`finish`/`reset`,
  whose stdx implementations raise `CryptoException` — a type `std` cannot even name, so the
  interface could not declare it if it wanted to. The same shape blocks `stdx.compress.zlib` (26),
  `stdx.compress.tar` (87), the stream half of `stdx.net.http` (191) and `stdx.net.tls` (32):
  every one of them implements a `std.io` interface.
  **The three coherent answers**, and they have to be chosen once rather than per package:
  (a) each SPI interface declares a std-level checked exception it owns (`IOException` for the
  stream interfaces — that is batch 3a already — and a new `DigestException` for `Digest`), and
  implementations narrow to it, which means every implementation's own exception type has to
  become a subtype of that one; (b) SPI implementations may not raise checked exceptions at all,
  so these become unchecked, which is the answer `@Derive` already got; (c) the interfaces carry
  an inferable clause, which the base design does not have — a declaration's list never depends on
  its implementors.
  **Recommendation:** (a) for the stream and digest interfaces, where failure is the caller's
  business and an owned exception type exists or can be added; (b) for `ToString` and any other
  interface whose method is called from places that cannot handle a failure. What decides it is
  not the checker but the API: can a caller do anything with the failure?
- **Q-STD-8 `ToString.toString` when printing can fail** (raised by the stdx ring, 2026-08-23).
  Six diagnostics in `stdx.encoding.json` are `toString()` implementations that raise
  `JsonException` — and say so in their doc comments — over a `std.core.ToString` that declares
  nothing, so the clause cannot be written where the failure happens. The same shape is waiting in
  `stdx.chir` and `stdx.syntax`, and `@Derive` had it too (fixed at the generator: the derived
  branch now raises an unchecked exception). Either (a) `ToString.toString` stays clause-free and
  an implementation that cannot print raises an **unchecked** exception, or (b) `ToString` declares
  a clause, which every `toString()` call site in the language then pays for.
  **Recommendation: (a).** `toString` is called from diagnostics, logging and interpolation, where
  a checked failure has nowhere to go; and a JSON tree that cannot be printed is a broken
  invariant of the value, not a condition its caller could have avoided. That makes it the same
  ruling as the `@Derive` fallback, and it needs the same kind of change in each implementation.
- **Q-STD-7 unittest acquires 23 fs obligations** from batch 1: recommend catch-and-wrap internally rather than leaking `FSException` into the test framework's API.
- The 23 UNCERTAIN classes of `stdlib-exception-inventory.md`.


**stdx (phase 3), 2026-08-23.** stdx builds at `warn` (`cj.py build stdx` passes the same flags as
std). Its capability surface is hidden in the normal build by `-Woff=all` in stdx's own CMake, so
it has to be swept package by package with the `build.ninja` commands minus that flag. Started at
**1,408 diagnostics over 25 packages**; now **1,371 over 16**. Clean: compress, crypto.common,
net.tls.common, actors, actors.macros, plugin, string_intern, encoding.url, serialization. Down to
one ruling-blocked case each: unittest.data (`Iterator.next`, E-4) and effect (a `tryHandle`
override). Remaining, largest first: syntax 420, chir 229, net.http 191, crypto.keys 111,
crypto.x509 87, compress.tar 87, crypto.digest 78, crypto.crypto 46, net.tls 32, encoding.json 28,
fuzz 27, compress.zlib 26.

Two things learned while annotating, both general: a clause on a leaf **raises** the count in its
dependents before the ring reaches them, so intermediate totals go up; and an interface member's
clause is the one that matters — implementations may narrow it to nothing, so only those that
forward through the interface need to restate it (annotating all of them, as a first pass did in
`serialization`, imposes obligations on call sites that have none).

- **Clause-materializing fixer** (Migrating user code): inference over the whole package including exported declarations, written back as clauses. `CollectingMissHandler` already computes the lists; the new part is source rewriting. **Caveat D-4 applies**: public-surface output is an API-design proposal, not a diff to rubber-stamp.
- **Lints** (TODO section): redundant `throws` entry; undischarged capability (suppressible on public APIs).

## I.7 Extensions (explicitly outside the base design now)

- Exception conversions and automatic adapter generation: `conversions-adapt-plan.md` stays valid content-wise (rules verbatim); priority below everything above. T1.1 there is revised by the new `cause`/`suppressed` spec (set-once `cause`, read-only `suppressed` + `addSuppressed`, printer learns both chains, `(message, cause)` constructor convention).
- Capability-list polymorphism (`spawn<R, throws E>`, `Future<R, throws E = ()>`): roadmap, XL.
- `WrappedUncheckedException` + the handling sugar: roadmap with that extension.

---
- **The unreachable-`catch` diagnostic** moved out of the base design into "The
  unreachable-`catch` diagnostic" (an extension), taking the per-declaration throw-closure
  summary and its metadata rule with it. Was I14; nothing of it is implemented, and nothing in
  the base design now depends on it (the unchecked-boundary lint of the TODO list cites it but is
  itself off-by-default tooling).

# Part II — What the proposal must change

## II.1 Errata (text-level, each verified against the 2026-08-20 17:33 text)

- **E-1** "Stack traces and cause chains" writes `eErr.suppressed += eFrom`; "Standard library and toolchain impact" specifies `suppressed` as a read-only snapshot with `addSuppressed`. Fix to `eErr.addSuppressed(eFrom)`.
- **E-2** Audit tense: the toolchain-impact section says the classification is "confirmed by the annotation audit"; the migration section says "to be confirmed". It is *partially* confirmed (26 re-parents, 90 clauses). And the name marked "to confirm" is confirmed: **`UnsupportedException`**, not `UnsupportedOperationException`.
- **E-3** *(closed by the 2026-08-30 revision: the intrinsic is `unsafeCanThrow` and the toolchain section states outright that without Modal Cangjie the parameter carries no mode.)*
- **E-4 — now concrete.** The interface ruling ("streams declare `throws IOException`; implementations narrow") is inconsistent with `ContentFormatException <: Exception`. The inferred-override re-check found the instance the moment it ran over the stdlib: `std.io.StringReader.next()` — both the `Iterator<Rune>` and the `Iterator<String>` implementation — infers `ContentFormatException` against a clause-free `Iterator.next`, which at `error` level is a hard error and at `warn` a warning the migration cannot burn down. Re-parent under `UncheckedException` (it reports malformed input the reader cannot recover from) or under `IOException` and declare it on the stream interfaces — but decide, because the std build now depends on it.
- **E-5** Two renumberings in one day left internal consistency intact (verified: no stale anchors) but make every external citation rot; consider freezing numbering or publishing stable anchors.
- **E-13** *(closed — the revision states in "Capability capturing" rule 1 that an entry's kind follows its hierarchy and one list may mix kinds.)*
- **E-15** The effect examples use a **`Resumption` binding that the effect-handler implementation does not have**: `handle (_: GetLogger, r: Resumption<Logger>) { resume r with logger }` does not parse (the compiler's form is `handle (_: GetLogger) { resume with logger }`, with no named resumption and no `Resumption` type in `stdx.effect`). The text is entitled to design ahead of the implementation, but "Effect requirements" rules 4 and 6 and the glossary's carrier list treat `Resumption` as a first-class value, and readers of the current compiler will look for it. Say that the named form is prospective, or restate rules 4 and 6 over the implicit resumption.
- **E-16** "Capability scopes" rule 1 says the implicit `close()` of try-with-resources is inside the `try`'s scope, with a "to be confirmed against the language specification". **Probed 2026-08-30: the implementation agrees with the bullet.** A `close()` that throws is caught by the SAME try's `catch` clauses (a resource whose `close` throws `CloseExc`, `try (r = ...) {} catch (e: CloseExc)` — caught, exit 0): the closing `finally` is desugared *inner* to the user's catches, unlike a user-written `finally`, which stays outside the scope. So the reading is right for the compiler as built; what remains is the author blessing it against the language spec and dropping the TODO. The erratum stands only as "the bullet pre-answers its own TODO".
  "exactly as a declaration `throws` clause does", and the entry rule admits exception types
  only; that commands may also be captured reaches the reader solely through the blanket
  substitution at the head of "Effect requirements". One clause in the capturing rule would make
  it findable from where it is implemented.
- **E-20** Effect requirements say requirement checking is "level-independent" — meant as
  "independent of the **exception** level", which the new independent effect axis makes ambiguous.
  Say it explicitly (review finding).
- **E-21** The heading "No unchecked commands" now sits above a rule that introduces
  unchecked-effects packages, `@AssumePerforms` and `unsafeCanPerform`. True as stated — there is
  no unchecked command *hierarchy* — but it reads as "no unchecked escape mechanisms". Reword
  (review finding).
- **E-22** `unsafeCanThrow`'s subsection derives the carrier restriction from the regions section
  but does not state it locally; for an `unsafe` intrinsic the rule ("the callback must not return
  or store a carrier of the fabricated capability") should be visible at the declaration (review
  finding).
- **E-19 — a property in an interface can never declare what its accessors throw.** The rule that
  lists clause-bearing declarations includes property accessors, and the override rule speaks of
  "a method *or property accessor*" — both true wherever an accessor has a **body**. They are
  unreachable for an **abstract** accessor, which is exactly the interface contract. Probed
  2026-08-30, six forms:

  | form | result |
  |---|---|
  | `interface I { prop v: Int64 { get() throws E } }` | parse error — *body of function 'get' is missing* |
  | `interface I { prop v: Int64 throws E }` | parse error — *expected declaration, found 'throws'* |
  | `interface I { prop v: Int64 { get() throws E { … } } }` (default impl) | **accepted** |
  | `open class A { public open prop v: Int64 { get() throws E { … } } }`, override narrows | **accepted** |
  | `interface I { func value(): Int64 throws E }` (the same contract as a **method**) | **accepted** |
  | interface `prop`, implementation's accessor throws | coverage violation, always |

  So the mechanism is `ParsePropMemberDecl`, which requires a body on every accessor, plus
  `AddSetterGetterInProp`, which synthesizes the abstract ones with an empty `FuncBody` and no
  clause — the contract is therefore always `throws ()`. **The asymmetry is the finding:** an
  interface method may declare what it throws, an interface property may not, though the design's
  whole motivation ("an interface definition cannot know about all possible types of exceptions
  that implementations will need to throw") applies identically to both.

  **It bites real code.** `std.net`'s `StreamingSocket.localAddress` and `.remoteAddress` document
  `@throws SocketException`, and `TcpSocket`'s accessors throw exactly that; the interface cannot
  say so, so every such implementation is a permanent coverage violation. (Four more properties in
  the same file document `IllegalArgumentException`, which is unchecked and therefore harmless.)

  **Four ways out, with what each costs:**
  1. **Abstract accessor clauses** — `prop v: Int64 { get() throws E; set(x) throws F }`. Closest
     to what the text already promises, keeps getter and setter independent, and needs the parser
     to accept a bodyless accessor where a bodyless method is accepted. S–M in the compiler; it is
     a language-grammar change, so it is the author's call, not ours.
  2. **A clause on the property** — `prop v: Int64 throws E`, distributed to both accessors.
     Smaller grammar, but loses the getter/setter distinction the text's own example uses.
  3. **Capture instead** — the implementation declares `captures E` and its accessors require
     nothing (probed: accepted). This is precisely what "Capability capturing" was designed for,
     and it works for properties today — but it needs Modal to be sound, and pre-Modal `captures`
     is outside this tier by ruling.
  4. **Accept the restriction** and say so in the text: properties carry clauses only where they
     have bodies; an interface property that can fail is expressed by a method, or by capture.

  **Ruled by the author 2026-08-30: support both (1) and (2)** — a clause on an abstract accessor
  and a clause on the property itself, the latter distributed to the accessors that do not carry
  their own. The design is in `property-clauses-design.md`; the implementation item is I31, and the
  text needs the grammar section to grow both forms.

- **E-18** §5.3.1's macro sentence — "a non-public macro can never be an expansion root and is an
  ordinary inference-eligible declaration" — describes a declaration the language does not have:
  the parser mandates `public` on every macro (*expected 'public' before macro declaration*), so
  the clause is vacuous. Either drop it, or say plainly that every macro is exported and therefore
  never inferred.
- **E-17** The text states the "Capability regions" rules for the **base design**, but the author
  has scoped them to Modal CangJie (2026-08-23). Either the section says so — regions are a Modal
  requirement, not a base-tier one — or the base design keeps rules the base tier will not enforce,
  which is exactly the guarantee gap the state table warns about. The same applies to the two
  region rules that live in "Effect requirements" (resumptions are handler-bound; `resume r with v`
  is an origin-flow boundary).
- **E-14** The state table's Modal-less row reads "partial: carrier escape unverified, within a
  function included". The intended reading — the *unverified* part includes the within-a-function
  case, as the Modal-less section states outright — is the opposite of the one a reader takes on
  first pass ("within a function is included in the guarantee"). Reword.
- **E-6** The rule-by-rule rewrite of "Capability parameters in declarations" dropped the
  unchecked-entry restriction (old rule 5) — it now lives only in "Unchecked exceptions"
  ("Unchecked types in `throws` lists"), and the entry rule (rule 2) does not point at it.
  Likewise rule 4 (several clauses union) does not point at "Interaction with an explicit
  `throws`", where the interactions that actually constrain it live (`...` repeats
  idempotently; `throws () throws A` is an error). Both are implemented and both had to be
  found by reading other sections. Add the two cross-references.

## II.2 Design tensions and disadvantages (with prototype evidence)

### D-0 · Phase ordering and modes — the one that matters

The design recommends `types → modes → capability parameters → capability arguments` and
the prototype implements exactly that. Under Modal a capability-capturing lambda is a
region-bound value and its mode depends on its captures — which is what the post-Sema pass
computes. The author raised the circularity on 2026-08-20.

**What the text already contains (and should make explicit):** path (b) of "Required
extension: try-scoped capability regions" says a capability-capturing literal or instance
"has its mode **capped at `local?`**". Modal's own rules make this the only possible
consequence (no function object is `local!`; capabilities are captured through a `local?`
alias, which the updated Modal draft permits — Open questions, item 2). Capping is binary
and monotone, so the pipeline survives as **check-and-cap**: discover capability-capturing
values, lower them to `local?`, propagate region-boundness through captures/stores, and
re-validate the lowered values' uses (no use after the `try`, no assignment outward). A
third stage, not a fixpoint. `architecture.md` had this right from the first session; the
PR-1735 study confirmed the Modal prototype derives lambda modes from expected types and
validates captures post hoc — and, because modes participate in interning and mangling
there, mode rewriting is structurally impossible: "no mode rewriting" is forced.

**The genuine break:** Modal methods **overload on the receiver-mode specifier**. A cap
arriving after overload resolution can invalidate the overload Sema chose; re-resolving
would silently change which code runs. The sound rule is to **reject** with a
capability-aware diagnostic — a completeness loss the text should state where it
recommends the phase ordering. A (modes, captures) fixpoint is the only way to *accept*
such programs; recommendation: don't.

**What the text should add:** (i) at "Phase ordering": the ordering is sound because
capability capture only ever caps a mode, and overload-by-receiver-mode conflicts are
rejected; (ii) promote the sentence "path (b) is an implementation of path (a)'s
semantics, so materializing capabilities changes the lowering, not which programs
type-check" from mid-paragraph to a stated invariant the exception-safety theorem
references — it is the design's future-proofing contract against evidence passing;
(iii) elevate Open-questions item 3 (the forwarding rule, read literally, rejects every
capability propagation step) from "open question" to "blocking dependency on the Modal
authors".

### D-0b · "Skeletons" underspecified — the review's central architectural point, confirmed

Phase ordering says *type/mode skeletons → capability parameters → clause components of types →
capability arguments*, and adds that no earlier stage consults inferred lists. The prototype read
`SEMA` as a **finished** type checker, and every confirmed inference defect of the 2026-08-30
review — the reference leak, the stale joins, the size-compared completion, the generic reference
demanding `Generics-T` — is one mechanism: an early stage **fixed a result computed while a list
was temporarily empty**, and completion could not reach it. The text never says which type
products must be completed after inference (references, bound methods, inferred variable types,
returns, joins, invariant containers, generated wrappers) nor which constraints must be replayed.
Until it does, every implementation will rediscover the same holes. The implementation side is
I35/S5; the text side is a normative paragraph in Phase ordering enumerating exactly that.

### D-1 · Capturing iterators buy uniformity with three costs
(a) The flagship IO use case — iterating a file's lines — now depends on an *unconfirmed*
Modal requirement (`for-in` over `local!` iterators). (b) The obligation moves to
construction: a mid-iteration failure and a construction failure become indistinguishable
in the discipline, and the `try` must wrap the loop merely to build the iterator (prototype
evidence: every StringReader constructor site, including tests that never iterate, acquires
the obligation). (c) In the degraded mode a captured-`IOException` iterator escaping its
`try` is precisely the phantom hole, on the most common API shape the library ships.

### D-2 · List-variable invariance makes `Future` collections monomorphic
`Array<Future<Unit, E>>` requires every element to carry the same list; heterogeneous futures
cannot share a collection except by `E = Exception`, losing precision. `waitAll` works only
because of that uniformity. State the limitation and the `E = Exception` idiom.

### D-3 · Two "assume" constructs with opposite safety polarity
`@AssumeThrows` *adds* obligations (errs safe); `unsafeAssumeHandled` *removes* them (errs
unsafe). A terminology note contrasting them, cross-linked both ways, closes a real hazard
cheaply.

### D-4 · The fixer will materialize the disease the introduction diagnoses
The introduction criticizes Java for "polluting interfaces with implementation-specific
exception types"; the fixer mechanically writes inferred lists onto exported declarations.
Prototype evidence: mechanical inference yields `FSException` on a test framework's API and
raw `Exception` on std.net — true lists, wrong APIs. "Migrating user code" needs the caveat
that public-surface output requires API review; abstraction boundaries are exactly where
conversions were supposed to help, and they are now an extension.

### D-5 · The escape hatch is all-or-one
Single `E` per call; several specific types need nesting or the coarse `E = Exception`. A
tuple form, consistent with capability list aliases, would cost little.

### D-6 · *(resolved by the revision: assumption imports are package-scoped)*

The tension was that per-file syntax fed a package-unit analysis with per-file claims. The revised
text rules the annotation package-scoped ("applies to every call into the dependency from the
whole consuming package, whether or not the calling file repeats it"), and the implementation
follows; D15's per-file half is superseded.

### D-8 · The `spawn`/lazy restriction is heavier than its placement suggests

Without capability-list polymorphism, `spawn` cannot release checked exceptions, a lazy iterator
must be consumed inside its handler region, and deferred computations are checked at construction
rather than execution. "Known limitations" states this honestly, but both external reviews
independently concluded the same thing: for a language with first-class concurrency the
restriction is severe, and "Capability-list polymorphism" is practically a prerequisite for any
real async API, not an optional convenience. The text should say which of the two it is.

### D-7 · The base design keeps the boilerplate it calls "very common"
With conversions demoted, handle-convert-rethrow at every abstraction boundary is manual in
v1. A defensible trade (elaboration out of checking) — but state it as an accepted v1 cost
in "Forcing a decision nobody can make" or "Migrating user code".

**Cross-proposal obligation (from the review's Modal analysis, recorded, out of tier):** the
capability-blind treatment of a literal's mode — Modal computes modes from ordinary captures only,
capability captures arrive later and only cap — contradicts Modal's own "a lambda's mode is
determined by its captures" as written. When Modal integration starts, this must land as an
explicit amendment to the Modal proposal, not remain an internal assumption of this one.

## II.3 Open readings to rule (each implemented conservatively; widening is backward-compatible)

| # | Question | Implemented | Reversal cost |
|---|---|---|---|
| Q5 | Do conversions apply to `throw` expressions or calls only? | planned uniform | moot for v1 (conversions are an extension) |
| Q6 | Misplaced `@AssumeThrows` — error or ignored? | error | ratified (D15); flagging only |
| Q12 | `resume throwing e` "resolves in the handler body's enclosing capability scopes". A `handle` body, like a `catch` body, is outside its own `try`'s scope — so the requirement cannot be met by the `try` whose command the handler serves, even when that `try` also catches `E`. Intended (the text calls it the conservative choice), but it means the common shape "perform, handler translates failure into an exception the same `try` catches" needs an outer handler. Confirm, or adopt the refinement the text mentions | implemented conservatively (I24, batch A): resolves in the handler body's enclosing scopes | S either way |
| Q9 | *(answered by the revision: "Reflection and runtime casts" rule 2 accepts a parameter-typed target outright and classifies such casts as an unchecked boundary, outside the guarantee — exactly the implemented behavior)* | accepted | none — text and prototype agree |

## II.4 Upstream compiler defects found on the way (not ours; worked around)

- **U1** `IsLegalAccess` dereferences `node.curFile->curPackage` guarded only by a
  `CJC_ASSERT` that compiles out in release, while guarding the same pointer correctly ten
  lines either side; any node reaching type-legality checking without a file is a
  location-less ICE. Worked around (`AddCurFile` walks import annotations); the deref is
  untouched.

---

# Part III — Resolved, kept for the lessons

- **T1–T4 landed (2026-08-31): the decision-free queue up to inference completion.** Ten
  ledger rows closed (I32–I34, I36–I38, I42–I45); I35, the confirmed soundness leak, is what T5
  is for and is still open. Two findings outlived their batches:

  **A persistent cache turns a question asked too early into a permanent wrong answer.** I36 was
  filed as "`where`-bounds are not applied in the open form" and read like a normalization-ordering
  bug. It was neither: `IsSubtype` caches across phases, my own earlier round had normalization
  running at clause elaboration, and asking there about a `GenericsTy` whose bounds are not yet
  attached returns `false` — which is then cached for the whole compilation, including for every
  later site where the bound *is* known. The fix is not to order the phases but to never ask:
  `NormalizeCapTys` keeps a bound-less generic entry verbatim instead of comparing it.
  **Lesson:** with a cache that outlives phases, "ask early and re-ask later" is not available;
  every query against a structure that is still being built has to be suppressed, not repeated.

  **A stopgap that discharges an obligation somewhere plausible hides that it is discharged
  nowhere.** The formation-site demand (MF2) made references to inferred declarations pay their
  list where the value was formed. That is a defensible reading in isolation, and it passed its
  own tests — but `try { g = risky }` discharged the list at the assignment and left the later
  `g()` demanding nothing. The two readings differ only when formation and call sit in different
  scopes, which is exactly the interesting case. **Lesson:** when a value carries an obligation,
  the obligation belongs to its type, not to a site; any rule of the form "it is paid *here*"
  should be read as a claim that needs a test where *here* and the use are deliberately separated.

- **The chapter-5 review analyzed (2026-08-30 evening): twelve claims, twelve confirmed.** The
  reviewer worked against the same-day text revision, which is ahead of the implementation by one
  round: the effects axis (`--enable-checked-effects`, `@AssumePerforms`, `unsafeCanPerform`), the
  `unsafeCanThrow` rename, free declaration clause order, the sibling-catch rule for `resume
  throwing`, and `where`-bounds in the semantic form are all new text. Probed and confirmed as
  implementation defects regardless of revision: the generic-`Error` demand, field initializers
  outside inference, `for-in` demanding nothing, the **formation-site soundness hole** (a value
  formed under a discharging `try` and called after it — compiles at `error`, leaks at run time),
  uninstantiated entries at reference sites, the size-compared completion, and the open-form
  `where`-bound coverage. Code-read and confirmed: the plural `Handler<`, fabricate-all-params,
  the duplicated eligibility predicate with the `...` gap, the fixed clause order. The review's
  phase-ordering critique is accepted as D-0b: our own R-round fixes (formation-site demand, the
  side-map union in `HandleCall`, the late override recheck, the incremental rollback) are four
  patches over one missing mechanism — completion of capability components in expression types.
  Its Modal chapter is out of tier by standing ruling; one obligation from it is recorded above as
  a cross-proposal note. **Lesson:** the reviewer graded the same code B against the old text and
  C+ against the new one in the same document — a moving spec makes "conformance" a two-argument
  predicate, and the ledger's state line must always say which revision it is measured against.

- **R5: the review's tails (2026-08-30).** The meet had never been tested — the join was, and the
  contravariant half rode along untested for months; both of the text's examples are tests now,
  plus the comparable case where the meet keeps the narrower entry. Erasure had the opposite
  problem: it was *argued* (capability lists sit outside `typeArgs`, so CHIR and codegen never see
  them) and believed, but nothing checked it. Compiling one package twice — with every clause and
  with none — and diffing the symbol tables gives **130 symbols, zero difference**, which is now a
  test rather than an argument. And the checker's header comment still described a pass that
  ignored `handle` clauses: the reviewer read it and took it for the design, which is the cost of a
  stale comment stated exactly.

- **I28 closed by deciding where the machinery already decides (2026-08-30).** The hash cannot
  carry an inferred list — it is computed at `AST_DIFF`, before the inference that derives it — and
  the attempt to make it carry one anyway cost 185 upstream failures, because it changed the
  recompilation set of every build whether or not the feature was on. The fix that works is at the
  scope-analysis result and **gated on the feature**: if any declaration scheduled for
  recompilation is inference-eligible, the round rolls back to a full package compilation. Builds
  without the flag keep their sets exactly (1,944/1,944 confirms), and the reproducer that could
  not be committed as a test in August is a test now.
  **Lesson:** the second attempt succeeded not because it was cleverer but because it asked *who
  already owns this decision* — the incremental machinery has a rollback verdict, and the feature
  only had to raise it. The first attempt tried to teach the hash something the hash cannot know.

- **R3: the semantic form reached identity (2026-08-30).** Normalization moved to the four
  boundaries where a list is *produced* — clause elaboration for declarations and for functional
  type nodes, generic substitution, the inferred write-back — plus the `.cjo` loader, so nothing
  downstream had to learn the rule: identity, subtyping, invariance, joins, printing and metadata
  all follow from one canonical value. Interning stays untouched, which is the whole lesson of the
  reverted 2026-08-22 attempt: coverage needs `IsSubtype`, and `IsSubtype` inside type formation
  re-enters it. `NormalizeCapTys` also drops a concrete unchecked entry, so §5.1.2 reaches identity
  too — `safeThrow<Unchecked>` and the clause-free shape are one type now, not merely assignable.
  One regression appeared and is worth remembering: **making lists legitimately empty broke a
  defence-in-depth path.** `HandleCall` re-derives the callee's declared list when the call's type
  carries none — written for types rebuilt by machinery that predates the feature. With
  normalization, "carries none" became a legitimate state, so the fallback fired and demanded the
  *uninstantiated* `CanThrow<E>` for a call that had pinned `E` to an unchecked type. The fallback
  now applies the call's own mapping and normalizes. **Lesson:** a defensive path keyed on "this
  looks empty, something must have been lost" becomes a bug the moment empty becomes a real answer.

- **R1 + R2 landed (2026-08-30): three rulings and the try-with-resources hole.** Q11's
  restoration turned on reading the solver before writing anything: the language reports *unable to
  infer* only for a variable with **no constraints at all**, while a `where T <: Exception` bound
  seeds the constraint set and the variable is then **solved at its bound**. So `g(0, f)` compiling
  was ordinary language behaviour, not a capability anomaly — and the ruled rejection had to be a
  dedicated post-resolution check rather than a solver change, which would have altered ordinary
  `where`-bounded code and, worse, which overload wins. Two implementation traps on the way, both
  caught by the tests rather than by reasoning: consulting the solved `instTys` made the check
  never fire (they are exactly the silent choice being rejected — only author-written arguments
  count), and reporting per parameter showed one of two (the position+severity dedup again, now
  encountered for the third time — batching per site is becoming the house pattern).
  Q10 landed as a single gate at `GetFunctionTy`: with both features off the list is dropped where
  every `FuncTy` is built, so identity, subtyping, overloading, joins and the `.cjo` follow without
  each of them being taught the rule. Q8's residue — the implicit `close()` demanded nothing
  because the pass runs before desugar — is closed by synthesizing the demand per resource inside
  the try's own scope, which the 2026-08-30 probe had already shown is where the closing lands.
  **Lesson:** "does the language already do X in the general case?" is worth ten minutes in the
  solver before touching it — the answer reframed the fix from *change inference* to *add a check
  beside it*, and that is the difference between a two-file change and a regression in every
  generic call in the language.

- **I29 closed by reading the language, not by code (2026-08-30).** §3.2 rule 5 says macros called
  from other macros behave as ordinary functions. Probing showed the premise does not exist in the
  form the rule seems to describe: a macro cannot be *called* by name at all — `Risky(input)`
  inside another macro body is *undeclared identifier*. Macro composition exists only as `@Inner`
  inside a `quote`, i.e. a nested expansion evaluated by the compiler when the consuming package is
  built. So there is no static call edge to check: each macro body is checked against its own
  clause where it is compiled (already done), and the expansion root is the compiler's contract
  (already done). The rule is satisfied vacuously in the prototype, and the clarified text now says
  "within a macro package", which is the same reading. Side finding: E-18, §5.3.1's non-public
  macro sentence is about a declaration the parser forbids.

- **External review analyzed (2026-08-30), four defects confirmed by probe, four fixed the same
  day.** An independent review of `58985730`/`7c1c12c06d`/`0a1ec17`/`4eb1cd8` landed. Its
  escape-analysis findings (`captures` pre-Modal, `resume with` flow, regions, the closed-build
  verifier) are out of this tier's scope by the author's ruling and were set aside; of the rest,
  every claim was probed before being believed. Confirmed and **fixed**:
  - **The inferred-list leak through function values — the review's P0, and real.** `let w: () ->
    Unit = risky` with an inferred-throwing `risky` compiled at `error` and leaked at run time:
    reference expressions are typed before inference, so the completed declaration type never
    reaches them, and `HandleCall` unioned the side map for calls only. Fixed at the formation
    site: a reference that turns an inferred declaration into a value demands the inferred list
    there (`DemandInferredOnValue`), references are call-graph edges as §5.3.4 requires, and the
    collecting pass picks the demand up so a function that only *references* a thrower infers the
    requirement itself. Formation-site payment is stricter than the text's type-riding reading —
    recorded beside C15, which made the same trade for assumption imports.
  - **A covered entry was still demanded.** `throws Base, Derived` demanded both at the call site;
    the semantic form says the list is `{Base}`. Call-site demands now pass through
    `NormalizeCapTys`.
  - **An entry instantiated to an unchecked type did not vanish from the type.** `safeThrow<ReqExc>`
    was not assignable to the clause-free shape, though §5.1.2 says the instantiated clause *is*
    clause-free. Coverage now treats an unchecked sub-entry as trivially satisfied (the type
    manager learns the `UncheckedException` root at type-check preparation); the entry still
    prints in the type and still splits identity in invariant positions — the residue below.
  - **Effect capabilities were named `Handler<C>`;** §5.4 defines `CanPerform<C>`. Renamed.
  Confirmed and **recorded, not fixed**:
  - **Semantic form is observable in invariant positions** — `Box<() throws (Base, Derived) ->
    Unit>` and `Box<() throws Base -> Unit>` are two types where the text says one. The notes
    previously claimed nothing observes the identity difference; the review found the observer.
    The fix is canonicalization at construction, which was tried and reverted (17 breakages —
    subtype queries during type formation); it needs the `CapList` design, not another attempt at
    interning time. Upgraded from artifact to I30.
  Already in the ledger, confirmed by the review independently: I28 (incremental inferred lists,
  with the review agreeing the 1,944 green tests cannot see it), Q10/I18 (checking-off semantics
  must be normatively chosen), I20/Q11 (the generics example), I29 (nested macros), Q8/E-16
  (try-with-resources), C9 (LSP/cjd skips the pass), the `GetFunctionTy` defaulted parameter, and
  the stdlib/tooling state. **Lesson:** the reviewer found the observer for a difference we had
  declared unobservable, and the leak sat exactly where the notes already pointed (MF2-half) —
  a recorded "half" defect is a defect, and "nothing observes it" is a claim that expires.

- **Re-read of §3, §5 and §6 against the prototype (2026-08-23, evening).** The text had moved
  again — macros are now listed among the declarations that may carry a clause (§3.2 rule 1), with
  their own rule 5, and §5.4 rule 3 states outright that a macro may not carry `performs`, which
  answers Q13 in favour of what was implemented. Four rules were probed rather than assumed, and
  three of them already held: an entry whose type instantiates to an unchecked exception **vanishes**
  (§5.1.2 — `generic<MyUnchecked>()` requires nothing); the join of two functional types **unions**
  their capability lists (§3.4.3 — `if (c) { g } else { h }` types as `() throws (B, A) -> Unit`);
  and a `public` macro is **never inferred**, so a clause-free macro body that throws is an error
  (§5.3.1). Two did not, and are fixed:
  - **The assumption rule was too narrow.** §6.3.2 rejects `@AssumeThrows` on a package that
    *records* clauses of its own, and §6.1 says a `warn` package records **trusted** lists. The
    implementation only rejected packages verified at `error` — a distinction I had reasoned my way
    into a day earlier and the text does not make. Widened, and the `warn` test inverted to expect
    the rejection.
  - **The warning group had the wrong name.** §6.1 names it `checked-exceptions`
    (`-Woff checked-exceptions`); it was `chexc`, the flag's alias. Renamed, help golden with it.
  One more thing the probes turned up, which is neither the text's fault nor a rule: **the
  compiler's diagnostic set deduplicates by position and severity alone**
  (`equalFunc` in `DiagnosticEngine.h`), so a call site missing three capabilities reported one,
  and the next only after that one was fixed. The reporting handler now batches misses per site and
  emits one diagnostic naming all of them; a site missing exactly one keeps the singular message,
  which is what every existing test asserts.
  **Lesson:** three of five suspected gaps were not gaps. Probing each rule with six lines of
  CangJie costs a minute and is the only thing that separates "the text says X and I believe we do
  X" from knowing — and the two real gaps were both places where I had reasoned past the text
  rather than read it.

- **I28 attempted and reverted: coarse spreading is not affordable.** An incremental build hashes
  each declaration into a signature hash (which spreads to dependents) and a body hash (which does
  not). Inference breaks that split: for a declaration with no `throws` clause that does not leave
  the module, the list every caller must satisfy comes from the body, so a body edit *is* a
  signature change. Folding the body hash into `SigHash` for exactly those declarations fixes the
  hole — the probe's silent incremental build starts reporting — and costs **185 failures in
  `compiler/IncrementalCompilation`**, which asserts precisely which declarations a given edit
  recompiles. That price is not payable: those tests encode the upstream contract of the feature.
  Reverted. What the attempt establishes is that the fix cannot live in the hash alone, because the
  hash is computed at `AST_DIFF`, *before* Sema, and the new inferred list is not known until
  after. A sound design has to close the loop: persist each package's inferred lists in the
  incremental cache, and after inference compare them against the cached ones — when one has
  changed, its dependents have been checked against a stale contract and the package needs
  another pass. Nothing cheaper is sound, because the change also propagates through calls: a
  caller whose own body did not change can still acquire a different inferred list.
  **Lesson:** a feature that derives part of a signature from a body cannot be bolted onto a
  hash-based invalidation scheme; the invalidation has to run where the derivation runs.
  The reproducer, kept here because it cannot be kept as a test while the hole is open (a test
  that passes only against the reverted fix would encode the bug):

  ```cangjie
  // build 1, then replace the body of 'risky' with 'throw IncrExc()' and build again
  package p
  class IncrExc <: Exception {}
  func risky(): Unit { () }                 // no clause: the list is inferred from this body
  public func caller(): Unit throws () { risky() }   // untouched, and must be re-checked
  main(): Int64 { caller(); return 0 }
  ```

  Both builds with `--incremental-compile --enable-checked-exceptions`: the second must report
  *Cannot find a capability for 'Class-IncrExc'*, as a full build of the same source does.

- **The 2026-08-23 evening round: macros, package metadata, assumption reach, and two fixes in
  std.deriving.** The author ruled that a macro may declare what it throws, and that capability
  regions belong to Modal CangJie rather than this tier (I4 stays recorded as a divergence, E-17).
  With the ruling in hand: `ParseMacroBody` takes a clause, `performs` is refused there because a
  macro body runs inside the compiler where no handler can be installed (Q13), and the 789-case
  macro suite stayed green. The `.cjo` now records what a package's lists are worth — the level
  checking ran at, whether effect handlers were on, and whether it carries capability metadata at
  all, which the first two cannot express for a file written before the feature. Two rules follow:
  an assumption over a package **verified at `error`** is a contradiction and is rejected, while
  one over a package built at `warn` stays legal because those lists are knowingly incomplete —
  that distinction is what keeps assumptions usable during the migration. And an assumption now
  reaches the function values a dependency hands out, not only the calls that resolve into it.
  **Lesson (test validity, again).** The first version of the covariant test passed against the
  unfixed compiler: all three of its assertions were the same message, and the boundary call alone
  produced it. Asserting the two *locations* that previously produced nothing is what made the test
  discriminate — a `scan` for a message says nothing about which site raised it.
  **Lesson (generated code).** Two capability diagnostics in stdx had no possible fix at the site
  they pointed at, because the code was generated: `@Derive` on a non-exhaustive enum emits
  `case _ => throw Exception("Should never happen")` into `toString` and `hashCode`, interface
  implementations that declare no clause. The fix belongs in the generator, and it is a
  classification question rather than a checking one — reaching that branch is a broken invariant,
  so it throws `IllegalStateException`, which is unchecked. Any macro that generates a `throw` into
  someone else's package has the same obligation: either the exception is unchecked, or the
  generated declaration carries its own clause (which is now possible for macros too).

- **stdx at `warn`, and the ICE it uncovered.** Building stdx with checking on died with an
  internal error — *begin of range is zero* — in `stdx.net.http`. A property accessor declared
  without a body (in an interface, or a field-like property) is generated by the compiler: it has
  no position and its identifier is synthesized (`$valueget`). Both override-coverage checks
  attached their diagnostic to it, and a zero range is an assertion failure in the diagnostic
  engine. They now resolve what to blame first — the property for an accessor, the enclosing
  declaration failing that, nothing if neither is in source — and name the property. The same
  applies to any declaration rebuilt from a `.cjo`, which has no position either.
  With that fixed, stdx builds green at `warn`. Its surface, which `-Woff=all` in stdx's own build
  hides, is **1,386 capability diagnostics across 25 packages** — 1,304 missing capabilities and 82
  override-coverage violations; the largest are `stdx.syntax` (420), `stdx.chir` (226) and
  `stdx.net.http` (170). Six leaf packages are now annotated and report nothing at all.
  **Lesson:** annotation propagates, so the surface grows before it shrinks — annotating the six
  leaves moved requirements outward and took the total to 1,401. A migration ring has to be
  completed package by package, dependents included, or it looks like a regression at every
  intermediate step. Two things the migration cannot express at all became I26 and I27: a `macro`
  declaration cannot carry a clause, and `@Derive`-generated members demand capabilities at a line
  where no clause can be written.
- **Incremental compilation and inferred lists (I28).** Declared clauses survive the cache in both
  directions — four tests pin that. Inference does not: a body edit that changes an inferred list
  leaves unchanged callers in the same package served from the cache, so the incremental build is
  silent where the full build reports the missing capability. Only non-exported declarations are
  inferred, which bounds the damage to one package but does not remove it: inside a package, a
  body is part of the API surface once inference exists, and the hashing does not know that.
  **Lesson:** every feature that derives a signature from a body has to be handed to the
  incremental machinery explicitly; the hash is a contract about what a change can affect, and
  inference silently widened it.

- **The `warn`-level link failure, and the rule it taught.** The first std build to get past
  compilation at `warn` failed at *link*, with ~116 undefined references to erased interface
  members (`_CNaf14PlatformSocketIG_E5write…`, `_CNby12SerializableIG_E11deserialize…`). The cause
  was `TypeManager::IsFuncTySubType`, which M2 had made capability-aware: that predicate is not a
  subtype test in the ordinary sense but the one that **pairs** a declaration with the one it
  implements — for generic instantiation (`OverrideFunctionResolver`, and through it
  `FindImplFuncForAbstractFunc`), for the override map, for the common type of a mocked parameter.
  With coverage folded into pairing, an override that violates coverage stops being *recognized as
  an override at all*: at `error` level the program is rejected before that matters, but at `warn`
  it is accepted, the call through the type parameter stays on the abstract interface member, and
  the abstract member has no body to link against. std.net is where it bit, because it deliberately
  routes calls through an F-bounded type parameter (`interface PlatformSocket<Self> where Self <:
  PlatformSocket<Self>`, "we abuse generic instantiation to avoid virtual invocations") and its
  implementations infer `SocketException` over clause-free interface members. The predicate is now
  blind to capability lists, with the reasoning in place: two functions never differ in list alone,
  since a list takes no part in overload resolution, so pairing is a question about shape, and
  coverage is a separate rule reported by the override checks. Pinned by
  `scopes/warn_override_resolution.cj`, which runs the program rather than only compiling it.
  **Lesson (two).** First, the reconstruction defect class has a mirror image: as dangerous as
  logic that *cannot see* capability lists is logic that suddenly *can* — every existing
  `IsSubtype`-shaped call site had to be asked whether it is testing subtyping or matching
  declarations. Second, a diagnostic level is not a display setting: downgrading an error to a
  warning means later stages must survive the very state the error existed to prevent, and here
  three days of "reproduces with checking off" pointed away from it, because a stale `std.net.a`
  in the incremental tree made the flag look irrelevant. Rebuilding one package directly from its
  `build.ninja` command turned a 25-minute experiment into a one-minute one and settled it.

- **Review of 2026-08-23 — sections 3, 5, 6 re-read, the prototype probed, the plan reset.**
  The text had moved again (cast rules by level, capturing-type cast targets, `resume` as a
  requirement and a flow site, the diagnostic out to an extension, multiplatform matching, a
  glossary). Probing found two of the new rules already satisfied — multiplatform matching, which
  the coverage-based comparison gives for free, and mixed-kind `captures` with checking off — and
  five not (I21–I25, all small). The escape hatch (I1) was mid-flight when the review started and
  stays in the working tree: compiler side built, std declaration and tests written, std rebuild
  pending. Its first std build failed for a reason worth keeping: the new inferred-override
  re-check fired as an *error* inside a `warn`-level build — the check had no `warn` variant — and
  what it flagged was real: `StringReader.next()` infers `ContentFormatException` over a
  clause-free `Iterator.next`. That is E-4 made concrete, and it needs a ruling before the std
  build is green at `error` again. **Lesson:** every new diagnostic the capability pass gains must
  be born with the level split, because the std build runs at `warn` and will be the first thing
  to hit it.
- **I3 and I13 closed together, by the re-check they were both waiting on.** An override's list is
  compared against the overridden declaration's during type check — which runs before inference, so
  a list a declaration only *acquires* by inference was never compared at all. That is why two
  narrowings existed: non-private static members required an explicit clause, and eligibility used
  the declaration's own modifier rather than effective visibility. The pairs are now recorded where
  the inheritance checker already has them and consumed after inference, so an inferred override
  requiring more than what it overrides is an error — and both narrowings could go. Static members
  are ordinary members again, and a `public` method of an `internal` class is inferred, as is a
  `private init` of a `public` class.
  **Lesson:** two "temporary" narrowings, months apart in the notes, turned out to be one missing
  check. Recording *why* a narrowing exists is what made them collapse into a single fix.
- **I2 closed: local functions infer.** A local function declaration is now an ordinary
  inference-eligible declaration with a capability list of its own — collected from every body
  (including bodies of declarations that are not themselves eligible, which is where the first
  attempt failed: a local function inside a function with an explicit clause was never collected),
  and checked against its own list rather than the scopes it is nested in. That replaces the
  purely lexical treatment the pre-Modal ruling had settled for (A2's neighbour): a requirement
  inside a local function is the local function's, and its call sites pay for it — so calling it
  outside the `try` that encloses its declaration is now an error rather than silently discharged.
  The isolation reuses the `spawn` shape: swap the supply stack for the body, restore after.
- **Semantic form: already satisfied, and the one place it is not is unobservable.** The revision
  made the canonical ("semantic") form of a capability list normative: a duplicate, or an entry
  covered by a more general entry of the same list, is not part of the list, and every rule that
  compares or consumes lists works on that form. The prototype turned out to satisfy it already,
  because every comparison is coverage-based (`IsCapTysSubsumed`) rather than element-wise: a test
  that spells duplicate and covered entries, assigns between coverage-equivalent spellings in both
  directions, and overrides against a redundant list passes unchanged. The one residual difference
  is type *identity* -- `() throws (A, B) -> R` and `() throws A -> R` intern as two types when B is
  covered by A -- and normalizing at interning was tried and reverted: running subtype queries while
  types are being formed broke 17 cases across generics, serialization and lambda checking. Nothing
  observes the difference (assignment works both ways by subtyping, overload resolution erases
  lists, the `.cjo` normalizes), so it stays as an artifact rather than a gap. The normalizer that
  the serializer had is now shared with the type manager.
- **I19 closed, and what it was.** A capability list mentioning a type parameter was never
  substituted at a call site, so every generic higher-order API with a clause was unusable
  (`handling<A>(thrower)` against `func handling<E>(fn: () throws E -> Unit)` reported *expected
  `() throws (Generics-Ti-1) -> Unit`*). The cause was one line in the substitution machinery:
  `FilterUnusedMapping` decides which mappings are still needed with `Ty::GetGenericTyArgs`, which
  walks `typeArgs` — and a capability list sits outside `typeArgs` by design, so a parameter
  reachable only through one looked unused, its mapping was dropped, and the raw placeholder
  survived into the checked type. Both overloads of the filter now use a walk that looks past
  `typeArgs`; `Ty::GetGenericTyArgs` itself stays as it was, because it also feeds type-argument
  inference, which must keep ignoring capability lists. That distinction cost a build: making the
  AST-level walk capability-aware fixed the substitution and broke the no-inference rule in the
  same step. Comparing lists also had to stop binding placeholders, which subtyping was happy to do.
  **Lesson:** the same question — "which type parameters does this type use?" — has two different
  right answers here, and the reconstruction defect class keeps producing them: capability lists are
  invisible to anything that reasons over `typeArgs`, which is most of the type machinery.
- **The 2026-08-22 round — the text moved, the prototype followed.** Three rules the prototype had
  implemented from earlier drafts were reversed by the revision, and one new rule arrived; all four
  are now in. *One clause per kind*: several `throws`/`captures` clauses no longer union — a second
  is an error, like a second `where`, and with it went the `throws () throws A` error and the
  `...` repeat rule (the macro argument for multiplicity does not survive: locating a clause to
  append to is the same work as merging into it, and merging preserves the list's inference
  status). *Casts*: a target containing a function type is now rejected in **any** position; the
  polarity-based pessimistic reading we shipped the day before is an extension, and its code moves
  there. *Capturing subclasses*: every subclass of a capturing class is itself capturing and must
  cover the superclass's list — the opposite of the rule we had implemented and pinned with a
  negative test, which is rewritten. *New*: `captures ()` (or a list that expands to nothing) means
  not capturing, and a capturing type has no implicit default constructor.
  The author also answered the two questions this round raised: a subclass cannot discharge the
  superclass's requirement locally — `super` must be a constructor's first expression, and even
  spelled otherwise the instance would be bound to a handler that dies with the constructor — and
  the property/accessor clause-overload sentence was withdrawn.
  **Lesson:** when the text is moving daily, "implemented" is not a resting state; the audit has to
  re-read the section it just conformed to. Two of the four reversals cost less to undo than they
  cost to write, because the tests named the rule rather than the behaviour.
- **The 2026-08-21 audit round, sections 5 and 6.** Seven more gaps found by probing and fixed
  the same day: the clause grammar is now unconditional (the flag decides what clauses *mean*,
  not whether they parse); effect requirements are checked wherever the effect-handler feature is
  enabled, at every exception level and always as errors, while exception requirements stay off
  when checking is off; a `captures` clause may name commands; a type parameter whose own bound is
  unchecked is rejected in a clause, since every instantiation of it would be; assumption imports
  are package-scoped, not file-scoped; `@AssumeThrows[]` is rejected with a message of its own;
  the `...` marker is rejected on a `performs` clause; and inference eligibility now uses
  **effective** visibility, so a `public` method of an `internal` class is inferred (I13, closed).
  The author's own answers landed in the same window: assumption scope (package), the empty
  assumption list (rejected), assumptions reaching function values in covariant positions (they
  do — now I16), and subpackage coverage (a separate import, which is what we implemented).
  **Lesson:** three of the seven were invisible in our own tests because the tests only ever ran
  the feature with its flag on and with exceptions in the picture — the axes a feature does *not*
  vary in its test matrix are where its conformance gaps hide.
  Two things did **not** land. Effective visibility was implemented and then reverted: with it, an
  `internal` class's `public` override became inference-eligible, and the prototype has no
  post-inference re-check of an inferred override against the declaration it overrides, so a
  standing negative test stopped reporting — the same machinery the static-member rule waits on
  (I3), now blocking I13 too. And checking effects on their own axis exposed I19, which is why one
  upstream effects test now fails; the annotation that would fix it does not compile yet.
- **The 2026-08-21 audit round, both halves.** The implicit-capability-passing section was
  audited rule by rule against the prototype (34 probe programs, not by reading). Five
  implementation gaps found and fixed the same day: several `throws`/`captures` clauses of one
  declaration now union instead of being rejected as duplicates (with `throws () throws A`
  refused and `...` idempotent across clauses); finalizers reject a clause and are no longer
  inference-eligible, which had let a finalizer silently acquire a list and call
  checked-throwing code; runtime casts and type patterns stopped handing back a
  clause-free function for `x as (() -> Unit)` -- first by reading the target pessimistically, and,
  once the base design was narrowed to rejection, by rejecting it; `...` is refused on exported declarations; `()` mixed with other
  entries gets a dedicated diagnostic instead of "expected '->'". In the other direction the
  author took four of the reported proposal defects: "variable initializers" became variable
  declarations, `throws ()` gained the note that it means the empty list everywhere and only
  omission varies, the captures scope is now stated to enclose a member's own clause scope
  (which is what the prototype already did), and the cast rule was rewritten by position —
  covariant positions receive `throws Exception`, contravariant ones keep the empty list,
  parameters flip the polarity, tuples keep it, and a cast now explicitly preserves a
  carrier's origin set. The polarity rewrite arrived while the first version was being
  implemented; the implementation follows the final text. Package-metadata normalization was
  answered by making it explicitly implementation design.
  **Lesson:** probing beats reading — three of the five gaps (finalizer inference, the cast
  hole, the `...` ban) were invisible in the source and only showed up as a program that
  compiled when it should not have.

- **The reconstruction defect class.** Capability lists survive only on paths built for them
  and vanish wherever pre-existing machinery rebuilds a type or declaration. Seven
  confirmed instances: accessor desugar (MF1), `GetAllGenericTys` (MF3), `PreSetDeclType`,
  the cjo loader (C1), incremental both directions (C2), the imported-accessor fallback,
  try/handle's retyped lambda copy (E2). Hence I.4 item 2.
- **Audit 2026-08-15 (36 agents, 11 defects):** all addressed — six silent unsoundness holes,
  two loud false positives, one parse-time blocker (`throws`/`captures` had to be soft
  keywords because `std.unittest.mock` declares `public func throws`). Two fixes narrowed
  (MF8, MF2-half; see I.1/I.3).
- **Review 2026-08-15 (F1–F6):** `performs` not hashed (F1) turned out to be the callee
  direction of C2 — two hashes exist, the clause hashing sat in the one that feeds the
  virtual/API hashes, not `DeclHash.sig` which drives spreading; clause order unenforced
  (F2); `Handler<C>` wording (F3); duplicate-`performs` wording (F4); `PrintNode` (F5) —
  all fixed. F6 (no remote for the notes repo) is still open.
- **E2** try/handle regions were never capability-checked (the parser clones the block into
  a lambda and sema types the clone) — silently dropped exception demands too. **E3**
  `@AssumeThrows` edits invisible to incremental (import annotations unhashed). Both fixed.
- **Error hierarchy demanded capabilities** (`Error <: ToString` is a separate root) — fixed
  (D18); the first exemption also silenced every effect demand and was caught by the
  `performs` negative tests within one build.
- **Test-validity lesson:** a passing test is evidence only if shown to discriminate. The
  first `incr_assume` draft passed against the unfixed compiler because its two versions
  differed by more than the annotation; the incremental decision log exposed it.
- **Process lessons:** commit on green before starting the next feature (three stash/split
  entanglements in one day); scripted edits must never contain a regex that can match
  ordinary syntax (two incidents); `pgrep -f` self-matches its own probe.

# Documentation conventions

- Source carries **no** proposal section numbers (compiler `7ba425ae`); comments state the
  rule they depend on.
- Notes cite section **titles**; a title change is a content change and is reviewed as one.
- Tests cite section titles.
