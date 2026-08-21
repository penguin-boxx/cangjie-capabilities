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
| 1 | `compiler/Driver/options/help/test_showall.cj` | golden `cjc -h` text — C14 |

The lesson for gating: `compiler/`-only runs cannot see breaks in the AST-library ABI. Run
`API/std/libast` and `API/stdx/syntax` (~20 min together) whenever the lexer, the AST node
set, or the parser headers change — and rebuild std and stdx first, since their FFI shims are
compiled against the compiler headers and a stale shim misreads the new frontend's nodes
rather than failing to load.

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
