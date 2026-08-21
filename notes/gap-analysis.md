# Proposal ↔ implementation gap analysis

**Single source of truth** for what separates the `chexc` prototype from the proposal, and
the proposal from a stabilizable design. Two parts: what the **implementation** must change,
what the **proposal** must change. A short third part keeps resolved items whose lessons
still matter. Updated at every milestone gate.

State: compiler `7ba425ae`, runtime `066a5ab`, tests `faca32ed9a`; proposal as revised
2026-08-21 10:53 (vault `6d517618`); the implicit-capability-passing section audited
rule-by-rule against the prototype on 2026-08-21 (34 probe programs, run not committed). Sections are cited by **title**, never number — the proposal renumbered
twice in one day and numbers in notes rot (see "Documentation conventions" at the end).

This document consolidates and replaces: `proposal-implementation-gaps.md` (ledger A–F),
`proposal-update-review-2026-08-20.md`, `production-gap-analysis.md`, `author-questions.md`,
`stdlib-migration-questions.md`, `audit-report.md`, `code-review-2026-08-15.md` — all in
git history. Decisions (D1–D18) stay in `autonomous-decisions.md`; the extension plan stays
in `conversions-adapt-plan.md`; the stdlib classification data stays in
`stdlib-exception-inventory.md`.

---

# Part I — What the implementation must change

## I.1 Base-design conformance (the proposal says it; we don't do it)

| # | Gap | Proposal section | Effort |
|---|---|---|---|
| I1 | **`unsafeAssumeHandled<E, R>(f)`** intrinsic is unimplemented | The escape hatch | S–M: caller demands nothing (capability-free FuncTy), the literal gets `E` from the expected type — only the intrinsic's own body needs an exemption; plus warn on unchecked `E` |
| I2 | **Local function declarations never infer** — `CollectEligible` walks top-level and member decls only; the text now says local functions "are ordinary inference-eligible declarations with lists of their own" | Which declarations are inferred | M: extend collection + call-graph edges; then drop the hand clause on `fs/directory.cj walkFuncWrapper` |
| I3 | **Non-private static class members require explicit clauses** (our MF8 narrowing); the text's uniform rule covers "instance and static methods" | Which declarations are inferred | M: needs the post-inference override re-check MF8 anticipated |
| I4 | **No intra-function capability-scope check** — both canonical escapes of the regions section (assignment to an outer `local?` variable; capability leaving inside a lazy value via the `try` result) are ACCEPTED | Required extension: try-scoped capability regions; Checking without Modal CangJie | M: see Part II D-0 and `architecture.md` "status 2026-08-21" — implementable now as a third stage, mode-free |
| I5 | Diagnostic omits the mode (`CanThrow<E>` not `CanThrow<E> @ local!`) | Capability argument inference | trivial at Modal integration (ruling 3) |
| I6 | `...` marker works on declarations (parsed, unions with inference, rejected in functional types); the missing half is the ban on **exported** declarations — `public func f() throws A, ...` is accepted | Interaction with an explicit `throws` | S |
| I7 | CLI spells `--enable-checked-exceptions=warn`; text spells `--enable-checked-exceptions warn` | Standard library and toolchain impact | S, or keep `=` and note it |
| I8 | **Multiple clauses on one declaration are rejected** — `throws A throws B, C` is a parse error (`duplicate 'throws' clause`), `captures A captures B` fails to parse at all. The text makes both legal and unions the entries (macro-appended clauses, conditional compilation) | Capability parameters in declarations rule 4; Capability capturing rule 1 | S–M: union in `ParseCapabilityClauses` / `ParseCapturesClause`, plus the `...`-idempotence and `throws () throws A` error of "Interaction with an explicit `throws`" |
| I9 | **Finalizers escape the rules twice**: a `throws` clause on `~init` is accepted (the text bans clauses there), and `~init` is inference-eligible, so a finalizer silently acquires a list and may call checked-throwing code — the text says no capability scope encloses a finalizer, and the captures scope already excludes it (`CapabilityCheck.cpp` `hasReceiver`) | Capability parameters in declarations rule 1; Capability scopes; Capability capturing rule 3 | S: exclude finalizers in `IsEligible` + reject the clause in `ChkThrowsClauseOfFuncBody` |
| I10 | **Runtime casts and type patterns read optimistically** — `x as (() -> Unit)` and `case g: () -> Unit` hand back a clause-free function, laundering a `throws` requirement out of the type system (a soundness hole, not just a gap); the invariant-position rejection is missing too | Reflection and runtime casts | M: pessimistic read (`throws Exception` in covariant positions) at cast/type-pattern targets + reject functional types in invariant positions |
| I11 | Missing-capability diagnostic prints internal names: `Cannot find a capability for 'Class-AException' (of type 'CanThrow<Class-AException>')`. The model message spells the source name; other clause diagnostics already do (`unchecked exception type 'U' ...`) | Capability argument inference | S (same root as C7) |
| I12 | `throws A, ()` / `throws ((), A)` — illegal per rule 3 — surface as `expected '->' in function type`; no dedicated diagnostic | Capability parameters in declarations rule 3 | S |

**Audited and conforming** (implicit capability passing, rule by rule, 2026-08-21): the
intrinsic's contravariance and non-denotability; clause placement on functions, instance and
static methods, primary and secondary constructors, interface and extension methods, property
accessors, operators, `main` (and the bans on foreign/`CFunc`/whole-`prop` clauses); entries
including nested parenthesized lists, aliases, `Exception`-bounded type parameters, `throws ()`
as a whole list; requirement sites; all four scope introducers (including wildcard `catch (_)`
as `Exception` and try-with-resources initializers) and all the exclusions except finalizers
(I9) — `catch`/`finally` blocks, default parameter values against the callable's own scope,
instance field initializers against every constructor, top-level and static initializers;
innermost-first resolution with no ambiguity error for several suitable entries in one scope;
capabilities-are-not-values; functional-type syntax, subtyping, joins and meets; literal lists
from the expected type only; generics (capability inference after type-argument inference,
capability lists out of type-argument inference); overloading by recursively erased signatures,
for functions, methods and constructors; override and redefinition including statics and
generic substitution; capturing — construction-site obligation, alias entries, `where`-order,
subclass opacity, statics and finalizers excluded from the captures scope, structs, primary-
constructor ban, rejection on interfaces and enums; runtime erasure.

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

- **C5** Macro NodeFormat does not serialize `ThrowsClause` — macro-generated code cannot declare clauses (blocks `std.unittest` from offering checked APIs).
- **C6** `CanThrow` does not exist as a type; entries live directly in `FuncTy::capTys`. Working as intended (strongest form of the intrinsic NOTE in "Type of exception capabilities"); revisit only if effects materialization needs a real type.
- **C7/C8** Diagnostics: generic inference failure shows the uninstantiated capability row with no dedicated message; override/clause diagnostics print raw `Class-X` names.
- **C9** LSP/cjd compiler instance no-ops the pass — no IDE diagnostics.
- **C10** `--enable-chexc` alias retained beside the canonical flag.
- **C11** ASTWriter exports generic/inline bodies without clause nodes (silent; no crash observed).
- **C12** Six source comments still cite proposal numbers or removed notes files (`CompilerInstance.cpp:732`, `TypeChecker.cpp:223`, `CapabilityCheck.cpp:821/839/915`, `StructInheritanceChecker.cpp:1338`); one of them cites a rule that has since moved out of the section it names. The convention is no numbers in source.
- **MF2 half** Inferred lists are written into declaration types, but a requirement at *function-value formation* from a clause-bearing declaration is not demanded; the audit disproved the original premise — recheck against the final text.
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
- **Q-STD-7 unittest acquires 23 fs obligations** from batch 1: recommend catch-and-wrap internally rather than leaking `FSException` into the test framework's API.
- The 23 UNCERTAIN classes of `stdlib-exception-inventory.md`.

## I.6 Tooling now called for by the text

- **Clause-materializing fixer** (Migrating user code): inference over the whole package including exported declarations, written back as clauses. `CollectingMissHandler` already computes the lists; the new part is source rewriting. **Caveat D-4 applies**: public-surface output is an API-design proposal, not a diff to rubber-stamp.
- **Lints** (TODO section): redundant `throws` entry; undischarged capability (suppressible on public APIs).

## I.7 Extensions (explicitly outside the base design now)

- Exception conversions and automatic adapter generation: `conversions-adapt-plan.md` stays valid content-wise (rules verbatim); priority below everything above. T1.1 there is revised by the new `cause`/`suppressed` spec (set-once `cause`, read-only `suppressed` + `addSuppressed`, printer learns both chains, `(message, cause)` constructor convention).
- Capability-list polymorphism (`spawn<R, throws E>`, `Future<R, throws E = ()>`): roadmap, XL.
- `WrappedUncheckedException` + the handling sugar: roadmap with that extension.

---

# Part II — What the proposal must change

## II.1 Errata (text-level, each verified against the 2026-08-20 17:33 text)

- **E-1** "Stack traces and cause chains" writes `eErr.suppressed += eFrom`; "Standard library and toolchain impact" specifies `suppressed` as a read-only snapshot with `addSuppressed`. Fix to `eErr.addSuppressed(eFrom)`.
- **E-2** Audit tense: the toolchain-impact section says the classification is "confirmed by the annotation audit"; the migration section says "to be confirmed". It is *partially* confirmed (26 re-parents, 90 clauses). And the name marked "to confirm" is confirmed: **`UnsupportedException`**, not `UnsupportedOperationException`.
- **E-3** `unsafeAssumeHandled`'s signature uses `@ local?` in a base-design std.core declaration, but the design explicitly supports a Modal-less tier whose toolchain cannot parse modes. State the degraded-mode surface form (modes stripped).
- **E-4** The interface ruling ("streams declare `throws IOException`; implementations narrow") is inconsistent with `ContentFormatException <: Exception` — std.io's own read paths throw it and no `InputStream` implementation could under narrower-only overriding. Re-parent under `IOException` (recommended), declare both, or keep those APIs off the interface — say which.
- **E-5** Two renumberings in one day left internal consistency intact (verified: no stale anchors) but make every external citation rot; consider freezing numbering or publishing stable anchors.
- **E-6** The rule-by-rule rewrite of "Capability parameters in declarations" dropped the
  unchecked-entry restriction (old rule 5) — it now lives only in "Unchecked exceptions"
  ("Unchecked types in `throws` lists"), and the entry rule (rule 2) does not point at it.
  Likewise rule 4 (several clauses union) does not point at "Interaction with an explicit
  `throws`", where the interactions that actually constrain it live (`...` repeats
  idempotently; `throws () throws A` is an error). Anyone implementing from the section
  alone gets both wrong. Add the two cross-references.
- **E-7** Moving package metadata out of "ABI and reflection" dropped its **canonical
  normal form** rule (aliases expanded, duplicates and subsumed entries removed, remaining
  antichain canonically ordered; diagnostics print the same form). "Package metadata" now
  keeps only level, throw-closure summary and epoch, and nothing else states a recorded
  form beyond "lists are semantically sets" plus alias transparency. The prototype
  normalizes on the `.cjo` path (`NormalizeCapTys`) because the signature hash drives
  incremental recompilation — without the rule, equivalent-but-differently-ordered lists
  are a legal encoding and cause cross-toolchain rebuild churn. Restore one rule.
- **E-8** "Not on finalizers, foreign functions, `CFunc` types, or variable initializers" —
  an initializer is an expression, not a site a clause could attach to; the rule means
  variable *declarations*.
- **E-9** `throws ()` is stated twice with different force and the two are never related:
  in a functional type it "denotes the same type as omitting the clause", on a declaration
  it is authoritative-empty — it pins emptiness and disables inference ("Interaction with
  an explicit `throws`"). Same spelling, same section neighbourhood, opposite defaults
  against omission. One sentence in "Functional types" would close it.

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

### D-6 · "The package is the unit of the analysis" sharpens the unresolved Q1
The per-file-enabling rejection argues the package is the analysis unit, yet assumption
imports are file-scoped syntax: two files of one package asserting different lists about
the same dependency feed one inference graph with per-file demands. Coherent (implemented),
but the text still does not say whether that is intended.

### D-7 · The base design keeps the boilerplate it calls "very common"
With conversions demoted, handle-convert-rethrow at every abstraction boundary is manual in
v1. A defensible trade (elaboration out of checking) — but state it as an accepted v1 cost
in "Forcing a decision nobody can make" or "Migrating user code".

### D-8 · The pessimistic cast rule is right, and much bigger than it reads

"Reflection and runtime casts" closes a real hole — a `() throws E -> R` value laundered
into a clause-free `() -> R` by `as` — by reading a functional cast target pessimistically
(`throws Exception` in covariant positions) and rejecting functional types in invariant
positions. Three things the text should say out loud:

1. **CangJie has no declaration-site variance for user generics**, so "invariant position"
   is not a corner: *every* generic target carrying a functional type argument is rejected —
   `ArrayList<() -> R>`, `Option<() -> R>`, `Box<() -> R>`, an array of callbacks. Casting
   a collection of functions out of `Any` stops working entirely. That may be the right
   price, but it should be stated as a rule, not implied by one example.
2. **The polarity rule is given by example** ("the target itself and function-typed
   results" vs "parameter positions keep the empty list they spell"). A positional
   statement — positions reachable only through result arrows are read as
   `throws Exception`; positions reachable through a parameter arrow keep the written list
   — settles the nested cases (`(() -> R) -> Unit`, `() -> (() -> R)`) that the example
   does not.
3. **Carriers are not mentioned.** An instance of a capturing class, or a literal that
   captured a capability, is the other value that can carry evidence past a cast. The
   answer is presumably that modes already stop it — a carrier is `local!` and cannot reach
   an `Any`-typed slot — but the section reads as if functional types were the only
   channel. One sentence, and the closure claim of "Capabilities are not values" becomes
   checkable.

Prototype status: unimplemented (Part I, I10); the cast currently launders requirements.

## II.3 Open readings to rule (each implemented conservatively; widening is backward-compatible)

| # | Question | Implemented | Reversal cost |
|---|---|---|---|
| Q1 | Assumption import per FILE or per PACKAGE? | per file (import is file-scoped syntax) | file→package widening is compatible; see D-6 |
| Q2 | What does `@AssumeThrows[]` mean? | same as bare: `Exception` | low; could reject the form |
| Q3 | Does an assumption cover subpackages? | no, exact package match | exact→prefix widening is compatible |
| Q4 | Do assumptions reach function VALUES from the package? | no, resolved calls only | **moderate** — moves assumptions into type formation; decide before more boundary work |
| Q5 | Do conversions apply to `throw` expressions or calls only? | planned uniform | moot for v1 (conversions are an extension) |
| Q6 | Misplaced `@AssumeThrows` — error or ignored? | error | ratified (D15); flagging only |
| Q7 | Where does a class's `captures` scope sit in the innermost-first search — inside or outside the method's own `throws` scope? | outside (the method's own clause wins) | low now, **material once regions land**: it decides whether a carrier is tied to the instance's region or to the caller's `try` |
| Q8 | Try-with-resources: the initializers are inside the `try` scope, but what covers the **implicit `close()`**? It sits in `finally` position, which the same list excludes | nothing is demanded (the pass sees `resourceSpec`, never the implicit call) | none while `Resource.close()` is clause-free; annotating it would break every try-with-resources at once |

## II.4 Upstream compiler defects found on the way (not ours; worked around)

- **U1** `IsLegalAccess` dereferences `node.curFile->curPackage` guarded only by a
  `CJC_ASSERT` that compiles out in release, while guarding the same pointer correctly ten
  lines either side; any node reaching type-legality checking without a file is a
  location-less ICE. Worked around (`AddCurFile` walks import annotations); the deref is
  untouched.

---

# Part III — Resolved, kept for the lessons

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
