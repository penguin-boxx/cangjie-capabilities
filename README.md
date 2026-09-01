# Capability-based checked exceptions for Cangjie — the compiler prototype

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

The work is a prototype in the honest sense: the checking pipeline is built end to end and
gated by a test suite of its own, one soundness item is known-open, and three planned
batches are unstarted. Section [State](#state) says exactly which.

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

## The result in numbers

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

## What the prototype does

- **Clauses.** `throws E1, E2` and `performs T` on functions, methods, constructors,
  property accessors, operators, extensions and interface members; on functional types
  (`(A) throws (E) -> R`); in any order with `where`; `throws ()` is legal.
- **Types.** Capability lists are canonicalized and take part in type identity, while
  staying out of type-argument inference and overload resolution — as the design requires.
  Function subtyping is permutation- and length-insensitive over the lists; overriding and
  redefinition check pointwise subsumption.
- **Checking.** A pass after type checking walks each body against a stack of supplies
  (the callable's own list, each `catch` pattern, a literal's expected type, class
  captures, `handle`) and discharges the demands: `throw`, every call after generic
  substitution, default-value expressions, field initializers, and the implicit calls —
  `close()` of try-with-resources, `iterator()`/`next()` of `for-in`.
- **Inference.** Declarations that may omit their list get one computed bottom-up over the
  intra-package call graph, one SCC pass with Kleene iteration, cycles diagnosed rather
  than approximated.
- **Migration and escape.** `@AssumeThrows` on imports and declarations, `unsafeCanThrow`,
  `UncheckedException`, and a `--enable-chexc off/warn/error` axis with its own warning
  group, so an unannotated corpus keeps compiling.
- **Cross-package.** Lists are serialized into `cjo` metadata from signature data, never as
  materialized parameters, and incremental compilation invalidates on the right edits.
- **Standard library.** The checked flows of `std` (fs, io, and the escape hatch in
  `std.core`) and several `stdx` packages are annotated; the whole of `std` and `stdx`
  builds under checking.

## State

Development ran as a queue of batches, each gated before it was committed.

- **Landed: T1–T4** — correctness fixes from the external review, text synchronization
  (free clause order, the `unsafeCanThrow` rename, `resume throwing` against the try's own
  catches), `where`-bound coverage, and inference reach (field initializers into
  constructors, the `for-in` protocol).
- **In progress: T5, inference completion.** Written but not gated, and therefore not in
  the pinned compiler. It closes the one **known-open soundness hole**: an inferred
  capability list does not reach the expression type, so a function value formed inside a
  discharging `try`, stored outward and called after it, compiles at `error` and throws
  uncaught at run time. Recorded as I35 in the gap analysis, with the probe that
  demonstrates it and the design in `notes/inference-completion-design.md`.
- **Not started: T6–T8** — the checked-effects axis, clauses on properties, and a cleanup
  tail.
- **Out of scope by ruling:** escape analysis of every kind — capability regions and
  capture sets belong to the parallel Modal Cangjie proposal. Consequently the prototype
  accepts both canonical escapes of a try-scoped capability; the guarantee it delivers
  today is checked documentation plus complete demand/supply checking, not the full
  lifetime guarantee.

[`notes/gap-analysis.md`](notes/gap-analysis.md) is the single ledger of everything
separating the implementation from the proposal and the proposal from a stabilizable
design; it is the document to read before trusting any claim above.

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
