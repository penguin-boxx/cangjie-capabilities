# Prototype → production gap analysis

Date: 2026-08-15 (section numbers updated to the 2026-08-20 proposal revision). Premise: the proposal stabilizes roughly as written (with the Q1–Q4 and
inventory rulings folded in). This maps what separates the `chexc` branch from an
implementation that could ship in the official toolchain. Effort classes: S (days),
M (weeks), L (months), XL (joint effort with another feature's timeline).

The one-paragraph version: **the prototype is a faithful semantic model of the proposal,
not a draft of the production patch.** Its architecture (stage separation, the miss-handler
seam, capTys-out-of-typeArgs) transfers directly; its *code* transfers partially; and three
things it deliberately does not attempt — Modal integration, evidence-passing readiness, and
toolchain-wide integration (LSP/macros/formatter/CJMP) — are where most of the production
cost lives.

---

## 1. What transfers as-is (the asset list)

- **The pipeline shape.** `capability-blind types → capability parameters (§6.2) →
  clause completion → capability arguments → scope check` is a production-shaped pass
  order; it was chosen precisely so inference never entangles type checking.
- **The miss-handler seam.** One walker, parameterized over what happens to a miss:
  reporting, inference collection — and, in production, LSP quick-fix collection and a
  clause-suggestion tool fall out of the same seam (see §8).
- **The disjoint-roots argument** (D17) for exceptions vs effects, and the subsumption
  algebra (set-based `IsCapTysSubsumed`, canonical normal form and its soundness proof).
- **The test corpus** (~80 cases, negative-heavy) and, as importantly, the *ledger method*:
  every deviation, ruling, and open reading is written down. Production implementers
  inherit ~35 micro-decisions the proposal text does not state (D1–D17, rulings 1–14,
  A/B/C/E sections, Q1–Q4). Folding these back into the spec text before stabilization
  is itself a work item (§9).

## 2. Architectural debts that need rework, not extension

### 2.1 Phantom capabilities vs Modal CangJie (XL — the big one)
The proposal's §4.3 makes try-scoped capability *regions* a required extension; soundness
of first-class functions rests on it. The prototype implements path-b phantom capabilities
with **no escape analysis** (author ruling: wait for Modal). Concretely unsound today, by
design: a clause-free literal that captures a capability can flow out of its try region and
be invoked with no handler alive. §5.2.3's boundary rule is enforced only in its subtype
half, not its region half. Production cannot ship `error`-level checking without this, and
it is not incremental work on our pass — lambda mode inference from captures, region-bound
values, and `~local` boundary defaults make the check region-aware rather than lexical.
Timeline is coupled to Modal CangJie landing upstream. **This is the critical path.**

### 2.2 Make the reconstruction defect class unrepresentable (L)
Seven confirmed instances of "capability list silently dropped by a path that rebuilds a
type/declaration"; 118 unaudited `GetFunctionTy` call sites. The prototype's defaulted 4th
parameter was the right call for velocity and is the wrong call for production: the fix is
to remove the default (or fold params+ret+caps into one `FuncSig` value), turning every
future omission into a compile error, then burn down the 118 sites once. Mechanical but
wide; do it before any other production work touches types.

### 2.3 The `performs`/`throws` shared list splits under evidence passing (M–L)
Valid only while both capability kinds are phantom (D17 records this). Evidence passing
makes `Handler<C>` a real runtime value: separate list, separate lowering, CHIR
representation, new ABI surface, schema change. All current call sites that read `capTys`
must be revisited with the same discipline as 2.2 — ideally as part of the same refactor.

### 2.4 Inference results live beside the AST (M)
`InferredCapabilities` map + completed declaration types + *uncompleted* expression types
works because exactly one consumer exists. Production has many consumers (LSP hover,
CHIR, refactorings, diagnostics provenance). Either complete expression types in a
dedicated pass or route every consumer through one query API; the current split is a
maintenance trap.

## 3. Known open holes (deliberate, ledgered)

| Item | Status | Production action |
|---|---|---|
| Escape of capability-carrying values (2.1) | open by ruling | Modal integration |
| MF8: non-private static class members need explicit clauses | over-restriction | post-inference §3.8 re-check |
| MF2 formation half | premise disproved in audit; recheck against final spec text | spec clarification |
| Q1–Q4 §5.2.2 readings | awaiting author | fold ruling into spec + tests |
| U1 upstream `IsLegalAccess` null-deref | worked around | upstream a real null check |
| **NEW: `@AssumeThrows` invisible to incremental** — `HashImportSpec` hashes paths/alias but not annotations, so changing an assumption list does not dirty the file's declarations | confirmed today, unfixed | same fix family as F1; hash import annotations (S) + red-first incr test |

## 4. Toolchain integration not attempted (collectively L–XL)

- **LSP/IDE (C9).** The LSP instance no-ops the pass. Production needs in-IDE diagnostics,
  clause-aware hover/signature help, completion inside clauses, quick-fixes ("add
  `throws E`", "wrap in try/catch", "add alias"). The miss-handler seam is the natural
  quick-fix provider. Also `.cj.d` files (CjdCompilerInstance): declaration files must
  carry clauses or documentation and headers lose the contract.
- **Macros (C5).** NodeFormat/TokenSerialization don't carry `ThrowsClause`: macro-generated
  code cannot declare clauses. Blocks any macro-heavy library (std.unittest itself) from
  offering checked APIs. Schema + quote/interpolation support.
- **cjfmt / cjlint.** The formatter has its own grammar; it has never seen `throws`,
  `performs`, `captures`, or `@AssumeThrows`. Formatting a migrated stdlib mangles it
  today. Lint rules (e.g. "clause entry already subsumed") are greenfield.
- **CJMP.** Untested against common/specific merging; one suspicious interaction (clause
  nodes through `MatchSpecificWithCommon`). Needs its own test matrix.
- **Interop.** FFI rejects clauses (done), but the Java-side story — mapping Java checked
  exceptions to clauses at mirror boundaries — is an obvious stabilization question with
  nothing implemented.
- **Reflection.** Erasure story is as-designed; production should decide whether DECLARED
  clauses are reflectively queryable from metadata and document it.

## 5. Serialization/ABI maturity (M)

- Fields were appended so old cjo loads in the new compiler — but there is **no feature
  gate in the other direction**: an old compiler reading a new cjo silently drops
  capability metadata, so a mixed-toolchain build silently loses checking. Production
  needs a cjo feature bit + policy (reject or warn).
- §3.10.2's remaining metadata: per-package check level (`error|warn|off`) and the ABI
  epoch are unimplemented; the whole-build guarantee of §5.2.4 is not diagnosable without
  them ("this binary links warn-level packages" should be a stateable fact).
- Canonicalization happens at write; production should verify at load too (defense against
  hand-built cjo) — cheap.

## 6. Diagnostics and UX (M, but user-facing quality lives here)

- **Provenance is the big one.** Inference makes requirements non-local: "why does `f`
  require `E`?" has an answer three calls deep. The fixpoint currently keeps no derivation;
  production wants a provenance chain per inferred entry ("required by `g` at line N, via
  `h`"). Retrofit is straightforward in the collecting handler but costs memory; design it,
  don't bolt it on.
- Type rendering: diagnostics print internal names (`Class-MyExc<Int64>`) — C8.
- No fix-its; no "a conversion exists (§8.10)" notes; no localization.
- The `chexc` warn group exists and works; keep.

## 7. Performance (unknown → must be measured, M to react)

Never profiled. Known hot-spot candidates: per-demand linear scope scan × `IsSubtype`;
`GetAllSuperTys` allocation per effect miss; Kleene iteration re-walking whole bodies per
round (quadratic on large SCCs — real stdlib packages will find this); interning pressure
from capability-bearing FuncTys; three whole-package walks that could fuse. None of this
matters at prototype scale; all of it needs numbers at stdlib scale. Add a compile-time
benchmark to the perf suite *before* optimizing.

## 8. Migration tooling (M — and a gift, not a chore)

Production migration of an ecosystem cannot be hand-annotation. The prototype already
contains the tool in embryo: run the checking walker in collect mode over a package and
the residual set per declaration IS the minimal clause. A `--suggest-throws` mode (or a
fixer emitting diffs) reuses `CollectingMissHandler` unchanged. Recommend building this
during our own stdlib migration — it pays for itself immediately and ships as the
ecosystem's migration story.

## 9. Spec-fold-back (S–M, organizational)

Before stabilization, the proposal text must absorb: the 14 author rulings, D1–D17
(especially D15/D16/D17), the A/B ledger sections (ratified deviations and
interpretations), resolved Q1–Q4, and the inventory classification principle. The
prototype is currently the only artifact where several normative behaviors are stated
(e.g. union-not-append for assumptions, spawn's empty stack, catch-outside-try scoping,
misplaced-annotation-is-error). A spec no one can implement without reading our ledger
is not stabilized.

## 10. What the prototype should NOT try to close

Worth saying explicitly: the remaining §8.10/§8.11/§8.3–8.5 features, the R6 site audit, and
the diagnostics polish are all *cheaper to redo on the production base* than to perfect
here if the base refactors of §2 happen. The prototype's job — de-risking the semantics,
finding the 20+ defects the ledger records, proving the pipeline order, and producing the
test corpus — is largely done. Further prototype investment should optimize for *transfer*
(tests, ledger, spec text), not for polish.
