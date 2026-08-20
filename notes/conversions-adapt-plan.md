# Implementation plan: §8.10 conversions (`chexc-conversions`) and §8.11 adapt (`chexc-adapt`)

Date: 2026-08-15. Base: compiler `85c06a22`, runtime `066a5ab`, tests `85018920dc`.
Both features are "serious prototypes" per the author directive: own branches, based on
finished development, extensively tested, all-green suites (revised D13: tests written
first and run red locally, committed only passing). Preserved red tests live in scratchpad
`redtests/{conversions,adapt}/` and return with the implementations.

Rulings already in hand: D10 (conversion semantics), D11 (canonical nesting order), D12
(adapt = synthesized capturing class).

**STATUS UPDATE 2026-08-20:** the proposal revision moved both features out of the base
design (conversions → §8.10, "elaboration, not checking"; adapt → §8.11) with rule content
verbatim unchanged — this plan's semantics remain valid, its section numbers do not.
Execution priority drops below the base-design conformance items of
notes/proposal-update-review-2026-08-20.md (unsafeAssumeHandled, local-fn and static
inference, stdlib batch 3). T1.1 is revised by proposal §11.1: `cause` is set-once,
`suppressed` is a read-only snapshot with `addSuppressed` (no longer deferred once the
extension lands), the default printer learns both chains, and new exceptions adopt a
`(message, cause)` ctor convention — plus E-1 of the update review (the `+=` in §8.10.2
is an erratum).

---

## Part 0 · Precursor on `chexc` (shared by both branches)

**T0.1 — Lift `NormalizeCapTys` out of the serializer.**
It lives in `ASTWriterImpl` (`src/Modules/ASTSerialization/ASTWriterImpl.h`); conversions
need it for D11 nesting order and adapt for the captures union. Move to
`TypeCheckUtil` (`NormalizeCapTys(TypeManager&, const std::vector<Ptr<Ty>>&)`), have the
writer call it, re-gate the serialization group. One canonical order, one implementation —
drift here would make nesting order disagree with exported metadata.
*Commit to `chexc` before branching. Effort: S.*

---

## Part 1 · §8.10 Exception conversions → branch `chexc-conversions`

### 1.1 Semantics being implemented (proposal §8.10.1–6.2.4, exact)

- Last-resort step on a **missed demand**: rule 1 — an available capability wins, no
  conversion considered. Rule 2 — exactly one visible `Convertible<From, To>` whose target
  capability is suitably in scope ⇒ wrap the site. Rule 3 — two or more applicable ⇒
  **ambiguous conversion** error. Rule 4 — `From` matched exactly (no variance). Rule 5 —
  no chaining. Rule 6 — `captures` demands (capturing ctors, adapt) never convert.
- Unchecked `To` (§8.10.4): target gate trivially satisfied — fires anywhere `From` misses.
- Inference (§6.2 sentence + §8.10.4): inside an inference-eligible declaration the
  resolver consults only **explicit-source scopes** (enclosing try-catch, literal
  expectation) or unchecked targets; the decl's own growing list is never a target. Net
  effect on the inferred list: removal of the source type.
- Nesting (D11): multiple conversions on one site nest outermost-first in the canonical
  order of the normalized list.
- Runtime shape (D10):
  `try { e } catch (eFrom: From) { let eTo = To.convertFrom(eFrom); <set cause if absent>; throw eTo }`.
  `convertFrom`-throws → suppressed chain: **still deferred** (D10); recorded gap.

### 1.2 Architectural decisions (made now; P-C1 goes to author-questions as Q5)

- **P-C1 · Which demands convert.** Call-site demands AND `throw`-expression demands, both
  including assumption-import demands (§5.2.2 says assumed requirements participate).
  §8.10.1's text says "call site"; §3.3's says "if no suitable capability is found …
  attempted as a last resort", which covers demands generally. Implemented uniformly
  (a `throw` is the degenerate call); ratify as **Q5** in author-questions.md. Excluded:
  captures demands (rule 6), effect demands (`Command` — `Convertible` is Exception-bounded),
  Error/unchecked (exempt before any miss).
- **P-C2 · Check stays pure; rewrite is a separate stage.** During the reporting walk the
  resolver intercepts misses *before* `HandleMiss` and records `ConversionPlan`s; after
  `CheckCapabilities` returns clean, `ApplyConversionPlans` (new, in
  `PerformCapabilityCheck` after the check) materializes the wrappers. Inference-mode walks
  resolve (restricted scopes) but never record plans — their only effect is that a
  converted source never reaches `CollectingMissHandler`, which is precisely the spec's
  "removal of its source type". Ambiguity during collect mode degrades to a plain miss
  (source propagates); the final reporting walk re-derives and reports the ambiguity error,
  so nothing is lost and iterated walks never emit diagnostics.
- **P-C3 · Rewrite via `desugarExpr`, never parent surgery.** The synthesized (fully typed)
  `TryExpr` is assigned to `site->desugarExpr` — the codebase's standard idiom; Walker,
  Collector and CHIR all consume it. Cause-wiring is done by a package-private std.core
  helper `setCauseIfAbsent(e, cause)` called from the synthesized catch (nodes carry
  `Attribute::IN_CORE`, which `IsLegalAccess` admits) — three simple statements instead of
  hand-typing a match on `?Exception`.
- **P-C4 · Lookup direction: table, then scope filter.** A per-package `ConversionTable`
  (`From-ty → [(To-ty, convertFrom decl)]`) built once by scanning visible `ExtendDecl`s
  (package files + imported, via the extend map that `BuildExtendMap` populates) for
  supertype `Convertible<F, T>`. Resolver: `table[From]` (exact-`From`, rule 4) filtered by
  `HasSuitableSupply(To)` over the mode-appropriate scopes, plus unchecked-`To` candidates
  passing unconditionally. ≥2 survivors ⇒ ambiguous. This is the faithful reading of step 2
  (candidates come from the table; scope only gates them) — the inverted direction
  (iterate supplies, test conformance) wrongly explodes under a `catch (Exception)`.
- **P-C5 · Scope provenance.** `SupplyScope` gains a source tag
  (`DeclClause | TryCatch | Literal | Captures | InferredAugment`); collect-mode target
  search admits `TryCatch | Literal` only (§8.10.4). Reporting mode admits all.

### 1.3 Task list

**Stdlib first (runtime repo, branch `chexc-conversions`):**
- T1.1 `Exception.cause`: private backing var + `public mut prop cause: ?Exception` in
  `libs/std/core/exception.cj` (author ruling in D10). Check `toString`/printing for the
  "Caused by:" chain — if Exception printing has no cause rendering, add it (bounded:
  one level per link, existing format conventions).
- T1.2 `Convertible` interface in std.core, exactly the proposal signature:
  `public interface Convertible<From <: Exception, To <: Exception> { static func convertFrom(x: From): To }`.
- T1.3 Package-private `func setCauseIfAbsent(e: Exception, cause: Exception): Unit`.
- T1.4 Rebuild std, API smoke, commit. (These are additive and harmless without compiler
  support; the SDK from this branch is what the compiler branch develops against.)

**Compiler (branch `chexc-conversions`):**
- T1.5 Scope tagging (P-C5): `CapabilityCheck.cpp` — `SupplyScope` → struct with tag;
  touch every `supplies.emplace_back` site (FUNC_BODY, LAMBDA, TRY, captures push).
- T1.6 `ConversionTable` builder (P-C4) + `CLASS_CONVERTIBLE` constant; locate extend
  enumeration API next to `BuildExtendMap`'s consumers; unit of visibility = same rules as
  member lookup through extends (no new visibility logic).
- T1.7 Resolver seam: in `Demand()`, on miss and when the demand kind is convertible
  (P-C1 exclusions), consult resolver before `missHandler.HandleMiss`. Outcomes:
  single candidate → record plan (reporting mode) / swallow (collect mode); multiple →
  `sema_chexc_ambiguous_conversion` (reporting mode; lists candidates) / plain miss
  (collect mode); none → miss as today. Demand sites must pass their kind (call / throw /
  captures / assumed) — extend `Demand`'s signature.
- T1.8 `ApplyConversionPlans`: group plans by site; per site sort by canonical order
  (lifted `NormalizeCapTys` order), build nested typed `TryExpr`s inside-out (first in
  canonical order = outermost), assign `site->desugarExpr`. All nodes typed by hand;
  precedent: `DesugarForPropDecl`.
- T1.9 Diagnostics: `sema_chexc_ambiguous_conversion` (+ candidate notes). Backlog note:
  "a conversion exists but its target is not in scope" hint on the ordinary miss.
- T1.10 The §8.10.3 lints (orphan-prone, public-conversion) — **explicitly out of scope**;
  ledger entry.

**Tests (restore 4 preserved + new; all committed green):**
- T1.11 Restored: `convert_basic` (runtime cause check), `convert_rules_neg` (rules 4+5),
  `convert_ambiguous_neg` (rule 3), `convert_priority_and_captures` (rules 1+6).
- T1.12 New: nesting order — one call converting two Froms; assert catch-order observably
  (outer target catches first) AND `cause` chain identity. · Unchecked target fires with
  no scope gate. · Cause preset by user `convertFrom` is not overwritten. · Inference
  interaction: non-public clause-free callee → source type inferred, NO conversion (the
  §8.10.4 closing example, both directions: with explicit try-catch source in scope the
  conversion DOES fire and the inferred list shrinks). · Assumed-demand conversion
  (`@AssumeThrows` + Convertible). · Cross-package `Convertible` (public extend crosses
  cjo; consumer converts). · Step-1 no-rewrite semantics (direct capability present ⇒
  original handler sees the exception — runtime assert, strengthens the preserved neg).
- T1.13 Risk probe (cheap, before finishing): extends hashing × incremental — does a new
  `Convertible` extend in a dependency dirty the consumer? If not, ledger entry E4
  (compilation is import-sensitive per §8.10.3, so staleness here is real).

**Gates:** CheckedExceptions + Parser + Sema + IncrementalCompilation LLT, ctest, std API
smoke (core/fs/io/mock), fmt. Effort: **L** (the largest remaining feature).

### 1.4 Recorded gaps (ledger entries on landing)
- `suppressed` chain for throwing `convertFrom` (D10 deferral) — synthesized code omits it.
- §8.10.3 lints; metadata recording of public conversions beyond the existing extend export.
- Q5 (= P-C1) pending ratification.

---

## Part 2 · §8.11 adapt → branch `chexc-adapt`

### 2.1 Semantics (proposal rules 1–4, D12)

`adapt<I>(x)`: intrinsic declared in std.core. Rule 1 — every abstract method of `I` has a
name+signature match in `x`'s type *up to throws lists* (modes: pre-Modal, ignored). Rule 2
— the residual union (below) must be capability-covered at the adapt site; conversions
never apply (rule 6 of §8.10.1). Rule 3 — expands to a synthesized capturing class whose
`captures` lists the requirements; result `I` (the `@ local!` region half is pre-Modal
deferred, same caveat as all of §3.9). Rule 4 — identity caveats documented, tested, accepted.

**Residual, not raw union:** `I`'s methods may declare their own throws. Adapter methods
copy `I`'s clauses verbatim; the captures list is the normalized union over matched pairs
of (`x.m` capTys entries not subsumed by `I.m` capTys). Raw-union would over-demand at the
adapt site for exceptions the interface itself admits.

### 2.2 Architectural decisions

- **P-A1 · Synthesis happens BEFORE the capability check, so the checker needs zero
  adapt-specific code.** Pipeline: (i) type check of the call (`SynAdaptCall`) validates
  rule 1, computes matched pairs + residual union, records an `AdaptPlan`; (ii) a
  `SynthesizeAdapters` step in `PostTypeCheck` (which runs before `CAPABILITY_CHECK`;
  precedent: `DesugarForPropDecl` lives there) builds the fully-typed class and assigns
  `ce->desugarExpr = <ctor call>(x)`. The capability check then sees a finished capturing
  class: `DemandConstructedCaptures` charges the adapt site through the EXISTING §3.9 path
  (rule 6 exclusion falls out — captures demands already skip the conversion resolver per
  P-C1), and the walker checks the synthesized method bodies for real (forwarding calls
  discharge against the class captures) instead of trusting them by construction.
- **P-A2 · Recognition by declaration identity.** std.core declares
  `public func adapt<I, T>(x: T): I` with an empty-body/intrinsic marker;
  `SynTypeOfCallExpr` special-cases `resolvedFunction == GetImportedDecl(CORE, "adapt")`.
  `I` must be given explicitly (it is not inferable from arguments); `T` is the argument's
  static type.
- **P-A3 · Scope of the prototype.** `I` must be an interface whose requirements are
  methods only — interfaces demanding props or static members are rejected with a
  dedicated diagnostic (gap ledger; the proposal is silent, and prop-forwarding is
  mechanical follow-up work, not design). Default-implemented methods of `I` are inherited,
  not forwarded. One synthesized class per distinct `(I-ty, T-ty)` per package (dedupe map).
- **P-A4 · Naming/attrs.** `Adapter$<mangle(I)>$<mangle(T)>`, `COMPILER_ADD`, file =
  the call's `curFile`. Not exported (`doNotExport` — adapters are per-package; a second
  package adapting the same pair synthesizes its own).

### 2.3 Task list

- T2.1 std.core `adapt` declaration (runtime branch `chexc-adapt`; tiny — signature only,
  body `throw` unreachable or intrinsic-marked, matching how core stubs are done; verify
  the existing `@Intrinsic` route vs plain-decl+frontend-expansion — take whichever the
  codebase precedent supports with less machinery, document in the commit).
- T2.2 `SynAdaptCall` in `src/Sema/TypeCheckExpr/` (new file, mirroring `PerformExpr.cpp`
  shape): rule-1 matching over `I`'s abstract method set vs `T`'s visible members
  (inherited + extends, same lookup the checker of §3.8 uses — reuse
  `GenerateTypeMappingBetweenFuncs` neighborhood); diagnostics: not-an-interface,
  missing/mismatched method (name the first offender precisely), unsupported prop/static
  requirement, missing explicit `I`. Records `AdaptPlan` (side map, `InferredCapabilities`
  pattern).
- T2.3 `SynthesizeAdapters` in PostTypeCheck: hand-typed ClassDecl — `inner` field, init,
  forwarding methods (clauses copied from `I`), `capturesClause` from residual union
  (typed `RefType` nodes exactly as the cjo loader builds them), inheritedTypes = [I];
  intern class ty; dedupe per P-A3; append to `curFile->decls`; set `desugarExpr`.
  **The heaviest task on either branch** — budget accordingly, verify with AST dump tests.
- T2.4 AST size table untouched (no new node kinds) — but `CreateTest.CheckASTSize` gate
  runs anyway.
- T2.5 Tests — restored `adapt_basic`, `adapt_neg` (+ its exact missing-capability
  assert), new: multi-method residual union with subsumption (`x` throws Derived where `I`
  admits Base ⇒ not captured; union normalization drops subsumed entries) · interface with
  its own throws (residual excludes it; call through adapter demands `I`'s clause at call
  site like any interface call) · generic instantiation (`adapt<Sink<Int64>>(x)`) ·
  identity caveats (`adapt(x) !== x`, `as` does not see through — runtime asserts,
  documenting rule 4) · dedupe (two adapts, same types — compile+run; AST dump shows one
  class) · discharge shape (adapt inside try whose catch covers the union compiles;
  sibling without → the preserved neg) · cross-package `T` (adapt an imported class —
  exercises imported-member matching).
- T2.6 Cross-branch test (adapt × conversions rule 6: a Convertible for a captured
  requirement must NOT fire) — lives in whichever branch merges second; tracked here so it
  is not lost.

**Gates:** same battery as Part 1. Effort: **M–L** (T2.3 dominates).

---

## Part 3 · Sequencing, risks, and the recommendation

**Recommended order: Part 0 → conversions → adapt.** Conversions is the larger and
architecturally deeper change (resolver inside the demand path, scope provenance) and its
stdlib prerequisites (`cause`, `Convertible`) are already ruled; adapt's dominant cost is
mechanical synthesis and benefits from the resolver's demand-kind plumbing (P-C1 tags)
being settled first. Reverse order works too — the only hard coupling is the rule-6
exclusion tag and T0.1.

**Risks, ranked:**
1. Hand-typed AST synthesis (T2.3, T1.8) — the codebase's precedents (`DesugarForPropDecl`,
   `DesugarInTypeCheck`) are the guide; wrong/missing types surface as CHIR crashes, so
   every synthesis test must include a `%run` case, not just compile.
2. The reconstruction defect class (7 prior instances): the synthesized nodes' FuncTys
   must carry capTys where clauses exist (adapter methods copying `I`'s clauses). Build
   them through `GetFunctionTy(..., capTys)` — never a bare reconstruction.
3. Extend-map enumeration for the ConversionTable — API uncertainty; timebox, and if the
   map is member-lookup-shaped only, fall back to scanning `ExtendDecl`s of package+imports
   directly.
4. Double-walk of `desugarExpr` sites by the checker (original + desugar): today's
   behavior for all desugars and green; conversions add wrappers only after the check, and
   adapt's original call demands nothing (`adapt`'s own FuncTy is capability-free). Assert
   this reasoning with the discharge-shape tests.
5. Incremental staleness for import-sensitive conversion visibility (T1.13 probe): E4
   candidate, same family as E3.

**Interaction with pending rulings:** none blocks. Q-STD-5 (io interfaces) changes which
conversions are *idiomatic* (IOException boundaries), not how they work; if it lands
mid-implementation, add one io-flavored conversion test. Q1–Q4 orthogonal. Q5 (new, = P-C1)
filed alongside this plan.

**Branch mechanics:** both branch from compiler `85c06a22` / test `85018920dc`; runtime
branches mirror by name (`chexc-conversions` carries T1.1–T1.4; `chexc-adapt` carries
T2.1). The working tree holds ONE branch at a time and the SDK is rebuilt on switch —
commit-on-green before every switch (the day's stash lessons are ledgered in D13/process
notes; do not develop feature N+1 on uncommitted feature N).
