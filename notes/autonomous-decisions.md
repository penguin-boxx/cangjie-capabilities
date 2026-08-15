# Autonomous implementation decisions

Decisions taken without author consultation, per the directive to work autonomously and
record core decisions. Each states the decision, why, and how to reverse it. Author: please
skim; anything marked ⚠ is a judgment call I would most like reviewed.

AUTHOR-CONFIRMED ORDER (2026-08-15):
1. §6.3 inference → `chexc`
2. §6.1 aliases → `chexc`
3. §5.2.2 assumption imports → `chexc`
4. cjo serialization / package metadata (closes gaps C1–C3) → `chexc`
   — author moved this AHEAD of conversions and adapt
5. §6.2 exception conversions → branch `chexc-conversions` (on top of chexc)
6. §6.5 adapt → branch `chexc-adapt` (on top of the above)
Features 5 and 6 stay on separate branches by author ruling: both synthesize runtime
constructs, and §6.5 is explicitly deferred by the proposal itself.

---

## D1 §6.5 adapt and §6.2 conversions live on separate branches (author ruling)

§6.5 opens: "Automatic adaptation is **not** proposed for the initial design … This section
records the intended shape of the extension." Author ruling 2026-08-15: implement both §6.5
and §6.2 on their own branches on top of `chexc` (`chexc-adapt`, `chexc-conversions`), so
neither speculative feature lands on the main line. `chexc` therefore carries only the
proposal's initial-design features. Reverse by deleting the branches.

## D2 §6.1: aliases expand during clause elaboration, not in the type system

A `typealias X = (A, B)` used in a `throws`/`captures` clause expands to the capability
list at clause-elaboration time (the same place clause types become `FuncTy::capTys`);
the alias remains an ordinary tuple typealias everywhere else. Expansion is recursive with
a visited-set cycle check; a cycle is a dedicated error. Consequence: no new type-system
concept, and `throws (A, B)` (parenthesised list) and `throws X` (tuple alias) produce
identical capability lists, which is what §6.1 specifies.
Element validation reuses the existing clause-entry rules (subtype of Exception, no
concrete unchecked type — §3.2 rules 3 and 5, as §6.1 requires).

## D3 §6.1: a bare tuple type in a clause is also a list

`throws (A, B)` already parses as a two-entry list (B2 in the gaps ledger). For symmetry a
tuple TYPE reaching clause elaboration (via an alias) expands the same way, so the two
spellings are indistinguishable after elaboration. Nested tuples flatten recursively.

## D4 §5.2.2: assumed lists are stored per (importing package, imported package)

`@AssumeThrows[E1, E2] import p` records the list against the imported package name in the
current package's context; `@AssumeThrows` bare means `Exception` (spec). At a call site
whose callee declaration belongs to an assumed package, the assumed list is demanded in
addition to the callee's own (currently empty — see C1) capability list. The record is
consumer-local and never serialized (spec: "never exported as facts about the dependency").
Reverse by deleting the annotation handling; no metadata implications.

## D5 §5.2.2: assumed demands are ordinary demands

They participate in inference, conversions, and the miss diagnostic exactly like declared
ones (spec says so for inference and conversions). The diagnostic names the assumption as
the source ("required by the call to 'f' (assumed by @AssumeThrows on 'import legacy.db')")
so the obligation is traceable to the import that created it.

## D6 ⚠ §5.2.2: applies to calls into the imported package only, not transitively

A call into package P assumed as throwing E demands E. Calls that P makes internally are
not re-examined (they are unchecked code). This matches "imposed as a throws list on every
call into that package" read literally. It also means assumption imports do not compose
transitively through re-exports — flagged because the spec does not discuss re-exports.

## D7 §6.2: conversions are decided in CapabilityCheck, applied in a later desugar

Capability checking runs before DESUGAR_AFTER_SEMA and must stay a pure check (architecture
invariant). So the miss path records a *conversion site* (call, From, To, the `convertFrom`
declaration) instead of mutating the AST; a new desugar step in DESUGAR_AFTER_SEMA wraps
the recorded calls in the synthesized `try/catch`. This keeps the "no type mutation during
checking" property that inference relies on.

## D8 §6.2: lookup is exact-From, single-step, and requires the target in scope

Implemented exactly as §6.2.1 rules 1–5: capability present → no conversion considered;
otherwise find visible `Convertible<From, To>` whose `To` capability IS in an active scope;
exactly one → convert; several → ambiguity error; none → the ordinary missing-capability
error. `From` matched by type identity, never by subtyping (rule 4). No chaining (rule 5).

## D9 §6.2: `captures` requirements never convert

Rule 6: conversion is not attempted for requirements arising from a capturing constructor
(or `adapt`), because the capability would be stored rather than used during the call. In
the implementation these demands are tagged at their origin (`DemandKind::Storage`) and the
conversion step skips them.

## D10 §6.2: settable `cause` is added to std.core; `suppressed` is deferred (author ruling)

Per §6.2.2, the generated handler is
`let eTo = To.convertFrom(eFrom); if (eTo.cause is None) { eTo.cause = eFrom }; throw eTo`.
Author ruling 2026-08-15: add a settable `cause` to std.core Exception (needed for the
core feature); DEFER `suppressed` — the `convertFrom`-throws case of §6.2.2 is recorded as
a gap instead of adding a second stdlib API.

## D11 §6.2: multiple converted requirements nest in canonical order, outermost first

§6.2.1 requires deterministic nesting. Canonical order = the normalized-list order of
§3.10.2 rule 1 (subsumed entries dropped, remainder sorted by type name), which is also
what the serialization milestone will use.

## D12 ⚠ §6.5: `adapt<I>(x)` synthesizes a capturing class, reusing §3.9 machinery

The synthesized class implements `I`, holds `x` in a field, forwards each method, and
carries a `captures` clause with the union of the forwarded methods' `throws` lists — so
construction demands those capabilities at the `adapt` site (§6.5 rules 2–3) through the
already-implemented §3.9 path. Method matching is by name and signature up to `throws`
lists (rule 1). Identity caveats (rule 4) are accepted as documented.

## D13 Test-first for every feature

Each feature gets a red-first LLT group under `compiler/CheckedExceptions/` committed
before implementation, positive and negative cases both, following the existing convention.
Groups: `aliases/`, `assume/`, `conversions/`, `adapt/`.

## D14 Stuck-work policy

Per the directive: if a feature cannot be finished, its work is committed on a branch
`chexc-<feature>` (not `chexc`), the reason recorded here and in the gaps ledger, and the
next feature is started. `chexc` stays green at every commit.

## D15 §5.2.2: the annotation is per file, and only `import` may carry it

`@AssumeThrows` is recorded per FILE, not per package: imports are file-scoped in CangJie,
so the file that wrote the import is exactly the scope of the consumer's trust claim. A
call is matched against the claim of `ce.curFile` (falling back to the file of the
enclosing declaration, for call sites rebuilt by a desugar that dropped `curFile`).

The claim is registered under every name `ImportContent::GetPossiblePackageNames()` yields,
so `import legacy.db.*`, `import legacy.db` and `import legacy.db.query` all match a callee
whose `fullPackageName` is `legacy.db`, and matching is exact on the callee's package —
no prefix matching, so a subpackage is not covered by its parent's assumption.

Placing it anywhere else is an ERROR (`sema_chexc_assume_throws_not_on_import`) rather than
being ignored: an inert annotation reads as a claim that is being honoured. The parser
accepts it on an import only when `--enable-checked-exceptions` is on; without the flag it
takes the pre-existing "unexpected annotation on import" path.

## D16 §5.2.2: `@AssumeThrows` with no list assumes `Exception`; the demand is a union

Both the bare form and an empty bracket list mean `Exception` (the proposal specifies the
bare form; an explicit `[]` is treated identically rather than given a second meaning).
Assumed entries are UNIONED into the call's demand list, never appended blindly — the
proposal's "assumptions only add obligations relative to the read-as-empty default" — so
assuming a type a checked dependency already declares changes nothing.

Assumed requirements reach inference through the same path as declared ones: the map is
built once per package and shared with the inferencer's checkers, so a clause-free internal
function calling into an assumed package has those types inferred into its list.
