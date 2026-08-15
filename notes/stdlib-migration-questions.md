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

## Bookkeeping

- The inventory needs follow-up rows for the std.ast family and every type in Q-STD-2/3
  it did not enumerate; added to its TODO header when rulings land.
- Once batch-1 clauses land, `cj.py build_std` permanently gains
  `--build-args=--experimental --build-args=--enable-checked-exceptions=warn` — a clause
  does not parse with the feature off (the ratchet).
- Downstream effect to expect: programs compiled WITH checking against the migrated SDK
  acquire real obligations from std's annotated surface (that is the point); our own
  CheckedExceptions tests will be re-gated after each batch.
