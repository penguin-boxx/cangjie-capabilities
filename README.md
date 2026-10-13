# Capability-based checked exceptions for Cangjie — compiler implementation

This repository collects one result: a working implementation, in the real Cangjie
compiler and standard library, of the design in
[`proposal/Checked exceptions for Cangjie.md`](proposal/Checked%20exceptions%20for%20Cangjie.md).

Throwing a checked exception of type `E` requires a **capability** of type `CanThrow<E>`,
and the only ordinary source construct that produces one is a `try`-`catch` handling `E`.
Capabilities travel down the call stack as implicit, compile-time-erased parameters
declared by a `throws` clause, are inferred where the declaration allows it, and vanish
entirely after type checking — no runtime cost, no ABI change, and no effect-polymorphic
signatures in user code. The same mechanism checks effect-handler requirements through a
`performs` clause and `CanPerform`.

The working tree implements declaration-local contract completion during Sema and the proposal’s section 6 checking policies, metadata, and consumer-local assumptions. See [State](#state) and the [gap ledger](notes/gap-analysis.md) for the scope and validation status.

## What is in this repository

| Path | Contents |
|---|---|
| [`proposal/`](proposal/) | The design document the implementation follows. |
| [`notes/`](notes/) | The engineering record — start at [`notes/README.md`](notes/README.md). |
| [`cangjie_compiler/`](cangjie_compiler) | Submodule. The compiler: parser, elaboration, subtyping, the capability checker, inference, serialization. |
| [`cangjie_test/`](cangjie_test) | Submodule. The LLT suites, ours under `testsuites/LLT/compiler/CheckedExceptions/`. |
| [`cangjie_runtime/`](cangjie_runtime) | Submodule. Runtime and standard library, including the annotated `std` packages. |
| [`cangjie_stdx/`](cangjie_stdx) | Submodule. The `stdx` packages and their annotations. |
| [`cangjie_test_framework/`](cangjie_test_framework) | Submodule, upstream and unchanged — the harness the LLT suites run under. |
| [`patches/`](patches/) | The same four deltas as `git format-patch` series against upstream, for reading or for reconstruction without the submodules. |
| `cj.py`, `docker/` | The build and test driver. Everything runs in a container; nothing is installed on the host. |
| `scripts/` | One-off maintenance scripts (history rewrites, comment hygiene). |

Each submodule is pinned at the head of its `chexc` branch. Clone with submodules:

```sh
git clone --recurse-submodules https://github.com/penguin-boxx/cangjie-capabilities.git
```

Upstream for all five components is `https://gitcode.com/Cangjie/<name>.git`; the four
changed ones are published, with full history, under the same GitHub account.

## Historical prototype snapshot

| | commits | delta against upstream |
|---|---|---|
| compiler | 44 | 80 files, +4,435 −97 |
| tests | 43 | 166 files, +4,804 −1 |
| runtime / `std` | 6 | 35 files, +184 −118 |
| `stdx` | 4 | 22 files, +315 −156 |

The feature's own suite is 164 test files in twelve groups — `parse`, `types`, `scopes`,
`inference`, `assume`, `captures`, `unchecked`, `performs`, `aliases`, `macros`,
`serialization`, `abi`. At the pinned compiler, with `std` and `stdx` rebuilt against it:

| gate | result |
|---|---|
| `compiler/CheckedExceptions` + `compiler/Sema/effect` | 171 / 171 |
| `compiler/Sema` (full) | 3,502 / 3,502 |
| `compiler/IncrementalCompilation` | 1,944 / 1,944 |
| `compiler/Macro` | 789 / 789 |
| compiler unit tests (ctest) | 49 / 49 |
| `std` and `stdx` built with checking at `warn` | clean, no ICE |

Baseline, exclusions and the reasoning about which suite catches which class of defect are
in [`notes/test-baseline.md`](notes/test-baseline.md).

## What the compiler implements

- **Clauses.** `throws E1, E2` and `performs T` on functions, methods, constructors, property headers and accessors, operators, extensions, and interface members; on functional types (`(A) throws (E) -> R`); in any order with `where`. `throws ()` is legal, and abstract contexts permit bodyless accessors.
- **Types.** Normalized capability lists participate in type identity and full function subtyping. Ordinary generic variables preserve whole functional types; capability-only variables are excluded from inference. Overload identity and override pairing erase capabilities recursively, and completed override contracts are checked separately.
- **Checking.** The final read-only pass checks typed bodies against lexical supplies: callable requirements, handlers, expected literal types, and receiver captures. It validates calls, throws, defaults, field initializers, and implicit resource and iterator calls without initiating inference or repairing types.
- **Inference.** Sema completes each eligible declaration once, in dependency order, before publishing its final capability-bearing type. Re-entering an active inferred contract is an error; written complete contracts permit recursion. Nested omitted clauses capture enclosing supplies, while nested `throws ...` declarations infer independently.
- **Checking policy.** Exceptions and effects independently use Off, Warn, or Error. Disabled components are erased during elaboration and import projection; enabled lists remain canonical even with warnings suppressed. Malformed clauses, ordinary typing failures, and inference cycles remain errors. Handler syntax is enabled separately with `--enable-eh`. `unsafeCanThrow`, `UncheckedException`, and `stdx.effect.unsafeCanPerform` retain their existing behavior.
- **Cross-package.** Metadata records both producer checking levels and capturing status. Sema derives pure consumer views and applies package-wide `@AssumeThrows` and `@AssumePerforms` before typing consumes them. References carry requirements without demanding them; calls and property getters demand them. Incremental invalidation includes original dependency policies and contracts, assumption imports, and aliases. Runtime parameters and scheduler state are not serialized.
- **Standard library.** Existing checked flows in std and stdx remain annotated, socket properties use header clauses, and recursive internal helpers have complete written contracts. Both libraries build at warning level; broader API annotation remains outside this migration.

## State

The current implementation replaces package-wide inference and post-Sema repair with declaration-local completion. It includes property-header clauses and bodyless abstract accessors, non-Modal constructor and receiver captures, corrected inference visibility, and `stdx.effect.unsafeCanPerform`. `CAPABILITY_CHECK` remains read-only validation of demands and completed override contracts. Capability metadata retains the existing clause encoding and adds compatible policy and capturing-status fields. Runtime erasure and ABI remain unchanged.

Section 6 acceptance on 2026-10-13 passes all 365 checked-exception/effect drivers, including all 175 active rewrite cases and 70 compatibility cases, and all 49 compiler unit suites. All 46 std and 38 stdx Cangjie modules were invalidated and rebuilt with both checking axes at Warn using the same final compiler. The full configured Sema, incremental, macro, and module integration gate passes all 6,315 cases. The original rewrite baseline was 60 passing and 31 failing; the compatibility extension originally passed 15 of 63 new cases. The gap ledger records compiler identity and validation logs.

Modal modes, escape analysis, origin propagation, the optional closed-build verifier, and broader library API annotation remain deferred. Independent checked effects and expanded assumption-import semantics are implemented. Historical T1–T8 records describe earlier implementations and do not override this migration's accepted scope. [`notes/gap-analysis.md`](notes/gap-analysis.md) records the final gates, compiler identity, and deferred scope.

Both checking levels default to Off. Use `--experimental --enable-checked-exceptions error` for exception checking and `--experimental --enable-eh --enable-checked-effects warn` for effect checking. Either axis can be enabled independently. Warn records complete contracts and package trust; suppressing a warning group changes reporting only.

## Building and testing

Everything runs in the `cangjie-dev` container built from [`docker/Dockerfile`](docker/Dockerfile);
`cj.py` is the driver.

```sh
./cj.py build image                 # once
./cj.py build compiler              # ~10-20 min warm, ccache in the image
./cj.py build std                   # the stdlib, with checking at 'warn'
./cj.py build stdx
./cj.py test compiler               # ctest unit tests
./cj.py test llt --filter compiler/CheckedExceptions compiler/Sema/effect
```

`cj.py --help` lists the rest. Builds are slow, so the working practice was to batch every
edit of a cycle, format before building, and run every suite against one build.

## Reading order

1. This file, then [`proposal/Checked exceptions for Cangjie.md`](proposal/Checked%20exceptions%20for%20Cangjie.md) — sections 1–2 for the motivation, 3, 5 and 6 for what is implemented.
2. [`notes/architecture.md`](notes/architecture.md) — how the design maps onto the compiler's phases, and why the staging is what it is.
3. [`notes/autonomous-decisions.md`](notes/autonomous-decisions.md) — the rulings and the decisions taken without consultation, each with its reasoning.
4. [`notes/gap-analysis.md`](notes/gap-analysis.md) — the open ledger, in both directions.
5. `git log` in `cangjie_compiler`, or [`patches/compiler/`](patches/compiler/) — the development history, review-sized and in order.

## Provenance and license

The five component repositories are forks of the Cangjie project
(`https://gitcode.com/Cangjie/`), which is licensed under **Apache-2.0 with Runtime
Library Exception**; every change to them is an addition to that code and carries the same
terms, and each fork keeps the full upstream history and its `main` branch untouched
beside the `chexc` branch of this work. The proposal, the notes and the build driver are
this author's own.
