# Completing inferred capability components (I35 / T5) — design note

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
