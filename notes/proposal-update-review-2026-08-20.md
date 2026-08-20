# Proposal update review — 2026-08-20

Proposal edited 2026-08-20 14:18 (Modal file unchanged since 08-10). The Vault moved
(`Projects/Effect system/…` → `Projects/CJ/…`); both workdir symlinks repointed. Baseline
for this diff: the sections read verbatim during the 2026-08-15 sessions plus the known
line-anchor map. Snapshot of today's text: scratchpad `proposal-2026-08-20.md` (1907 lines).

## 1 · What changed

**Restructuring (content-preserving moves):**
- §6.2 Exception conversions → **§8.10** and §6.5 adapt → **§8.11**, both now explicitly
  "outside the base design" — conversions because they are *elaboration, not checking* (the
  one property the base design refuses, §9.3); adapt "not proposed for the initial design".
  Rules 1–6 of conversions and rules 1–4 of adapt are **verbatim unchanged**. §3.3 lost its
  two conversion hooks ("last resort", "synthesized conversion boundary" scope item): the
  base-design checker has NO conversion step at all.
- Renumbering: inference §6.3→**§6.2**, unchecked §6.4→**§6.3** (escape hatch §6.3.3),
  unreachable-catch §6.6→**§6.4**. §7 is now "Known limitations".

**New design content:**
- **§6.3.3 `unsafeAssumeHandled<E, R>(f)`** — a BASE-DESIGN std.core intrinsic: runs `f`
  supplying a fabricated capability for `E`; zero runtime content; `E` explicit (asserting
  `Exception` asserts everything via functional-type subtyping); carrier discipline
  Modal-deferred like the rest of §4.3.
- **§8.9 Capability-list polymorphism** — list variables (`func spawn<R, throws E>`,
  `Future<R, throws E = ()>`), definition-site-only inference, invariant, non-goal for
  ordinary HOFs. §7.1 now states the base-design consequence in text: a `spawn` block
  cannot throw checked exceptions at all — **our empty-stack spawn rule is ratified**
  (was an author ruling, now proposal text).
- **§6.2.1 inference scope extended/clarified:** "local function declarations are ordinary
  inference-eligible declarations with lists of their own" and the uniform "all kinds of
  callables" rule with NO static-member carve-out.
- §6.2.6 (public opt-in via `...` — not proposed), §9.4 (per-file *enabling* REJECTED, with
  the package-is-the-unit-of-inference argument; warn + CI ratchet is the sanctioned
  migration granularity — exactly our cj.py state), §9.5 (degraded mode is transitional by
  design), §9.6 (Option-twins rejected), §12 TODO (two lints, corpus study, and "type-checker
  prototype … validate the phase ordering of §6.2.3" — i.e. this project).
- **§5.4 adopts the clause-materializing fixer** — the `--suggest-throws` idea from our
  production-gap analysis is now proposal text (inference over the whole package including
  exported decls, written back as explicit clauses).
- **§11 concretizes `Exception.cause`/`suppressed`:** cause set-once `mut prop`,
  `suppressed` read-only snapshot + `addSuppressed`, default printer learns both chains,
  `(message, cause)` ctor convention, corpus survey before landing. Both "arrive with the
  conversion extension" — supersedes D10's suppressed-deferral framing.
  Also new: `WrappedUncheckedException` (with §8.5 sugar); std ships NO public Convertible.

**Rulings that answer our standing questions:**
- **Q-STD-5 → RULED = option 1** (§11.2): "streams declare `throws IOException`; in-memory
  implementations override with narrower lists per §3.8." Interface policy stated generally
  (predominantly-throwing interfaces declare; predominantly-pure stay clause-free with
  capture for effectful impls; long-lived effectful types declare because capture
  region-binds).
- **Q-STD-6 → RULED, third way** (§11.2): NOT protocol polymorphism — "IO-backed iterators
  become capturing classes" (`File.lines()` captures `CanThrow<IOException>`, is `local!`);
  `for-in` over `local!` iterators is a Modal requirement to confirm (§4.4).
- **§5.3 scope/rulings:** regex ruled CHECKED (data-driven use decides); `std.convert` and
  `encoding.*` join the checked set; starter table matches our phase-1 re-parents
  (UnsupportedException naming "to confirm"); **shipping policy: a module ships either
  unannotated or `error`-clean — `warn` is a development state, not a shipping state.**
- Q1–Q4 (§5.2.2): substantive text unchanged — still OPEN. The §5.2.2 sentence dropped its
  "and exception conversions" clause (consistent with the §8.10 move) and softened
  "precisely checkable" → "checkable relative to the consumer's trusted assumption".
  Q5 (throw-expr conversions) is moot for the base design and remains open inside §8.10.

## 2 · Implementation work items, ranked

**A. Base-design conformance (compiler):**
1. **`unsafeAssumeHandled` (§6.3.3)** — std.core intrinsic decl + checking. Most falls out
   of existing machinery: the caller demands nothing (capability-free FuncTy) and the
   literal argument's body receives `E` via the expected-type rule; only the intrinsic's
   own body needs a check exemption (intrinsic-marked, no body). Plus: warn on unchecked-`E`
   instantiation. Tests: assume-and-run, runtime propagation on escape, explicit-`E`
   requirement. Effort S–M.
2. **Local functions become inference-eligible (§6.2.1)** — `CollectEligible` walks only
   top-level/member decls today; local `FuncDecl`s never infer (we hand-annotated
   `walkFuncWrapper` in std.fs precisely because of this). Extend collection + call-graph
   edges; then drop that stdlib clause. Effort M.
3. **Statics infer (§6.2.1 uniform rule)** — our MF8 restriction (non-private static class
   members demand explicit clauses) is now a proposal-conformance gap, not polish. Needs
   the post-inference §3.8 re-check MF8 already anticipated. Effort M.
4. **Citation renumbering** — every compiler comment/diagnostic/test header citing
   §6.2/§6.3/§6.4/§6.5/§6.6 old numbering, and the notes corpus. Mechanical, zero behavior;
   do it as one sweep commit per repo. Effort S–M.
5. CLI cosmetic: proposal spells `--enable-checked-exceptions warn|error`; we implement
   `=warn|=error`. Confirm the space form or keep `=` — S, note in gaps ledger either way.

**B. Stdlib batch 3 (unblocked by the rulings; brings fs/io to error-clean):**
6. **Interface clauses (Q-STD-5 ruling):** `throws IOException` on
   `InputStream.read`/`OutputStream.write`/`Seekable.seek` (+ decide `Resource.close` in
   the audit); `File.*` inherit-and-declare, `ByteBuffer`/`ChainedInputStream` override
   NARROWER (§3.8 narrowing already implemented). Clears the 6 deliberate residual sites.
   Effort S–M.
7. **Iterator capture (Q-STD-6 ruling):** the StringReader iterator types capture
   `ContentFormatException` (construction-site obligation) instead of clause-bearing
   `next()`. Design note first — construction sites move the demand. Effort M.
8. **Batch-2 scope grows:** + `std.convert`, `encoding.*` (regex ruling confirms batch-2
   classification). Then per-module `error`-clean flips per the shipping policy — roadmap.
**C. Toolchain (adopted into the proposal):**
9. **Clause-materializing fixer (§5.4)** — inference-over-everything + write-back. The
   collect seam already computes the lists; the new part is source rewriting. Effort M.
10. §12 lints (redundant entry; undischarged capability) — backlog, S each.

**D. Extensions (explicitly deprioritized by the move):**
11. `chexc-conversions`/`chexc-adapt` plan remains VALID content-wise (rules verbatim;
    adapt's future-work fence matches P-A3). Update plan header: extension status, §8.10/
    §8.11 numbering, T1.1 revised to the §11 cause/suppressed spec (set-once, printer,
    `addSuppressed` — suppressed no longer deferred once the extension lands). Execution
    now ranks BELOW A+B+C.
12. §8.9 list polymorphism — new roadmap XL (parser `<R, throws E>`, list-variable kind,
    invariance, definition-site inference). Not started.
13. `WrappedUncheckedException` + §8.5 sugar — roadmap with the extension.

## 3 · Validations the update hands us

Spawn-empty-stack ratified (§7.1) · phase ordering endorsed (§12 names our prototype's
job) · expected-type literal rule confirmed (§6.2.1 last para) · adapt scope fence matches
P-A3 · per-file rejection (§9.4) matches the warn-ratchet migration we shipped · fixer
adopted (§5.4) · std ships no public Convertible (matches our test-only usage).

---

## 4 · Proposal-side findings (per the two-way-evolution directive)

The update is clean where mechanical care was needed — **no stale anchors survived the
renumbering** (verified by grep), and the §2.1 pitch was consistently reworded to
"a planned extension". The following are the places where the proposal text itself needs
work, each verified against today's text and, where possible, against prototype evidence.

### Errata (text-level fixes)

- **E-1 · `suppressed` API contradicts itself.** §8.10.2 writes `eErr.suppressed += eFrom`;
  §11.1 specifies `suppressed` as "a read-only snapshot with `addSuppressed`". A `+=` on a
  read-only member cannot both hold. Fix §8.10.2 to `eErr.addSuppressed(eFrom)`.
- **E-2 · Audit tense mismatch + a name to close.** §11.1 says the classification is
  "confirmed by the annotation audit"; §5.3 says "to be confirmed". Factually it is
  *partially* confirmed: the prototype's audit re-parented 26 classes and annotated 90
  fs/io flows. And the name marked "to confirm" is confirmed: the class is
  **`UnsupportedException`**, not `UnsupportedOperationException`.
- **E-3 · Base-design std.core signature uses Modal syntax.** `unsafeAssumeHandled`'s
  parameter is `(() throws E -> R) @ local?` — but the base design explicitly supports a
  Modal-less degraded mode (§5.5, §9.5), whose toolchain cannot parse `@ local?` (ours is
  exactly such a toolchain). The degraded-mode surface form of every mode-annotated
  std.core signature needs one sentence: modes are stripped, semantics per §5.5.
- **E-4 · The §11.2 interface ruling is inconsistent with std.io's own types.**
  "Streams declare `throws IOException`; in-memory implementations override with narrower
  lists" requires every stream-thrown type to be `<: IOException` — but
  `ContentFormatException <: Exception` directly (verified in source), and std.io's own
  read paths throw it on malformed stream content. Under §3.8 narrower-only, no
  `InputStream` implementation could ever throw it. Options: re-parent
  `ContentFormatException <: IOException` (recommended — it is an io-domain failure);
  interfaces declare both; or those APIs stay off the interface (the accidental current
  state). The ruling should say which.

### D-0 · The checker's phase ordering assumes modes are capability-independent — Modal breaks it

**Raised by the author, 2026-08-20; the sharpest finding in this review.**

The base design says capability checking may run after type checking, and the prototype does
exactly that: `types+modes (capability-blind) → capability parameters → capability arguments →
scope check`. That order is what makes the whole implementation tractable, and it is sound
*only while capabilities are phantom*.

Under Modal CangJie a capability-capturing lambda is a region-bound value, and **its mode is
determined by what it captures**. What it captures is precisely what the post-Sema pass
computes. So the dependency is circular in the direction the pipeline cannot express:

1. Sema assigns the literal a mode without knowing its captured capabilities;
2. the capability pass then discovers those captures;
3. if they should have forced `this @ local!`, the mode already assigned is wrong, and
   nothing re-checks it.

Prototype evidence that this is not hypothetical: §5.2.3's boundary rule is enforced only in
its subtype half (a `() throws E -> R` value cannot flow into a `() -> R` parameter). Its
REGION half — a clause-free literal that captures a capability instead of declaring it is
region-bound and must not escape — is unenforced today, and the `spawn` rule the prototype
implements (empty capability stack inside a spawned block, now §7.1 base text) is a lexical
stand-in for a region discipline the checker cannot express at this phase.

**Consequence for the text.** §4.3 states that try-scoped capability regions are a required
extension, and §5.5 offers the Modal-less degraded mode, but neither says that a
post-type-check capability pass depends on modes being independent of captures — i.e. that
the natural implementation strategy stops working exactly when Modal lands. Whoever
implements this after Modal must either fold capability checking INTO type checking, or make
mode assignment a fixpoint over (modes, captures) instead of a pipeline stage. That is a
different compiler architecture, not an increment on this one, and the proposal should say so
where it recommends the phase ordering (§6.2.3) and where it defers escape analysis (§4.3).

**Refinement (2026-08-20, after a close read of "Escape analysis" §4.3/§4.4 with the
author's question in hand).** The proposal's path (b) contains more of the answer than the
paragraphs above credit, and D-0's "different compiler architecture" conclusion narrows:

- Modes are never *inferred from* captures — they are **capped by** them. Path (b): a
  capability-capturing literal or instance "has its mode capped at `local?`", and Modal's
  own rules make this the only possible consequence (no function object is `local!`;
  capabilities are captured via a `local?` alias — open question 2 confirms the updated
  Modal draft permits exactly this shape). Capping is binary and monotone, so the
  post-Sema arrangement survives as **check-and-cap**: discover capability-capturing
  values, lower them to `local?`, propagate region-boundness monotonically through
  captures/stores, and re-validate the lowered values' uses (no use after the `try`, no
  assignment outward). A third pipeline stage, not a fixpoint.
- The one genuine break is **mode-dependent overloading**: Modal methods overload on the
  receiver-mode specifier, so a cap can invalidate an overload Sema already chose.
  Re-resolving would silently change which code runs; the sound design is to REJECT with
  a capability-aware diagnostic. This is the residue of D-0 — a completeness loss the
  proposal should state where it recommends the phase ordering.
- The future-proofing hint is open question 1's resolution: specify (b) as an
  implementation of (a)'s SEMANTICS, so evidence passing "changes the lowering, not which
  programs type-check". That principle, plus the §4.4 list (forwarding conflict,
  unwinding, `local?` invocation, `for-in` over `local!`), is the full remaining surface
  to negotiate with the Modal authors.

**Cost of not saying it.** An implementer follows §6.2.3's ordering, ships the Modal-less
tier, and discovers at Modal-integration time that the pass must be rebuilt — the single
largest schedule risk in the design, currently invisible in the text.

### Disadvantages and design tensions (with prototype evidence)

- **D-1 · The capturing-iterator ruling buys uniformity with three real costs.**
  (a) The flagship IO use case — iterate a file's lines — now depends on an *unconfirmed*
  Modal requirement (`for-in` accepting `local!` iterators, §4.4); if that falls through,
  checked IO iteration has no story at all. (b) The obligation moves to construction: a
  mid-iteration disk failure and a construction failure are indistinguishable in the
  discipline, and the `try` must wrap the loop merely to *build* the iterator — prototype
  evidence: sketching the StringReader conversion showed every constructor call site
  (including tests that never iterate) acquiring the obligation. (c) In the degraded mode
  a captured-`IOException` iterator escaping its `try` is precisely the phantom-capability
  hole — on the most common API shape the library ships. §7.1/§5.5 should acknowledge (c)
  explicitly for iterators, not only for `spawn`.
- **D-2 · List-variable invariance makes `Future` collections monomorphic.** §8.9.4's
  invariance means `Array<Future<Unit, E>>` requires every element to carry the *same*
  list; heterogeneous futures cannot share a collection except by instantiating
  `E = Exception` and losing precision. `waitAll` in §8.9.5 works only because of that
  uniformity. The non-goals section fences virality but does not state this concrete
  limitation; it should, with the `E = Exception` idiom as the documented out.
- **D-3 · Two "assume" constructs with opposite safety polarity.** `@AssumeThrows` *adds*
  obligations (errs safe); `unsafeAssumeHandled` *removes* them (errs unsafe). The shared
  "assume" stem invites confusion in exactly the migration codebases that will use both.
  The `unsafe` prefix mitigates; a terminology note contrasting them (and cross-links both
  ways) would close the hazard cheaply.
- **D-4 · The §5.4 fixer will materialize the disease the intro diagnoses.** Line 31
  criticizes Java for "polluting interfaces with implementation-specific exception types";
  the fixer mechanically writes inferred lists onto *exported* declarations. Prototype
  evidence: mechanical inference on public surfaces yields `FSException` on a test
  framework's API and raw `Exception` lists on std.net (Q-STD-2/7) — true lists, wrong
  APIs. §5.4 needs the caveat that public-surface output is an API-design *proposal*
  requiring review, not a diff to rubber-stamp — abstraction boundaries are exactly where
  §8.10 conversions were supposed to help, and they are now an extension.
- **D-5 · The escape hatch is all-or-one.** Single `E` per call; several specific types
  need nested calls or the coarse `E = Exception`. Acknowledged via §8.9 futures, but the
  main consumer is migration-era code, which gets the coarse tool first. A tuple form
  (`unsafeAssumeHandled<(A, B)>`), consistent with §6.1 aliases, would cost little.
- **D-6 · §9.4 sharpens the unresolved Q1.** The new argument — "the package is the unit
  of the analysis" — now sits in tension with assumption imports being file-scoped
  syntax: two files of one package asserting different lists about the same dependency
  feed one package-level inference graph with per-file demands. Coherent (implemented),
  but §5.2.2 still does not say whether that is intended (author-questions Q1, open since
  08-15, now with a proposal-internal tension attached).
- **D-7 · The base design keeps the boilerplate it calls "very common".** With conversions
  demoted, handle-convert-rethrow at every abstraction boundary is manual in v1 — §8.10's
  own intro names the pattern "very common but quite verbose". That is a defensible
  trade (elaboration out of checking), but it should be stated as an accepted v1 cost in
  §2.1.4 or §5.4 rather than left implicit, because it directly weakens the migration
  pitch the fixer section makes.
