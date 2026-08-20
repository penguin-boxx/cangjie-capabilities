# Stdlib migration: design decisions needed (phase 2)

Date: 2026-08-15. Input: warn-mode build of the full stdlib after phase 1 (the 26 obvious
re-parents): **4,172 warnings, 47 (package, exception type) pairs**. Full per-site listing:
scratchpad `warn-classification.txt` (regenerable: `classify_warnings.py logs/std-warn1.log`).

Per the author directive, phase 2 annotates only the OBVIOUS checked flows and leaves the
rest as warnings. This file records everything that is NOT obvious — each with a
recommendation so a ruling can be applied mechanically — plus what was resolved
compiler-side. Companion: the 23 UNCERTAIN classes of `stdlib-exception-inventory.md`.

## Resolved compiler-side while migrating

- **The Error hierarchy demanded capabilities** (28 warnings in std.core alone;
  `OutOfMemoryError`, raw `Error`). `Error <: ToString` is a separate root, and the
  proposal's §1.1 split (fail-fast for bugs — Midori's Error Model) makes the intent
  clear: never tracked. `Demand` now exempts class types under neither tracked root.
  The first version of the exemption ("not under Exception") silently exempted every
  effect Command too — commands are also classes outside Exception — and the performs
  negative tests caught it within one build cycle. Recorded as decision D18.

## The annotation plan (what phase 2 does WITHOUT asking)

Criterion for "obvious": a public callable whose body directly throws (or transparently
propagates, one call ring, no catch) its package's canonical checked exception, where the
principle (I/O, parse, net, concurrency-wait → checked) decides without judgment.

- **Batch 1 (this pass):** std.fs → `throws FSException` (75 sites); std.io →
  `throws IOException` / `throws ContentFormatException` (22 sites).
- **Batch 2 (next pass):** std.regex `RegexException` (52); std.time `TimeParseException`,
  `InvalidDataException` (16 — parse per principle); std.process `ProcessException` (50);
  std.database.sql `SqlException` (22); std.net `SocketException`/`SocketTimeoutException`
  (140 — the *specific* socket types only, NOT the raw-Exception sites, see Q-STD-2).

Everything below stays a warning until ruled.

## Q-STD-1 · std.ast: 2,800 warnings (67% of total) — recommend unchecked

`FlatBuffersException` (1950), `ASTException` (806), `ParseASTException` (44) — thrown by
the macro/AST serialization machinery (including the vendored flatbuffers port). These
were never in the inventory: its grep enumerated `<: Exception` roots in `libs/std` and
these live in ast internals the first sweep did not classify.

**Recommendation: unchecked (re-parent), possibly excepting `ParseASTException`.**
Malformed-buffer and inconsistent-AST conditions are data-integrity/contract violations —
a macro author cannot meaningfully recover from a corrupt flatbuffer mid-expansion, and
2,800 standing warnings make warn-mode unusable for anyone compiling macro-heavy code.
`ParseASTException` is arguably genuine parse → checked; but its 44 sites sit on the same
internal surface. A split ruling (ParseASTException checked, rest unchecked) is coherent
if you want `std.ast.parse*` APIs to carry contracts.

## Q-STD-2 · Raw `throw Exception(...)` in public code — needs API design, not a clause

net 242 · unittest 192 · deriving.resolve 20 · ast 16 · core 10 · misc ~30. Annotating
these `throws Exception` would be true but maximally uninformative — every caller's catch
degrades to catch-all, which is §2.1's anti-pattern. The real fix is introducing specific
exception types per package (e.g. net's raw throws becoming `SocketException` siblings),
which changes public API and is not mine to decide.

**Recommendation:** rule per package. For std.net specifically the specific types already
exist — most raw sites look like legacy shortcuts; migrating them to `SocketException`
subtypes then annotating mechanically would clear 242 warnings with real information.

## Q-STD-3 · std.reflect: six types, 254 warnings — a genuine split

Dynamic-name lookups (`InfoNotFoundException` 98, `InvocationTargetException` 28) are
environmental — the name arrives at runtime; a caller CAN sensibly handle absence →
**checked**. Misuse types (`IllegalTypeException` 90, `IllegalSetException` 16,
`MisMatchException` 6) read as contract violations → **unchecked**. `ReflectException`
(16) is the umbrella parent — splitting its children across the boundary re-parents the
hierarchy, same shape as the IllegalFormatException conflict the inventory already flags.

**Recommendation:** checked = {InfoNotFound, InvocationTarget}, unchecked = the misuse
set, `ReflectException` stays checked as umbrella. Needs your call because it re-parents.

## Q-STD-4 · std.runtime, std.env, unittest.common — small, judgment-laden

- `MemoryInfoException`/`ProfilingInfoException` (12): environmental introspection
  failures → lean checked; tiny surface either way.
- `EnvException` (22): inventory-UNCERTAIN already (mixed contract/environmental sites —
  may want splitting).
- `DataModelException` (46) + `JsonException` (22) in unittest.common: parse-per-principle
  says checked, but they are framework-internal plumbing for test configuration; checked
  clauses here surface in every custom-configuration test signature.
  **Recommendation:** unchecked, as framework machinery (consistent with the phase-1
  unittest re-parents).

## Q-STD-5 · The io stream interfaces — RULED 2026-08-20 (proposal §11.2, option 1)

**Ruling in proposal text:** "streams declare `throws IOException`; in-memory
implementations override with narrower lists per §3.8." Implementation = batch 3, item B6
of notes/proposal-update-review-2026-08-20.md. Caveat E-4 there: `ContentFormatException`
is not under `IOException`, so the ruling as written cannot cover std.io's own read paths
until the author picks re-parent / declare-both / stay-off-interface.

(Original question kept below for the record.)

After three annotation rings, exactly six fs/io sites remain warning, and they are all
interface-bound: `File.read/write/seek/close` (IOStream, Seekable, Resource) and
`ByteBuffer.seek`, `ChainedInputStream.read`. Annotating an implementation whose interface
method has no clause violates §3.8 (an override may not require more than the declaration
it implements), so the clause must go on the INTERFACE — `InputStream.read`,
`OutputStream.write`, `Seekable.seek`, `Resource.close` in `libs/std/io/stream.cj`.

That is the single highest-leverage decision in the whole migration: those four methods are
the contract every stream in the ecosystem implements. Options:

1. **`throws IOException` on the interface methods.** Honest — a stream read genuinely can
   fail — and makes every IO consumer statically account for it. Cost: every implementation
   and every call site in the ecosystem is affected at once. This is the "IO is checked"
   world the proposal is arguably for.
2. **Leave the interfaces clause-free; make IO failures unchecked.** Zero ecosystem churn,
   but concedes that the largest recoverable-error domain in the standard library is
   outside the system, which undercuts the feature's main use case.
3. **Wait for §8.3 (discharge by eta-expansion) / capability-polymorphic interfaces.** The
   proposal's §8.3 sketches coercion; a `throws`-polymorphic `read` (Swift's `rethrows`
   shape) would let `File.read` declare and in-memory streams not. Not specified today.

**Recommendation: (1), but only as a deliberate ecosystem-wide decision, not a migration
side effect.** Until ruled, the six sites stay warnings.

## Q-STD-6 · `Iterator.next()` — RULED 2026-08-20 (proposal §11.2, a third way)

**Ruling:** not protocol polymorphism — "IO-backed iterators become capturing classes"
(`File.lines()` captures `CanThrow<IOException>`, is `local!`); `for-in` over `local!`
iterators is a Modal requirement to confirm (§4.4). Implementation = batch 3, item B7 of
the update review; the ruling's costs are documented there as D-1 (construction-site
obligations, §4.4 dependency, degraded-mode escape).

(Original question kept below for the record.)

`StringReader`'s two `next()` methods warn and cannot be annotated: `next()` comes from the
core `Iterator<T>` protocol, which has no clause, so §3.8 forbids adding one in the
implementation. Consequence: **no iterator anywhere can perform checked-throwing work**, so
`for (x in stream)` over anything fallible is impossible in checked code — the iteration is
either unchecked or must be rewritten as explicit calls.

This is precisely Swift's `rethrows` problem. A general answer needs capability
polymorphism over the protocol (`Iterator<T> throws E`), which is beyond the current
proposal. Ruling needed on whether iteration is in scope for the checked world at all; the
same argument applies to `Collection`, `Iterable`, and anything else with a fixed protocol.

## Q-STD-7 · unittest acquires fs obligations (23 sites)

Annotating fs made `std.unittest` warn at 23 sites where the framework touches the
filesystem (report writing, temp dirs). Annotating them would put `FSException` in the test
framework's public API, which every user test signature would then have to account for.
**Recommendation:** unittest catches and wraps internally (framework machinery, consistent
with the phase-1 re-parents), rather than propagating. Needs a ruling because it is API
surface, not a mechanical fact.

## Bookkeeping

- The inventory needs follow-up rows for the std.ast family and every type in Q-STD-2/3
  it did not enumerate; added to its TODO header when rulings land.
- Once batch-1 clauses land, `cj.py build_std` permanently gains
  `--build-args=--experimental --build-args=--enable-checked-exceptions=warn` — a clause
  does not parse with the feature off (the ratchet).
- Downstream effect to expect: programs compiled WITH checking against the migrated SDK
  acquire real obligations from std's annotated surface (that is the point); our own
  CheckedExceptions tests will be re-gated after each batch.
