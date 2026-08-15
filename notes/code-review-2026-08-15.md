# Code review: checked-exceptions prototype (branch `chexc`)

Date: 2026-08-15. Reviewer: Claude (self-review of the full branch, with fresh adversarial
probes against the built compiler — every non-obvious claim below was verified by running
code or reading the exact lines, not from memory).

Scope: 12 commits, 70 files, +3396/−743 vs upstream base `098c1b26`, across
`cangjie_compiler` + `cangjie_test` (+ one unpushed `cangjie_runtime` commit). Nine proposal
features implemented; CheckedExceptions suite 74/74, ctest 49/49, last full LLT regression
5949/5954 (5 = since-removed placeholder groups).

---

## 1. Architecture verdict

Three load-bearing decisions, all of which held under later features:

- **`FuncTy::capTys` participates in interning identity but never enters `typeArgs`.**
  This is what erases capabilities from CHIR/codegen — and the branch touches **zero**
  backend files (verified: no CHIR/CodeGen paths in the diff). Every feature since —
  aliases, inference, serialization, effects — rode on it unchanged.
- **`CAPABILITY_CHECK` is a pure check with a miss-handler seam.** Inference reuses the
  checking walker wholesale (`CollectingMissHandler`); assumption imports and `performs`
  both slotted into the same walker with no new pass. The seam earned its keep three times.
- **Phantom capabilities → linear phase order.** `types+modes → cap params → cap args →
  scope check` survived contact with effects. But note D17's time bomb: sharing one
  capability list between `throws` and `performs` is valid ONLY while both are phantom;
  evidence passing (§8.2) forces a split. This is recorded, not deferred silently.

**The recurring defect class** — the single most important thing to know when extending
this code: capability lists survive only on paths built for them and vanish wherever
pre-existing machinery reconstructs a type or declaration. Every instance found so far:
MF1 (accessor desugar), MF3 (`GetAllGenericTys`), `PreSetDeclType`, C1 (cjo loader),
C2 (incremental), the imported-accessor fallback, and E2 (try/handle retyped lambda copy).
There are **118** `GetFunctionTy` call sites not visibly passing a capability list (most
legitimately capability-free — primitives, CFuncs, tests — but nothing separates the
benign from the silent-drop sites except a targeted audit). Recommendation R6.

## 2. New findings from this review (all verified today)

| # | Sev | Finding |
|---|---|---|
| F1 | **HIGH** | `ASTHasher` never hashes `performsClause` (`throwsClause` is hashed at lines 340, 661, 1099 and `capturesClause` at 1215; `performs` at none). A declaration whose ONLY change is its `performs` clause keeps its hash, so incremental compilation will not re-check dependents → stale effect obligations. Same bug class as C2, one layer up. Fix is mechanical: add to the same three sites. |
| F2 | MED | Clause order is not enforced. `func f(): T throws E performs H` compiles clean (probe r3), violating §9.1 rule 8 (`performs` before `throws`). Cause: the two `ParseCapabilityClauses` call sites around generic constraints let the second pick up whichever clause the first left. The functional-type path rejects wrong order but with a misleading "expected `->`" diagnostic. |
| F3 | LOW | Effect misses are diagnosed as `CanThrow<Cmd>`; proposal §8.2 names the effect capability `Handler<Cmd>`. One kind-keyed message template fixes it. |
| F4 | LOW | A duplicate `performs` clause is diagnosed with the duplicate-`throws` wording. |
| F5 | LOW | `PrintNode` omits `performsClause` — AST dumps lie by omission for effect clauses. |
| F6 | LOW | Repo hygiene: the **notes repo has no remote** — the ledger, decisions, author questions and this review exist on one machine only; `cangjie_runtime` is 1 commit ahead unpushed (`bf71deb`, UncheckedException); stray `canon_tmp/`, `perf_tmp/`, `review_tmp/` dirs in the workdir. |

## 3. Probed and refuted (the E2 fix holds)

Because the E2 hole (try/handle regions unchecked) came from the parser cloning blocks into
lambdas, I probed the two sibling shapes with the built compiler:

- a `throw` inside the **finally** block of a try/handle → correctly errors (probe r1);
- a `throw` inside a **catch** body of a try that also has handlers → correctly errors (r2).

So the fix covers all three block kinds, not just the try block where the hole was found.

## 4. Standing accepted gaps (ledger cross-refs, not re-litigated)

C4 `...` marker parse-rejected · C5 macros cannot emit clauses (NodeFormat) · C7/C8
diagnostics polish · C9 LSP instance no-ops the pass · MF8 non-private static class members
need explicit clauses · MF2 function-value-formation half · U1 upstream `IsLegalAccess`
null-deref (worked around, unfixed upstream) · Q1–Q4 §5.2.2 readings awaiting author ·
D17 list split required under evidence passing.

## 5. Test coverage

**Strong:** the discriminating tests are negative — they caught the `IsCommandTy` generic
bug (inference silently swallowing effect requirements) and E2; the serialization matrix
covers every boundary shape incl. an incremental case and a byte-level canonical-form
check; suite is now all-green by policy (revised D13), so any failure is signal.

**Gaps, in priority order:**
1. Cross-package `performs` — capTys serialize, so it *should* work, but nothing tests it.
2. Generic commands (`performs Cmd<T>`, instantiation at call sites).
3. `performs` on property accessors, lambdas and functional types (parser paths exist and
   are plumbed; only declaration-level `performs` is exercised end to end).
4. Assumption imports × incremental compilation.
5. Cross-package captures of a *generic* capturing class.
6. `xpkg_captures_pos` does not discriminate (documented in its commit; kept as runtime
   sanity only).

## 6. Code quality notes

- Comment discipline is the branch's best property: nearly every non-obvious block cites
  its proposal section, so code→spec tracing works in both directions.
- Minor duplication/cost (all prototype-acceptable, listed for honesty):
  `CollectAssumedThrows` runs twice per package (inference + reporting pass);
  `NormalizeCapTys` is O(n²) subtype calls per list; `ChkAssumeThrowsAnnotations` walks the
  whole package even when no file has the annotation; `IsCommandTy` re-fetches the Command
  decl and allocates a supertype set per missed demand.
- The E2 fix ("walk whichever copy carries types") is a heuristic coupled to parser
  internals; an assertion (`tryLambda != null ⇒ !handlers.empty()`) would harden it.

## 7. Recommendations, ordered

1. **R1 (do before stdlib migration): fix F1** — add `performsClause` to the three
   ASTHasher sites, plus an incremental LLT case mirroring `incr_caps` with a `performs`
   clause change.
2. **R2: enforce clause order** in `ParseCapabilityClauses` (track which clauses were seen
   in which order; diagnose on `performs` after `throws`) and give the functional-type path
   a real diagnostic.
3. **R3: repo hygiene** — add a remote for the notes repo and push; push `cangjie_runtime`;
   delete stray workdir dirs.
4. **R4: add the two highest-value missing tests** (cross-package performs, generic
   command) before the stdlib migration exercises those paths blind.
5. **R5: diagnostics pass** (F3, F4, C7, C8) — can ride the stdlib-migration milestone.
6. **R6: audit the 118 bare `GetFunctionTy` sites** — one sweep, classifying each as
   capability-free-by-construction or a latent drop site. The defect class has produced
   seven confirmed instances; the enumeration is the only way to bound it.

## 8. Process notes (brief)

Three stash/split entanglement incidents (all caught pre-commit: `git status`, linker,
regressing test) traced to one sequencing mistake — building feature N+1 on uncommitted
feature N. Rule adopted: commit on green. The wrong-cwd/stale-binary trap recurred until
absolute paths + explicit BUILD-exit checks became habit; `cj.py` now caps ctest
parallelism, retiring the MacroTest false alarm. The author's all-green-suite directive
removed a standing 5-failure noise floor that had already cost one masked regression.
