# Stdlib exception inventory (for §6.3 unchecked classification)

> **Status 2026-08-30.** The classification data below is unchanged and still the working input for
> the migration. What has happened since: the 26 obvious re-parentings landed in `std.core`, the
> `fs`/`io` ring is annotated, and the stdx ring reached 1,324 diagnostics over 15 packages (see
> `gap-analysis.md` I.5). The UNCERTAIN rows here are exactly the ones still waiting on rulings,
> and they have been consolidated into Q-STD-1…9 there — Q-STD-9 in particular subsumes the
> recurring "interface in std, implementation elsewhere" shape (`Iterator.next`, `Resource.close`,
> `ToString.toString`, `Digest.write`).

Prepared during M3 per author ruling 9. Source: `cangjie_runtime/stdlib/libs/std` (plus the
vendored flatbuffers copy), enumerated via `grep -rn '<: Exception'` and one follow-up level
of subclassing. Classification principle (author ruling): **contract / state / index /
arithmetic / unwrap → unchecked; I/O, parse, net, concurrency-wait → checked.** Lines marked
UNCERTAIN need author judgment. Paths are relative to `cangjie_runtime/stdlib/`.

Notes on mechanics: under §6.3, "unchecked" means the class (and hence all its subclasses)
becomes a subtype of `UncheckedException`; a checked subclass of an unchecked class is
impossible. Conflicts of that kind are called out explicitly below.

## std.core

| Class | Verdict | Location | Rationale |
|---|---|---|---|
| ArithmeticException | unchecked | libs/std/core/arithmetic_exception.cj:11 | arithmetic per principle |
| OverflowException (<: ArithmeticException) | unchecked | libs/std/core/overflow_exception.cj:15 | arithmetic; inherits parent's status |
| IllegalArgumentException | unchecked | libs/std/core/illegal_argument_exception.cj:11 | contract per principle |
| IllegalFormatException (<: IllegalArgumentException) | unchecked, UNCERTAIN | libs/std/core/illegal_format_exception.cj:11 | thrown by string→number parsing in std.convert, which is "parse → checked"; but its parent is unchecked, so checking it would require re-parenting — author call needed |
| IllegalMemoryException | unchecked | libs/std/core/illegal_memory_exception.cj:11 | memory-contract violation |
| IllegalStateException | unchecked | libs/std/core/illegal_state_exception.cj:11 | state per principle |
| IndexOutOfBoundsException | unchecked | libs/std/core/index_out_of_bounds_exception.cj:11 | index per principle |
| NegativeArraySizeException | unchecked | libs/std/core/negative_array_size_exception.cj:11 | contract (size argument) |
| NoneValueException | unchecked | libs/std/core/none_value_exception.cj:11 | unwrap (`Option.getOrThrow`) per principle |
| UnsupportedException | unchecked | libs/std/core/unsupported_exception.cj:11 | contract (operation not supported by receiver) |
| ExclusiveScopeException | unchecked, UNCERTAIN | libs/std/core/exclusive_scope.cj:63 | scope/state misuse of the exclusive-scope facility; experimental feature, semantics may still move |
| IncompatiblePackageException | unchecked, UNCERTAIN | libs/std/core/incompatible_package_exception.cj:11 | raised at package load: environmental, but unhandleable in practice (init-time, fatal) — lean unchecked |
| SpawnException | checked, UNCERTAIN | libs/std/core/spawn_exception.cj:11 | thread-spawn failure is an environmental resource error (concurrency); not a caller bug — lean checked |
| TimeoutException | checked | libs/std/core/timeout_exception.cj:11 | concurrency-wait per principle |

## std I/O, filesystem, environment, process, net

| Class | Verdict | Location | Rationale |
|---|---|---|---|
| IOException | checked | libs/std/io/io_exception.cj:14 | I/O per principle |
| ContentFormatException | checked | libs/std/io/content_format_exception.cj:14 | parse of stream content per principle |
| FSException (<: IOException) | checked | libs/std/fs/fs_exception.cj:13 | filesystem I/O |
| EnvException | checked, UNCERTAIN | libs/std/env/env_exception.cj:15 | environment access is environmental, but some throws are argument-contract (e.g. invalid variable names) — may want splitting |
| ProcessException (<: IOException) | checked | libs/std/process/process_exception.cj:16 | process I/O and lifecycle is environmental |
| SocketException (<: IOException) | checked | libs/std/net/socket_exception.cj:20 | net per principle |
| SocketTimeoutException | checked | libs/std/net/socket_exception.cj:59 | net + wait-timeout per principle |

## std data handling (parse-ish)

| Class | Verdict | Location | Rationale |
|---|---|---|---|
| ArgumentParseException | checked | libs/std/argopt/arg_opt.cj:800 | parses external user input (argv) |
| TimeParseException | checked | libs/std/time/date_time.cj:1456 | parse per principle |
| InvalidDataException | checked | libs/std/time/timezone.cj:844 | tzdata file loading/parsing (I/O + parse of external data) |
| RegexException | checked, UNCERTAIN | libs/std/regex/regex_exception.cj:11 | "parse → checked" (patterns may be user input), but most patterns are literals where failure is a programming error (Java makes this unchecked) |
| SqlException | checked | libs/std/database/sql/sql_exception.cj:22 | external database I/O |
| PrecisionMismatchException | unchecked | libs/std/math/numeric/decimal.cj:2191 | internal (non-public) arithmetic-precision contract |
| ConcurrentModificationException | unchecked | libs/std/collection/concurrent_modification_exception.cj:11 | state violation (mutation during iteration) |
| IllegalSynchronizationStateException | unchecked | libs/std/sync/ireentrant_mutex.cj:28 | state violation (unlock without lock etc.) |
| OvershiftException | unchecked | libs/std/overflow/throwing_op.cj:836 | arithmetic (shift width contract) |
| UndershiftException | unchecked | libs/std/overflow/throwing_op.cj:850 | arithmetic (shift width contract) |

## std.ast (macro tooling)

| Class | Verdict | Location | Rationale |
|---|---|---|---|
| ASTException | unchecked, UNCERTAIN | libs/std/ast/exception.cj:11 | mostly contract misuse of AST node APIs, but macro authors may reasonably want to handle failures — lean unchecked |
| ParseASTException | checked | libs/std/ast/exception.cj:23 | parse of token streams/source per principle |
| MacroContextException | unchecked, UNCERTAIN | libs/std/ast/ffi.cj:261 | contract: context APIs used outside a macro evaluation; but message-passing failure modes are environmental |
| FlatBuffersException | checked, UNCERTAIN | libs/std/ast/flatc_exception.cj:9 | internal (non-public); signals malformed serialized buffers = parse of data, but callers are compiler-internal — status barely observable |

## std.reflect

| Class | Verdict | Location | Rationale |
|---|---|---|---|
| ReflectException | checked, UNCERTAIN | libs/std/reflect/exception.cj:11 | not covered by the principle: lookups fail on legitimately absent members (dynamic, handleable — Java checks these), yet many uses are contract errors — author call for the whole hierarchy |
| InfoNotFoundException (<: ReflectException) | checked, UNCERTAIN | libs/std/reflect/exception.cj:25 | absent member lookup — follows parent decision |
| MisMatchException (<: ReflectException) | checked, UNCERTAIN | libs/std/reflect/exception.cj:39 | type mismatch on reflective use — follows parent |
| IllegalSetException (<: ReflectException) | checked, UNCERTAIN | libs/std/reflect/exception.cj:53 | setting immutable member — contract-flavored, follows parent |
| IllegalTypeException (<: ReflectException) | checked, UNCERTAIN | libs/std/reflect/exception.cj:67 | follows parent |
| InvocationTargetException (<: ReflectException) | checked, UNCERTAIN | libs/std/reflect/exception.cj:81 | wrapper around the target's exception — interacts with §8.10 conversions; needs its own design note |

## std.runtime (introspection; internal classes)

| Class | Verdict | Location | Rationale |
|---|---|---|---|
| MemoryInfoException | unchecked, UNCERTAIN | libs/std/runtime/runtime_memoryInfo.cj:43 | internal; runtime introspection failure = environment/state — lean unchecked |
| ProfilingInfoException | unchecked, UNCERTAIN | libs/std/runtime/runtime_processorInfo.cj:30 | internal; same as above |

## std.unittest (test framework; exceptions are framework control flow)

| Class | Verdict | Location | Rationale |
|---|---|---|---|
| AssertException | unchecked | libs/std/unittest/assert_exception.cj:19 | assertion failure = framework control flow, must cross user frames unhindered |
| AssertIntermediateException | unchecked | libs/std/unittest/assert_exception.cj:46 | framework control flow |
| UnittestException | unchecked | libs/std/unittest/unittest_exception.cj:10 | framework-internal error reporting |
| ErrorWrapperException | unchecked | libs/std/unittest/unittest_exception.cj:24 | internal wrapper, control flow |
| UnittestTimeoutException | unchecked, UNCERTAIN | libs/std/unittest/unittest_exception.cj:38 | timeout suggests checked by principle, but it is thrown BY the framework to abort user code, not handled by it — lean unchecked |
| UnittestOptionValidationException | unchecked | libs/std/unittest/common/option_validators.cj:13 | configuration contract |
| JsonException | unchecked, UNCERTAIN | libs/std/unittest/common/json_exception.cj:19 | protected/internal; parses framework-owned JSON — parse says checked, internal usage says it never escapes |
| DataModelException | unchecked, UNCERTAIN | libs/std/unittest/common/serialization_data_model.cj:376 | protected/internal serialization contract |
| BenchmarkStoppedError | unchecked | libs/std/unittest/framework.cj:311 | internal control flow (non-public) |
| PrettyException (abstract, mock) | unchecked | libs/std/unittest/mock/exceptions.cj:12 | mock-framework reporting hierarchy |
| IllegalMockCallException | unchecked | libs/std/unittest/mock/internal/exceptions.cj:14 | mock misuse = contract |
| NoDefaultValueForMockException | unchecked | libs/std/unittest/mock/internal/exceptions.cj:24 | mock configuration contract |
| MockReturnValueTypeMismatchException | unchecked | libs/std/unittest/mock/internal/exceptions.cj:34 | mock configuration contract |
| UninitializedStaticCallHandler | unchecked | libs/std/unittest/mock/internal/exceptions.cj:41 | framework state |
| MalformedMacroException | unchecked | libs/std/unittest/mock/mockmacro/syntax_errors.cj:74 | internal macro contract (non-public) |
| MacroException | unchecked | libs/std/unittest/testmacro/exception.cj:13 | internal macro contract (non-public) |

## Vendored third party

| Class | Verdict | Location | Rationale |
|---|---|---|---|
| FlatBuffersException | checked, UNCERTAIN | third_party/flatbuffers/cangjie/exception.cj:9 | duplicate of the std.ast copy; same reasoning |

## Summary

- Direct `<: Exception` classes found: 50 (34 outside std.unittest, 16 in std.unittest); plus
  11 notable indirect subclasses listed inline (IOException, ReflectException,
  ArithmeticException, IllegalArgumentException children).
- Verdict counts over all rows: 21 checked / 40 unchecked (of 61 rows).
- UNCERTAIN rows (18): IllegalFormatException, ExclusiveScopeException,
  IncompatiblePackageException, SpawnException, EnvException, RegexException, ASTException,
  MacroContextException, FlatBuffersException (both copies), ReflectException + its 5
  subclasses, MemoryInfoException, ProfilingInfoException, UnittestTimeoutException,
  JsonException, DataModelException.
- Structural conflict to resolve for §6.3: IllegalFormatException (parse-flavored) sits under
  unchecked IllegalArgumentException; InvocationTargetException interacts with §8.10
  conversions.
