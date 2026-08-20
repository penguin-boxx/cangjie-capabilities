# Open questions for the author

Proposal-text ambiguities where the implementation had to pick a reading. Each entry records
what I chose, why, and what it costs to change the decision later. **Nothing here is blocking**
— the prototype builds and is tested under the chosen reading. These are for ratification.

Related files, which this one deliberately does not duplicate:
- `notes/autonomous-decisions.md` — decisions I made and consider settled (D1–D16).
- `notes/proposal-implementation-gaps.md` — divergences between proposal and implementation.
- `notes/stdlib-exception-inventory.md` — the 18 `UNCERTAIN` stdlib migration items.

Status legend: **OPEN** = awaiting your call · **RATIFIED** = you decided, decision recorded.

---

## Q1 §5.2.2 — Is an assumption import per FILE or per PACKAGE? · OPEN

**Implemented:** per file.

**The choice.** CangJie imports are file-scoped, so I scoped the trust claim to the file that
wrote the import. Consequence: in a multi-file package,

```swift
// a.cj
@AssumeThrows[SqlException]
import legacy_db.*
```

imposes nothing on calls to `legacy_db` made from `b.cj` — `b.cj` must repeat the annotation on
its own import.

**Why this reading.** §5.2.2 says "the import is where the trust relationship lives", and imports
are per file; this also matches how `@When` and import visibility already behave.

**The alternative.** An assumption is a claim about a *dependency*, and dependencies are a
package-level notion, so one annotation anywhere in the package could cover every call into that
package from the whole package. More convenient and harder to get subtly wrong (no way to forget
the annotation in one file and silently lose the obligations), at the cost of action at a
distance: a call in `b.cj` acquiring an obligation from a line in `a.cj`.

**Cost of changing.** Widening file → package is backward compatible: strictly more calls acquire
obligations, and code that annotated every file keeps compiling. Narrowing package → file is a
breaking change. This is why I took the conservative side.

**Ask.** Please state which §5.2.2 means. The proposal currently does not say — and the 2026-08-20 update's §9.4 ("the package is the unit of the analysis") sharpens the tension; see D-6 in notes/proposal-update-review-2026-08-20.md.

---

## Q2 §5.2.2 — What does an explicitly empty `@AssumeThrows[]` mean? · OPEN

**Implemented:** identical to the bare `@AssumeThrows`, i.e. assumes `Exception`.

**The choice.** The proposal specifies the bare form assumes `Exception` but is silent on an
explicit empty list. I treat both the same rather than inventing a second meaning.

**The alternative.** Read `[]` as "assume nothing" — a no-op, matching the read-as-empty default.
That has a real argument behind it: `throws ()` is meaningful as an *authoritative* empty clause,
so a reader may expect `[]` to be its analogue. But assumption imports have no authoritative
notion — the default already is empty — so "assume nothing" is exactly "write no annotation",
making the form useless and a plausible typo silently inert.

**Cost of changing.** Low either way; the two readings differ only for a form nobody should write.
Cheapest resolution may be to reject `@AssumeThrows[]` outright as an error.

**Ask.** Bare-equivalent (current), no-op, or rejected?

---

## Q3 §5.2.2 — Does an assumption cover SUBPACKAGES of the named package? · OPEN

**Implemented:** no. Matching is exact on the callee's `fullPackageName`.

**The choice.** `@AssumeThrows[E] import legacy.db.*` imposes `E` on calls into `legacy.db` and
**not** on calls into `legacy.db.internal`, even though the latter is a subpackage. The claim is
registered under every name the import could denote (`ImportContent::GetPossiblePackageNames()`),
so `import legacy.db`, `import legacy.db.*` and `import legacy.db.query` all match `legacy.db`
itself — but nothing prefix-matches.

**Why this reading.** Each subpackage is imported separately and is a separate dependency; an
assumption that silently spread down a package tree would be a broader claim than the user wrote.

**The alternative.** Prefix matching, so one annotation covers a dependency's whole tree. More
convenient for a large unchecked dependency; correspondingly easier to over-claim.

**Cost of changing.** Widening exact → prefix is backward compatible (strictly more obligations).

**Ask.** Confirm exact matching, or ask for prefix matching.

---

## Q4 §5.2.2 vs §5.2.3 — Assumptions do not reach function VALUES obtained from the package · OPEN

**Implemented:** the assumed list is imposed on *resolved calls* into the assumed package. A
function value obtained from an unchecked package and called later carries no capability list, so
its call site acquires nothing.

```swift
@AssumeThrows[SqlException]
import legacy_db.*

let f = legacy_db.getHandler()  // f : (String) -> Int64, no capabilities
f("select 1")                   // no SqlException obligation
```

**Why this reading.** §5.2.2 imposes the list "on every call into that package"; a call through a
value is a call into a function type, not into the package, and §5.2.3 already treats function
values at the boundary as their own topic. Imposing obligations on values would require tracking
provenance of the value through the type system, which the erasure design deliberately avoids.

**The alternative.** Impose the assumed list when forming a function value from an assumed
package's declaration — i.e. give the resulting value the assumed capability list. Coherent, and
closer to "every call", but it makes the assumed list part of a *type*, which then flows into
inference and across package boundaries in a way a purely consumer-local claim should not.

**Cost of changing.** Moderate: it moves assumptions from the demand side into type formation.
Better decided before the serialization milestone fixes what crosses package boundaries.

**Ask.** Confirm calls-only (current), or ask for value-formation coverage.

---

## Q5 §8.10.1 — Do conversions apply to `throw` expressions, or to calls only? · OPEN (extension-scoped since 2026-08-20: conversions moved out of the base design, so this is moot for v1 and applies within the §8.10 extension)

**Planned (P-C1 in conversions-adapt-plan.md):** uniformly — call demands, `throw`-expression
demands, and assumed demands all attempt conversion; captures and effect demands never do.

**The tension.** §6.2.1 opens with "for each call site `e`", but §3.3's general rule says
"if no suitable capability is found, exception conversions are attempted as a last resort",
which covers demands generally, and §5.2.2 explicitly says assumed requirements participate.
A raw `throw eFrom` with only a `To` capability in scope converts coherently
(`try { throw eFrom } catch ...` — the degenerate wrap), and excluding it would make
`throw e` and `call-that-throws e` behave differently for no user-visible reason.

**Cost of changing.** Narrowing to calls-only later is a small resolver filter; widening is
what is implemented. Ask: confirm uniform, or restrict to calls.

---

## Q6 §5.2.2 — Should a misplaced `@AssumeThrows` be an error? · RATIFIED (self, D15)

**Implemented:** error `sema_chexc_assume_throws_not_on_import`.

Recorded here only because it is a user-visible rule the proposal does not state. An annotation
that is silently inert reads as a claim being honoured, which is the worst failure mode for a
trust feature — so it is rejected rather than ignored. Flagging in case you would rather it be a
warning; no further action expected.
