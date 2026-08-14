# Proposal ↔ implementation inconsistencies

Living document — updated at every milestone gate. State as of M3 committed,
§6.4+§3.9 in implementation. Sections: (A) deviations ratified by the author,
(B) interpretations of ambiguous/underspecified text (ratified), (C) implementation
artifacts and restrictions the proposal does not sanction (each with its fix-by
milestone), (D) proposal features not yet implemented (roadmap ledger).

## A. Author-ratified deviations from proposal text

| # | Proposal | Implementation | Rationale / resolution |
|---|---|---|---|
| A1 | §3.3 diagnostic spells `CanThrow<E> @ local!` | Mode omitted: `(of type 'CanThrow<E>')` | Modes don't exist pre-Modal (ruling 3). Restore wording at Modal integration. |
| A2 | §5.5 degraded mode includes intra-function escape checks (use-after-try, assignment-out) | NO escape checks of any kind — checking is purely lexical/scope-based | Ruling 10: no hand-written escape analysis before Modal. Guarantee is weaker than §5.5 describes until Modal lands. Proposal §5.5 may deserve a note. |
| A3 | §3.9 rules 3/4: capture only in `this @ local!` ctors; body coverage depends on receiver modes | Pre-Modal: EVERY ctor captures; EVERY method/prop body covered | Rulings 11. Modal-mode rules take over when Modal lands. |
| A4 | §3.9 derives the primary-ctor ban from modes (primaries are `~local`) | Ban enforced directly, pre-Modal | Ruling 12, forward-compatible. |
| A5 | §4.2 spawn safety comes from Modal's spawn rule | Lexical rule: spawn bodies start with an empty capability scope stack | Ruling 5 — simplest sound equivalent pre-Modal. |
| A6 | §8 anticipates effects integration | try/handle, perform, resume are ignored entirely by capability checking | Ruling 4 (superseded by later directive: effects checking is a LATER milestone, after stdlib cleanup). |
| A7 | §6.4 splits checked/unchecked | M3 shipped all-checked; §6.4 in flight | Ruling 1 — transitional, closes with the current milestone. |
| A8 | (not in proposal) | `throws` banned on foreign funcs AND CFunc types | Author ruling (M2 round). Proposal could state this; §5.2 interop may revisit. |
| A9 | §3.10.2 rule 3 mentions error/warn levels per package | Implemented as per-invocation `--enable-checked-exceptions[=error|warn]` + `chexc` warn group | Ruling 8. Per-package level recording arrives with metadata (D5). |

## B. Ratified interpretations of ambiguous text

| # | Proposal text | Interpretation implemented |
|---|---|---|
| B1 | §3.7 "considered same types by overload resolution" | Overload-resolution-only rule: cap-differing FuncTys ARE distinct interned types; all overload/duplicate/shadow machinery compares modulo caps (EraseCapTys). |
| B2 | §3.4 grammar: `throws (E1, E2)` in types | After `throws`, `(` ALWAYS opens the capability list, never a paren/func type. |
| B3 | §3.3 "one capability per exception type listed in its catch patterns" — wildcard patterns unaddressed | `catch (_)` / wildcard supplies `CanThrow<Exception>` (mirrors Sema's caught-type computation). |
| B4 | §3.2 clause position | `throws` accepted before AND after `where`; duplicate clause diagnosed and dropped. |
| B5 | Bare-list vs parenthesised clause forms | Decls accept both `throws A, B` and `throws (A, B)`; functional types accept only `throws (…)` and single-type sugar `throws E ->` (commas belong to enclosing constructs). |
| B6 | (was a gap; author then added §3.4 join/meet text) | Join = union with redundancy pruning; meet = entries covered by every operand list. Implementation matches the added text. RESOLVED — kept for history. |
| B7 | §6.3.4 originally banned recursion; author replaced with least-fixpoint | Implementation will go straight to fixpoint (§6.3 milestone); poly-recursion detected via occurs-check on SCC call-edge substitutions. |

## C. Implementation artifacts / restrictions (not sanctioned by the proposal)

| # | Artifact | Impact | Fix by |
|---|---|---|---|
| C1 | cjo serialization DROPS capTys (FuncTyInfo untouched); §3.10.2 requires full clause metadata | Cross-package `throws` checking is silently absent: imported decls arrive cap-free | Serialization milestone (after §6.3 per roadmap) |
| C2 | Incremental compilation path (`PreSetDeclType` skips cached tys) loses caps | Same as C1 for incremental builds | Serialization milestone |
| C3 | capTys interning keeps written order — `throws (A,B)` and `throws (B,A)` are distinct (mutually subtyped) types; §3.10.2 rule 1 wants canonical normal form in metadata | Harmless in-memory (set semantics live in subsumption); metadata canonicalization pending | Serialization milestone |
| C4 | `...` marker parse-rejected EVERYWHERE (proposal allows it on non-exported decls, §6.3.5) | `throws A, ...` unusable until inference | §6.3 (lift for decls only; stays banned in types per §3.4) |
| C5 | Macro NodeFormat does not serialize ThrowsClause — macros cannot emit `throws` clauses | Macro-generated checked APIs impossible | Deferred (original plan M6); test exists in colleague's suite as precedent |
| C6 | `CanThrow` does not exist as a type at all (entries stored directly in FuncTy::capTys); proposal §3.1 primary text declares a std.core enum (NOTE offers intrinsic alternative) | No user-visible CanThrow; diagnostics print the name only as text | Working as intended (strongest form of the §3.1 NOTE); revisit only if effects materialization (§8.2) needs a real type |
| C7 | §3.6 inference-failure wording: "mismatched types" showing the uninstantiated capability row, plus "parameters and arguments mismatch" — no dedicated "cannot infer T from capability list" diagnostic | Cosmetic | Backlog (diagnostics polish) |
| C8 | Override/§3.8 diagnostic prints raw Ty names (`Class-BException`); clause-entry diagnostics print source text | Cosmetic inconsistency (matches upstream style) | Backlog |
| C9 | LSP/cjd compiler instance no-ops the CapabilityCheck stage — no capability diagnostics in IDE | IDE parity gap | Backlog (plan: run-for-diagnostics) |
| C10 | `--enable-chexc` alias retained alongside canonical `--enable-checked-exceptions` | Not in proposal; convenience | Keep or drop at author's pleasure |
| C11 | ASTWriter exports capturing/clause-bearing generic/inline bodies without the clause nodes (silent) | Related to C1/C5; no crash observed | Serialization milestone |

## D. Not yet implemented (roadmap ledger, no divergence intended)

- §6.3 capability parameter inference (red tests committed; miss-handler seam ready)
- §6.1 capability list aliases; §6.2 exception conversions; §6.5 adapter generation
- §3.10.2 package metadata (canonical form, levels, ABI epoch) — with C1–C3
- §5.1/§5.2 checked↔unchecked interop defaults, assumption imports, boundary function values
- §4 Modal integration (waiting on upstream per ruling 14) and §5.5's intra-function checks (see A2)
- §7 spawn/Future beyond the lexical rule; §8 extensions (incl. effects — later milestone by directive)
- Stdlib migration (§5.3): inventory drafted, 18 UNCERTAIN awaiting author; one-pass cleanup after §6.3
