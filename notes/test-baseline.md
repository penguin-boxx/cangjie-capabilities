# Test baseline (pre-development), 2026-08-14

SDK: release build of upstream `main` (cangjie_compiler @ 098c1b26a1) — compiler, runtime,
stdlib, stdx. Built and run in the `cangjie-dev` container via `./cj.py`. Not built: cjdb
(debugger), tools (cjpm/cjfmt/...), Java interop (CJMP).

## Results

| Suite | Result |
|---|---|
| Compiler unittests (`./cj.py test compiler`, ctest) | **49/49 pass** |
| LLT `API/stdx` (1,219 cases) | **100% pass** (needs CANGJIE_STDX_PATH — set by cj.py) |
| LLT `compiler/ Runtime/ API/` (19,261 cases) | **Pass modulo the exclusions below** |

## LLT accounting (from the 2026-08-14 full run + retests)

Initial full run: 17,695/19,261 pass. All 1,566 failures were dispositioned:
- 1,219 `API/stdx` — env: CANGJIE_STDX_PATH unset → fixed in cj.py, now 100% green.
- 216 `compiler/CJMP` — needs Java interop libs (`java.lang` package) we did not build.
  Excluded from baseline. Revisit only if interop becomes relevant.
- 96 mixed — flaky under `-j8` load (pass on retest at `-j4`). Treat singleton failures
  near timeouts as suspect-flaky; retest before investigating.
- 28 `API/std/time*` + signal/bench — env: missing tzdata in image → fixed (Dockerfile).
- 5 persistent, all environmental (evidence in logs/):
  - `API/std/math/test_math_round_NaN.cj` — testsuite DEPENDENCE helper `caserunner.cj`
    not found (suite packaging quirk, not SDK).
  - `API/std/reflect/organizationName.cj` — shells out to `cjpm` (tool not built).
  - `API/std/socket/redesign/functional/tcp_connection_timeout.cj` — container networking.
  - `compiler/Driver/options/toolchain/android_clang_search_lib{,64}.cj` — need Android NDK.

Standing exclusions for development runs: `Tools/cjdb` (not built; also needs pexpect —
now in image), `compiler/CJMP`, and the 5 cases above. Stock `[EXCLUDE-TEST-CASE]` entries
are inherited automatically by `./cj.py test llt --filter`.

## Full-tree run 2026-08-21 (compiler `62c20e99`)

First run of the **whole** tree (19,831 cases: `compiler/ Runtime/ API/ Tools/cjdb`) since the
baseline; every gate in between covered the 3,934-case `compiler/` set only. Result:
**19,006 pass, 825 fail**. All 135 non-excluded failures were retested at `-j4` and are
deterministic — no load-flakes this time.

| Count | Group | Disposition |
|---|---|---|
| 474 | `Tools/cjdb` | debugger not built — standing exclusion |
| 216 | `compiler/CJMP` | Java interop not built — standing exclusion |
| 8 | macro token round-trips (`Macro/annotation`, `Macro/expr`, `unittest` power-assert) | **C13(a)** — token ordinals shifted by the chexc token additions; fixed, the tokens were dead and are deleted |
| 118 | `API/stdx/syntax` (106), `API/std/libast` (12) | **C13(b)** — stale `std.ast`/`stdx` FFI shims: built 08-15/08-14 against older compiler headers, node layouts have moved since; fixed by rebuilding std and stdx |
| 6 | math DEPENDENCE helper, reflect→`cjpm`, socket timeout, signal, 2× Android NDK | environmental, as in the baseline above |
| 2 | `API/stdx/net` | not investigated; presumed network |
| ~~1~~ | ~~`compiler/Driver/options/help/test_showall.cj`~~ | *fixed 2026-08-23: the golden lists `--enable-chexc`, its severities and the `chexc` warning group; the group is 5/5* |

Since 2026-08-21 evening, one more **expected** failure: `compiler/Sema/effect/effect_perform_02.cj`.
Effect requirements are now checked wherever the effect-handler feature is enabled (the proposal's
own axis rule), and that upstream test passes a `perform`ing literal through a clause-free `() ->
Int64` parameter — exactly what the capability discipline rejects, since the handler is installed
dynamically and the type says nothing. The migration the design intends is to annotate the callback
`fn: () performs T -> Int64`, which does not compile yet for an unrelated reason (I19: a capability
list mentioning a type parameter is not substituted at the call site). Fix I19, then annotate.

The lesson for gating: `compiler/`-only runs cannot see breaks in the AST-library ABI. Run
`API/std/libast` and `API/stdx/syntax` (~20 min together) whenever the lexer, the AST node
set, or the parser headers change — and rebuild std and stdx first, since their FFI shims are
compiled against the compiler headers and a stale shim misreads the new frontend's nodes
rather than failing to load.

## Working-tree state, 2026-08-23 (evening)

Compiler `39ac1dc4`, std rebuilt from it and **green at `warn`** (exit 0). Targeted groups
`compiler/CheckedExceptions` + `compiler/Sema/effect`: **137/137 pass**, which includes the seven
tests of this round. The std build emits `StringReader.next()` warnings from the inferred-override
re-check (gap-analysis E-4) and ~1,486 capability warnings overall; at `warn` the build completes.

Two traps this round cost time, both worth keeping:
- `EXEC-PIPE-1:` asserts the compiler exits **1**. A test that expects warnings and a successful
  build must use `EXEC-PIPE:` — the failure reads "Command return code 0 not equals to expected
  return code 1", which says nothing about the diagnostics that were in fact all correct.
- An incremental std build reuses `modules/.../std.<pkg>.a`, so a compiler change that should
  affect a package can appear to change nothing — a stale archive is what made a capability-gated
  link failure look flag-independent for a day. To rebuild one package on its own (a one-minute
  loop instead of a 25-minute one), take its `COMMAND` line from
  `cangjie_runtime/stdlib/build/build/build.ninja`, delete the target `.a`, and run it under
  `./cj.py sh` with `envsetup.sh` sourced.

**`compiler/IncrementalCompilation`: 1,944 cases, all green** (2026-08-23). Worth knowing before
touching `ASTHasher`: the suite asserts precisely which declarations a given edit recompiles, so a
change to what feeds `DeclHash.sig` shows up there in the hundreds — 185 failures for one such
experiment (gap-analysis I28). Run it whenever the hashing changes; it takes about ten minutes.

## The feature's own suites, 2026-08-30 (after R1–R5)

`compiler/CheckedExceptions` holds **154 source files across twelve groups** — many are
dependencies of multi-file cases, so the case count is lower:

| group | what it pins |
|---|---|
| `parse` | clause grammar: placement, `()`, `...`, duplicates, order, the soft keywords |
| `types` | functional subtyping, joins **and meets**, overloading, generics, semantic-form identity, cast targets |
| `scopes` | the four scope introducers and the exclusions; `warn` level; the escape hatch; try-with-resources closing |
| `inference` | SCC/fixpoint, recursion, effective visibility, overrides, **references as inference edges** |
| `captures` | the clause, constructors, subclass restatement, mixed kinds |
| `unchecked` | the taxonomy, unchecked entries, generic instantiation to an unchecked type |
| `aliases` | tuple aliases, recursive flattening, cycles |
| `assume` | assumption imports, package scope, covariant function values, recorded-level rejection |
| `performs` | effect requirements: `perform`, `handle`, kinds kept apart, `resume throwing` |
| `serialization` | `.cjo` round-trips, cross-package surfaces, incremental cases |
| `macros` | a `throws` clause on a macro; `performs` refused |
| `abi` | **erasure**: clause-bearing and clause-free twins must have identical symbol tables |

Gate numbers on `629d4ecd` (compiler), all green:

| suite | result |
|---|---|
| `compiler/CheckedExceptions` + `compiler/Sema/effect` | **161 / 161** |
| `compiler/Sema` (full, includes the above) | **3,502 / 3,502** |
| `compiler/IncrementalCompilation` | **1,944 / 1,944** |
| `compiler/Macro` | **789 / 789** |
| `compiler/Driver/options/help` | **5 / 5** |
| compiler unit tests (`cj.py test compiler`) | **49 / 49** |
| std, stdx at `warn` | build clean, no ICE |

One trap when writing capability tests, found during the batch-2 audit and still true: the
`Walker` visits both a node's `desugarExpr` and the node's own children, so a construct the
compiler desugars — a property read on the right-hand side of a property assignment is the known
case — is walked twice and can raise the same demand twice. Write assertions with
`// ASSERT: scan`, **never** with exact error counts, or a test starts failing on an unrelated
desugar change.

Which suite catches what, learned the hard way:

- **`compiler/Sema` in full** is the gate for anything touching type identity — the reverted
  canonicalization-at-interning attempt failed exactly there and nowhere else.
- **`compiler/IncrementalCompilation`** asserts *which declarations* an edit recompiles, so any
  change to what feeds `DeclHash.sig` shows up there in the hundreds (185 failures for one such
  experiment). A feature-gated change does not move it at all, which is how R4 was made acceptable.
- **`compiler/Macro`** must run whenever the parser changes: the token-ordinal regression of August
  and the macro clause grammar both landed there first.
- A **std build at `warn`** is the only thing that exercises the feature over a real corpus; two
  defects (the override-pairing link failure, the accessor ICE) appeared there and in no suite.

## How to reproduce

```
./cj.py test compiler                       # ctest unittests
./cj.py test llt --filter compiler/ Runtime/ API/   # full baseline (hours)
./cj.py test llt --filter API/stdx          # stdx group (~15 min)
./cj.py test llt --filter <case-or-dir...>  # targeted
```

Notes: full-suite runs at -j8 produce ~0.5% load-flakes; retest failures at -j4 before
trusting them. Framework report ends with a `TestSuiteTask: ... Total/PASS/FAIL` line;
per-run artifacts land in logs/llt_temp/<timestamp>/.
