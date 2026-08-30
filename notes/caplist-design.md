# Canonical capability lists (I30) — design note

**Problem.** The proposal makes the *semantic form* of a capability list normative: a duplicate
entry, or one covered by a more general entry of the same list, **is not part of the list**, and
"every rule of this document that compares or consumes lists operates on semantic forms"
(§3.2 rule 2). The prototype satisfies that behaviourally — every comparison is coverage-based —
but not in **type identity**: `FuncTy` stores the raw, order-sensitive `capTys` it was built with,
and identity is what interning keys on. Observable in three places, all found by review or probe:

1. **Invariant positions.** `Box<() throws (Base, Derived) -> Unit>` is not assignable to
   `Box<() throws Base -> Unit>` though the two lists have one semantic form. Subtyping of the
   *element* never runs — invariance compares identity.
2. **Printing.** Diagnostics show the raw spelling, including entries the language says are not
   there, and including entries that instantiated to unchecked types (which the coverage fix of
   2026-08-30 made assignable but did not remove from the type).
3. **Metadata churn.** The `.cjo` normalizes on the way out, so a package's own types and the
   types its consumers reconstruct can differ in spelling — harmless today because consumers
   compare by coverage, but it is one more place where "the same list" has two representations.

**Non-goal.** This note does not split `throws` from `performs` storage (D17) and does not change
what a list *means*. It makes one representation canonical.

## Why not normalize at interning

Tried 2026-08-22 and reverted: `GetTypeTy<FuncTy>` runs while types are being formed, and coverage
needs `IsSubtype`, which re-enters type formation. 17 tests broke across generics, serialization
and lambda checking. The lesson stands: **normalization must never run inside the interning path.**

## The design: normalize at producers

One function — `TypeManager::NormalizeCapTys`, which already exists and is already shared with the
serializer — applied at the four boundaries where a capability list is *produced*. Everything
downstream then interns the canonical form, so identity, subtyping, joins, printing and metadata
agree without any of them changing.

Normalization = (a) drop duplicates, (b) drop entries covered by another entry of the same list,
(c) drop concrete entries whose type is an unchecked exception — the rule of §5.1.2, using the
`uncheckedExceptionTy` the manager now holds — and (d) return the list untouched when it still
contains an inference placeholder (already the behaviour: comparing would bind it).

| # | Producer | Site |
|---|---|---|
| 1 | Clause elaboration for declarations | `TypeChecker.cpp` (`GetFuncBodyCapTys` consumers, ~line 504, 731), `PreCheck.cpp:1824` |
| 2 | Clause elaboration for functional **type nodes** | the `FuncType` path that builds a `FuncTy` from `ft.throwsClause` / `ft.performsClause` |
| 3 | Generic substitution | the `FuncTy` branch of `GetInstantiatedTy` — this is where an entry becomes unchecked or becomes covered by a sibling |
| 4 | Inferred lists written back | `CompleteInferredCapabilityTypes` |

Joins and meets already normalize (`JoinOrMeetCapTys`), and the loader
(`ReferenceLoader.cpp:380`) reads lists the writer already normalized — but it gets (1)'s treatment
anyway, so a `.cjo` from an older compiler cannot smuggle a raw list in.

**Ordering.** Normalization sorts nothing: it preserves first-seen order among the entries it
keeps, which is what the serializer's stable order already assumes and what keeps diagnostics
reading in source order.

## What this closes

- I30's three symptoms above.
- The residue of the 2026-08-30 unchecked-instantiation fix: coverage currently *tolerates* an
  unchecked entry; after (3) the entry is gone from the type, so `safeThrow<ReqExc>` and the
  clause-free shape are literally one type, as §5.1.2 says.
- The MF-class question "can a rebuilt type differ from the original" for capability lists
  specifically: after this, two lists with the same semantic content are the same pointer.

## What this does NOT close: C16

Printing a mixed list as `throws (A, C)` where `C` is a command needs the *kind* of each entry, and
`Ty::String()` has no access to the import manager to ask whether `C <: Command`. Three options
were considered:

- a `capKinds` bitmask beside `capTys`, filled at elaboration — but every `GetFunctionTy` caller
  would have to supply or preserve it, which is exactly the defaulted-parameter trap that already
  loses lists (the reviewer's point about `GetFunctionTy`);
- a process-global pointer to the `Command` declaration consulted from `String()` — smallest
  change, worst taste, and wrong under multiple compiler instances;
- the D17 split (separate `throwsTys` / `performsTys`), which is the honest fix and is deliberately
  deferred to evidence passing.

**Decision: C16 stays recorded, not fixed here.** It is a printing defect with no semantic effect;
the kind is already carried by the entry's own hierarchy everywhere it matters (discharge never
crosses kinds).

## Verification

1. `compiler/CheckedExceptions` + `compiler/Sema/effect` — the feature's own suites.
2. **`compiler/Sema` in full (3,934 cases)** — this touches type identity, so the general
   type-checking suite is the real gate; the 2026-08-22 attempt was caught exactly there.
3. `compiler/CheckedExceptions/serialization` specifically, for `.cjo` round-trips.
4. std at `warn` and stdx at `warn` — both must stay green, and the stdx sweep must not grow.
5. New tests: `Box` invariance both directions; a printed type in a diagnostic showing the
   canonical form; `safeThrow<Unchecked>` assignable *and* printing clause-free; a duplicate
   spelled list interning to the same type as its canonical twin.
