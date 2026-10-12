# Completing inferred capability components (I35 / T5) — design note

**Historical design, superseded by the declaration-local migration.** This note records the former T5 post-Sema completion/replay approach. The working implementation now completes declaration contracts during Sema and removes that repair pipeline; see [the current architecture](architecture.md) and [validation status](gap-analysis.md). The historical analysis below is retained for context.

**The hole.** A reference to a declaration whose list is inferred gets its type during Sema, when
the list is still empty; completion afterwards updates the *declaration's* type and nothing else.
The prototype compensated by demanding the list where the value is **formed**, which is unsound in
one direction the review found and a probe confirmed:

```cangjie
var g: () -> Unit = { => }
try { g = risky } catch (e: LeakExc) { }   // formation demand discharged here
g()                                        // clause-free type: demands nothing
```

compiles at `error` and throws through `main`. Under the text's reading the assignment itself is
the error: `() throws LeakExc -> Unit` is not a subtype of `() -> Unit`.

**The fix, in the text's own terms.** The list rides the type; the call pays. Two steps:

1. **Complete** the capability component of expression types that mention an inferred declaration:
   a reference used as a value, a bound method, and the type of a binding initialized from one.
2. **Replay** the capability-sensitive checks that Sema decided while the component was empty —
   assignment, initialization against a declared type, argument passing, `return`.

Overload resolution is *not* replayed: it never consults capability lists, so its result cannot
change. This is the phase ordering the text prescribes, with the completion step it leaves
implicit (design tension D-0b).

## Scope of this batch

| completed | replayed |
|---|---|
| `RefExpr` / `MemberAccess` naming an inferred declaration, when used as a value | `VarDecl` with a declared type and an initializer |
| the `VarDecl` type of `let f = inferredFn` (no declared type) | `AssignExpr` |
| | call arguments |
| | `return` against the enclosing declared result type |

Left for a later round, recorded rather than assumed: joins/meets that mixed an inferred type,
aggregate and container element types, compiler-generated wrappers. Each is the same mechanism
(complete, then replay); none is reachable without a completed reference type, so this batch is
the prerequisite for all of them.

## Mechanism

A second walk after `CompleteInferredCapabilityTypes`, in the same stage:

- **Completion.** For every `RefExpr`/`MemberAccess` whose target is in the inferred map, rebuild
  its type as the declaration's completed `FuncTy`, instantiated through the reference's own
  `instTys` — the instantiation `DemandInferredOnValue` already needed (I35b). Propagate into the
  `VarDecl` whose initializer is exactly that expression and which has no declared type.
- **Replay.** Walk the same bodies; at each of the four positions above, compare the (possibly
  completed) source type against the target type with `IsSubtype`, and report a dedicated
  diagnostic when the capability component is what fails — the ordinary type error was already
  reported by Sema if the shapes disagreed, so a failure here is always about capabilities.

`DemandInferredOnValue` and the "pays at formation" note in artifact C15 retire with it; the call
site pays, which is what every other requirement does.

## Diagnostic

A dedicated message, because the ordinary "mismatched types" would name two types that print
identically to a reader who does not know about erasure:

```
error: 'risky' requires 'CanThrow<LeakExc>', which '() -> Unit' does not provide
  note: the list is inferred from the body of 'risky'
```

## Verification

The probe above becomes a test (rejected at the assignment, not at the call). The existing
`infer_ref_value*.cj` pair changes meaning: formation inside a `try` no longer discharges
anything, and the *call* is what needs the capability. Gates: full `compiler/Sema`,
CheckedExceptions, serialization, IncrementalCompilation, std and stdx at `warn`.

## Round 2 (2026-09-25): derived types, joins, aggregates, inferred result types

**What T5 left open was larger than its scope table said.** T5 completed a reference to an
inferred declaration and the binding it initialized — but not the *names* of that binding, so even
`let w = risky; w()` compiled at `error` and threw through `main` (the positive test
`infer_ref_value.cj` passed because its call was inside a `try` anyway). The deferred round —
joins, aggregates, container element types — therefore also had to cover every type type check
*derived* from a completed one. Reproducers: `probe_ch3/i1*`, `i2`, `i5`, `i8`, `i10`, and
`probe_fix/w1`–`w4` (binding name, implicit body result, `for-in` element, lambda result).

**Mechanism: the same two steps, generalized.**

1. **Completion** (`CapabilityTypeCompleter`) is now a post-order walk repeated to a fixed point
   (a binding or a callable can be named before its own completion is reached; monotone, so it
   terminates — bounded at 32 rounds as a guard). Each rule re-makes one derivation type check made,
   with the join of "Joins and meets" restricted to what completion produces — a type that differs
   from what type check saw in capability components alone (`WidenCapabilities`: union of lists in
   semantic form at every functional position with the same shape; parameter positions untouched,
   since no inferred list reaches a parameter type):

   | node | takes |
   |---|---|
   | `RefExpr` / `MemberAccess` | the completed declaration type (a function with an inferred list or an inferred result, a binding re-typed below), instantiated through `instTys` and — for a member — through the (completed) receiver |
   | `VarDecl` without a declared type, `VarWithPatternDecl`, `for-in` pattern | the initializer's type / the tuple component / the iterated element (`next()` of `iterator()`, out of its `Option`) |
   | `Block`, `ParenExpr`, any expression with a `desugarExpr` | the last expression / the operand / the desugaring (operator subscripts are completed through theirs) |
   | `IfExpr`, `MatchExpr`, `TryExpr` | the join of the branches |
   | `ArrayLit`, `TupleLit` | the join of the elements as element type / the components |
   | tuple access, `VArray` access | the component / the element |
   | `CallExpr` | the (completed) callee's result |
   | `FuncBody` with a compiler-added result type (functions and lambdas), then its `LambdaExpr` | the join of the body's value and every `return` |

2. **Replay** (`CapabilitySubtypeReplay`) now re-judges only sources completion changed (the set
   is returned by the completion and passed in), structurally (`CollectUnadmitted`: every list
   entry of the source not admitted by the target at the same position, through tuples and nominal
   type arguments), at: declared-type bindings, assignments, arguments, `return` against a WRITTEN
   result type, a body's last expression against a written result type (new), and an inferred
   result type against the result of the declaration it overrides (new).

**Consequences worth knowing.**
- A `return` in a function whose result type is inferred used to be replayed against the result
  type type check had inferred while the list was empty — a false positive (`func mk() { return
  risky }` was an error). The inferred result type is now completed instead.
- Element types are type-level: `let arr = [quiet, risky]` makes `arr[0]()` require the list too.
- Instantiations type check solved are still not re-solved (`pick(risky, quiet)`, `Some(risky)`,
  `later(risky)`, `[risky].map(...)`): the replay reports the argument that no longer fits the
  instantiation. Stricter than the text (which would infer the type argument with the list), never
  weaker; unchanged from T5.
- The protocol lookup shared with the checking pass (`FindNullaryMemberOf`) now searches
  extensions: `Array`'s `iterator()` lives in one, and so can a user type's `iterator()`, `next()`
  or `close()` — those implicit calls demanded nothing before (a residue of I34).

**Still not covered** (recorded in the gap analysis): match-case patterns binding from a completed
selector (`match ((risky, 1)) { case (f, _) => f() }`), optional chaining, `spawn` results,
compiler-generated wrappers, casts, and a completed value flowing into a supertype of a different
nominal declaration (an interface its class implements) — the structural walk follows the same
declaration only.
