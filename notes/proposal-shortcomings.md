# Proposal shortcomings, by chapter

A by-chapter view of everything currently standing against the **text** of *Checked exceptions for
Cangjie*, arranged for editing the document chapter by chapter. `gap-analysis.md` Part II remains
the ledger of record — every item here carries its ledger ID, and this file is regenerated from it,
not maintained independently. Measured against the revision of **2026-08-30 17:54**; chapter
numbers are that revision's and are given for orientation only (the corpus convention stands: cite
by title, numbering rots — which is itself item E-5).

Status tags: **[open]** needs an author decision or text work · **[ruled]** decided, text update
pending · **[wording]** local rewording, no decision needed · **[tension]** a design cost to state,
not a defect · **[interlock]** blocked on / blocking something outside the text.

---

## 1 · Introduction — clean

No standing items. The introduction's critique of Java interface pollution is load-bearing for two
items elsewhere: D-4 (ch. 6) and D-7 (ch. 2).

## 2 · Idea overview

- **[wording] E-1** — "Stack traces and cause chains" writes `eErr.suppressed += eFrom`, while the
  toolchain chapter specifies `suppressed` as a read-only snapshot. One of the two must yield.
- **[tension] D-7** — with conversions demoted to an extension, handle-convert-rethrow at every
  abstraction boundary is manual in v1 — the very boilerplate the design calls "very common".
  A defensible trade, but state it as an accepted v1 cost where the decision pressure is discussed.

## 3 · Implicit capability passing design

- **[ruled] E-19 / I31** — a property in an interface cannot declare what its accessors throw: an
  abstract accessor cannot carry a clause (needs a body), and the property itself has no clause
  position — while an interface *method* declares its list freely. Bites `std.net`'s socket
  interfaces, whose doc comments promise `SocketException` the type system cannot see. **Author
  ruled 2026-08-30: support both forms** — a clause on a bodyless accessor and a clause on the
  property, distributed to accessors without their own. The text must gain both (this chapter and
  the grammar chapter); design in `property-clauses-design.md`, two sub-questions there (Q14
  distribution-vs-prohibition, Q15 sugar-vs-first-class in metadata).
- **[wording] E-16** — the try-with-resources bullet states the implicit `close()` is inside the
  try's scope *and* flags its own premise "to be confirmed against the language specification".
  The premise is now probe-confirmed (the closing desugars inner to the catches, so the same
  clauses catch it): bless it against the spec and drop the TODO. The bullet should not pre-answer
  its own open question either way.
- **[wording] E-6** — the rule-by-rule rewrite dropped two cross-references: the entry rule no
  longer points at the unchecked-entry restriction (which now lives only in "Unchecked
  exceptions"), and the one-clause rule no longer points at "Interaction with an explicit
  `throws`". Both rules are implemented; both had to be found by reading other chapters.

## 4 · Escape analysis   *(out of the implementation tier by ruling; text items only)*

- **[open] E-17** — the chapter states the capability-region rules for the **base design**, but the
  author has scoped regions to Modal Cangjie (ruling of 2026-08-23). Either the chapter says so —
  regions are a Modal-tier requirement — or the base design permanently claims rules its base tier
  will not enforce, which is exactly the guarantee gap the state table warns about. The two region
  rules living in "Effect requirements" (resumptions handler-bound; `resume with` a flow boundary)
  need the same scoping.
- **[open] D-0** — three additions where the phase ordering is recommended: (i) state that the
  ordering is sound because capability capture only ever *caps* a mode, and that
  overload-by-receiver-mode conflicts are **rejected**, not re-resolved (a completeness loss the
  text should own); (ii) promote "materializing capabilities changes the lowering, not which
  programs type-check" from mid-paragraph to a stated invariant the exception-safety theorem
  references; (iii) elevate open-question item 3 (the forwarding rule, read literally, rejects
  every capability propagation step) from "open question" to "blocking dependency on the Modal
  authors".
- **[interlock]** — the capability-blind treatment of a literal's mode (modes from ordinary
  captures only; capability captures arrive later and only cap) contradicts Modal's own "a
  lambda's mode is determined by its captures" as written. This must land as an explicit
  **amendment to the Modal proposal**, not remain an internal assumption of this one. Both
  external reviews flagged it independently.
- **[tension]** — the safety theorem's preservation premise rests on the chapter's own unresolved
  open questions (forwarding, unwinding, `finally`/`exclave`, `local?` calls, reflective
  construction, future resumptions). The text is honest about each; what is missing is the single
  sentence that the theorem is **blocked** on that list, not merely adjacent to it.

## 5 · Further language features

- **[open] D-0b — the chapter's central architectural gap, confirmed by the second review.**
  "Phase ordering" says *type/mode skeletons → capability parameters → clause components of types
  → capability arguments* and that no earlier stage consults inferred lists — but never defines
  what a "skeleton" leaves unfixed. An early stage can *fix a result computed while a list was
  temporarily empty*, and completion cannot reach it afterwards; every confirmed inference defect
  in the prototype (the reference leak, stale joins, the size-compared completion) is this one
  mechanism. The chapter needs a normative paragraph enumerating (a) which type products are
  completed after inference — references, bound methods, inferred variable types, returns,
  joins/meets, invariant containers, generated wrappers — and (b) which constraints are replayed.
  Companion point: capability lists are excluded from type *inference* but still participate in
  type *checking*; the text leans on the first as if it settled the second.
- **[wording] E-20** — "requirement checking is level-independent" now reads ambiguously beside
  the independent effect axis; say "independent of the *exception* level".
- **[wording] E-21** — the heading "No unchecked commands" sits above the rule introducing
  unchecked-effects packages, `@AssumePerforms` and `unsafeCanPerform`. True as stated (no
  unchecked command *hierarchy*), but it reads as "no unchecked escape mechanisms".
- **[wording] E-22** — `unsafeCanThrow`'s subsection should state the carrier restriction locally
  ("the callback must not return or store a carrier of the fabricated capability") instead of
  leaving it implicit in the regions chapter; for an `unsafe` intrinsic the rule belongs at the
  declaration.
- **[open] E-15** — the effect examples bind a `Resumption` value (`handle (…, r: Resumption<…>)`)
  that the effect-handler implementation does not have — `resume` is a statement, and rule 4 of
  this very chapter says a first-class resumption does not exist. The examples should use the
  implemented shape.
- **[wording] E-18** — "a non-public macro can never be an expansion root and is an ordinary
  inference-eligible declaration" describes a declaration the language rejects: the parser
  mandates `public` on every macro. Drop the sentence or state that every macro is exported.
- **[tension, review]** — "Effect requirements" has grown a flag, a severity, a warning group, a
  metadata level, a boundary semantics, an assumption annotation and an escape hatch: nearly a
  proposal of its own inside one numbered rule list. Consider promoting it to a chapter (or an
  appendix) so the size of the change is visible; the substitution framing ("every rule of the
  exception axis, substituted") would survive the move.
- **[tension] D-3** — `@AssumeThrows` *adds* obligations (errs safe), `unsafeCanThrow` *removes*
  them (errs unsafe). The polarity note exists; cross-link the two constructs both ways.
- **[tension] D-5** — the escape hatch takes a single `E`; several specific types need nesting or
  the coarse `E = Exception`. A tuple form consistent with capability-list aliases would cost
  little. (Named-pair rationale in "Discussion" does not preclude it.)
- **[interlock] E-4** — the stream-interface ruling ("streams declare `throws IOException`,
  implementations narrow") is inconsistent with `ContentFormatException <: Exception` as shipped:
  `StringReader.next()` infers a type the clause-free `Iterator.next` cannot cover. Needs the
  Q-STD-9 ruling (ch. 11) before stdlib batch 3a; the text and the hierarchy must move together.

## 6 · Compatibility, interoperability and migration

- **[wording] E-14** — the state table's Modal-less row, "partial: carrier escape unverified,
  within a function included", reads on first pass as "within a function is covered" — the
  opposite of the intent. Reword.
- **[wording] E-2** — the toolchain chapter says the stdlib classification is "confirmed by the
  annotation audit"; the migration section says "to be confirmed". Pick a tense.
- **[open] D-4** — the introduction criticizes Java for interface pollution; the migration
  chapter's fixer mechanically writes inferred lists onto exported declarations. Prototype
  evidence: mechanical inference yields `FSException` on a test framework's API and raw
  `Exception` on `std.net` — true lists, wrong APIs. The fixer's public-surface caveat exists;
  strengthen it to "an API-design proposal requiring review", and note that abstraction
  boundaries are exactly where the demoted conversions were supposed to help.

## 7 · Known limitations

- **[tension] D-2** — list-variable invariance makes `Future` collections monomorphic:
  `Array<Future<Unit, E>>` needs one list for every element, so heterogeneous futures share a
  collection only at `E = Exception`. State the limitation and the idiom.
- **[open] D-8** — both external reviews independently concluded the `spawn`/lazy restriction is
  heavier than its placement suggests: without capability-list polymorphism, `spawn` cannot
  release checked exceptions and deferred work is checked at construction. The text should say
  whether "Capability-list polymorphism" is an optional extension or a practical prerequisite for
  any real concurrency API — the reviews say the latter.

## 8 · Possible extensions

- **[open] Q5** — do conversions apply to `throw` expressions or to calls only? Moot for v1
  (conversions are an extension) but the extension section should carry the answer it intends.
- No other standing items; the encapsulation and polymorphism extensions read consistently with
  the base design as revised.

## 9 · Discussion — clean

E-13 closed by revision; the escape-hatch naming rationale and innermost-first selection are now
recorded here. No standing items.

## 10 · Grammar impact

- **[open]** — the formal grammar is still the chapter's own TODO; both reviews list it among the
  stabilization blockers (together with typing judgments, which no chapter owns).
- **[ruled] E-19 follow-up** — the two property-clause forms must appear here once ch. 3 gains
  them: the bodyless-accessor production and the property-level clause position.

## 11 · Standard library and toolchain impact

- **[open] Q-STD-9 — the SPI-interface question; the single ruling the migration keeps hitting.**
  An interface in `std` declares no clause, implementations elsewhere throw — `Iterator.next`
  (E-4), `Resource.close` (E-16's neighbour), `ToString.toString` (Q-STD-8), `Digest.write`
  (whose stdx implementations raise a type `std` cannot even name). Blocks the zlib/tar/http/tls
  rings. Three coherent answers are in the ledger with a recommendation: (a) SPI interfaces
  declare an owned std-level checked exception; (b) SPI implementations raise unchecked (the
  answer `@Derive` already got); (c) inferable interface clauses — rejected by the base design.
- **[open] Q-STD-1** — `std.ast` is 67% of the whole std surface (≈2,800 warnings); recommend
  unchecked (framework data-integrity), optionally keeping `ParseASTException` checked.
- **[open] Q-STD-2** — raw `throw Exception(...)` (≈242 sites): `throws Exception` annotations are
  uninformative; per-package specific types are API design, not annotation work.
- **[open] Q-STD-3** — `std.reflect` (254): split lookup-failure (checked) from misuse
  (unchecked); re-parents the hierarchy, so it is a call.
- **[open] Q-STD-4 / Q-STD-7** — the small sets (runtime/env/unittest.common), and unittest's 23
  inherited fs obligations (recommend catch-and-wrap, not leaking `FSException` through a test
  framework's API).
- **[tension] D-1** — capturing iterators (migration batch 3b) buy uniformity at three costs: the
  flagship IO case depends on an unconfirmed Modal requirement; the obligation moves to
  construction (every `StringReader` constructor site pays, including tests that never iterate);
  and in the degraded mode the escaping iterator is precisely the phantom hole on the most common
  API the library ships.
- **[interlock]** — the closed-build verifier, the fixer, and the lints are specified here and
  exist nowhere; fine for a proposal, but the chapter should say which of them gate stabilization.

## 12 · TODO — one entry answerable now

The `close()`-desugaring question is answered by probe (inner to the catches — E-16): confirm
against the spec and retire it. The remaining entries (formal grammar, corpus study) stand; add
typing judgments for resolution, inference and region flow — both reviews list their absence as a
stabilization blocker no current TODO covers.

## 13 · Glossary — clean

No standing items.

---

## Cross-cutting

- **[open] E-5** — two renumberings in one day kept internal consistency but rot every external
  citation; freeze numbering, or publish stable anchors. (This file cites by title for exactly
  that reason.)
- **[tension]** — the same code graded B against the previous revision and C+ against the current
  one *in the same review*: conformance to a moving text is a two-argument predicate. Not a text
  defect, but an argument for marking revisions (a date in the header, a change log) so claims of
  conformance can name their target.

## Resolved by the current revision — for the record

E-3 (`unsafeCanThrow` with the Modal-less no-mode note), E-13 (mixed-kind `captures` entry rule),
D-6 (assumption imports package-scoped), Q9 (parameter-typed cast targets accepted as an unchecked
boundary), Q10/Q11 (author rulings, implemented), Q12/`resume throwing` (rewritten as the
sibling-catch rule — now implementation gap I37, not a text question), I29's macro sentence
("within a macro package"), and the free declaration clause order with its recorded rationale.
