# Checked exceptions for Cangjie

Status: draft, work in progress — some sections are informal or incomplete.

Reading guide: Sections 1–2 motivate the design and can be read on their own; Sections 3–7 are the normative core and may be skimmed on first reading; Section 8 sketches possible extensions; Sections 9–11 record decision rationale, grammar analysis, and standard-library and toolchain impact; Section 12 collects cross-cutting work items; Section 13 is a glossary.

**Summary**. This proposal introduces **capability-based checked exceptions** for the Cangjie language. Throwing a checked exception of type `E` requires a **capability** object of type `CanThrow<E>`, and the only ordinary source construct that introduces one is a `try-catch` handling `E`. Capabilities propagate down the call stack as implicit, compile-time-erased parameters declared with a `throws` clause, and Modal Cangjie's escape analysis, extended in [Section 4](#4-escape-analysis), guarantees that a capability never outlives the handler that introduced it. Together this gives a static guarantee that every checked exception is handled — at zero runtime cost, and without the effect-polymorphic signatures that burden `Result` and row-based designs. The same mechanism also checks effect-handler requirements, with a `performs` clause and a `CanPerform` capability ([Section 5.4](#54-effect-requirements)); the body of the design is stated for exceptions, and effects arrive by substitution there.

Checked exceptions and Modal Cangjie are parallel, independently enabled features; Modal Cangjie is itself at the proposal stage. It powers the full guarantee, which is therefore conditional on both proposals landing; without it, `throws` clauses still work as **checked documentation** — machine-verified requirement lists the compiler keeps consistent with the code ([Section 6.5](#65-checking-without-modal-cangjie)).

Goals, in priority order:
- Statically verify that recoverable exceptions are handled.
- Preserve backward compatibility with unchecked exceptions and support gradual migration.
- Support higher-order functions and inheritance without requiring effect polymorphism in user signatures.
- Keep the annotation burden low enough for practical adoption (inference, aliases).
- Impose zero runtime overhead for capability bookkeeping: capabilities are fully erased after type checking and do not affect the ABI.
- Build on existing language features — Modal Cangjie's `local` modes and the existing exception machinery. The surface-language footprint is small: one capability type (`CanThrow`), two declaration clauses (`throws`, `captures`), and a small amount of library support (`UncheckedException`).
- Be extensible to effect handlers ([Section 5.4](#54-effect-requirements)).

Non-goals:
- Tracking unrecoverable errors: programmer errors remain unchecked exceptions, and fatal failures remain outside exception tracking entirely ([Motivation of checked exceptions](#12-motivation-of-checked-exceptions)).
- Effect/capability polymorphism in the base design; it is deferred to extensions. Consequently, exception checking cannot be deferred from a lazy computation's construction site to its execution site — this limits `spawn` blocks, lazy iterators, and deferred computations generally ([Lazy computations and `spawn`](#71-lazy-computations-and-spawn)).
- Monadic syntax/tagless-final style.

## 1. Introduction

Static validation of error handling is an important feature for language users who value program reliability and the ability to find bugs before production use. Cangjie currently provides no such validation: all exceptions are unchecked — a function's signature says nothing about what it may throw, and the compiler does not verify that any exception is ever handled.

Throughout this document, an exception type is **checked** if its handling is statically verified, and **unchecked** otherwise — today, every exception is unchecked. How exception types are classified is defined in [Unchecked exceptions](#51-unchecked-exceptions).

Previous approaches to statically tracked errors are widely considered unsatisfactory in one way or another. Java's checked exceptions pollute interfaces with implementation-specific exception types and force handling decisions on layers that cannot make them (see [Overview of issues and our solutions](#21-overview-of-issues-and-our-solutions)). Designs based on `Result` types or typed `throws` clauses, as in Rust and Swift, give a computation a single error-type position — independent failures must be combined at the type level, through a sum type, a hierarchy, or conversions — and require higher-order functions that propagate callback failures to abstract over the error representation (see [Other approaches to typed errors](#22-other-approaches-to-typed-errors)).

This proposal aims to solve most of the convenience issues of existing implementations, providing users with confidence about the error paths of a program. It adapts the capability-based approach to the Cangjie language — an approach developed in academic research ("Safer exceptions for Scala", Odersky et al.; "Effects as Capabilities", Brachthäuser et al.) and implemented as Scala 3's experimental `saferExceptions` feature, whose `CanThrow` capabilities this design directly parallels.

### 1.1 Anatomy of error handling

Let us walk through error management to understand the requirements and motivation better.

A program has a happy path, where it successfully does what it is supposed to do. Sometimes execution encounters situations where proceeding is impossible. Such situations fall into a few categories, which differ in whether recovery is realistically possible — and, therefore, in whether the type system should track them:

| Category                   | Description                                                                                           | Examples                              | Recovery                                      | Tracking  |
| -------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------- | --------------------------------------------- | --------- |
| **Programmer's errors**    | The program is in a state that was not supposed to occur: contracts or invariants in code are broken. | failed assertion, index out of bounds | Not realistic: catching likely hides a defect | Unchecked |
| **Fatal failures**         | The runtime cannot reasonably continue.                                                               | out of memory, stack overflow         | Not realistic                                 | Untracked |
| **I/O errors**             | The file system, network, or operating system is not in the state an operation requires.              | file not found, connection refused    | Often possible                                | Checked   |
| **Invalid external input** | Data from outside the program fails validation.                                                       | deserialization of malformed data     | Usually possible                              | Checked   |

When an error occurs, the robust strategy is to abandon the potentially invalidated state rather than repair it in place: repair code runs exactly on the paths that are exercised rarely and reviewed least, so that is where bugs hide. The call stack is the map of that state — each frame owns what its call built — so abandoning a failed computation's state means discarding its frames: unwinding.

So, a program unwinds part of its call stack, finding a place with enough context to decide how the failure should be treated, reaching a **handling boundary** — a choice of how much state to abandon. Examples of handling boundaries are:
- The whole process. In that case a program does not need to recover. For example, command line utilities usually go that way.
- A user's request. Web servers can abort a user's request if something goes wrong and proceed with other requests.
- A function call. For example, a network request can be immediately retried.
- A public API. An exception should be wrapped in a domain error type to encapsulate implementation details (`SqlException` → `UserNotFoundException`).

Checked exceptions verify precisely this: every checked exception should find its handling boundary.

### 1.2 Motivation of checked exceptions

The main purpose of checked exceptions is to force a programmer to **make a decision about every checked error type**:
- Handle and return to the happy path (if handling is easy).
- Wrap in a different type and propagate (on an API boundary).
- Propagate (if nothing meaningful can be done here).

For example, the following function explicitly decides to propagate errors to the call site, requiring the call site to handle `NetworkException` and `SqlException` (the `throws` syntax is introduced in [Section 3](#3-implicit-capability-passing-design)):
```swift
func addUser(db: Database, user: User)
throws NetworkException, SqlException {
    db.query(...)
}
```
In the `main` function, a user handles both declared exceptions:
```swift
main() {
    try {
        let db = Database(...)
        let user = User.from(Process.current.args[1])
        addUser(db, user)
    } catch (e: NetworkException) {
        // retry
    } catch (e: SqlException) {
        // report
    }
}
```

With Cangjie's current exception mechanism, there is no statically checked way to be sure that all potentially recoverable exception types are treated by a programmer: exceptions lurk implicitly, commonly leading to unpredictable runtime failures.

The workarounds are:
- Document exceptions in comments or `@throws`-style annotations. This fails silently as code evolves: nothing verifies the documentation against actual behavior.
- Perform exhaustive testing of error paths (including I/O), which is not always reliable or practical.
- Abandon exceptions for the `Result<Res, Error>` type, which is verbose and not well-composable ([Section 2.2.1](#221-result)).

When these fall short, errors surface in production, where they are most expensive.

The argument sharpens as code is increasingly machine-generated. Generated code raises volume while lowering per-line review attention, and empirical studies find missing checks that surface as runtime exceptions among its most common defects ("Assessing the Quality of Code Generation by ChatGPT", Liu et al., IEEE TSE 2024). Static contracts are the check that scales with generation, and a compile error is a signal both humans and coding agents can act on before execution: unchecked, an unhandled error path is a silent runtime bug the agent never observes; checked, it must be resolved before the code is done — which forces the decision, though it cannot force a good recovery policy. The same holds for any low-review-bandwidth setting; generation merely makes it the common case.

Let us consider examples of potentially recoverable errors whose handling is better tracked by the type system:
1) **Parsing/deserialization**, working with unknown data from the outside. Various recovery strategies can be imagined: retry the request for data; report to a user; fall back to another format, etc.
2) **Filesystem I/O**. On `FileNotFoundException` a file can be created. On `PermissionException` a user can be asked to fix it. Or more context information can be attached to an error before rethrowing.
3) **Network I/O**. On `TimeoutException` — retry. On `ConnectionRefusedException` — circuit break. On `AuthenticationException` — refresh credentials or request reauthentication.
4) **Mutable state**, which depends on the outside world. For example, a request may be valid only if previous requests have brought the system into a particular state; on a state-mismatch error, the caller can re-synchronize its view of the state and retry.
5) **Library errors**. Libraries generally do not know how a user would react to particular errors, or whether they are really recoverable in a user's domain. So, callers should be required to make the decision themselves.

Conversely, as the taxonomy above indicates, some kinds of errors should not be tracked:
1) **Programmer's errors**. Catching them likely hides defects.
2) **Fatal failures**, such as out-of-memory or stack overflow: no local recovery is realistic.
3) **Fatal by choice**. An error type that is recoverable in principle may still be declared fatal by a programmer who decides not to address it, or to address it in a uniform way at the top level of an application ([Unchecked exceptions](#51-unchecked-exceptions)). Still, making this decision should be forced and explicit.

## 2. Idea overview

We achieve exception checking simply by passing around special objects. Specifically, the `throw` construct, besides an exception of type `E`, requires an object of type `CanThrow<E>` called a **capability**. At the same time, the only way to construct a capability is to use `try-catch`:
```swift
// not a syntax, just an idea
try { cap: CanThrow<SomeException> => // construct capability

    throw (SomeException(), cap)      // use capability

} catch (e: SomeException) {
    // ...
}
```
So, the presence of a capability object proves that there is a handler for the corresponding exception type.

Capabilities are a type-checking construct only: they are fully erased after type checking and have no runtime cost ([ABI and reflection](#310-abi-and-reflection)).

If, however, a capability object escapes a `try-catch`, we will be able to throw an exception outside:
```swift
// not a syntax, just an idea
var f
try { cap: CanThrow<SomeException> =>
    let g = { => throw (SomeException(), cap) }
    f = g
} catch (e: SomeException) {
    // ...
}
f() // no guarantee of handling here
```

To be sure that every exception can only be thrown inside a corresponding `try-catch` and, thus, is always caught, we need to prevent capabilities from escaping.

Modal Cangjie provides the escape-analysis machinery we build on: its modes confine values across function boundaries. Ordinary modes do not distinguish separate `try` scopes inside one function, so a targeted extension additionally ties a capability-capturing value to the exact `try` that supplied the capability ([Section 4](#4-escape-analysis)). We type capabilities as `CanThrow<...> @ local!`; a value capturing one becomes region-bound and try-associated:
```swift
// not a syntax, just an idea
var f
try { cap: CanThrow<SomeException> @ local! =>
    let g = { => throw (SomeException(), cap) }
    // g : (() -> Nothing) @ local?, tied to this try because it captures cap
    f = g // error: must not outlive the try
} catch (e: SomeException) {
    // ...
}
```

We also need a mechanism that propagates capabilities down the call stack implicitly, so that checked exceptions do not place a large syntactic burden on programmers:
```swift
func f(): Nothing
throws SomeException
// capability parameter c2: CanThrow<SomeException> @ local!
{
    throw SomeException() // capability c2 is passed implicitly
}

try { // c1: CanThrow<SomeException> @ local! is available here
    f() // capability c1 is passed implicitly
} catch (e: SomeException) {
    ...
}
```

**Summary**. What is needed to construct a capability-based checked exceptions feature for Cangjie:
1. Ad-hoc implicit function parameters to distribute capabilities.
2. An extension of Modal Cangjie's escape analysis to try-scoped capability regions ([Section 4](#4-escape-analysis)).
3. Further language features: unchecked exceptions, capability list aliases, and capability parameter inference ([Section 5](#5-further-language-features)).

Note that the checked exceptions feature remains useful without Modal Cangjie, as checked documentation ([Section 6.5](#65-checking-without-modal-cangjie)).

### 2.1 Overview of issues and our solutions

Let us discuss the issues that usually bother users of checked exceptions or other similar features, and how we are going to overcome them. All claimed convenience features will be discussed in detail later.

#### 2.1.1 Error composition

Suppose we have the following two functions:
```swift
func f() throws A
func g() throws B
```
If we write a function that calls both of them and propagates their errors, with our approach we can easily do that. It will simply be a function `h` that receives two capabilities:
```swift
func h() throws A, B {
    f()
    g()
}
```

With the `Result` type (as in Rust), the two error types must first be merged into one **type-level sum** — a hand-written `enum`, or a structural sum type added to the language (preferably powered by variance support) — and the values threaded through it. `throws A, B` never forms such a type: the two requirements stay separate, and no type combining `A` and `B` exists anywhere in `h`:
```swift
enum AandB { A(A) | B(B) }

func f(): Result<Unit, A>
func g(): Result<Unit, B>

func h(): Result<Unit, AandB> {
    f() .mapError { e => A(e) }
        .flatMap { _ =>
            g().mapError { e => B(e) }
        }
}
```

#### 2.1.2 Higher-order functions

Capability-based checked exceptions are fully compatible with higher-order functions that invoke their argument during the call. Function literals can simply capture capabilities at the call site. A higher-order function should only guarantee that it does not escape its argument function; APIs that defer execution instead are the limitation of [Lazy computations and `spawn`](#71-lazy-computations-and-spawn).
```swift
func map<T, R>(xs: Array<T>, f: ((T) -> R) @ local?): Array<R>

func sqrtAll(xs: Array<Int>): Array<Int>
throws NegativeException // c: CanThrow<NegativeException> @ local!
{
    map(xs) { x =>
        if (x < 0) {
            throw NegativeException() // capability c is captured
        }
        sqrt(x)
    }
}
```

Other approaches require higher-order functions that propagate callback errors to be polymorphic in the error type.

Note that `map`'s `@ local?` function parameter relies on invoking a `local?` function value — one of the Modal Cangjie specification points tracked in [Section 4.7](#47-open-questions).

#### 2.1.3 Interfaces and inheritance

An interface declaration cannot be aware of all possible exceptions of its implementations. So, in Java, it either prohibits implementations from throwing checked exceptions at all, or exposes a too-general exception type, forcing users of all implementations to deal with it instead of dealing with the concrete exceptions of a particular implementation.

For example, consider the `java.lang.Appendable` interface, which declares that its methods throw `IOException`. However, many standard implementations — `StringBuilder`, `StringBuffer`, `CharArrayWriter`, `PrintStream` — never actually throw it, while I/O-backed implementations such as `FileWriter` and `BufferedWriter` do:
```java
interface Appendable {
    Appendable append(CharSequence csq) throws IOException;
}
```

In our approach, an interface whose implementations share no stable exception contract can stay clause-free; its methods are only annotated with modes. To conform to such an interface, an implementation class can capture all the capabilities it requires (the modal annotations — `local?`, `local!`, `demode`, `exclave` — are introduced in [Section 4.1](#41-modal-cangjie-in-brief)):
```swift
interface Appendable {
    func append(this @ local?, s: String)
}

class FileWriter <: Appendable
captures FileException // store the capability inside instances
{
    demode let path: Path // the field stays ~local inside a local! instance

    init(this @ local!, path: Path) {
        exclave { // mandatory in local! constructors
            this.path = path
        }
    }

    func append(this @ local?, s: String) {
        // ...
    }
}

func test() {
    try {
        // ctor captures CanThrow<FileException> @ local!
        let w: FileWriter @ local! = FileWriter(Path("log.txt"))
        use(w)
    } catch (e: FileException) {
        // ...
    }
}

func use(a: Appendable @ local?) {
    a.append("hello")
}
```

The interface declares `this @ local?` receivers, so its methods are callable on instances of any mode; capability access on `local?` receivers is governed by rule 3 of [Capability capturing](#39-capability-capturing).

The pattern has a cost: capturing region-binds the instance, tying its lifetime to the supplying handler — right for short-lived adapters, wrong for long-lived services. An interface whose implementations predominantly throw one error family should instead declare it; the dividing policy is recorded in [Section 11.2](#112-annotation-of-standard-apis).

#### 2.1.4 Forcing a decision nobody can make

One of the deepest frustrations about checked exceptions is that they force every layer of the call stack to make an error-handling decision, but most layers have no meaningful action to take.

We address this issue in two ways. Firstly, class capturing moves implementation-specific exceptions to the object construction site, so interface users are not required to deal with them.

Secondly, we support unchecked exception types. So, if domain logic decides that an exception can only be handled at the top level, it can wrap it in an unchecked exception, e.g. `RequestException`, that by project convention will be handled at the boundary of a user's request.

#### 2.1.5 Signature pollution across layers

When calling three functions, each of which throws three different exceptions, we end up dealing with nine exceptions:
```swift
func f1() throws A, B, C
func f2() throws D, E, F
func f3() throws G, H, I
func g() throws A, B, C, D, E, F, G, H, I {
    f1(); f2(); f3()
}
```

Firstly, exception hierarchies work as expected. By contravariance of `CanThrow` ([Type of exception capabilities](#31-type-of-exception-capabilities)), a capability for a base exception type satisfies the requirement for any of its subtypes, so declaring a common base covers a whole family with a single entry:
```swift
// A, B, C <: LibException
func f1() throws LibException {
    throw A() // CanThrow<LibException> @ local! is suitable
}
```

Secondly, we provide exception list aliases. So, for exceptions that often occur together, one type can be used:
```swift
type AB = (A, B)
```

Thirdly, we provide capability parameter inference, so `throws` declarations can be mostly omitted in declarations not visible outside the module.
```swift
func h() { // throws A, B, C, D, E, F, G, H, I - inferred
    f1(); f2(); f3()
}
```

Each mechanism trades differently:

| Mechanism      | Benefit                | Cost                          |
| -------------- | ---------------------- | ----------------------------- |
| Base exception | smaller public list    | less per-subtype precision    |
| Alias          | less repetition        | same semantic requirement set |
| Inference      | no internal annotation | public APIs stay explicit     |

#### 2.1.6 API evolution

With checked exceptions, public `throws` changes affect source contracts — adding an entry may break callers, while removing one is generally compatible, though it can strand handlers — but never the base runtime ABI ([Section 3.10.1](#3101-runtime-abi)). Also, some argue that checked exceptions expose a library's implementation details. Let us argue against these considerations.

Firstly, if some exception is removed from the list while a user has logic based on it (e.g. retry), then with checked exceptions there is enough information to issue a warning about unreachable code when the `try` body's throw story is statically closed (a planned diagnostic — [Section 8.14](#814-the-unreachable-catch-diagnostic)).

Secondly, if some exception is added to the list, then this is a potentially recoverable exception, and a user should make a decision about it.

Thirdly, a library should introduce its own exception hierarchy to throw domain errors without exposing implementation details. Checked exceptions help to avoid propagating recoverable errors that expose implementation details.

Note also that a library anticipating evolution can avoid addition-related breaking changes altogether by declaring a base exception type instead of the concrete ones. A signature `throws NetworkException` permits throwing any subtype of `NetworkException`, since the capability for the base type is suitable for all of them ([Type of exception capabilities](#31-type-of-exception-capabilities)). When a later version starts throwing a new subtype, the signature — and therefore client code — does not change: clients already handle `NetworkException`. The cost is precision: clients can no longer be forced to make per-subtype decisions — taken to the extreme, one root type over a whole API recreates the `throws Exception` anti-pattern, so declaring bases suits hierarchies designed for evolution, not blanket use.

The change kinds, in one matrix (binary compatibility is never affected, [Section 3.10.1](#3101-runtime-abi)):

| Change                                                | Source effect on consumers                                                                                |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Add a `throws` entry                                  | may break callers — a new obligation                                                                      |
| Remove a `throws` entry                               | compatible; may strand handlers                                                                           |
| Change a functional type's clause in a signature      | subtyping may break at use sites                                                                          |
| Add or widen `captures` on a class                    | construction sites acquire obligations; instances become `local!`-only; subclass headers restate coverage |
| Change an inferred list of a non-exported declaration | invisible outside the module ([Section 5.3.1](#531-which-declarations-are-inferred))                      |

### 2.2 Other approaches to typed errors

Here we consider other popular approaches to typed errors. Error-union designs, such as Zig's error sets and OCaml's polymorphic variants, sit between the two below: they give `Result`-style errors structural composition, at the cost of union/row machinery that Cangjie lacks.

#### 2.2.1 Result

The ability of a computation to finish with an error can be encoded by returning an `enum Result` defined as follows:
```swift
enum Result<T, E> {
    | Success(T)
    | Error(E)
}

func f(): Result<Int, SomeError> {
    ...
}
```

Although quite popular and easy to understand, this approach has several severe disadvantages:
1. Only one error-type position is available.
    - The single error type can be made to encode several by constructing a combined type — a base type, a union or sum type, or a row — each with its own costs.
2. Every higher-order function must be polymorphic in the error type if it propagates errors from an argument function to the caller.
3. A call site must pattern-match on `Result` even just to propagate an error further. Although some implementations bypass this issue:
    - Rust automatically generates this code via the `try!` macro (or the `?` operator), even with error conversion — such sugar shortens the threading, while the structural costs of points 1, 2, and 4 remain.
    - Swift also generates propagating code (the `try` keyword).
    - Haskell uses the monad interface and `do`-notation.
4. Higher-order functions that propagate callback failures need a version that works with `Result`: `func mapResult<T, R, E>(xs: List<T>, f: (T) -> Result<R, E>): Result<List<R>, E>`.
    - Swift's polymorphism in the error type covers this automatically.

In summary, the capability-based approach solves two key problems of `Result`. Firstly, it never constructs a type-level sum of error types — no union, sum, or row type is needed, because a capability parameter list holds each requirement separately. Secondly, it does not require error type polymorphism, since capabilities can simply be captured by first-class functions.

#### 2.2.2 Row types

An effect row is an extensible set of effect labels (exceptions among them), possibly ending in a row variable; function types record a computation's effects in such a row, and higher-order functions abstract over the row contributed by their callback. For example, in the Koka language, the `map` function can be declared as follows (`e` is the row of effects, e.g., exceptions):
```
fun map(xs : list<a>, f : a -> e b) : e list<b>
match xs
  Nil          -> Nil
  Cons(x, xs') -> Cons(f(x), map(xs', f))
```

This approach still requires explicit effect polymorphism for higher-order function declarations. Moreover, row types would have to be designed and implemented in Cangjie from scratch.

#### 2.2.3 Capability-based: Scala 3 safer exceptions

The closest relative of this proposal is Scala 3's experimental `saferExceptions` feature, which shares the core mechanism: an erased capability `CanThrow[E]` with no runtime footprint, required by `throw` and introduced by `try-catch`. The differences are instructive:

1. **Encoding.** Scala encodes exception lists with union types and context-function types — `R throws E1 | E2` desugars to `CanThrow[E1 | E2] ?=> R` — and capabilities are ordinary givens resolved by general implicit search. Cangjie has neither union types nor general implicits, so this proposal uses dedicated capability parameter lists with set-like subtyping instead ([Section 3](#3-implicit-capability-passing-design)): an ad-hoc but self-contained mechanism.
2. **Soundness story.** Scala's base feature does not enforce non-escape: a closure may capture a capability and escape its `try`, and the documentation asks users to verify non-escape manually ("the only loophole arises for scoped capabilities"). Closing the loophole is delegated to capture checking — a separate extension whose documentation describes it as a highly experimental research project. This proposal instead builds on Modal Cangjie's mode system, extended with try-scoped capability tracking ([Section 4](#4-escape-analysis)), making non-escape part of the base design rather than a future add-on. (The Modal-less mode of [Section 6.5](#65-checking-without-modal-cangjie) is the transitional exception.)
3. **Scope.** Class capturing (`captures`, [Section 3.9](#39-capability-capturing)), automatic exception conversions (an extension, [Section 8.4](#84-exception-conversions)), and capability parameter inference ([Section 5.3](#53-capability-parameter-inference)) have no counterpart in the Scala feature.
4. **Checked/unchecked split.** Scala fixes the split structurally (checked = subtype of `Exception` but not of `RuntimeException`); this proposal makes it an explicit opt-out via the `UncheckedException` base class ([Section 5.1](#51-unchecked-exceptions)).

### 2.3 Related work

The comparisons of Section 2.2 cover the design alternatives; this section records the wider lines of work this proposal draws on, and what it takes from each.

**Capability-based exceptions and effects.** The direct ancestor is "Safer Exceptions for Scala" (Odersky, Boruch-Gruszecki, Brachthäuser, Lee, Lhoták; SCALA 2021; [Scala 3 docs](https://docs.scala-lang.org/scala3/reference/experimental/canthrow.html)), discussed in Section 2.2.3. Its authors' follow-up metatheory, "Capturing Types" (Boruch-Gruszecki et al.; TOPLAS 2023), is the principal rival route to non-escape: capture sets appear in user-facing types, which buys effect polymorphism at the price of a new kind of type — this design keeps capabilities invisible and buys non-escape from the mode system instead ([Section 4](#4-escape-analysis)). "Effects as Capabilities" (Brachthäuser, Schuster, Ostermann; OOPSLA 2020) is the Effekt language's second-class-capability discipline, philosophically closest to our phantom capabilities. The formal antecedent for values confined to their introducing scope is "Gentrification Gone Too Far? Affordable Second-Class Values for Fun and (Co-)Effect" (Osvald et al.; OOPSLA 2016), whose Coq soundness proof is the natural template for formalizing [Section 4.6](#46-exception-safety).

**Modal and locality types.** Modal Cangjie builds on "Oxidizing OCaml with Modal Memory Management" (Lorenzen, White, Dolan, Eisenberg, Lindley; ICFP 2024) and OxCaml's `local` mode ([Section 4.1](#41-modal-cangjie-in-brief)). "Modal Effect Types" (Tang, White, Dolan, Hillerström, Lindley, Lorenzen; OOPSLA 2025) shares this design's goal — no effect-polymorphic higher-order signatures — reaching it through a modal type structure, where this design uses erased capability parameters and confines modes to escape control. "Rows and Capabilities as Modal Effects" (Tang, Lindley; POPL 2026) unifies row- and capability-based effect systems in one modal framework and is the state of the art any formalization of [Section 4](#4-escape-analysis) should measure against; "Data Race Freedom à la Mode" (Georges et al.; POPL 2025) extends the same mode family along new axes with a Coq-mechanized core calculus — the proof bar for this design's escape story.

**Effect handlers.** The encapsulation problem of [Section 8.9](#89-exception-encapsulation) is tunneling ("Abstraction-Safe Effect Handlers via Tunneling", Zhang & Myers, POPL 2019; Biernacki et al., POPL 2020); the compilation strategy of [Section 8.1](#81-optimizing-effect-handlers) is evidence passing ("Effect Handlers, Evidently", Xie et al., ICFP 2020; "Generalized Evidence Passing for Effect Handlers", Xie & Leijen, ICFP 2021). Koka ("Type Directed Compilation of Row-Typed Algebraic Effects", Leijen; POPL 2017) is the mature row-based alternative (Section 2.2.2).

**Mainstream designs.** Swift's typed throws (SE-0413, shipped in Swift 6.0) admits exactly one error type per function and rejected union syntax; the multi-entry lists of [Section 3](#3-implicit-capability-passing-design) are the generalization available to a language without union types ([Section 9.2](#92-functional-type-syntax) records the syntax comparison). Kotlin deliberately made all exceptions unchecked, generalizing from Java's checked-exceptions experience; Section 2.1 is this design's answer to that experience, point by point. Midori's Error Model (Joe Duffy, "The Error Model", 2016) validates the split of Section 1.1 — fail-fast for bugs, statically checked exceptions for recoverable errors — from a large industrial deployment, and Rust's error-conventions RFC 236 draws the same recoverable/unrecoverable line for `Result` versus `panic!`.

## 3. Implicit capability passing design

Implicit capability passing in fact requires an ad-hoc design of implicit function parameters that works only for capability objects. We call them **capability parameters** (which expect **capability arguments** to be passed in).

Capability arguments are just like ordinary function arguments, except that ordinary ones are passed explicitly by programmers, while capability arguments are inferred automatically by the compiler (see inference details below).

A `throws` clause is a **capability-requirement list**, not a may-throw list. Three sets must be kept apart:

| Concept                           | Meaning                                                                                                                                |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Capability requirement (`throws`) | evidence the callable needs from its call site                                                                                         |
| Captured capability set           | evidence stored in a literal or capturing instance ([Section 3.5](#35-first-class-functions), [Section 3.9](#39-capability-capturing)) |
| May-throw set                     | exceptions that may dynamically escape an invocation                                                                                   |

A clause-free callable may still throw checked exceptions through captured capabilities: the design verifies handler presence for every throw; it does not compute may-throw sets.

Capability parameters and arguments exist only during type checking. After that, they are completely erased and have no effect on the ABI.

Note that if Modal Cangjie is disabled, everything below remains valid without the Modal Cangjie annotations and restrictions — except [Capability capturing](#39-capability-capturing), which needs modes; [Section 6.5](#65-checking-without-modal-cangjie) defines that mode.

### 3.1 Type of exception capabilities

`CanThrow<T>`, where `T <: Exception`, is a compiler-known **intrinsic** type: it has no source-level declaration and is not denotable in user-written code — which the `throws` syntax never requires (rationale in [Section 9.7](#97-the-canthrow-intrinsic)).

The type constructor `CanThrow<T>` is contravariant with respect to its argument, so `B <: A ==> CanThrow<A> <: CanThrow<B>`, reflecting that a handler for a base exception type can catch more specific exception types as well:
```swift
try { // c: CanThrow<Exception> @ local! =>
    // CanThrow<Exception> @ local! <: CanThrow<SomeException> @ local!
    throw SomeException() // c is ok here
} catch (e: Exception) {
    ...
}
```

Values of type `CanThrow` only witness the presence of some handler, while the actual handler is still resolved dynamically:
```swift
try {
    let f = { => throw A() }
    try {
        f()
    } catch (e: A) {
        // this handler will run
    }
} catch (e: A) {
    // unreachable
}
```

### 3.2 Capability parameters in declarations

We allow callables to have capability parameters in addition to ordinary parameters. They are declared with a `throws` clause — a soft keyword ([Grammar impact](#10-grammar-impact)) placed like a `where` block: `where` restricts type parameters, `throws` restricts the call site, and the order of the two is arbitrary.

1) **Where `throws` clauses may appear.** On functions; instance and static methods; primary and secondary constructors; interface methods; extension methods; property accessors; operators; and macros. Not on finalizers, foreign functions, `CFunc` types, or variable declarations.
```swift
func f(x: A): B
throws CException, DException
// after desugaring: CanThrow<CException> @ local!, CanThrow<DException> @ local!
{
    ...
}

interface I {
    func m(): Int
    throws MException

    prop q: Int throws WException
}

class A {
    A(let x: Int)
    throws CreationException { ... }

    init()
    throws CreationException { ... }

    func m()
    throws MException { ... }

    prop p: Int {
        get() throws GException { ... }
        set(value) throws SException { ... }
    }
}
```

2) **Entries.** The `throws` keyword is followed by a list of entries. An entry is an exception type — a type parameter bounded by `Exception` included — an alias naming one ([Capability list aliases](#52-capability-list-aliases)), or a parenthesized list of entries, so lists nest arbitrarily. A list denotes the set of exception types obtained by flattening; the `CanThrow<...> @ local!` constructor is never written.
```swift
func g() throws A, (B, C), MyAliases // the set {A, B, C} plus the alias's entries

func eqOrThrow<T, E>(x: T, y: T, mkE: () -> E): Unit
where T <: Equatable<T>, E <: Exception
throws E {
    if (x != y) throw mkE()
}
```

The **semantic form** of every capability list is canonical: a duplicate entry, or an entry covered by a more general entry of the same list, is not part of the list — it introduces no capability parameter, no requirement, and no synthesized field. Coverage is subtyping provable in the declaration's context, `where`-bounds included: an entry `E` with a declared bound `E <: IOException` is dropped from `throws (E, IOException)` already in the open form. Every rule of this document that compares or consumes lists operates on semantic forms.

3) **The empty list.** `()` is the empty list of entries and is legal only as the whole list — not nested in or mixed with other entries. `throws ()` declares that the callable requires no exception capabilities from its call sites.
```swift
func answer(): Int
throws () { 42 }
```

4) **One clause.** A declaration carries at most one `throws` clause, like `where`; a second is an error. A macro that adds requirements merges entries into the existing clause ([Section 9.11](#911-one-clause-per-kind) records the rationale).

5) **`main` and macros.** The `main` function may also have a capability parameter list, which means that the enumerated exceptions should be handled by the default exception handler:
```swift
main()
throws QException {
    // ...
}
```
A macro declaration follows the same pattern with the compiler in the runtime's role, at the **expansion root** only. Within a macro package, macros called from other macros behave as ordinary functions in terms of exceptions.

### 3.3 Capability argument inference

When invoking a callable, capability arguments are not passed explicitly by a call site. Instead, the compiler finds them in the currently active **capability scopes**; since capability arguments do not exist at runtime, checking that a suitable capability is in scope is all that is needed.

#### 3.3.1 Requirement sites

A call requires the capabilities of the callee's `throws` list. The `throw` expression is itself a requirement site: it can be seen as a call to a function `safeThrow`:
```swift
func safeThrow<E>(e: E): Nothing
where E <: Exception
throws E { // requires CanThrow<E> @ local!
    throw e
}
```

#### 3.3.2 Capability scopes

Capability scopes are introduced by:

1) **A `try` block** — one capability per exception type listed in its `catch` patterns (a pattern `e: E1 | E2` introduces two; a wildcard `catch (_)` supplies `CanThrow<Exception>`).
```swift
try {
    // c1: CanThrow<AException> @ local!,
    // c2: CanThrow<BException> @ local! =>
    ...
} catch (e: AException) {
    ...
} catch (e: BException) {
    ...
}
```

2) **A try-with-resources expression** — the same scope as rule 1, extended to the resource initializers: the capabilities the `try` provides are visible there. The implicit `close()` calls are covered dynamically: the specification's equivalent expansion places the user's `catch` clauses outermost, with closing in an inner `finally` — so a capability acquired from this `try` still has its handler on the stack while the resources close.
```swift
try (input = FileReader("in.txt"),   // initializer failure: caught below
     output = FileWriter("out.txt")) {
    output.write(input.read())       // body: same clauses
} catch (e: FileException) {
    // also reached by an exception from an implicit close() —
    // unless the body threw too: then the body's exception wins
    // and the close() exception is discarded (the runtime's choice,
    // not a missing handler)
}
```

3) **The body of a callable with a `throws` list.**
```swift
func f()
throws AException, BException {
    // c1: CanThrow<AException> @ local!,
    // c2: CanThrow<BException> @ local! =>
    ...
}
```

4) **The body of a function literal** whose expected type has capability parameters ([Section 3.5](#35-first-class-functions)).

5) **In a class with a `captures` clause:** constructor bodies and bodies with a `this @ local!` or `this @ local?` receiver (rule 3 of [Capability capturing](#39-capability-capturing)). This scope encloses the members: a member's own `throws` list scope (rule 3) is inner to it.

Some contexts are explicitly *not* covered by the scope they are adjacent to:
- A `catch` block is not inside its `try`'s capability scope: rethrowing a caught checked exception requires a capability from the enclosing scopes. The same holds for `finally` blocks.
- A default parameter value expression is checked against the callable's own capability scope, as if it appeared at the beginning of the body — not against the scopes of any call site.
- An instance field initializer has no scope of its own: its requirements must be satisfiable by the capability scope of every constructor.
- Top-level variable initializers, static field initializers, and finalizers can contain no undischarged checked requirement: no capability scope encloses them.

#### 3.3.3 Resolution

We say that a capability `c` of type `B` is **suitable** as a capability argument for a capability parameter of type `A` if `B <: A` — by contravariance, a handler for a base type serves any of its subtypes ([Section 3.1](#31-type-of-exception-capabilities)). Resolution rules:

1) **Lookup.** Capability argument inference looks for a suitable capability in the active capability scopes; lists on both sides are in semantic form (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)).

2) **Innermost scope wins.** If several capabilities are suitable, the innermost enclosing scope that contains one supplies it. The choice never affects runtime behavior — handlers are resolved dynamically — but it determines the `try` scope that capability-capturing values are tied to, and so which programs type-check:
```swift
func demo()
throws E { // c1: CanThrow<E> @ local!
    var later: (() -> Unit) @ local? = { => }
    try { // c2: CanThrow<E> @ local! — innermost, so the literal below captures c2
        let f = { => throw E() }
        later = f // error: f is tied to this try and must not outlive it
    } catch (e: E) { }
    later()
}
```
Had the outer `c1` been chosen instead, `f` would be tied to the whole body of `demo` and the assignment accepted: the same source, typed differently. Innermost-first is the choice that agrees with dynamic dispatch — a throw at that point would reach the inner handler; the rejected alternatives are examined in [Section 9.12](#912-innermost-first-selection).

3) **Within the scope, the choice is immaterial.** A `try`'s capabilities share the `try`'s region, while the parameters of one declaration or literal, and the captured capabilities of one instance, each enclose their whole scope — any suitable entry yields the same checking. Under semantic forms and single class inheritance, at most one *concrete* entry of a scope is suitable for a concrete requirement anyway — a concrete type's supertypes form a chain.

If no suitable capability is found, a compile error is reported with a message like the following. It spells out the actual type of the capability to avoid surprising users with the mode and type-variance details.
```
Cannot find a capability for `AException` (of type `CanThrow<AException> @ local!`)
in the current scope.
Required by `f(42)` on N:M.
```

#### 3.3.4 Capabilities are not values

**Capabilities are never first-class values.** Explicitly:
1) The type `CanThrow` is not denotable ([Section 3.1](#31-type-of-exception-capabilities)): no variable, field, container element, or generic argument can even be declared to hold a capability — `Box<CanThrow<E>>` is unwritable.
2) No expression evaluates to a capability: capabilities are unnamed and unreferenceable from source, are not bound by `catch` or `match` patterns, and cannot be returned or passed as ordinary arguments (they pass only as implicit capability arguments).

For presentation purposes, in examples we assign names to capabilities; these names are not source syntax.

### 3.4 Functional types

#### 3.4.1 Syntax

Capability parameters are reflected in a functional type with syntax:
```swift
(A, …, Z) throws (AException, …, ZException) -> Result
```
The compiler elaborates it internally to a function type with erased capability parameters (the expanded form is not source syntax, [Section 3.1](#31-type-of-exception-capabilities)):
```swift
(A, …, Z) throws (CanThrow<AException> @ local!, …, CanThrow<ZException> @ local!) -> Result
```
If there is only one capability parameter, parentheses can be omitted:
```swift
(A, …, Z) throws AException -> Result
```
An empty capability list — `()`, the empty entry list of [Capability parameters in declarations](#32-capability-parameters-in-declarations) — is permitted and denotes the same type as omitting the clause:
```swift
(A, …, Z) throws () -> Result // same type as
(A, …, Z) -> Result
```

**Spelling does not create types.** The capability-list component of a functional type is the list's semantic form (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)): entry order, duplicates, covered entries, and `throws ()` versus omission are spelling. Functional types that differ only in spelling are the *same type*, not merely mutual subtypes, so they interchange even where subtyping does not reach — invariant positions and equality constraints. An open type parameter's entry is covered only when provably so — a `where`-bound can prove it in the open form (rule 2); otherwise such equalities appear at instantiation.
```swift
var handlers: Array<() throws Exception -> Unit> = []
let extended: Array<() throws (Exception, IOException) -> Unit> = handlers
// ok: IOException is covered by Exception, so the two type arguments
// are one type — invariance is satisfied by equality, not subtyping
```

Clauses in nested functional types bind to the arrow they precede; the arrow is right-associative:
```swift
() throws A -> () throws B -> Unit
// same as: () throws A -> (() throws B -> Unit)
// a function requiring an A capability that returns a function requiring a B capability
```

This way, we can abstract over exception handlers:
```swift
func retrying<R>(f: (() throws TimeoutException -> R) @ local?): R
throws ServiceUnavailableException {
    // ...
    try {
        let result = f()
        return result
    } catch (e: TimeoutException) {
        // ...
    }
    // ...
}

func sendRequest()
throws TimeoutException

func test()
throws ServiceUnavailableException {
    retrying(sendRequest)
}
```

`retrying` transforms one requirement into another. Its parameter type promises the callback a `TimeoutException` capability, and its own `try` supplies it — the callback's requirement is discharged inside `retrying` and never reaches the caller. What the caller pays is `retrying`'s own clause: `ServiceUnavailableException`, thrown when the retries are exhausted. The call site of `test` handles timeouts nowhere and unavailability once, which is the point.

#### 3.4.2 Subtyping

A functional type `F2` is a subtype of another functional type `F1` if ordinary parameters and the result are related as usual (parameters contravariantly, result covariantly) and the capability parameters of `F2` can be satisfied in every capability scope that satisfies the capability parameters of `F1` — so any call site that provides `F1`'s capabilities can safely invoke an `F2` function. In exception-type terms:
```
Args1 <: Args2 (pointwise)      Res2 <: Res1
forall Cap2 in Caps2. exists Cap1 in Caps1. Cap2 <: Cap1
--------------------------------------------------------
 Args2 throws Caps2 -> Res2 <: Args1 throws Caps1 -> Res1
```
Equivalently, for every capability parameter `CanThrow<Cap2> @ local!` of `F2` there must be a capability parameter `CanThrow<Cap1> @ local!` of `F1` that is suitable for it, i.e. `CanThrow<Cap1> <: CanThrow<Cap2>` by contravariance (see [Capability argument inference](#33-capability-argument-inference)).

Examples:
```swift
func f() throws (AException, BException) {}
// (CanThrow<AException> @ local!, CanThrow<BException> @ local!)

// permutations are spelling — the same type (Section 3.4.1)
let f1: () throws (BException, AException) -> Unit = f

// addition is ok - more requirements
let f2: () throws (AException, BException, CException) -> Unit = f

// pointwise subtyping is ok - requirements are more specific
// AException <: BaseException
let f3: () throws (BaseException, BException) -> Unit = f
// CanThrow<BaseException> @ local! <: CanThrow<AException> @ local!
```

#### 3.4.3 Joins and meets

Wherever the language computes a common supertype of functional types componentwise — the branches of `if` and `match` expressions, array-literal elements — the capability-list component of the join is the **union** of the lists, taken in semantic form (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)): covered entries are not part of the result. Dually, the meet — which the join's parameter positions require by contravariance — keeps the entries that both lists cover: with single class inheritance, of two comparable entries the more specific one, while incomparable entries have no common subtype and contribute nothing. For entries not provably comparable — unbounded generic parameters — contributing nothing is a deliberate loss of precision, not a claim of emptiness.

```swift
func g() throws AException
func h() throws BException

let f = if (cond) { g } else { h }
// f: () throws (AException, BException) -> Unit — the join of the branch types
```

```swift
func p(callback: () throws AException -> Unit)
func q(callback: () throws BException -> Unit)

let k = if (cond) { p } else { q }
// k: (() -> Unit) -> Unit — the parameter type is the meet of the parameter
// types: unrelated AException and BException contribute no common entry,
// so only a requirement-free callback is valid for both branches
```

Joins and meets only combine capability lists that are already fully known: no inference unknown ever stands for a list, so this is not the row-style unification that [Generics](#36-generics) excludes. When type-argument inference reconciles functional types whose known lists differ, the same combination applies.

### 3.5 First-class functions

A function literal can capture capability objects just as it captures any other value. The capturing function object then becomes region-bound itself and is subject to the region discipline of [Section 4.4](#44-capability-regions), which prevents it from escaping. This holds for every way a function object over capabilities arises — a literal, a local function converted to a value, a bound method of a capturing receiver, a compiler-generated wrapper; only the expected-type rule below is specific to literals.

This is the hardest spot of the design for users: the literal becomes region-bound by capturing a value that is not denotable, not visible in the source. A rejection that merely says the literal is `local?` is unexplainable. Diagnostics must reconstruct the chain: which capability was captured, for which exception type, at which `throw` or call inside the body, and which `try` or clause introduced it — with the Modal Cangjie modes spelled out in secondary notes, as the message of [Section 3.3.3](#333-resolution) spells out the capability's full type. Modes are vocabulary the user learns from Modal Cangjie; what never surfaces is its internal/external bookkeeping ([Section 4.7](#47-open-questions)).
```
error: `f` cannot be assigned to `later`: `f` is bound to the `try` at N:M
       because its body throws `E` (at K:L), which that `try` handles.
note: `f` has mode `local?`: it captures the capability for `E`
      (of type `CanThrow<E> @ local!`) introduced by that `try`,
      so it must not outlive it.
```

A function literal can have capability parameters. A capability parameter list cannot be specified manually in a function literal; it is inferred from an expected type.
```swift
func test()
throws SomeException
// c1: CanThrow<SomeException> @ local! =>
{
    let f = { =>
        throw IOException() // error
    }
    let g: () throws IOException -> Unit = { =>
        // c2: CanThrow<IOException> @ local! =>
        throw IOException() // c2 is ok
    }
    withIOException {
        // c3: CanThrow<IOException> @ local! =>
        g() // c3 is ok
        throwingSomeException() // c1 is ok
    }
}

func withIOException<R>(f: (() throws IOException -> R) @ local?): R {
    try {
        f()
    } catch (e: IOException) {
        ...
    }
}

func throwingSomeException(): Unit
throws SomeException
```

### 3.6 Generics

The type of a capability in a capability list can be a polymorphic type variable or can freely include polymorphic type variables:
```swift
func safeThrow<E>(e: E): Nothing
where E <: Exception
throws E {
    throw e
}

func f<T>(): Nothing
throws GenericException<T> {
    throw GenericException<T>()
}
```

The inference of capability arguments depends on the inference of type arguments, not vice versa:
```swift
func test()
throws GenericException<Int> {
    f() // error, not enough information to infer T
    f<Int>() // ok
}
```

Capability parameters of argument functions are not considered in type argument inference (to avoid introducing row-type unification); their ordinary parameter and result components participate as usual:
```swift
f : () throws A -> Unit
func g<T, G>(x: Int, block: () throws (T, G) -> Unit)
where T <: Exception, G <: Exception

g(0, f) // error: unable to infer generic type variables T and G
```

### 3.7 Overloading

For overload resolution purposes, every function signature is considered with capability lists erased recursively — the declaration's own lists and those of every functional type within the signature. Two declarations whose signatures coincide after this removal are rejected at declaration time:
```swift
// compile error
func f(x: Int) throws AException {}
func f(x: Int) throws BException {}

// ok
func g(x: Int32) throws AException {}
func g(x: Float32) throws (BException, CException) {}
```

Consequently, argument function types that differ only in capability parameter lists are the same type for overload resolution:
```swift
// compile error
func h(block: () throws AException -> Unit) {}
func h(block: () -> Unit) {}
```

Why literals could not disambiguate such overloads, and the explicit abstractions that would lift the restriction, are the business of [Explicit capability abstractions](#82-explicit-capability-abstractions).

### 3.8 Overriding and redefinition

The rule for override/redefinition is consistent with the subtyping of functional types.

If a method or property accessor is overridden (redefined) in a subtype, the override's function type must be a subtype of the original's: for every capability parameter of the override (redefinition), some capability parameter of the original must be suitable for it. In exception-type terms, every exception type in the override's `throws` list must be a subtype of some exception type in the original's list. The comparison is of semantic forms after type-argument substitution (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)): aliases expanded, entries instantiated to unchecked types vanished ([Section 5.1.2](#512-capability-requirement-at-throw)), kinds compared separately.

Constructors are not subject to this rule, since they are not overridden: a subclass constructor is a new declaration, and the capability requirements of its `super` call are checked at that call site by the ordinary rules of [Capability argument inference](#33-capability-argument-inference).
```swift
interface I {
    func f()
    throws B, C

    static func g()
    throws Exception
}

class C <: I {
    func f()
    throws B // a narrower list is ok
    {
        // ...
    }

    static func g()
    throws D // CanThrow<Exception> @ local! <: CanThrow<D> @ local!
    {
        // ...
    }
}
```

**Multiplatform matching.** A platform declaration matches its common declaration (Cangjie Multiplatform) only if their capability clauses are equal up to normalization: as sets, up to coverage, aliases expanded. Spelling — order, nesting, an alias versus its expansion, a covered entry — never affects matching. Equality is deliberate where overriding admits narrowing: common callers pay the common list regardless, so a narrower platform list would only let platform surfaces diverge silently.

### 3.9 Capability capturing

Inheritance poses a big challenge for checked exceptions because an interface definition cannot know about all possible types of exceptions that implementations will need to throw. The capability-based approach offers a solution: an implementation class can **capture** the capabilities its methods need when an instance is constructed, so that the methods require nothing from their callers and can override clause-free interface methods.

1) **The clause.** A class declares `captures E1, E2` on its header: every instance stores a capability for each listed type in a synthesized, private field, and the class's methods use those capabilities without receiving them from call sites. Like `throws`, `captures` is a soft keyword ([Grammar impact](#10-grammar-impact)); it takes a list of entries exactly as a declaration `throws` clause does (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)), its position relative to `where` is arbitrary, and a class carries at most one (rule 4 of [Section 3.2](#32-capability-parameters-in-declarations)). Take an interface whose methods carry Modal Cangjie modes, and an existing implementation whose method declares a specific exception:
```swift
interface Appendable {
    func append(this @ local?, s: String)
}

class FileWriter {
    func append(this @ local?, s: String)
    throws FileException {
        // ...
    }
}
```
An adapter captures the capability the implementation requires, so its `append` needs nothing from outside and overrides the interface method (a class written from scratch captures directly, as `FileWriter` does in [Section 2.1.3](#213-interfaces-and-inheritance)):
```swift
class FileWriterAdapter <: Appendable
captures FileException
// instances store c: CanThrow<FileException> @ local!
{
    demode let writer: FileWriter // the field stays ~local inside a local! instance

    init(this @ local!, writer: FileWriter) {
        exclave { // mandatory in local! constructors
            this.writer = writer
        }
    }

    func append(this @ local?, s: String) {
        writer.append(s) // the stored c is passed here
    }
}
```
`captures ()` — or a list statically empty after alias expansion — is equivalent to omission: the class is not capturing.

2) **Constructors.** Every constructor of a capturing type — class or struct — must be `this @ local!`: a `~local` instance could outlive the `try-catch` that supplied the capability, and a `local?` instance could not be tied to it by the analysis of [Section 4.4](#44-capability-regions). Consequently a capturing type has no primary constructor, which is always `~local`, and no implicit default constructor; it declares explicit `init` constructors. Every constructor implicitly requires the captured capabilities at its call site and initializes the synthesized fields, so the fields are present in every instance. When the captured capabilities come from different scopes, the instance is bound to all of them — effectively to the innermost. A type that also needs capture-free instances is a different type. Exceptions unknown to interface users are thus handled at the implementation object's creation site:
```swift
// in FileWriterAdapter:
init(this @ local!, writer: FileWriter) {
    // implicitly receives c: CanThrow<FileException> @ local! from the call site
    exclave {
        this.writer = writer
        // ... and stores c in the synthesized field
    }
}

func test() {
    let w = FileWriter()
    try { // c: CanThrow<FileException> @ local! =>
        let a: FileWriterAdapter @ local! = FileWriterAdapter(w) // captures c
        use(a)
    } catch (e: FileException) {
        // ...
    }
}
```

3) **Receivers.** The capability scope covers constructor bodies and bodies with a `this @ local!` or `this @ local?` receiver — by rule 2, any instance a receiver can refer to carries the capabilities. Finalizers are excluded regardless of receiver mode: they may run after the supplying handlers are gone.
```swift
// `this @ local?` methods are callable on instances of any mode
// (submode accessibility); inside `append`, the captured capability is in scope
func use(a: Appendable @ local?) {
    a.append("hello")
}
```

4) **Subclasses.** Every subclass of a capturing class is itself a capturing class: its `captures` list must cover the superclass's — each superclass entry covered by an own entry of the same kind, possibly a more general one. The capture set of an `open` class is thus part of its public contract: changing it changes what subclasses must declare. Rule 2 then needs no special case for inheritance: the subclass constructor implicitly requires its own listed capabilities, and the `super` call resolves the superclass constructor's requirements from the class capture scope like any call. [Section 9.13](#913-capture-sets-are-restated-not-inherited) discusses the choice of restating over inheriting.
```swift
// a framework's extension point
public open class RotatingFileWriter
captures FileException {
    public init(this @ local!, path: Path) { ... }

    public open func append(this @ local?, s: String) { ... }
}

// extending it in application code
class AuditedFileWriter <: RotatingFileWriter
captures AuditException, FileException // own capture, plus coverage of the superclass's
{
    init(this @ local!, path: Path) {
        // ... super(path) resolves CanThrow<FileException> from the capture scope, like any call
    }

    func append(this @ local?, s: String) {
        audit(s)        // uses the captured AuditException capability
        super.append(s) // the superclass's capability is its own business
    }
}
```

5) **Structs.** `captures` is allowed for `struct`s. Copying duplicates the capability, which is sound: each copy retains the same origin set ([Section 4.4](#44-capability-regions)) — neither may outlive it — and capabilities are freely duplicable evidence. A capturing struct never implements `Copyable` (point 8 of [Section 4.2](#42-what-already-holds)): soundness of copying is not permission to cast out of `local?`.

### 3.10 ABI and reflection

#### 3.10.1 Runtime ABI

Capability parameters and arguments are stripped after type checking:

1) A declaration `func f(x: Int) throws AException` introduces no runtime parameters, instructions, storage, or calling-convention changes: after erasure, its lowering is that of `func f(x: Int)`. Inferred capability lists ([Capability parameter inference](#53-capability-parameter-inference)) are likewise absent from symbols.
2) Values of type `CanThrow<T>` are never materialized at runtime, and `throw` lowers to the same instruction sequence as in unchecked code.
3) The synthesized capability fields of `captures` declarations ([Capability capturing](#39-capability-capturing)) are erased: a capturing class or struct has the same layout as one without the clause.
4) First-class function values share the runtime representation and calling convention of their erased counterpart: `() throws E -> R` is laid out and called exactly as `() -> R`. The functional-type subtyping rule therefore requires no adapter or coercion code at the boundary.
5) A direct consequence: changes to a `throws` list are never a binary-compatibility break; at the source level, additions may break callers while removals are generally compatible (see [API evolution](#216-api-evolution)).
6) How clause changes drive incremental recompilation is implementation design, under one constraint: clauses are absent from symbols but not from typing, so a clause change must invalidate dependents like any signature change.

#### 3.10.2 Reflection and runtime casts

Information about `throws` or `captures` clauses is not available at run time via reflection. It can be made available later ([Reflective clause metadata](#813-reflective-clause-metadata)).

Erasure applies to runtime type arguments too: a clause-bearing functional type and its erased shape are one runtime type with one identity, so printing shows no trace of the clause —
```swift
TypeInfo.of<() throws SomeException -> Unit>() == TypeInfo.of<() -> Unit>() // true: one runtime type
print(TypeInfo.of<() throws SomeException -> Unit>()) // prints the erased type — no trace of the clause

let f: () throws SomeException -> Unit = { => throw SomeException() }
TypeInfo.of(f) // the same type info again
```
Were the first line false — the clause serialized into the type argument's metadata — equality, dictionary keys, and casts would split one type into two. This identity is what the clause-aware relaxation of [Runtime casts to functional types](#812-runtime-casts-to-functional-types) would deliberately give up, which is why that relaxation is a semantic change, not an addition.

Reflective **invocation and construction** are an unchecked boundary:
1) Requirements are not consulted at run time; an exception escaping a reflective call behaves as one from unchecked code.
2) Reflective construction requires no capabilities: the capability fields are erased, so constructing a capturing type succeeds.

Runtime casts and type patterns see the same erased shape and cannot verify a clause:
1) A cast or type-pattern target containing a functional type — in any position — is rejected. Like any checking violation, this is a warning at the `warn` level and an error at `error` ([Section 6.1](#61-compatibility---checked-and-unchecked-code)). Relaxations that make such casts usable are deferred to [Runtime casts to functional types](#812-runtime-casts-to-functional-types).
2) A target with a **parameter-typed** argument — `x as Box<T>` with `T` a type parameter — is accepted: rejecting it would break ordinary generic code. When `T` is instantiated with a functional type, this is rule 1's laundering under another name; such casts are therefore an **unchecked boundary** — outside the guarantee ([Section 6.3.4](#634-scope-of-the-guarantee)).
3) A cast or type-pattern target that is a **capturing type** follows Modal Cangjie's mode-preserving pattern rules: on a region-bound operand it is legal — the result takes the operand's mode.

## 4. Escape analysis

Exception safety hinges on one property: a capability must never be usable after its `try-catch` has finished. Most of this guarantee comes from Modal Cangjie, whose escape analysis keeps values from outliving their regions across function boundaries; lifetimes finer than a function are this design's own. This section summarizes the relevant parts of Modal Cangjie and the reliance points that hold under its current draft ([Section 4.1](#41-modal-cangjie-in-brief), [Section 4.2](#42-what-already-holds)), shows the gap ([Section 4.3](#43-the-gap)), states the capability-region semantics the base design requires ([Section 4.4](#44-capability-regions)) and how they are implemented ([Section 4.5](#45-implementation-strategy)), states the safety property ([Section 4.6](#46-exception-safety)), and lists the open dependencies on Modal Cangjie ([Section 4.7](#47-open-questions)).

### 4.1 Modal Cangjie in brief

Modal Cangjie annotates types with **modes**. On the `local` axis (one axis of a planned tri-axis system, next to `unique` and `immutable`): `T @ local!` (the value is bound to a region and cannot escape it), `T @ local?` (a restricted view: the value may be region-bound or may alias an unrestricted one, and no use of it may extend it beyond its existing region — it can be returned only when it is a parameter or a field of one), and `T @ ~local` (unrestricted, the default). The submode order is `local! <: local?` and `~local <: local?`. A **region** spans one function invocation: it opens when the function is entered and closes when control returns — or earlier, via an `exclave` block, which closes the region and evaluates its block outside of it; `exclave` is banned inside `try`/`catch` blocks and inside `spawn`.

Within a function, a `local!` value is either **internal** (bound to this invocation's region, e.g. a `local!` local variable) or **external** (bound to the direct caller's region, e.g. a `local!` parameter; external becomes internal inside `exclave`). The distinction is deliberately two-level: Modal Cangjie avoids full lifetime analysis, so it never tracks *which* ancestor region a value belongs to, only "mine" vs. "my caller's".

The rules this proposal interacts with most:
- A lambda capturing region-bound state is itself region-bound: a `~local` lambda may capture only `~local` variables; a `local?` lambda may also capture `local?` (including a `local?` alias of a `local!` value); **`local!` variables can never be captured**, and no function object has mode `local!`.
- A `local!` argument can be passed only where it is **internal**; an external `local!` parameter cannot be forwarded to a `local!` parameter of a callee (except inside `exclave`).
- Instance fields take data types and **deeply inherit** the instance's mode; the `demode` modifier pins a field at `~local` regardless of the instance's mode. Assignment into `local?` fields of non-`Copyable` type is prohibited.
- Methods and constructors carry a `this` mode specifier: a method is callable when the receiver's mode is a **submode** of its specifier, methods may overload on the specifier, and overrides must keep it. Constructors are selected by instance mode; `local!`/`local?` constructors must begin with a mandatory `exclave`; primary constructors are always `~local`.
- `throw e` and `perform e` require `e` to be `~local`; a `catch` pattern binds the exception at `~local`.
- A `spawn` block may not reference any outer `local?` or `local!` variable.
- `Copyable` is a declared, struct-only interface — classes and enums can never implement it; `T <: Copyable` licenses free casts out of `local?`.

The updated Modal Cangjie proposal is the authoritative source for these rules; the summary above covers only what this proposal depends on.

### 4.2 What already holds

The following reliance points of this design are confirmed against the updated proposal:

1. **Exception objects are unrestricted.** `throw` requires a `~local` exception and `catch` binds at `~local`, so modes constrain only capabilities, never the exceptions themselves — matching the split this design assumes throughout. OxCaml draws the same line: its stack-allocation rules permit locally allocated `exn` values but allow only global ones to be raised.
2. **`spawn` supplies the execution-context boundary.** The `spawn` rule forbids referencing outer region-bound variables — the boundary [Lazy computations and `spawn`](#71-lazy-computations-and-spawn) needs. Capabilities are unnamed, so the capability analysis applies the same rule to capability use inside `spawn` (rule 6 of [Section 4.4](#44-capability-regions)).
3. **Containers are confined coarsely.** A closure, tuple, array, or object holding a region-bound value is itself region-bound, which blocks cross-function smuggling of carriers. *Which* region a carrier belongs to is not tracked by Modal Cangjie; that is the origin set of [Section 4.4](#44-capability-regions).
4. **The adapter pattern type-checks.** Interface methods with `this @ local?` receivers are callable on instances of any mode under the submode accessibility rule — exactly what [Capability capturing](#39-capability-capturing) needs (rule 4 there covers the capability side).
5. **Capability storage in constructors type-checks.** Once the capability reaches the constructor (rule 4 of [Section 4.4](#44-capability-regions)), storage is ordinary: a `local!` constructor begins with a mandatory `exclave`, inside which `this` and `local!` parameters are both internal, so the assignment into the synthesized field is well-typed.
6. **`super` calls keep the mode.** A `super` or delegated constructor call must select the same `this` mode as the calling constructor — what makes the `local!`-to-`local!` constructor chains of capturing hierarchies well-formed (rule 4 of [Capability capturing](#39-capability-capturing)).
7. **Finalizers cannot reach capabilities.** A finalizer may access only `Copyable` fields, so the synthesized capability field is unreachable from it — the Modal Cangjie side of the finalizer exclusions of [Section 3.3.2](#332-capability-scopes) and [Capability capturing](#39-capability-capturing).
8. **`CanThrow` imposes no requirement on the enum rules.** As a compiler-known intrinsic ([Type of exception capabilities](#31-type-of-exception-capabilities)), a capability can be given any mode directly, and the `Copyable` laundering hazard is closed by construction: the intrinsic implements no interfaces. Modal Cangjie grants `Copyable` types a free `local? → ~local` cast, which would launder a capability out of its `try-catch`; the exclusion exists only to block that cast and imposes no linearity — capabilities remain freely duplicable evidence. A capturing struct ([Capability capturing](#39-capability-capturing)) is likewise not `Copyable`, structurally: its synthesized capability field counts as a non-`Copyable` field, exactly as a reference field would; `Copyable` holds only when every field's type is `Copyable` and cannot be added by `extend`.
9. **FFI cannot smuggle capabilities.** `@C` functions take and return `~local` values only, so neither a capability nor a carrier can cross the foreign boundary; foreign functions and `CFunc` types carry no clauses, and `throws` is rejected on them. Reflection is handled by this design rather than by modes: casts to functional targets are rejected and cannot launder a clause, while reflective invocation is not closed but quarantined as an unchecked boundary ([Reflection and runtime casts](#3102-reflection-and-runtime-casts)).

### 4.3 The gap

Modal Cangjie's regions are per function invocation, and its internal/external tracking is deliberately two-level. Capabilities, however, need **per-`try`-block** lifetimes: a capability must not escape the `try` that introduced it, even within a single function. No combination of the current modes provides this for a `try` body checked *in place* — the desugared reading of [Section 4.4](#44-capability-regions) recovers the granularity from per-invocation regions, at the cost of the deltas stated there. Typing capabilities `local!` conflicts with the capture and forwarding rules of [Modal Cangjie in brief](#41-modal-cangjie-in-brief); typing them `local?` type-checks but is unsound inside one function:

```swift
func f() {
    var g: (() -> Unit) @ local? = ...
    try { // cap: CanThrow<E> @ local? =>
        g = { => throw E() } // local? lambda capturing cap — allowed
    } catch (e: E) { }
    g() // the handler is gone; cap is used after its try closed
}
```

A second canonical escape — the historical hole of the ancestor design ([Section 2.2.3](#223-capability-based-scala-3-safer-exceptions)) — travels through the `try` expression's own result value: nothing throws while the `try` runs, and the capability leaves inside a lazy value.

```swift
let it = try {
    xs.iterator().map { x =>
        if (x < 0) { throw NegativeException() }
        x
    } // lazy: the literal, capturing the capability, is stored inside the iterator
} catch (e: NegativeException) { emptyIterator() }
it.next() // throws; the handler is gone
```

Both examples must be rejected. Every rule they exercise is intra-function, where Modal Cangjie enforces nothing: assignment to a `local?` variable accepts any mode, a `local?` lambda may capture `local?` values, and the value of a `try` takes the join of its branches' modes. The semantics of [Section 4.4](#44-capability-regions) close the gap.

### 4.4 Capability regions

A **capability region** is the dynamic lifetime of a handler; the capability scopes of [Section 3.3.2](#332-capability-scopes) are their lexical counterparts.

**The model.** The region of a `try` is the invocation of its body, exactly as if the body were a callback passed to a runtime-privileged introducer: `try { b } catch (e: E) { h }` reads as `tryCatch(bodyLiteral, handlerLiteral)`, with the introducer supplying the body literal's `CanThrow<E>` parameter, backed by the real handler frame. Under this reading, Modal Cangjie's per-invocation regions already have the right granularity — nested tries are nested invocations — and the rules below are its ordinary capture, return, and call rules, adjusted for the three things a `try` body permits that a literal does not:

- **Free use of enclosing mutable variables.** Ordinary literals cannot capture mutable locals at all; a `try` body reads and writes them freely. The synthetic callbacks are compiler forms exempt from that ban — `spawn`'s block, likewise not an ordinary lambda, is the precedent — accessing mutable free variables in place; writes stay transparent for ordinary values and are disciplined only for region-bound ones (rule 3).
- **`return`/`break`/`continue` crossing the body** — rule 1's exit list.
- **Free use of enclosing `local!` values** — the synthetic callbacks receive them by lambda-lifting: every free variable becomes a hidden parameter preserving its original mode, internal/external status, origin set, and links, never reclassified by the ordinary direct-caller convention.

The model governs **capabilities and carriers only**: ordinary values created inside a `try` remain in the enclosing function's Modal region — the translation refines lifetimes for capability provenance and never re-regions ordinary allocation. In particular, a fresh `local!` value made in the body may be assigned to an enclosing `local!` variable exactly as today.

Three facts fall out of the model rather than needing rules of their own:

- The two escapes of [Section 4.3](#43-the-gap) are an assignment to a captured variable and a return of a non-parameter-derived `local?` value — both already illegal for literals.
- `catch` versus `handle`: an unwound body invocation is gone; a suspended one is live.
- The escape hatch ([Section 5.1.3](#513-the-escape-hatch)) is the same introducer minus the handler.

Every capability has an **origin**: the region of the `try-catch` that introduced it. A capability parameter's origin is whatever the caller supplied; inside the callee it is known only to enclose the invocation, which is all the callee ever needs.

Rules:
1) **Try-region lifetime.** The region of a `try` opens before its resource specifications are evaluated and stays open through the body. When it closes depends on the clause kind:
   - With `catch` clauses, it closes on every exit from the body — normal completion, an exception, `return`, `break`, `continue` — and before any user-written `catch` or `finally` body runs: unwinding into a `catch` is irreversible, so the protected computation will not resume. Requirements raised in those bodies belong to the enclosing region.
   - With `handle` clauses, handlers resume, so the region stays **live** while the protected computation runs *or is suspended in a handler*, across every resumption — closing only when the `try` completes or aborts with no live resumption. Liveness is dynamic and distinct from lexical availability: the handler body still has no lexical access to the region's capabilities ([Section 3.3.2](#332-capability-scopes)).
   - In a mixed form the rule is per path: an exception path irreversibly unwinds and closes the body region before entering `catch`; a performed-command path suspends the body and keeps the region live while `handle` executes.
   - The compiler-generated resource closing of try-with-resources is part of the protected body ([Section 3.3.2](#332-capability-scopes)), not a user `finally`.
2) **Carriers and origin sets.** The values that carry capabilities are the **carriers**:
   - **Root carriers**: a function object capturing a capability, an instance of a capturing type, and — prospectively, should the effect design introduce one — a first-class resumption value (rule 4 of [Effect requirements](#54-effect-requirements)).
   - **Transitive carriers**: an aggregate containing a carrier — a field, array, tuple, or generic container holding one, a bound method of a capturing instance, a compiler-generated function object.
   - Carriers are `local?` at most (function objects) or `local!` (capturing instances); Modal Cangjie enforces that cap across function boundaries.

   A carrier's **origin set** is the union of the origins of the capabilities it captures and of the origin sets of the carriers it stores. A join — the value of an `if`, `match`, or `try` — unions the sets of its branches; copying and aliasing preserve the set.

   An origin set is either `Known(R)` — a set of regions, `main`'s default handler and the synthetic region of the escape hatch being ordinary regions — or `Unknown`, and `Unknown` absorbs every union:
   - A carrier produced at an unchecked boundary — reflective construction ([Reflection and runtime casts](#3102-reflection-and-runtime-casts)) — is `Unknown`, never empty.
   - Checked code cannot type such a value as its capturing nominal class: boundary products are `~local`, and the `~local`-operand cast to a capturing type is the one still rejected (rule 3 of [Reflection and runtime casts](#3102-reflection-and-runtime-casts)). It may still be exposed through a non-capturing supertype, and the `Unknown` provenance propagates with the value into every analysis — throw-closure, lints, the no-throw extension — where it suppresses every negative conclusion.
   - Closed-build verification rejects its sources ([Section 6.3.4](#634-scope-of-the-guarantee)).
3) **Flow condition.** A value with origin set *R* may flow only into storage, or into a result, whose lifetime is contained in every region of *R*. In particular it is neither assigned to a variable declared outside the innermost region of *R*, nor the value of a `try` whose own region is in *R* — the two examples of [Section 4.3](#43-the-gap) — nor stored where Modal Cangjie's `local?` rules would already reject a region-bound value.
4) **Forwarding.** Capability arguments are exempt from the argument-internality rule of [Modal Cangjie in brief](#41-modal-cangjie-in-brief): a capability parameter may be passed on to any callee requirement it covers, and its origin is unchanged by the step.
5) **Call boundary.** A call moves origins in directed ways, all accounted at the call site:
   - *Result.* A `local?` or `local!` result carries the union of the origins of the supplied capability arguments and of the origin sets of every carrier-valued input, receiver included. The capability-argument part is a **result seed**: it attaches to the result value only and follows it forward — into aggregates built from it, and into any later store of it, where it becomes a write and propagates normally — but it never propagates backward through the result's links into the call's inputs. This costs no soundness: the callee's own checking forbids capability-derived carriers from entering external storage, so there is nothing real for backward propagation to model; a validate-and-return call under a local `try` therefore type-checks, while a callee that actually stores a carrier is still caught by the write rule.
   - *Writes.* The receiver and each region-bound (`local!` or `local?`) argument acquire the union of the origin sets of the *other* region-bound carrier inputs — a callee can exchange stored carriers among them. Each acquisition is checked at once against the acquiring object's region, and the taint attaches to the objects, so every alias sees it.
   - *Links.* **Links** are created by every reference-forming operation: a call links its region-bound result to all region-bound inputs and the inputs to one another; a field or element store links container and stored value; aggregate construction links the aggregate to its components; extraction links the result to its source; constructor results are the call case. Links form only between region-bound (`local!`/`local?`) endpoints: a reference to a `~local` value — a `demode` field store included — creates no link, and origin propagation never enters a `~local` value, which is safe because carriers cannot be stored into unrestricted storage at all; the local container depends on the unrestricted referent, never conversely. Links are persistent, symmetric relations that survive returns and copies. Any origin a linked object acquires *through a write* propagates through its link closure, each object checked against its own region — result seeds stay with their value (*Result* above) — this is what catches a write landing behind an alias: a view returned over `box` is linked to it, so tainting the view taints `box`, wherever it is aliased.
   - *Nothing else moves.* A `~local` input acquires no origins, and capability origins reach no input at all: the callee's own checking forbids storing region-bound values into unrestricted storage and capability-derived carriers into external storage, so those flows cannot exist.

   The rule is conservative — a setter that stores nothing still taints its receiver — and needs nothing beyond the call site; a per-declaration summary of which inputs reach which outputs would refine it.
6) **`spawn`.** A `spawn` body uses no capability of an enclosing region and no carrier with a non-empty origin set — the `spawn` rule of Modal Cangjie applied to unnamed capabilities.

### 4.5 Implementation strategy

Two shapes can implement the semantics of [Section 4.4](#44-capability-regions) — not rival semantics, but two ways of realizing its one model, the body-as-callback reading:

a) **Extend Modal Cangjie proper.** `try-catch` opens a real **capability subregion** — one whose allocation rule leaves ordinary user values in the enclosing Modal region, per the model — and the four conflicting rules (lambda capture, argument forwarding, fields, receiver modes) receive capability-specific carve-outs. This reintroduces a slice of the lifetime tracking that Modal Cangjie deliberately avoids, and is a substantial ask of its authors.

b) **Phantom capabilities (adopted).** Capabilities are unnamed, erased, and cannot be referenced by user code, so nothing forces them to be checked as ordinary values. The compiler tracks origins with a dedicated analysis and involves modes only where capabilities enter real values — the carriers, whose mode cap Modal Cangjie enforces today — and checks the flow condition within each function.

Path (b) does not abandon the desugaring of [Capability parameters in declarations](#32-capability-parameters-in-declarations):

- Capability parameters of type `CanThrow<E> @ local!` remain both the mental model and the compiler's unifying representation — capability argument inference, functional-type subtyping, and override checking all operate on them.
- What changes is only which rules check them: dedicated capability rules — equivalent to the general ones minus the restrictions whose motivating hazards cannot arise for opaque, immutable, erased values — instead of the general Modal Cangjie value rules.
- This matches the erasure semantics of [ABI and reflection](#310-abi-and-reflection): values that never exist at runtime never reach the parts of Modal Cangjie that manage memory.

The dedicated rules must not be ad-hoc, however. Extensions introduce capability kinds that are real, region-bound runtime values — a handler closure ([Optimizing effect handlers](#81-optimizing-effect-handlers)), a handler identity ([Exception encapsulation](#89-exception-encapsulation)) — to which rules special-cased on opacity and erasure cannot apply, yet which must share one region model with the phantom kinds. Path (b) is therefore defined as an implementation of the semantics of [Section 4.4](#44-capability-regions): its checks enforce exactly what try-scoped regions enforce.

We name this the **lowering-independence invariant**: which programs type-check is determined by the capability-region semantics alone, never by how capabilities are represented. The exception-safety theorem of [Section 4.6](#46-exception-safety) is stated against this invariant, so it extends unchanged to capability kinds with runtime content.

Modeling `try-catch` as a region fits the modal foundation. Modal Cangjie builds on the modal-types line of work ("Oxidizing OCaml with Modal Memory Management", Lorenzen et al., ICFP 2024) and OxCaml's `local` mode, whose published semantics nests regions — "Regions nest, for instance when defining a local function", with `exclave` ending the current region and evaluating in the enclosing one; an earlier revision of the Modal Cangjie draft also carried a first-class `region(E)` construct in its core calculus. Only the surface language collapses regions to one per function invocation, so path (a) would negotiate surface rules, not the foundation.

The reliance on Modal Cangjie is severable: the clause machinery of [Section 3](#3-implicit-capability-passing-design) is mode-independent, while the escape discipline of [Section 4.4](#44-capability-regions) is not offered without Modal Cangjie. [Section 6.5](#65-checking-without-modal-cangjie) defines the degraded checking mode available without it.

### 4.6 Exception safety

The intended metatheory, whose core-calculus proof is proposed as future work ([Section 12](#12-todo)):

> **Theorem (exception safety).** In a closed build of `error`-level packages, with full Modal checking, containing no fabricated capabilities ([The escape hatch](#513-the-escape-hatch)), entered only through the `main` of a checked package, and with no transition through an unchecked invocation boundary ([Scope of the guarantee](#634-scope-of-the-guarantee)), every checked exception raised by `throw e` or injected by `resume throwing e` encounters a matching handler on the current stack — `main`'s default handler counting as one.

> **Lemma (erasure).** Erasing capabilities from a well-typed checked program leaves its runtime behavior unchanged.

The theorem extends to effect requirements by the substitution of [Section 5.4](#54-effect-requirements) — every executed `perform` encounters a matching live handler — with its premises read on the effect axis (`error`-level checked-effects packages, no unchecked-effects boundary, [Section 6.1](#61-compatibility---checked-and-unchecked-code)) and one added premise: resumptions never outlive their `handle` clause (rule 4 of [Section 5.4](#54-effect-requirements)).

Proof approach:

- *Translation.* The model of [Section 4.4](#44-capability-regions) is the translation: desugar each `try` into a call of a privileged introducer with the body as a callback, and instrument the operational semantics so that each introducer invocation pushes a fresh region token and each capability carries the token of its origin.
- *Preservation.* A token never becomes reachable after its frame is popped and never crosses an execution-context boundary — the flow condition, the call-boundary rule, and the `spawn` rule of [Section 4.4](#44-capability-regions).
- *Progress.* Every operation that raises or injects a checked exception — `throw e`, and `resume throwing e` ([Section 5.4](#54-effect-requirements)) — requires a capability, hence a token, hence a live matching handler frame; the premises exclude fabricated and unknown capabilities, so every token is a handler's.
- *Erasure.* Tokens are never inspected by program semantics, so erasing them — and all capabilities — leaves behavior unchanged, which is the erasure lemma and the justification for [ABI and reflection](#310-abi-and-reflection).

### 4.7 Open questions

What remains open are dependencies on the Modal Cangjie draft; the semantics of this design are stated in [Section 4.4](#44-capability-regions).

1. **Argument internality.** The updated proposal's call rule attaches the internality requirement to `local!` *arguments* rather than `local!` parameters. Read literally, this rejects forwarding an external `local!` to a `local?` parameter, which breaks ordinary code. Capabilities are unaffected under path (b) (rule 4 of [Section 4.4](#44-capability-regions)), but this document's examples that pass `local!` values rely on the intended reading — a **blocking dependency** on the Modal Cangjie authors until the rule is restated over parameters.
2. **Unwinding of function regions.** The Modal Cangjie proposal does not specify how its regions interact with exception propagation, `finally`, or `exclave` during unwinding; its ban on `exclave` inside `try`/`catch` blocks is adjacent but not this (and omits `finally`). Capability regions have their own lifetime rule (rule 1 of [Section 4.4](#44-capability-regions)); the interaction with function regions must be pinned down with the authors.
3. **Missing specification we depend on.** Invoking a `local?`/`local!` function value (the higher-order pattern of [Functional types](#34-functional-types)); generics × modes beyond the stated rule that modal types cannot be generic arguments; `for-in` iteration over `local!` iterator values, which IO-backed capturing iterators need ([Standard library and toolchain impact](#11-standard-library-and-toolchain-impact)).
4. **Locality of resumptions.** Checking effect requirements ([Section 5.4](#54-effect-requirements)) needs a resumption never to outlive its `handle` clause: resumed after the handler is gone, the body would run with a capability whose handler no longer exists. Today's implicit `resume` statement satisfies this by construction. The question is standing guidance for the effect design's evolution: should a first-class resumption value ever be introduced, it must be confined — a `local!` value bound to the handler body's region, not storable, not transferable to another execution context — or this design imposes the binding itself (rule 4 of [Section 5.4](#54-effect-requirements)). The same boundary carries value flows: how ordinary modes and lifetimes pass through `resume with` into the `perform` result is likewise the Modal proposal's to specify — rule 6 of [Section 5.4](#54-effect-requirements) states only the capability-region side.
5. **Reflective construction.** Reflection can instantiate a type whose every source constructor is `this @ local!`, yielding an unrestricted instance Modal construction rules forbid ([Reflection and runtime casts](#3102-reflection-and-runtime-casts)). Whether reflection is likewise a Modal-unsafe boundary — or such construction is rejected under Modal checking — is the Modal proposal's call.
6. **Diagnostics.** The internal/external distinction is counterintuitive even by the Modal Cangjie proposal's own admission; capability-related errors must never surface it. The spelled-out message of [Capability argument inference](#33-capability-argument-inference) is the model.

## 5. Further language features

No safety feature will be adopted if it is inconvenient to use. This section defines the exception taxonomy and the escape hatch, the features that reduce the annotation burden — aliases and inference.

### 5.1 Unchecked exceptions

For some exceptions, an application developer decides that no local recovery is meaningful: they are handled uniformly at a top-level fault barrier, or they abort the program. Typically these report programmer errors — violated contracts and invariants. Tracking them in every signature would be noise — worse, it would force handlers where no recovery exists, and a handler written to satisfy the compiler hides the defect it catches. So we make them unchecked.

#### 5.1.1 Definition

```swift
public open class UncheckedException <: Exception {}
```

Among subtypes of `Exception`, a type is **unchecked** iff it is a subtype of `UncheckedException`, and **checked** otherwise; the separate `Error` hierarchy is neither — it is untracked. Because Cangjie has single class inheritance, the classification is automatically coherent: no class can be a subtype of `UncheckedException` and of an unrelated checked class at the same time, so every exception type is unambiguously one or the other.

The fatal `Error` hierarchy is not an `Exception` and lies entirely outside capability tracking, by design: it reports conditions no program should handle locally.

`catch` of an unchecked type is legal and behaves as today.

#### 5.1.2 Capability requirement at `throw`

After ordinary typing establishes that `e` has a legal throwable type, `throw e` requires a capability based on the **static type** `T` of `e`:
1) If `T` is not a subtype of `Exception` — the fatal `Error` hierarchy ([Section 5.1.1](#511-definition)) — no capability is required: such throws lie outside tracking.
2) If `T <: UncheckedException`, no capability is required.
3) Otherwise a capability for `CanThrow<T>` is required — including when `T` is a common supertype such as `Exception` itself. This is sound: the requirement covers every checked exception the value might be.

**Unchecked types in `throws` lists.** A concrete entry of a `throws` list must not be a subtype of `UncheckedException`: throwing an unchecked exception never requires a capability, so such an entry would be misleading, and it is rejected with a dedicated diagnostic. Type parameters are exempt: a requirement whose type instantiates to an unchecked exception type is trivially satisfied, and after type-argument substitution the entry vanishes — `() throws E -> R` with `E` instantiated to an unchecked type is the clause-free `() -> R`. A capturing class whose `captures` entry instantiates to an unchecked type remains a capturing class — `local!` instances, `this @ local!` constructors — and only the construction-site obligation for that entry vanishes.
```swift
func h() throws IllegalStateException { ... } // error: unchecked type in a throws list
```

#### 5.1.3 The escape hatch

Migration and boundary code sometimes *know* an exception cannot occur, or deliberately accept a crash. We provide a scoped assumption instead of exposing capability values:

```swift
public func unsafeCanThrow<E, R>(f: (() throws E -> R) @ local?): R
where E <: Exception
```

`unsafeCanThrow<E>(f)` runs `f`, supplying the fabricated `CanThrow<E>` the name grants:

1) It is a type-level assumption with zero runtime content: if an `E` actually escapes `f`, it propagates exactly as an unchecked exception would.
2) It is a compiler intrinsic with a library-visible signature in `std.core` — no source operation fabricates capabilities.
3) Its polarity is the opposite of assumption imports ([Assumption imports](#632-assumption-imports)), which *add* obligations: this construct removes them.

`E` is written explicitly: capability lists do not participate in type-argument inference ([Generics](#36-generics)), so it cannot be inferred from the argument. The shape of the construct is discussed in [Section 9.10](#910-the-escape-hatch-as-a-higher-order-intrinsic).

### 5.2 Capability list aliases

If several exceptions commonly recur together in some piece of code, an alias can be introduced to avoid repetition.

A tuple of exceptions is treated as a capability list:
```swift
type MyModuleExceptions =
    (NetworkException, FileNotFoundException)

func f()
throws MyModuleExceptions { ... }
// same as
func f()
throws NetworkException, FileNotFoundException { ... }
```

Rules:
1) When an alias is used in a `throws` list, every element of its tuple must be a subtype of `Exception` and not of `UncheckedException`, matching rule 2 of [Capability parameters in declarations](#32-capability-parameters-in-declarations) and the unchecked-entry rule of [Unchecked exceptions](#51-unchecked-exceptions); the alias itself remains an ordinary tuple type elsewhere.
2) Elements may be type parameters and other aliases; expansion is applied recursively, and cycles are rejected. A type parameter bounded by `Exception` is admitted and may later instantiate to an unchecked type, in which case its entry vanishes like a direct generic entry ([Unchecked exceptions](#51-unchecked-exceptions)); one bounded by `UncheckedException` is rejected.
3) Tuples nest arbitrarily and flatten, as in rule 2 of [Capability parameters in declarations](#32-capability-parameters-in-declarations): naming a tuple and writing it inline are interchangeable.
4) An ordinary single-type alias works in a `throws` list as the type it names.
5) Aliases are the only way to name a list. A tuple is not an exception type: a type parameter bounded by `Exception` cannot be instantiated with one, so a list cannot be passed through generics — `f<(A, B)>()` against `func f<E>() throws E where E <: Exception` is rejected. Passing lists is [Capability-list polymorphism](#83-capability-list-polymorphism).
6) Aliases are transparent across packages: an exported list is the alias's expansion, so redefining an alias changes every exported list that uses it once its declaration is rebuilt.

### 5.3 Capability parameter inference

Listing all exceptions on every function declaration is tedious. We can relax this requirement and only require programmers to write exceptions explicitly on declarations visible outside the module. For the rest, we employ **capability parameter inference**.

Capability parameter inference works after type inference and before capability argument inference. It analyzes function calls and `throw` expressions in a given callable declaration, and infers the list of required capabilities.
```swift
func g(): Unit { // inferred throws AException
    throw AException()
}

func f(): Unit { // inferred throws AException, BException
    g()
    println(map(xs) { x =>
        if (x < 0) throw BException()
        sqrt(x)
    })
}
```

#### 5.3.1 Which declarations are inferred

Inference applies only to declarations that do not leave the **module**; we call the others **exported**.

- Visibility is effective visibility — the narrowest of the member's own modifier and those of its enclosing declarations.
- `private` declarations and `internal` ones — the default, visible to the package and its subpackages but to no other module — are inferred. So is a `private init` of a `public` class, or a `public` method of an `internal` class.
- Effectively `public` or `protected` declarations are never inferred: their lists never depend on their bodies, and a `protected` member may be overridden in other modules ([Package metadata](#62-package-metadata)). Top-level `protected` declarations are module-confined, but are kept with the exported ones deliberately — one rule per modifier, not per position.
- `main` is never inferred: a throwing `main` writes its list (rule 5 of [Capability parameters in declarations](#32-capability-parameters-in-declarations)). Macro declarations follow the general rule: a `public` macro is exported and never inferred — omission is its authoritative empty expansion-root clause — while a non-public macro can never be an expansion root and is an ordinary inference-eligible declaration.

This keeps the published API of a module independent of inference details and stable against changes in the bodies of its non-exported helpers. Inferred lists of `internal` declarations are recorded for subpackages ([Package metadata](#62-package-metadata)), and churn from them stays inside the module.

An override or implementation is checked against the overridden declaration's list ([Overriding and redefinition](#38-overriding-and-redefinition)) whether its own list is inferred or written. An inferred override requiring more than the overridden list is an error: a list depends on its own body only, never on its overriders.

Omitting the clause on an exported declaration is not an error: omission is the authoritative empty clause, identical to writing `throws ()` ([Section 5.3.5](#535-interaction-with-an-explicit-throws)). Requirement-free APIs — the majority — thus carry no annotation at all, and a body that does require a capability reports the error at the offending site, exactly as under an explicit `throws ()`. This matches the boundary rule that an unchecked package's lists read as empty ([Package metadata](#62-package-metadata)): a bare exported signature means "requires nothing" everywhere.

The rule covers all kinds of callables — top-level functions, instance and static methods, primary and secondary constructors, property accessors, extension methods, and operators. Accessors have no modifier of their own and take their property's visibility. An interface method declaration is treated as `public` for this purpose: its `throws` list is part of the interface contract and must be written explicitly.

Function literals never infer their own capability-parameter lists: the list is taken from the expected functional type, as described in [Section 3.5](#35-first-class-functions), and is empty when no expected type is available. Their bodies are still analyzed: a requirement not covered by the literal's own parameters resolves lexically from enclosing scopes — inside an inferred callable it thus contributes to that callable's inferred list, and the literal captures the resulting capability. Compiler-generated function objects follow the same rule; local function declarations are ordinary inference-eligible declarations with lists of their own.

#### 5.3.2 What is inferred

For an inference-eligible callable without an explicit `throws` clause, the inferred capability list is the union of the capability requirements collected from its body:

1. Every `throw e` contributes the **static type** `E` of `e`, when checked.
2. Every invocation the body performs, explicit or implicit, contributes the entries of the callee's post-inference `throws` list — the statically selected declaration's list or, for a call through a function value, the list of its functional type. Implicit invocations include `super` and delegating constructor calls, the capture obligations of capturing constructors ([Capability capturing](#39-capability-capturing)), property accessors, operators and indexing, the iterator protocol of `for-in`, and macro-generated calls.
3. A default-parameter expression contributes to its own declaration's list. An instance field initializer contributes to every inference-eligible constructor that evaluates it (the bullet of [Section 3.3.2](#332-capability-scopes)).

Discharge is decided **per requirement site**: a site contributes its exception type only if no capability scope active at that site covers it — an enclosing `try-catch`, the capability parameters of an enclosing literal, or the class capture scope ([Section 3.3](#33-capability-argument-inference)). Requirements in `catch` and `finally` blocks lie outside their `try`'s scope and propagate outward. The inferred list is the union over unsatisfied sites; it is attached to the declaration as if written explicitly and propagated to callers through the normal capability-argument inference of [Section 3.3](#33-capability-argument-inference).

#### 5.3.3 Phase ordering

Capability parameter inference runs as a distinct phase, after type and mode inference and before capability argument inference; the scope check of [Section 4.4](#44-capability-regions) runs last:

```
type/mode skeletons → capability parameters → clause components of types → capability arguments → escape check
```

Skeletons are complete without inferred lists: ordinary unification never infers from capability-list components ([Section 3.6](#36-generics)), though known clauses of expected types are read when checking literals against them. The clause components of types that contain *inferred* lists — such as the join of two inferred declarations in an `if` expression ([Section 3.4.3](#343-joins-and-meets)) — are completed after capability parameter inference, which is sound precisely because no earlier stage consults them.

The pipeline is acyclic because every arrow points right — capability analysis *reads* types and modes and never produces them:
- Capability lists of argument functions are excluded from generic type-argument inference ([Section 3.6](#36-generics)), and a literal's capability parameters come from its expected type only, never from its body or captures ([Section 3.5](#35-first-class-functions)). Modal Cangjie synthesizes a literal's *mode* from its ordinary captures at mode-inference time, where those captures are syntactically known; capability captures become known only in the capability phase.
- The `@ local!` mode on capabilities is fixed by the desugaring of `throws` and is not itself inferred.
- Capability analysis never changes a mode. A carrier keeps the mode Modal Cangjie inferred for it; the final check rejects every use of a carrier — or of a transitive carrier built from it — that would be illegal for a `local?` value: assignment, return, a join, aggregate construction, argument passing, receiver accessibility, constructor selection. This is the "cap" of [Section 4.4](#44-capability-regions), enforced as validation. The one place capability machinery reads receiver modes (rule 3 of [Capability capturing](#39-capability-capturing)) also sits in this final stage, when modes are final.
- The ordering is sound because validation only ever rejects — it never re-types and never re-resolves. The one construct it cannot serve is overloading on modes — the receiver specifier or parameter modes, both of which Modal Cangjie admits: a carrier discovered after overload resolution could invalidate the chosen overload, and re-resolving would silently change which code runs, so such programs are rejected with a capability-aware diagnostic — a stated completeness loss.

Capability arguments only require knowing the inferred capability list of each callee, which is available once the inference phase has completed.

#### 5.3.4 Recursion

Recursion — self-recursion or mutual — does not require explicit clauses. Within a strongly-connected component of the call graph restricted to inference-eligible declarations — its edges are calls and also *references*, since a reference's type carries the referenced declaration's list — the inferred lists are the **least solution** of the monotone equations

```
C(f) = local(f) ∪ ⋃ over call sites in f: (C(callee) ∖ discharged at the site)
```

where `local(f)` collects `f`'s own requirements and the per-site subtraction is the discharge of [What is inferred](#532-what-is-inferred) — by coverage, not literal set difference: `catch (e: BaseException)` discharges every requirement it covers.

- The candidate exception types are finitely many and union is monotone, so the least fixpoint exists, is unique, and is computed by iterating from empty lists to stabilization. Lists are compared up to coverage ([Functional types](#34-functional-types)), so coverage-redundant entries never accumulate.
- Least is also the right semantics: the smallest lists that make the cluster well-typed — what a user would have written by hand.
- Inference proceeds bottom-up over the components of the call graph. Cycle members are solved together, and a member carrying an authoritative explicit clause ([Section 5.3.5](#535-interaction-with-an-explicit-throws)) enters the equations as a constant, checked as usual.

The one case still requiring explicit clauses is **polymorphic recursion** over exception-relevant type parameters. The accepted fragment: along every cycle of the component, each such type parameter maps to itself, to another type parameter of the component, or to a closed type — then the candidate universe is finite. When a cycle re-enters a member at a growing instantiation (`f<T>` requiring `GenericException<T>` while calling `f<Box<T>>`), inference is rejected with an error naming the growing instantiation, and each member of the cycle declares its clause explicitly.

#### 5.3.5 Interaction with an explicit `throws`

If a declaration carries an explicit `throws` clause without the `...` marker (described below), inference is *not* performed for it. The explicit list is authoritative: each `throw` and each call inside the body is checked against it by the ordinary rules of [Section 3.3](#33-capability-argument-inference), and any missing capability is reported as an error at the offending site rather than silently added. This avoids surprising the user by augmenting a list they have written deliberately.

```swift
func f()
throws AException {
    throw AException() // ok, discharged by the explicit list
    throw BException() // error: no capability for `BException`
                       // (inference is disabled because of `throws AException`)
}
```

To opt back into inference, the explicit `throws` clause has to be removed — or ended with the `...` marker: `throws A, ...` declares `A` and re-enables inference, whose results are unioned with the explicit entries. This is useful when one exception deserves explicit documentation while the rest of the list would be maintenance burden.

```swift
func g()
throws AException, ... {
    throw AException() // ok, explicit
    throw BException() // ok, inferred in addition to the explicit entries
}
```

Placement of `...`:

- It appears only as the last entry of the `throws` clause, at most once; `throws ...` alone is the explicit spelling of "infer".
- It is not allowed on exported declarations, whose lists must not depend on inference ([Which declarations are inferred](#531-which-declarations-are-inferred)) — an opt-in for them is a possible extension ([Section 8.15](#815-inference-opt-in-for-public-declarations)) — and never appears in functional types ([Functional types](#34-functional-types)), whose capability lists are always complete.

A danger for generated code, stated plainly: a generator cannot see a declaration's inference status. Merging entries into an existing clause preserves that status — added entries leave an authoritative list authoritative and an open list open. But creating a clause on a bare declaration closes it (loudly: its other requirements become errors), and appending `...` to an authoritative list opens it, silently weakening the author's pin. The compiler does not police this; generators must choose which status they preserve.

The dual of `...` is the empty clause: `throws ()` is an authoritative empty list.

- It disables inference and asserts that the callable requires no exception capabilities from its call sites: any checked `throw` or call whose requirement is not discharged locally — by a `try-catch` or by a captured capability — is an error.
- Unlike omission, which for non-exported declarations means "infer", the empty clause pins this property against future edits of the body; on exported declarations omission already means the empty clause ([Which declarations are inferred](#531-which-declarations-are-inferred)).
- So `throws ()` means the same everywhere — the empty list, as in functional types ([Section 3.4.1](#341-syntax)). Only omission varies: the empty list on functional types and exported declarations, "infer" on inferable ones.
- It is *not* a no-throw guarantee: checked exceptions may still escape through capabilities captured by the instance or by enclosed literals ([No-throw guarantee](#86-no-throw-guarantee) explores that stronger property).

### 5.4 Effect requirements

Cangjie's effect handlers give `perform` the same problem `throw` has: a command performed without a handler in the dynamic context fails at run time. The capability mechanism checks it the same way. Performing a command of type `C` — a subtype of `Command<R>` — requires a capability of type `CanPerform<C>`; a `handle` clause of a `try` expression introduces one for its command type; and a declaration states its requirements with a `performs` clause.

```swift
class GetLogger <: Command<Logger> {...}

func f()
performs GetLogger {
    perform GetLogger().log("entered f")
}

func withLogger<R>(f: () performs GetLogger -> R): R {
    let logger = Logger()
    try {
        f()
    } handle (_: GetLogger) {
        resume with logger
    }
}
```

Every rule of [Section 3](#3-implicit-capability-passing-design) and [Section 4](#4-escape-analysis) applies under the substitution `throw` → `perform`, `catch` clause → `handle` clause, exception type → command type, `CanThrow<E>` → `CanPerform<C>`, `throws` → `performs`. Spelled out:

- `CanPerform` is a compiler-known, contravariant, erased, non-denotable intrinsic like `CanThrow`.
- `performs` is a clause of its own: at most one, `()` is the empty list; in functional types it precedes `throws`, while in declarations the `where`, `performs`, and `throws` blocks order freely ([Section 9.1](#91-keyword-scheme-throws-performs-captures)). Functional types carry both lists and are compared componentwise; an override may only narrow its `performs` list, as for `throws` ([Section 3.8](#38-overriding-and-redefinition)).
- One entry grammar serves all capability clauses (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)): which kinds a clause admits is validated at the use site — `throws` exception entries, `performs` command entries, `captures` both — and aliases are validated after expansion where they are used.
- `captures` may name commands. An entry's kind follows its hierarchy — a subtype of `Exception` stores `CanThrow`, a command type stores `CanPerform`; one list may mix kinds, and coverage never crosses kinds. Command entries carry the construction-site obligations and instance lifetime of exception entries ([Section 3.9](#39-capability-capturing)).
- The region of a `handle` clause is its `try`'s, and a `perform` in a `catch` or `handle` body resolves to the enclosing scopes.

Where effects differ:

1) **No inference.** A `performs` list is written on every declaration: effect requirements are semantic contract. Function literals still take their lists from the expected type. There is no `...` for effects.
2) **No unchecked commands.** There is no `UncheckedException`-style opt-out hierarchy for commands: every command type is tracked. The rest of the unchecked machinery extends by substitution — `--enable-checked-effects` with the same `warn` and `error` levels (the effect axis of [Section 6.1](#61-compatibility---checked-and-unchecked-code)), assumption imports as `@AssumePerforms` ([Section 6.3.2](#632-assumption-imports)), and the escape hatch as the twin intrinsic `unsafeCanPerform<C, T, R>(f: (() performs C -> R) @ local?): R where C <: Command<T>` — a separate name, since clause components cannot distinguish overloads ([Section 5.1.3](#513-the-escape-hatch), naming in [Section 9.10](#910-the-escape-hatch-as-a-higher-order-intrinsic)). A fabricated `CanPerform` that turns out wrong fails at the `perform` site, exactly as in unchecked-effects code.
3) **`main` and macros take no `performs` clause.** There is no default effect handler, and the compiler's expansion boundary handles exceptions only (rule 5 of [Capability parameters in declarations](#32-capability-parameters-in-declarations)). A macro body may still use `try-handle` internally.
4) **Resumptions are handler-bound.** The effect design provides only an *implicit* resumption: `resume` is a statement of the `handle` body, not a value. It cannot be named, stored, or transferred, so its confinement to the `handle` clause holds by construction.
5) **`resume throwing e` is a requirement site.** It injects `e` at the suspended `perform` site, so it is checked as a `throw e` there: classified by the static type of `e` ([Section 5.1.2](#512-capability-requirement-at-throw)) and resolved by the scopes that cover every possible `perform` site — the `try`'s own `catch` clauses and the scopes enclosing the `try-handle`. The site participates in explicit-clause checking, capability parameter inference, and throw-closure like any `throw`. `catch` clauses nested around the `perform` itself are not consulted: that needs a typed throw-contract on resumptions ([Capability-list polymorphism](#83-capability-list-polymorphism)).
```swift
try {
    f()                          // performs GetLogger somewhere inside
} catch (e: LoggerUnavailable) {
    // ← discharges the resume below: the injected exception
    //   surfaces at the perform, inside this try's body
} handle (_: GetLogger) {
    resume throwing LoggerUnavailable() // ok: a throw at the perform site
}

try {
    f()
} handle (_: GetLogger) {
    resume throwing LoggerUnavailable() // error: no catch on this try and
    // no CanThrow<LoggerUnavailable> in the enclosing scopes; a catch
    // around the perform inside f would not be consulted
}
```

The clause syntax parses unconditionally ([Grammar impact](#10-grammar-impact)); its meaning requires the effect-handler feature, which is experimental ([Section 6.1](#61-compatibility---checked-and-unchecked-code)). Compiling handlers to closures stored in capabilities is the optimization of [Section 8.1](#81-optimizing-effect-handlers).

## 6. Compatibility, interoperability and migration

Smooth migration and compatibility are among the biggest challenges when adding exception safety to a mature language with unchecked exceptions.

### 6.1 Compatibility - checked and unchecked code

To preserve backward compatibility, Cangjie code is compiled by default with exception checking off. Checking is enabled per package by the `--enable-checked-exceptions <level>` flag (taking its value as a separate argument like other valued options; initially in the experimental group, requiring `--experimental`, like `--enable-eh`), at one of two levels:
- `warn`: all checking runs, violations are reported as warnings, and clause metadata is recorded. This is the migration level — a package annotates incrementally while still building. The warnings form a dedicated warning group, `checked-exceptions` (suppressible with `-Woff checked-exceptions`).
- `error`: violations are errors.

With checking off, the clause syntax is still parsed (the grammar is unconditional, [Grammar impact](#10-grammar-impact)) but imposes no obligations and is not recorded.

The units:

- The **package** is the unit of compilation, of the checking level, of capability parameter inference ([Section 9.4](#94-rejected-sub-package-checking-granularity)), and of metadata.
- A **module** is the unit of distribution — a set of packages. Module exit decides only which lists must be written ([Which declarations are inferred](#531-which-declarations-are-inferred)).
- A **subpackage** is a separate package of the same module that sees its parent's `internal` declarations; it consumes its parent's recorded lists like any other consumer, at the parent's trust level. Packages of one module may be compiled at different levels.

The terms:

- Code compiled at `error` is **checked code**; code compiled with checking off is **unchecked code**.
- `warn`-level code is unchecked for guarantee purposes, since its recorded lists may carry unresolved warnings. Its lists are **trusted**: consumers type-check as if they were correct, but they are never a premise of the exception-safety theorem ([Section 4.6](#46-exception-safety)) — nor is any verdict derived from them.

Exception checking and Modal Cangjie are independently enabled features: checking is available without Modal Cangjie, in the degraded mode of [Section 6.5](#65-checking-without-modal-cangjie).

The resulting states, in one table:

| Package state                                                           | Recorded lists       | Guarantee contribution                                        |
| ----------------------------------------------------------------------- | -------------------- | ------------------------------------------------------------- |
| checking off                                                            | none (read as empty) | none                                                          |
| `warn`                                                                  | trusted              | none — unchecked for guarantee purposes                       |
| `error`, Modal-less ([Section 6.5](#65-checking-without-modal-cangjie)) | verified             | partial: carrier escape unverified — even within one function |
| `error`, with Modal                                                     | verified             | eligible for the full guarantee                               |

The full guarantee is a whole-build property, stated in [Section 6.3.4](#634-scope-of-the-guarantee); no package state establishes it alone.

The table describes exception requirements. Effect requirements ([Effect requirements](#54-effect-requirements)) have an axis of their own, mirroring the exception one:

- `performs` checking is enabled per package by `--enable-checked-effects <level>`, with the same `warn` and `error` levels, the same trust semantics for recorded lists, and its own warning group (`checked-effects`). The flag requires the effect-handler feature; a package's exception level and effect level are independent.
- A package compiled without the flag is **unchecked-effects code**: its `performs` lists read as empty, calls into it impose no obligations, and a `perform` it fails to handle is a runtime failure — the boundary semantics of [Section 6.3.1](#631-defaults), on this axis.
- Assumption imports extend to this axis: `@AssumePerforms` asserts `performs` lists on an unchecked-effects dependency under the rules of [Section 6.3.2](#632-assumption-imports). It has no bare form — there is no top command type to assume — so its list is always explicit.
- The functional-cast rejection of [Reflection and runtime casts](#3102-reflection-and-runtime-casts) follows the effect level as its exception half follows the exception level: a functional value may carry a `performs` component the cast would erase.
- The unchecked boundaries of [Section 6.3.4](#634-scope-of-the-guarantee) ignore `performs` like everything else: reflective invocation and construction, parameter-typed casts, and unchecked-effects callers.
- API evolution of `performs` lists follows the matrix of [Section 2.1.6](#216-api-evolution) on this axis: additions break checked-effects consumers, removals can strand a `handle` clause.
- A mixed `captures` list splits by entry kind: exception entries follow the exception level, command entries the effect level — one constructor can raise errors on one axis beside warnings on the other — and the type stays capturing regardless.
- Requirement *checking* is level-independent for effects; the *escape guarantee* is not: without Modal Cangjie, effect capabilities degrade exactly as exception ones do ([Section 6.5](#65-checking-without-modal-cangjie)).

The levels, assumption imports, and escape hatch of this section concern exceptions only.

When both features are enabled, compatibility along the mode axis — modal code consuming pre-modal code and vice versa — is the Modal Cangjie proposal's concern; this section covers only the checked/unchecked axis.

### 6.2 Package metadata

For every declaration visible outside the package — exported ones and `internal` ones seen by subpackages — the compiler records its full signature in the package's compile-time metadata (the `.cjo` / public signature surface), so that downstream checked packages can perform capability-argument inference, subtyping, and override checks across package boundaries. Recorded per declaration:

- its `throws` and `performs` lists;
- its `captures` list, with the constructor requirements it implies;
- the clauses of functional types occurring anywhere in the signature.

Lists are semantically sets. Exported declarations are never inferred ([Which declarations are inferred](#531-which-declarations-are-inferred)), so every list visible to other modules is authoritative — written explicitly, or empty by omission; lists of `internal` declarations, recorded for subpackages, may be inferred.

The metadata also records the level the package was compiled at ([Section 6.1](#61-compatibility---checked-and-unchecked-code)): lists from an `error`-level package are verified, lists from a `warn`-level package are trusted, and a package compiled with checking off records no `throws` lists. `performs` lists follow the effect level the same way ([Section 6.1](#61-compatibility---checked-and-unchecked-code)): verified at `error`, trusted at `warn`, absent without the flag.

The precise schema — including whether clauses are stored as written or desugared (e.g. `captures` into constructor requirements), and whether lists are stored spelled or canonical — is implementation design, outside this document's scope; every consumer reconstructs and uses the semantic form (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)).

### 6.3 Interoperability between checked and unchecked code

#### 6.3.1 Defaults

When calling a callable declared in checked code from unchecked code, `throws` requirements are ignored.

In the opposite direction — checked code calling into an unchecked package — the callee's lists read as empty ([Package metadata](#62-package-metadata)), so such calls impose no obligations (see [Section 9.3](#93-rejected-safety-devices-at-the-unchecked-boundary)):
```swift
import legacy.db // unchecked package

func f() {
    db.query(...) // no obligations; a leaked SqlException
                  // propagates like an unchecked exception
}
```

The same boundary arises inside checked code whenever an implementation may come from an unchecked package: a dynamically dispatched call through a checked interface whose implementing class is unchecked — plugins, service providers, dynamically loaded classes — is an unchecked invocation, and its requirements are as unenforced as a direct call into that package. So is a checked callback, listener, or hook invoked *by* unchecked code: the invoker supplies no handlers.

Real precision over an unchecked dependency comes from the dependency itself: once it annotates its source and enables checking, its recorded lists reach consumers through package metadata — trusted at `warn`, guaranteed at `error` ([Section 6.1](#61-compatibility---checked-and-unchecked-code)).

For teams that want strictness meanwhile, a lint can flag calls into unchecked packages.

#### 6.3.2 Assumption imports

A consumer that wants obligations over a dependency that has not annotated can opt in with an **assumption import**: the builtin annotation `@AssumeThrows` on the `import` of a package compiled with checking off, carrying a list of exception types. The list is imposed:

- as a `throws` list on every call into that package — functions, methods, property accessors, and constructors alike;
- on every functional type in a covariant position of its signatures — results, function-typed fields and properties, bound methods — so that a callback obtained from the package carries the assumption when it is invoked later.

It does not reach a functional type inside a type argument: `Array<() -> Unit>` is invariant, and rewriting it would let checked code store a throwing callback the dependency then invokes unhandled. Values extracted from such positions are invoked as unchecked code — clause-free and not throw-closed. The annotation is rejected on a package that records clauses of its own. Capability list aliases apply ([Capability list aliases](#52-capability-list-aliases)); the bare form assumes `Exception`, and the empty list `@AssumeThrows[]` is rejected:
```swift
@AssumeThrows[SqlException]
import legacy.db

@AssumeThrows // same as @AssumeThrows[Exception]
import old.utils

func g()
throws SqlException {
    db.query(...) // requires CanThrow<SqlException>, supplied by g's clause
}

func h() {
    try {
        utils.foo() // requires CanThrow<Exception>
    } catch (e: Exception) {
        // ...
    }
}
```

Trust and scope:

- Assumptions only add obligations relative to the read-as-empty default. They are trusted, not verified: an assumed list that misses an exception type leaves that type leaking exactly as without the import.
- They are purely static and consumer-local — the consumer's own claim, versioned with its code, never exported as facts about the dependency. Only their consequences in the consumer's own clauses cross package boundaries.
- An assumption import is package-scoped: the annotation applies to every call into the dependency from the whole consuming package, whether or not the calling file repeats it. It covers exactly what its `import` brings into scope; a subpackage is a separate import and takes its own annotation.
- When a declaration is visible through several annotated imports — of a member and of its package, in one file or in several — their lists merge: the obligation is the union, taken after alias expansion. Assumptions only ever add obligations, so merging is the conservative reading and needs no conflict rule.
- An override of an assumed declaration that lives in another unchecked package is not covered: dispatch into it is the boundary of [Section 6.3.1](#631-defaults).
- Note the polarity against the escape hatch ([The escape hatch](#513-the-escape-hatch)): `@AssumeThrows` *adds* obligations — safety-leaning relative to the empty default, and only as complete as the list — while `unsafeCanThrow` removes them and errs unsafe.

Assumed requirements participate in capability parameter inference like declared ones, and they make defensive `catch` clauses around unchecked calls checkable relative to the consumer's trusted assumption.

`@AssumePerforms` is the effect counterpart ([Section 6.1](#61-compatibility---checked-and-unchecked-code)'s effect axis): the same placement, scope, trust, and merging over an unchecked-effects dependency, with command-type entries. It has no bare form — there is no top command type — and the two annotations may sit on one import, each feeding its own axis.

Other granularities:
- **Per call** — a possible refinement.
- **Per function, per file** — not pursued: the import is where the trust relationship lives.
- **Per member** — not offered: precise per-declaration claims about a dependency are manifest territory ([Section 8.10](#810-capability-manifests)), where the external-truth caution applies.
- **Assumed `captures`** — not offered. One could imagine asserting that a class of the unchecked package captures a capability, paying one obligation at construction instead of one per method call ([Capability capturing](#39-capability-capturing)). The idea is coherent when the class has `this @ local!` constructors, which an exception-unchecked package may have — modes and checking are independent features. But such an assumption names a specific class, making it a per-declaration claim: manifest territory, as in the previous bullet. The per-call obligations of the assumed list serve the need.

#### 6.3.3 Function values at the boundary

Checked code cannot pass a checked-throwing function value into unchecked code, on two independent grounds: a value of type `() throws E -> R` is not a subtype of `() -> R` ([Functional types](#34-functional-types)), and a clause-free literal that *captures* a capability instead is region-bound, so it cannot flow into an ordinary unchecked parameter, whose mode defaults to `~local` ([Section 4.4](#44-capability-regions)) — it may flow into a parameter the dependency declares `@ local?` under Modal checking, since modes and exception checking are independent features and that declaration is Modal Cangjie's own verified promise of non-escape. Erasure makes the representations identical — which is exactly why the restriction must live in the types.

A callback is passed by discharging or converting first:
```swift
legacy.register {
    try {
        g()
    } catch (e: E) {
        // discharge: handle here — the wrapper's try supplies the capability,
        // and the lambda's type stays clause-free; or convert to unchecked:
        throw WrapperException(e)
    }
}
```
where `WrapperException <: UncheckedException`; [Section 8.5](#85-syntactic-sugar-for-handling) sugars the conversion form.

#### 6.3.4 Scope of the guarantee

A `throws` clause on a checked function does not by itself ensure a handler exists when the function runs. Unchecked code may invoke it, supplying no handlers — directly, since `throws` requirements are ignored there, or through a function value obtained by referencing a checked callable or receiving one as a result. (Checked code cannot pass a throwing value *into* an ordinary unchecked callable, [Section 6.3.3](#633-function-values-at-the-boundary); but separate compilation cannot stop an unchecked consumer from taking what checked code exports.) Erasure ([ABI and reflection](#310-abi-and-reflection)) makes this undetectable at run time: no capabilities exist, so there is no point at which anything could be checked or wrapped, and the exception propagates like an unchecked one.

The guarantee of checked code is therefore a whole-build property. The only **checked root** — the entry through which the runtime itself supplies a handler — is the `main` of a checked package; every other entry into checked code comes from a checked caller, which handles or propagates, or crosses an unchecked invocation boundary.

The full guarantee holds for executions that:

- stay within one closed build of `error`-level packages, with full Modal checking;
- enter through `main`;
- contain no fabricated capability ([The escape hatch](#513-the-escape-hatch));
- cross no unchecked invocation boundary — a call from unchecked code, a reflective invocation or construction, a cast to a parameter-typed generic target ([Reflection and runtime casts](#3102-reflection-and-runtime-casts)), a dispatch into an unchecked implementation, an unchecked callback;
- rest no premise on trusted inputs — `warn` metadata, assumption imports, capability manifests.

These are the premises of the theorem of [Section 4.6](#46-exception-safety), and they must be stated prominently in user documentation.

A successful `error` build alone is *not* evidence of them — unchecked dependencies and boundary sites build fine — so the toolchain offers a **closed-build verification mode** ([Section 11.5](#115-toolchain-surface)) with two verdicts:

- A **verified closed build** — every transitive package verified at `error`, no trusted metadata, no assumption imports, no fabricated capabilities, no boundary sites, and **signature-coherent**: every artifact was type-checked against the exact clause metadata of the dependency versions linked into the build (a clause/capture fingerprint suffices; erasure keeps stale combinations linkable, so coherence must be checked, not assumed) — establishes the full guarantee as a build verdict.
- An **audited build** — every boundary site explicitly acknowledged — establishes only the trace-conditional statement: executions that never cross an acknowledged boundary are covered. Acknowledgement changes diagnostics, never semantics.

Where effect requirements participate, verification additionally requires `error`-level checked-effects across the executing closure ([Section 6.1](#61-compatibility---checked-and-unchecked-code)), a supported backend, and resumption confinement in force ([Section 5.4](#54-effect-requirements)).

### 6.4 Migrating user code

For an existing codebase, once the standard library ships annotated ([Section 11.2](#112-annotation-of-standard-apis)):
1. Enable `warn` and burn the warnings down; a CI baseline over warning counts keeps already-clean files clean (per-file enforcement is deliberately tooling, not language — [Section 9.4](#94-rejected-sub-package-checking-granularity)). One class of warning appears even in clause-free code: casts to functional types ([Reflection and runtime casts](#3102-reflection-and-runtime-casts)) — event buses and registries storing callbacks in `Any` restructure or accept the flag's one hard break at `error`.
2. Materialize clauses mechanically: a toolchain fixer runs capability parameter inference over the whole package — including exported declarations, which the language itself never infers ([Which declarations are inferred](#531-which-declarations-are-inferred)) — and writes the resulting lists into source as explicit clauses, turning annotation work into diff review. Two qualifications:
   - Public-surface output is an API-design proposal, not a diff to approve. Mechanical inference writes implementation-specific exceptions onto exported declarations — the pollution criticized in [Section 1](#1-introduction) — so materialized lists on public APIs must be reviewed against the library's own exception hierarchy ([API evolution](#216-api-evolution)).
   - Where a body calls checking-off code, inference sees nothing; the fixer marks such a list incomplete rather than writing a silent empty one.
3. Flip the package to `error`.

Dependencies go first: a package at `error` still reads its checking-off dependencies as clause-free, so its runtime exception surface is complete only when every transitive dependency is at `error` — until then, the unchecked-call lint or assumption imports ([Section 6.3](#63-interoperability-between-checked-and-unchecked-code)) cover the gap, and "builds at `error`" is a package milestone, not the build's.

At entry points, `throws Exception` is the sanctioned way to pass everything beneath upward — but a clause creates no handler; it sends the requirement to the caller. For `main` the caller is the runtime, which supplies the default handler ([Section 3.2](#32-capability-parameters-in-declarations)). For request handlers, test bodies, and other framework entry points the caller is the framework: checked, it handles or propagates; unchecked, it is an unchecked invocation boundary outside the guarantee ([Scope of the guarantee](#634-scope-of-the-guarantee)), and the clause is documentation. No region-scoped ambient-capability device is part of the base design ([Section 8.11](#811-region-scoped-unsafe-capabilities)); the expression-scoped escape hatch is `unsafeCanThrow` ([The escape hatch](#513-the-escape-hatch)).

### 6.5 Checking without Modal Cangjie

Exception checking decomposes into clause machinery and escape discipline, and only the second depends on Modal Cangjie ([Section 4.5](#45-implementation-strategy)). For packages that do not enable Modal Cangjie — or while it is unavailable — checking runs in a **degraded mode**: capabilities are treated as `~local`.

Kept: all clause checking and propagation of [Section 3](#3-implicit-capability-passing-design) and the conveniences of [Section 5](#5-further-language-features); erasure and metadata unchanged. Also kept, syntactically: `spawn` blocks receive no ambient capability scope — enclosing capabilities are unusable inside them, since without modes nothing else stops a capability outliving its handler on another thread ([Lazy computations and `spawn`](#71-lazy-computations-and-spawn)).

Lost: escape control entirely — a capability-capturing value that outlives its `try`, within a function or across one, goes undetected; the capability regions of [Section 4.4](#44-capability-regions) are not enforced. `captures` ([Capability capturing](#39-capability-capturing)) is unavailable: it inherently speaks modes. The degradation covers both capability kinds: a function object capturing a `CanPerform` capability may likewise escape its handler, and a `perform` through it surfaces as the runtime's missing-handler failure — `performs` clauses remain checked documentation here, exactly like `throws`.

The mode's positioning is **checked documentation**:

- At `error`, every clause is a compiler-verified upper bound on the capability requirements visible in checked source and metadata — it may carry an unexercised entry, but never misses one the way `@throws` comments do ([Section 1.2](#12-motivation-of-checked-exceptions)). It is not a runtime may-throw summary ([Section 3](#3-implicit-capability-passing-design)), least of all across unchecked boundaries.
- At `warn` it is trusted migration metadata.
- The handling guarantee is partial. Under the other premises of [Scope of the guarantee](#634-scope-of-the-guarantee) — trusted inputs included among the exclusions — *every checked exception is handled, except through values that outlive their handler's scope, which is unverified*: the guarantee Scala's `saferExceptions` ships today ([Section 2.2.3](#223-capability-based-scala-3-safer-exceptions)).

It is an explicitly transitional state, not the design point.

A package that adopts checking before Modal Cangjie faces a breaking step when Modal is enabled: the regions of [Section 4.4](#44-capability-regions) start being enforced, rejecting capability-capturing literals passed to `~local` parameters (the mode rejection illustrated in [Section 6.3.3](#633-function-values-at-the-boundary)), returned capturing closures, assignments out of a `try`, lazy values leaving a `try`, aggregates holding carriers, and carriers crossing into `spawn`. This is the Modal migration itself, arriving at its own pace. In the expected order — Modal Cangjie first, since it releases earlier — no such seam exists.

## 7. Known limitations

### 7.1 Lazy computations and `spawn`

A capability must not be used by a computation that can outlive the `try` block that introduced it. `spawn` is the primary way this can happen without any value escaping through memory: the spawned computation keeps running after the region's lifetime has ended, so even a closure that is never stored anywhere must not capture `@ local!` capabilities. Therefore the argument of `spawn` — and of any API that defers or transfers execution, such as executors, timers, or OS callback registration — must be an ordinary escaping function type, which rules out capability capture. Escape analysis for capabilities must account for execution outliving a region, not only for values leaking out of it (see [Escape analysis](#4-escape-analysis)). Modal Cangjie's `spawn` rule already enforces exactly this restriction — the spawned block may not reference any outer `local?` or `local!` variable — so the base design needs no new mechanism here; the capability machinery must simply apply the same rule to unnamed capabilities.

`spawn` is only the sharpest instance of a general limitation: in the base design, a deferred computation's requirements are checked at its construction site — captured capabilities region-bind it there — never at its execution site. Lazy iterators share the shape (the second example of [Section 4.3](#43-the-gap)): consumption must stay within the constructing region, or the requirement must be discharged at construction. What lifts the limitation is moving the requirement site, which is exactly [Capability-list polymorphism](#83-capability-list-polymorphism).

As a consequence, in the base design the block passed to `spawn` cannot let a checked exception escape through verified code: every checked exception is handled inside the block or wrapped as unchecked ([Section 8.5](#85-syntactic-sugar-for-handling)). The natural semantics would be that the block may use exception capabilities that are in fact only required at the moment of `Future<T>.get` (the runtime transports an exception from the spawned thread to the `get` call site). Capturing these semantics precisely requires polymorphism over capability parameter lists, specified as the extension [Capability-list polymorphism](#83-capability-list-polymorphism).
```swift
public class Future<R, throws E = ()> {
	public func get(): R throws E
}

// expository — `spawn` is an expression form, see below
func spawn<R, throws E>(f: () throws E -> R): Future<R, E>

func test(): Int {
	let future = spawn { // future: Future<Nothing, (AException, BException)>
    	// c1: CanThrow<AException> @ local!,
    	// c2: CanThrow<BException> @ local! =>
    	if (...) {
        	throw AException()
    	} else {
            throw BException()
        }
    }
	try {
		future.get() // capabilities are checked only here
	} catch (e: AException) {
    	...
    } catch (e: BException) {
        ...
    }
}
```

Two facts anchor the extension to the real language. First, `spawn` is an **expression form**, not a library function — the `spawn` signature above is expository, and the real change is the expression's typing rule binding `Future`'s list parameter from the block. Second, `Future<T>` is named pervasively in user source, so the list parameter is defaulted to the empty list: `Future<Int64>` keeps compiling and means `Future<Int64, ()>`.

The sketch also rests on a runtime guarantee that must be stated as a requirement: an exception escaping the spawned block is caught at the thread boundary and stored in the future, to be re-raised at `get` with the original stack trace preserved — never a silent thread death. A failed future dropped without `get` reports to the uncaught-exception handler when collected rather than being swallowed, and a non-blocking observation API (`tryGet`-style) must not swallow stored failures either ([Section 8.3](#83-capability-list-polymorphism)).

## 8. Possible extensions

Extensions are ordered by decreasing probability of implementation. This section gives each extension's motivation and known problems; full details — rules, examples, interactions — live in the companion [Checked exceptions — extensions](<Checked exceptions — extensions.md>), numbered identically.

### 8.1 Optimizing effect handlers

Effect requirements are checked in the base design ([Effect requirements](#54-effect-requirements)). Beyond checking, evidence passing opens an optimization path: a tail-resumptive handler compiles to a closure stored in the capability ("Effect Handlers, Evidently", Xie et al., ICFP 2020), turning dynamic handler lookup into a direct call. This arrives as a **distinct, opt-in capability kind** for commands designated for it — a separate design with its own rules and trade-offs ([Section 9.8](#98-rejected-a-reserved-lowering-slot)); ordinary `CanPerform` stays erased.

Known problems:
- Evidence passing covers only tail-resumptive handlers, and its coherence results assume scoped resumptions — restrictions this extension inherits.
- Its capabilities are real, region-bound values: phantom-capability rules justified by erasure do not apply to them, which is why the base design enforces exact capability-region semantics the new kind can share (the lowering-independence invariant of [Section 4.5](#45-implementation-strategy)).
- Real capability values reopen the container and generic smuggling channels that unnameability closes for the phantom kinds.

### 8.2 Explicit capability abstractions

A function literal carries an explicit clause — `{ x: A performs GetLogger throws AException => ... }` — lifting the base-design rule that literal capability parameters come only from the expected type ([First-class functions](#35-first-class-functions)), and enabling the overload relaxation of [Overloading](#37-overloading): overloads differing only in argument-function capability lists become callable with explicitly abstracted literals.

Known problems:
- The lambda-grammar cost: one delimiter-bounded lookahead case, analyzed in [Grammar impact](#10-grammar-impact).
- Clause-less literals at relaxed call sites must stay ambiguity errors (with a fix-it), never default to the clause-free overload.

### 8.3 Capability-list polymorphism

Some APIs move an exception's *requirement site* across a region or thread boundary — `spawn` and `Future.get` are the canonical pair ([Lazy computations and `spawn`](#71-lazy-computations-and-spawn)). Capability-list variables — `func spawn<R, throws E>(f: () throws E -> R): Future<R, E>`, `class Future<R, throws E = ()>` — express this without row-type machinery: definition-site-only inference, no unification. A further use is a throw-contract on resumptions, which would let `resume throwing` resolve against the suspended `perform` site's own `catch` clauses (rule 5 of [Effect requirements](#54-effect-requirements)).

Known problems:
- `spawn` is an expression form: the real change is its typing rule, not a library signature.
- The runtime transport requirement of [Section 7.1](#71-lazy-computations-and-spawn) becomes load-bearing semantics.
- Invariance of list variables and definition-site-only inference are deliberate precision losses; whether they suffice for executor and combinator libraries needs validation.
- Invariance makes collections of futures monomorphic: `Array<Future<Unit, E>>` needs one list for all elements, so heterogeneous futures share a collection only at `E = Exception`, at the cost of precision.
- Discipline risk: list variables must stay off ordinary higher-order functions — capture remains the idiom there — or signatures regrow the effect polymorphism the design exists to avoid.

### 8.4 Exception conversions

A declared `Convertible<From, To>` lets the compiler insert the handle-convert-rethrow boundary pattern automatically, once, instead of per call site. The mechanism sits outside the base design because conversions are *elaboration*, not checking: the synthesized handler has runtime content, so the checking level affects behavior — the one property the base design refuses ([Section 9.3](#93-rejected-safety-devices-at-the-unchecked-boundary)).

Known problems:
- The extraction reason itself: the same source behaves differently with checking on and off where a conversion applies.
- Unchecked targets satisfy the target-in-scope gate trivially — a deliberate policy trade-off (the declared form of "this layer turns `From` into a top-level fault"), guarded by lints.
- Compilation is import-sensitive even though the meaning of compiled code is not.
- Handler nesting order, inference interactions (never target an evolving inferred list), and the captured-requirement exclusion demand careful specification — all recorded in the companion file.

### 8.5 Syntactic sugar for handling

Three forms: `unchecked { ... }` and `unchecked(expr)` discharge the enclosed requirements by wrapping into `WrappedUncheckedException`; `result { ... }` reifies the outcome, with the error type joined from the requirement set; a selective `try?`-style expression converts *one* chosen exception type to `None` while the rest propagate ([Section 9.6](#96-rejected-option-returning-twins)).

Known problems:
- All three discharge the *requirement set*: a throw through a captured capability passes through unwrapped and un-reified ([Section 3.2](#32-capability-parameters-in-declarations)).
- `result` presupposes a standard `Result` type, and cannot be a library function — its error type is computed from the requirement set.
- The `try?` syntax is open; selectivity is non-negotiable, since a blanket form would discard unrelated failures' diagnostics.

### 8.6 No-throw guarantee

A `nothrow` functional-type attribute: inhabited only by values with an empty capability list, an empty captured-capability set, *and* verified throw-closure per [Section 8.14](#814-the-unreachable-catch-diagnostic) — the stronger property that `throws ()` does not pin ([Section 5.3.5](#535-interaction-with-an-explicit-throws)); the first two conditions alone would not stop a checked exception arriving through unchecked code the body reaches. Wanted by finalization, lock bodies, and memoized computations.

Known problems:
- It promises the absence of *checked* exceptions only; unchecked exceptions can always occur, and the name must not oversell.
- The captured-set data comes from the escape analysis ([Section 4.4](#44-capability-regions)); the attribute's precision degrades with it in the Modal-less mode.

### 8.7 Subtyping on functional types: discharge by eta-expansion

A coercion for the direction subtyping cannot cover: when a value's capability list exceeds the expected type's, but the difference is available at the conversion site, the compiler eta-expands — the wrapper captures the difference.

Known problems:
- The elaborated value changes identity and costs a closure.
- Applicable only at concrete expected types, never during generic inference, never in overload resolution; the wrapper is region-bound, so only region-accepting positions admit it.

### 8.8 Automatic adapter generation

`adapt<I>(x)` — a compiler intrinsic expanding to the synthesized capturing class of [Capability capturing](#39-capability-capturing); implicit adaptation-as-coercion is deliberately rejected. Not proposed for the initial design: the manual pattern is expected to be rare.

Known problems:
- Adapter identity: `adapt(x) !== x`, casts do not see through it, equality forwards only if `I` requires it.
- Full specification — overloads, generics, properties, defaults, inheritance, conflicts, visibility, dispatch — is future work.

### 8.9 Exception encapsulation

Dynamic nearest-handler resolution lets an intermediate frame silently intercept exceptions of its argument computations. The fix is tunneling (Zhang & Myers, POPL 2019): capabilities carry a handler identity, and a throw unwinds to the handler that supplied its capability. The scope selection of [Capability argument inference](#33-capability-argument-inference) becomes the handler identity, and the within-scope choice the base design leaves open — every choice yields the same base checking result, by canonical forms and the conservative call boundary, not because origins are equal — must be pinned: within a `try`, the first `catch` whose declared type covers the required static type; the most specific suitable entry elsewhere.

Known problems:
- It materializes capabilities into handler tokens, arriving as a distinct opt-in capability kind ([Section 9.8](#98-rejected-a-reserved-lowering-slot)) — with an introducer-arity rule needed for virtual dispatch.
- Fault barriers need a sanctioned way to observe in-flight exceptions: an explicitly marked intercepting catch with a destination-preserving rethrow.
- Unchecked exceptions and exceptions from unchecked code keep nearest-handler semantics; encapsulation is a checked-only guarantee.
- Stack-trace optimization must be decoupled: a per-class opt-out, not handler-usage inference.

### 8.10 Capability manifests

A **capability manifest** is a file shipped alongside a compiled unchecked package that supplies `throws` lists for its public declarations, as if the package had declared them; checked consumers read the entries exactly like recorded clauses, amending the read-as-empty rule of [Package metadata](#62-package-metadata). A manifest is checked diagnostically at its source — the covered package is compiled at the `warn` level with the entries applied as its clauses, which can still ship violations; verification would require an `error` build with the manifest applied, and is impossible for a prebuilt binary without source — and trusted at the consumer, with the same silent-violation mode as the whole-build caveat of [Section 6.3](#63-interoperability-between-checked-and-unchecked-code). Format and discovery are implementation design.

This mechanism is an extension, not part of the migration story, and is restricted to dependencies that cannot be annotated (prebuilt binaries, abandoned packages). The caution is historical: Kotlin's external nullability annotations for Java — the same shape of externally maintained truth — were abandoned for version fragility, lack of local recourse where annotations were wrong (most severely at override boundaries), and unsustainable maintenance. Manifests should be vendor-supplied and verified, or not used at all; assumption imports ([Section 6.3](#63-interoperability-between-checked-and-unchecked-code)) cover the consumer-side need without external truth.

### 8.11 Region-scoped unsafe capabilities

A loud, `unsafe`-named construct injecting an ambient `CanThrow<Exception>` into a region (the analog of Scala's `import unsafeExceptions.canThrowAny`) would let unmigrated regions coexist with checked code. It is deliberately absent from the base design: it discharges obligations without a handler, so a function using it exports a clean `throws` list that misleads its callers. The honest states are `warn` ([Section 6.1](#61-compatibility---checked-and-unchecked-code)) and entry-point `throws Exception` declarations ([Section 6.4](#64-migrating-user-code)); the expression-scoped assertion `unsafeCanThrow` ([The escape hatch](#513-the-escape-hatch)) is the sanctioned form.

### 8.12 Runtime casts to functional types

The base design rejects any cast or type-pattern target containing a functional type ([Reflection and runtime casts](#3102-reflection-and-runtime-casts)): erasure leaves nothing to check, and a permissive reading would launder clauses. This extension makes such casts usable. Two designs are candidates: a **pessimistic reading** — the clause-free target acquires `throws Exception` in covariant positions and keeps the empty list in contravariant ones, the least type among those erasing to the target — sound for exceptions but unavailable for `performs`, which has no top command type, and still blind inside type arguments; or **clause-aware runtime subtyping** — function-type descriptors carry clause components that `is` and `as` consult, with no observation API ([Section 3.10.2](#3102-reflection-and-runtime-casts) keeps that a separate surface) — precise, covering `performs` and closing the parameter-typed boundary.

Known problems:
- The pessimistic reading treats one hazard two ways: concrete invariant positions stay rejected while a two-line generic helper reaches the same laundering through the parameter-typed boundary.
- Clause-aware subtyping puts clause components into runtime type metadata: descriptor cost, per-shape closure-class sharing, and `is`/`as` results that vary with a dependency's checking level — the trade-offs of [Section 9.9](#99-erasure-over-reified-clauses), whose full reification it partially adopts.
- Clause-aware subtyping is not purely additive: it redefines runtime type identity for clause-bearing functional types, and every surface reading that identity shifts together — `TypeInfo` equality (the identity example of [Section 3.10.2](#3102-reflection-and-runtime-casts) flips to false), printed type names begin to contain `throws`, `isSubtypeOf` starts distinguishing clauses, parameter-typed casts the base design accepts as an unchecked boundary (`x as Box<T>` over a functional instantiation) become checked and start failing where they silently laundered, and code keyed on function-type `TypeInfo` repartitions.

### 8.13 Reflective clause metadata

Clause lists are declaration metadata — per-declaration data like parameter names, no part of runtime type identity or value representation — so a reflective API over them (a `FunctionInfo.throwsTypes`-style surface, or a per-creation-site stamp for function literals, which have no declaration) is additive: no ABI consequence. Two constraints bind any such surface: absence must read as *unknown*, never as an empty list — values from unchecked code, reflective construction, or a fabricated region carry no information, and an empty answer would be the unsound negative conclusion the diagnostic of [Section 8.14](#814-the-unreachable-catch-diagnostic) exists to avoid; and for `performs` such a surface is a framework's only possible runtime view of effect requirements.

Known problems:
- Reflecting the clause of a *value's type* is not this extension: `() throws E -> R` and `() -> R` are one runtime type, and distinguishing them is the reification of [Section 9.9](#99-erasure-over-reified-clauses).
- Generic entries: what `throws GenericException<T>` reflects as — strings sidestep it, structured type info does not.

### 8.14 The unreachable-`catch` diagnostic

Changing a dependency's `throws` list can strand handlers; this diagnostic reports `catch` clauses (and `handle` clauses, [Effect requirements](#54-effect-requirements)) that no operation of the `try` body can reach, completing the API-evolution argument of [Section 2.1.6](#216-api-evolution). A sound rule cannot be read off requirement lists — a `throws` list is not a may-throw set ([Section 3.2](#32-capability-parameters-in-declarations)): clause-free values throw through captured capabilities, and clause-free declarations reach unchecked code. The rule therefore needs a per-declaration Boolean **throw-closure** summary — closed only when every reachable operation is statically resolved and free of unchecked, reflective, assumed, and fabricated exits — propagated through the call graph and recorded in package metadata. The full rule, its soundness conditions, and the interoperability story are in the companion file.

Known problems:
- The closure summary is a whole-graph analysis with metadata impact — the main implementation cost.
- Dynamic dispatch is closed only when statically resolved (non-`open` methods and classes, `sealed` hierarchies, known captured sets): an override may capture a capability without widening its list.
- Verdicts resting on assumption imports or `warn` metadata are trusted, and the exported summary must record them as not closed.
- The unchecked-boundary lint of [Section 12](#12-todo) shares the summary and arrives with it.

### 8.15 Inference opt-in for public declarations

The `...` marker of [Section 5.3.5](#535-interaction-with-an-explicit-throws) is barred from exported declarations: their lists are contracts, never computed from bodies ([Section 5.3.1](#531-which-declarations-are-inferred)). This extension would admit it on `public` declarations, letting a surface under active prototyping track its implementation instead of pinning a list at every edit. The cost is the reason for the bar: the exported list silently follows the body — an addition is a caller-side error by the evolution matrix of [Section 2.1.6](#216-api-evolution) — and package metadata starts depending on bodies, which dependents must treat as ordinary clause changes ([Package metadata](#62-package-metadata)).

## 9. Discussion

This section records design decisions whose rationale is not visible from the rules themselves.

### 9.1 Keyword scheme: `throws`, `performs`, `captures`

Earlier drafts used a single `using` clause for all capability parameters, following Scala 3's `using` for context parameters. The current scheme splits it: `throws` declares exception capability requirements, `performs` ([Effect requirements](#54-effect-requirements)) declares effect capability requirements, and `captures` declares class-level capability capture ([Section 3.9](#39-capability-capturing)). The reasons:

1. **The two capability kinds differ in almost every surface policy**, and one keyword buried the boundary:

| Policy                                                                                              | Exceptions (`throws`) | Effects (`performs`)                                                                                                   |
| --------------------------------------------------------------------------------------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Inference for non-exported declarations ([Section 5.3](#53-capability-parameter-inference))         | yes                   | no — effect requirements are semantic contract and, under evidence passing, ABI                                        |
| Erasure ([Section 3.10](#310-abi-and-reflection))                                                   | always                | always — evidence passing arrives as a distinct opt-in kind ([Section 9.8](#98-rejected-a-reserved-lowering-slot))     |
| Automatic conversions ([Section 8.4](#84-exception-conversions))                                    | yes                   | no                                                                                                                     |
| Unchecked escape hatch ([Section 5.1](#51-unchecked-exceptions))                                    | yes                   | yes — an overload by substitution (rule 2 of [Section 5.4](#54-effect-requirements))                                   |
| `main` clause handled by default handler ([Section 3.2](#32-capability-parameters-in-declarations)) | yes                   | no — there is no default effect handler                                                                                |
| List changes binary-compatible ([Section 3.10](#310-abi-and-reflection))                            | yes                   | yes while erased; the optimized opt-in kind follows its own ABI ([Section 9.8](#98-rejected-a-reserved-lowering-slot)) |

2. **Verb symmetry.** The operation keywords are `throw` and `perform`; the clause keywords are their third-person forms. A reader who knows the operation can guess the clause.
3. **`effect` was rejected for the clause** to keep the word available for a future effect-*declaration* form (Koka and OCaml both use `effect` as a declaration keyword; Cangjie's `class GetLogger <: Command<Logger>` encoding may want such sugar one day).
4. **`using` was dropped entirely.** Its C#/C++ connotations (imports, resource disposal) mislead; the "capability from context" reading is served better by each clause naming its kind; and its role as a reminder of capture semantics is now carried by `captures`. `with` was also unavailable: it is a reserved token used by `resume ... with` ([Grammar impact](#10-grammar-impact)).
5. **Lambda keyword budget.** In the base design, no clause keyword appears in function-literal syntax at all: capability parameters of literals are inferred from the expected type ([Section 3.5](#35-first-class-functions)). Explicit abstractions over both clause kinds are deferred to [Section 8.2](#82-explicit-capability-abstractions); their lambda-grammar cost is analyzed in [Grammar impact](#10-grammar-impact).
6. **`captures` sits on the class header, not on constructors.** The rules of [Section 3.9](#39-capability-capturing) force every `this @ local!` constructor of a capturing class to supply and store the capabilities, so the capture set is a property of the class; the earlier per-constructor `using let` misstated the scope and read as if the constructor itself threw. Now `throws` on a constructor always means "constructing may fail", and `captures` on the class always means "instances hold the handler capability". The same split decides subclassing: a subclass restates coverage of the superclass's captured types in its own `captures` (rule 4 of [Section 3.9](#39-capability-capturing)) rather than declaring `throws` on its constructors — that would give constructor `throws` a second, lifelong meaning, distinguishable only by consulting the superclass.
7. **`captures` names the mechanism, and its object is the capability.** Read naively, `captures FileException` suggests instances capture exception *values*; what is captured is the capability to throw one. The reading was kept deliberately. Capabilities are part of the user model, not compiler internals — functional-type subtyping, the resolution error message, region-binding, and the escape hatch are all stated in terms of them — so the clause may lean on the taught concept, and it buys the most teachable sentence of the design: a literal captures a capability, and a capturing class captures one at construction. Renames were considered and rejected: `defers E` names the moved obligation but loses the closure symmetry and reads as deferred throwing; `binds`, `requires`, `retains`, `holds` are vaguer or have the same wrong object; spelling the capability out — `captures CanThrow<E>` — is verbose, still elides the mode, and opens the non-denotable intrinsic into source syntax. Prose and diagnostics carry the disambiguation: always "captures the capability for `FileException`", never "captures `FileException`".
8. **The `...` marker** ([Section 5.3.5](#535-interaction-with-an-explicit-throws)) preserves the principle that an explicit list is authoritative while allowing partial lists. Under a single merged clause, a function forced to write an explicit effect entry would thereby have lost exception inference — or required an invisible per-kind exception to the authoritative-list rule.
9. **Clause order**: in functional types `performs` precedes `throws` (mirroring Swift's `async throws` order) — the pre-arrow clause sequence is a single grammar production, and printed types need one canonical spelling. In declarations the `where`, `performs`, and `throws` blocks order freely, each at most once ([Section 3.2](#32-capability-parameters-in-declarations)): they are keyword-led, a fixed order would buy nothing while `where` already sits anywhere, and tools print the functional-type order.

A pleasant convergence: Scala 3 spells the same concept as the type-level sugar `R throws E1 | E2` ([Section 2.2.3](#223-capability-based-scala-3-safer-exceptions)), so the keyword matches the established reading in the closest related design.

### 9.2 Functional type syntax

The clause in functional types sits between the parameter list and the arrow — `(A) throws (E1, E2) -> R` — with parentheses optional for a single entry and mandatory for several ([Functional types](#34-functional-types)). The choice was deliberate:

1. **It is the only position parseable as a soft keyword.** After a parenthesized parameter list, an identifier is a parse error today, and the clause commits to a function type whose `->` must follow ([Grammar impact](#10-grammar-impact)).
2. **A clause always precedes the arrow it modifies**, so nested types have no dangling-modifier problem (see the right-associativity example in [Functional types](#34-functional-types)).
3. **It stacks.** `(A) performs H throws E -> R` extends the same shape; Swift's `(Int) async throws(E) -> String` is precedent that two effect markers before an arrow read fine.
4. **The parenthesized-list rule doubles as disambiguation** for commas inside generic argument lists ([Grammar impact](#10-grammar-impact)).

The acknowledged wart: declarations and types order the clause differently (declaration: parameters, `: ReturnType`, `throws`; functional type: parameters, `throws`, `-> ReturnType`). No single position can agree with both, because declarations mark the result with `:` while types mark it with `->`. Both orders have familiar precedent — Java reads clause-after-result, Swift clause-before-arrow — and the keyword is identical in both, so only the layout differs.

Alternatives considered and rejected:
- **Trailing clause** (`(A) -> R throws E`): matches declaration order, but creates the dangling-modifier problem in nested types and places a soft keyword after an arbitrary complete type — the parsing hazard [Grammar impact](#10-grammar-impact) rules out.
- **Decorated arrow** (`(A) -[E]-> R`; Koka's `a -> e b`, Unison's `A ->{Abort} B`): the literature's standard and visually ideal — effects become properties of the arrow — but it requires new hard tokens, has no declaration-site counterpart in Cangjie (the same concept would get two unrelated spellings), and composes poorly with two capability kinds.
- **Type-level encoding** (explicit `CanThrow` parameters, or wrapper generics): exposes the plumbing the design erases, breaks set semantics (positional parameters cannot be permutation-insensitive), and degenerates into the `Result` encoding rejected in [Section 2.2](#22-other-approaches-to-typed-errors).
- **Outer suffix** (`((A) -> R) throws E`): unambiguous but verbose, and nests miserably.
- **Mandatory parentheses for single entries** (Swift's `throws(E)` style): more uniform, noisier for the dominant single-exception case. Swift's typed throws admits exactly one type; the parenthesized list is this design's generalization to capability sets.

Finally, the empty clause `throws ()` is permitted everywhere but meaningful only in declarations ([Section 5.3.5](#535-interaction-with-an-explicit-throws)): in a type, absence of the clause already denotes the empty list, so the empty clause is redundant there — harmless, and convenient for generated code; in a declaration, absence means inference for non-exported declarations — there the empty clause is the only way to state an empty list — while on exported declarations absence already denotes the empty list ([Which declarations are inferred](#531-which-declarations-are-inferred)).

### 9.3 Rejected: safety devices at the unchecked boundary

For checked code calling into unchecked packages ([Section 6.3](#63-interoperability-between-checked-and-unchecked-code)), two safety-leaning alternatives to reading the callee's lists as empty were rejected.

**Treating every such call as `throws Exception` by default.** Every call into an unannotated dependency would then require a `CanThrow<Exception>`, which in practice is discharged with blanket `catch (e: Exception)` handlers — training exactly the habit checking exists to remove — while conveying nothing about which exceptions actually flow. The same semantics remains available as an opt-in, per dependency, through assumption imports ([Section 6.3](#63-interoperability-between-checked-and-unchecked-code)): rejected as the default, offered as a choice.

**Wrapping boundary leaks into an unchecked `UnknownException`.** Since direct checked-to-unchecked call sites are statically known, the compiler could synthesize a `try` around each, rethrowing any leaked checked-classified exception as an unchecked `UnknownException` with the original as `cause` — erasure does not preclude this. It fails on other grounds. First, it makes the checking level change runtime behavior: identical source gains synthesized handlers when compiled checked, breaking the principle that checking is a purely static discipline with identical code generation ([Section 3.10.1](#3101-runtime-abi)) — declared conversions are the sanctioned, source-visible exception ([Section 8.4](#84-exception-conversions)). Second, it cannot be complete: calls through function values and dynamically dispatched calls landing in unchecked implementations have no statically known boundary — there erasure does bite — so the promised invariant (any in-flight checked exception has a handler) is not achieved anyway. Third, it breaks the pragmatic pattern of catching a known exception by name around a not-yet-annotated dependency, which would then surface as `UnknownException`.

### 9.4 Rejected: sub-package checking granularity

Enabling checking on units finer than a package — per file, most naturally — was considered and rejected. The package is not an arbitrary unit: it is the unit of the analysis. Capability parameter inference ([Section 5.3](#53-capability-parameter-inference)) runs over the package-internal call graph, which crosses files freely; a checked file calling an unchecked helper in the same package would find no capability list on it, declared or inferred, so checking would be hollow exactly where the call graph is densest. Package metadata ([Section 6.2](#62-package-metadata)) gives a package's recorded lists a single verification status; per-file enabling would fragment it into per-declaration trust for no gain, since the whole-build guarantee of [Section 6.3](#63-interoperability-between-checked-and-unchecked-code) composes over the weakest link anyway. Scala's per-file `saferExceptions` import is not a counterexample: Scala infers nothing — every capability is an explicit given, so a file is self-contained there. It is precisely inference that makes the package this design's smallest coherent unit.

What finer granularity is legitimately wanted for — keeping already-clean files clean during a migration — is a severity concern, not an enabling concern, and the `warn` level ([Section 6.1](#61-compatibility---checked-and-unchecked-code)) already serves it: the whole package is analyzed, diagnostics land per file, and a ratchet is CI tooling over warning counts. Should demand outgrow that, per-file escalation of `warn` to `error` on top of package-wide analysis touches neither semantics nor metadata, and can be added as tooling later.

### 9.5 The Modal-less degraded mode

The degraded mode of [Section 6.5](#65-checking-without-modal-cangjie) exists for schedule and adoption reasons, not design ones. Modal Cangjie is expected to land first; if it slips, exception checking should not be stranded — the clause machinery is independently useful as checked documentation, and Scala ships exactly this partial guarantee as its current state ([Section 2.2.3](#223-capability-based-scala-3-safer-exceptions)). Offering it as an explicit, named tier keeps the full guarantee's claim honest while widening adoption to codebases that have not taken up modes. The mode is transitional by construction: it ends in full Modal checking.

### 9.6 Rejected: `Option`-returning twins

Adding `Option`-returning variants beside throwing operations (`tryParse` next to `parse`) was rejected. Such twins are the unchecked world's compensation for invisible exceptions: they duplicate every API surface with a second name and discard the failure's diagnostic payload on the `None` path. With checked exceptions the throwing form is the single source of truth — type-level visibility through the clause, term-level silence through implicit propagation. `Option` remains where absence is a domain outcome rather than a failure (the criterion of [Section 5.1](#51-unchecked-exceptions)).

The legitimate residue is the local-default idiom: handling or defaulting one *expected* failure without `try`-`catch` ceremony. Typically a single entry of a callee's list is that special one, while the rest should propagate — which makes this use-site business, not API business: a possible `try?`-style expression, selective per exception type, is sketched in [Section 8.5](#85-syntactic-sugar-for-handling). The API stays single.

### 9.7 The `CanThrow` intrinsic

`CanThrow` is a compiler-known intrinsic rather than a library declaration ([Type of exception capabilities](#31-type-of-exception-capabilities)). The library alternative — a `public enum CanThrow<in T>` in `std.core` — was rejected: enums currently admit neither zero constructors (forcing a polluting dummy constructor) nor variance annotations (a variance proposal for enums is accepted but not yet implemented), and a denotable capability type is not wanted anyway — non-denotability is what makes capabilities never first-class ([Capability argument inference](#33-capability-argument-inference)).

The contravariance of `CanThrow` is a rule of the intrinsic, like the built-in variance of function and tuple types; it does not wait on enum variance. Every rule comparing `CanThrow` types does so inside dedicated capability rules, so an implementation may operate on exception types directly and needs the type itself only for diagnostics (the error message of [Capability argument inference](#33-capability-argument-inference) is the model).

### 9.8 Rejected: a reserved lowering slot

Two extensions want runtime capability content — [Exception encapsulation](#89-exception-encapsulation) a handler identity, [Optimizing effect handlers](#81-optimizing-effect-handlers) a handler closure. **Reserving a lowering slot now** — a hidden, initially dead parameter on every clause-bearing function, to go live when capabilities materialize — was rejected: a dead slot breaks the no-runtime-footprint claim of the base design today, and it would have to guess a representation that the two extensions need differently.

There is also nothing to reserve *for*. Such an extension arrives as a distinct, opt-in capability kind for the commands or exceptions that want it, with its own rules and trade-offs — materialization is a separate design, not a new compilation of this one. Ordinary `CanThrow` and `CanPerform` stay erased forever, so the extension is additive: existing binaries keep their meaning and no ABI transition, versioning scheme, or flag day exists for them. Both kinds coexist in one binary — that coexistence is the benefit of choosing a kind over a transition.

### 9.9 Erasure over reified clauses

Runtime casts to functional types cannot verify a clause under erasure, hence their rejection in the base design ([Reflection and runtime casts](#3102-reflection-and-runtime-casts)) and the relaxations of [Runtime casts to functional types](#812-runtime-casts-to-functional-types). The alternative — recording clauses in runtime function-type descriptors, so that `as`, `is`, and type patterns check clause coverage exactly — was considered and rejected for the base design.

It would buy exact casts with uniform type syntax, casts into invariant positions, and truthful `TypeInfo`, at no cost to calls or values: capabilities would stay phantom and only type metadata would grow. Four costs outweigh that.

1. Runtime type identity changes: `() throws A -> R` and `() -> R` become distinct runtime types, with distinct `TypeInfo` and distinct generic instantiations, and the function-type descriptor gains a field — an ABI break of exactly the kind the base design refuses to spend ([Section 9.8](#98-rejected-a-reserved-lowering-slot)), here on day one.
2. Runtime identity would depend on the checking level: a package compiled with checking off emits clause-free descriptors, so the same function has a different runtime type depending on a compile flag, and a checked consumer's `f is (() throws E -> R)` answers differently for the same library built at different levels. This is the defect that sank the boundary devices of [Section 9.3](#93-rejected-safety-devices-at-the-unchecked-boundary), and it contradicts the static nature of levels.
3. Clause entries that are type parameters need reified type arguments at run time; without them casts are exact only for concrete entries.
4. The gain is small: casts to functional types recovered from `Any` are rare, and `throws Exception` is the honest type of a value whose origin the caster does not know. Only the invariant position is lost, and a function-typed container recovered from `Any` is rarer still.

Reification has a natural home later, but only for the opt-in kind: [Exception encapsulation](#89-exception-encapsulation) changes its participating function values' layout anyway, and recording clauses in *those* descriptors costs nothing extra. Reifying ordinary erased `throws` types would remain a separate runtime-identity change — the one this section rejects.

### 9.10 The escape hatch as a higher-order intrinsic

`unsafeCanThrow` ([The escape hatch](#513-the-escape-hatch)) takes a callback rather than yielding a capability value. A value of type `CanThrow<E>` must be `@ local!` in some region, and a fabricated one has no honest region — any choice would either be uselessly narrow or lie to the mode system. The higher-order form scopes the fabrication to the call, where the synthetic region of [Section 4.4](#44-capability-regions) has a natural extent.

The pair is named for the capability it fabricates — `unsafeCanThrow`, `unsafeCanPerform` — leaning on the taught intrinsic types (point 7 of [Section 9.1](#91-keyword-scheme-throws-performs-captures)). Two names, not an overload: the signatures differ only in their clause components, which neither participate in overload resolution nor reach argument literals — those take their clauses from the expected type. Rejected: `unsafeAssumeHandled` (kind-ambiguous), `unsafeIgnoreException`/`unsafeIgnoreEffect` (read as swallowing at run time, when nothing is suppressed — the requirement is ignored, never the exception).

That `E` must be named is a consequence of keeping capability lists out of type-argument inference, and arguably a feature: the caller states what they assert. Asserting several types at once needs no list syntax, because functional-type subtyping already provides it — a `() throws (A, B) -> R` value coerces to `() throws Exception -> R`, so instantiating `E` with `Exception` asserts everything. [Capability-list polymorphism](#83-capability-list-polymorphism) would later allow precise lists.

### 9.11 One clause per kind

An earlier draft admitted several `throws` clauses on one declaration, unioning their entries, so that a macro could append a clause instead of merging into an existing one. Removed: the language allows one `where` clause per declaration, and a same-kind multiplicity for `throws` alone was an anomaly. The macro argument does not hold — a macro transforms the declaration's AST, and locating the clause to append a second one is the same work as merging entries into it, while merging is safer: entries added to an existing list preserve its inference status ([Section 5.3.5](#535-interaction-with-an-explicit-throws)), where an appended clause could silently flip it. Conditional compilation never needed multiplicity either: `@When` selects among whole declarations, each carrying its own complete clause. The removal also deleted the combination errors (`throws () throws A`) and the repeat-idempotence rule for `...`.

### 9.12 Innermost-first selection

When several scopes hold a suitable capability, resolution takes the innermost ([Section 3.3.3](#333-resolution)). Two alternatives were examined.

**Outermost-first** is sound in the base design and strictly more permissive: handlers are dynamic, so the choice affects only typing, and a carrier tied to a wider region is admitted in more places. It was rejected on three grounds. First, the choice stops being unobservable for capability kinds with handler identity — under evidence passing ([Optimizing effect handlers](#81-optimizing-effect-handlers)) the chosen capability names the handler that runs, and only innermost-first agrees with dynamic dispatch. Those arrive as distinct opt-in kinds and are no certainty, but resolution should be one rule across kinds — splitting it, or flipping it later, would be worse than the permissiveness is worth. Second, innermost-first is the straightforward rule to teach: the capability found is the one belonging to the handler a throw at that point would reach. Third, the programs outermost-first additionally accepts are exactly those where a carrier built under a local handler outlives it — code whose nearby `catch` silently never receives the escaped calls; a rejection naming the `try` is the more useful outcome, and the fix (hoist the literal, or catch at the right level) is local.

**A fallback hybrid** — innermost by default, retrying outer capabilities where the escape check would reject — was rejected outright. It makes selection depend on the verdict of the analysis that runs after it ([Phase ordering](#533-phase-ordering)), and the verdicts of different selections are coupled through origin-set unions, so the retry is a global search whose deterministic result the specification would have to pin, whose failures name no actionable site, and which abandons the pipeline's principle that validation only rejects — never re-resolves.

### 9.13 Capture sets are restated, not inherited

Rule 4 of [Capability capturing](#39-capability-capturing) makes a subclass restate coverage of the superclass's captured types instead of inheriting the capture set implicitly. Inheriting would be sound — the instance's origin set includes the superclass's captured origins either way — so this is an API-design choice. Restating keeps the header honest: the instance's full handler dependency, and with it the region story, is readable in one place. It keeps checking local: a body is checked against its own class's list, never against metadata of the ancestor chain. And it keeps evolution visible: a superclass changing its captures surfaces at subclass headers — which are construction sites, where such a change already breaks, locally and mechanically — instead of silently changing what subclass bodies may throw. The restated entries cost nothing: capabilities are freely duplicable evidence, and the same construction-site handler supplies every copy in the chain. Whether the synthesized fields are then shared or per-class is unobservable in the base design — covering entries discharge everything the superclass's would, and the fields are erased — becoming meaningful only under extensions that give capabilities identity ([Exception encapsulation](#89-exception-encapsulation)); the declaration `throws`-based alternative for constructors is rejected in point 6 of [Section 9.1](#91-keyword-scheme-throws-performs-captures).

Restating also forecloses no alternative. A subclass that *discharged* the superclass's requirement instead — `super(path)` wrapped in a `try-catch` inside its constructor, hoping for a freely constructible subclass of a capturing base — is impossible twice over: a `local!` constructor's `super` call must be its first expression, so the wrapping does not parse; and were it expressible, the superclass stores the capability, so the instance would be bound to a handler that dies when the constructor returns — unusable, by the region discipline of [Section 4.4](#44-capability-regions).

## 10. Grammar impact

The scheme was checked against the open-source Cangjie compiler ([cangjielanguage/cangjie_compiler](https://github.com/cangjielanguage/cangjie_compiler); relevant files: `include/cangjie/Lex/Tokens.inc`, `src/Lex/Lexer.cpp`, `src/Parse/ParserImpl.h`, `src/Parse/ParseDecl.cpp`).

**Availability.** `throws`, `performs`, and `captures` are not tokens: today they lex as plain identifiers. `throw` is reserved; `with` is reserved (used by `resume ... with`); the experimental effect tokens `perform`, `resume`, `throwing`, `handle` are keywords only when effect handlers are enabled (the lexer's keyword lookup consults the effect-handlers flag). Note the proximity of the expression keyword `throwing` (`resume ... throwing e`) to the clause `throws`: documentation and diagnostics must keep them distinct, and `throwing` must never be reused as a clause keyword.

**Keyword tiers with in-tree precedent.** Cangjie already has three: hard tokens; *contextual keyword* tokens that the parser re-admits as identifiers (`public`, `sealed`, `open`, … via `GetContextualKeyword()`); and *pure soft keywords* — `get`/`set` in `prop` bodies are plain identifiers value-checked by the parser.

**Proposal: all three clause keywords are pure soft keywords** (the `get`/`set` mechanism). Full reservation — even gated behind `--enable-checked-exceptions` — would break identifiers such as `captures`, a plausible API name (e.g. regex matchers). Backticked identifiers remain as an escape hatch, and later promotion to contextual tokens (for the benefit of tooling that does not run a parser) stays open.

**Position-by-position feasibility.** Each clause position is a parse error today, so the clauses are pure grammar extensions — no valid program changes meaning:
1. *Declaration clause.* After the parameter list, return type, and `where` constraints, an identifier is currently rejected (for generic declarations with a dedicated diagnostic, `parse_expected_where_brace`; otherwise as an invalid start of the next declaration). Newlines before the clause are transparent: the parser's lookahead skips `NL` by default, so the clause-on-its-own-line style used throughout this document parses without special cases. A second `throws` clause after the first is rejected with a dedicated diagnostic (rule 4 of [Section 3.2](#32-capability-parameters-in-declarations)), like a second `where`. Within a `throws` clause, `(` after `throws` or after a comma opens a nested entry list (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)), never a tuple type: nesting parses as list structure and `()` as the empty list, so no tuple-type ambiguity arises.
2. *Class header `captures`.* An identifier after the supertype list or constraints is currently an error; same situation. A second `captures` clause is rejected like a second `throws` (rule 4 of [Section 3.2](#32-capability-parameters-in-declarations)).
3. *Functional types.* An identifier after a parenthesized type is currently an error. Two rules make parsing deterministic: (i) multi-entry lists must be parenthesized — `(A) throws (E1, E2) -> R`, a single parenthesized entry in the grammar of rule 2 of [Section 3.2](#32-capability-parameters-in-declarations) — which simultaneously resolves the comma ambiguity inside generic argument lists such as `F<(A) throws (E1, E2) -> R, B>`; (ii) a clause keyword in type position commits to a function type, whose `->` must follow — bounded speculation of the kind the parser already performs to distinguish tuple types from function types.
4. *Lambdas.* Clause keywords appear in literals only under the extension of [Section 8.2](#82-explicit-capability-abstractions), which admits both `performs` and `throws`. A parameter named after a clause keyword is separated from a clause by what follows: `=>`, `,`, or `:` means a parameter; a type start means a clause. One case needs more than a token of lookahead: after a parameter whose type ends in a parenthesized type (`{ p: (B) performs H ... }`), the clause list must be scanned to its disambiguator — `->` continues the parameter's function type, `=>` closes it as the lambda's clause. This is the same delimiter-bounded speculation as tuple-vs-function types, and it runs inside the region the parser already scans to distinguish lambdas from blocks.
5. *List variables.* Under the extension of [Section 8.3](#83-capability-list-polymorphism), `throws` before an identifier inside a generic parameter list declares a capability-list variable. A generic parameter is a bare identifier today, so the position is a parse error now, and one token of lookahead separates the marker from a parameter named `throws`.

**The `...` marker and the empty clause.** The `...` token already exists in the lexer (`ELLIPSIS`); this design reuses it in one new position — the tail of a declaration `throws` list, at most once ([Section 5.3.5](#535-interaction-with-an-explicit-throws)). It is rejected in functional types and on exported declarations. The empty clause `throws ()` is permitted in declarations and functional types alike; it, `throws ...` alone, and the marker parse trivially within the entry-list grammar.

**Assumption imports.** Annotations on `import` declarations already exist in the grammar — builtin annotations are parsed and attached to imports, the mechanism `@When` conditional compilation uses — so `@AssumeThrows` and `@AssumePerforms` ([Section 6.3](#63-interoperability-between-checked-and-unchecked-code)) require registering builtin annotations, not new parsing.

TODO: formal grammar productions; precedence and associativity of clause keywords in nested functional types (`(A) throws E -> (B) throws F -> R`).

## 11. Standard library and toolchain impact

Everything the proposal adds to or requires from the standard library and the toolchain. Work in progress: the per-module lists are produced by the annotation audit.

### 11.1 Classification of standard exceptions

By the criterion of [Unchecked exceptions](#51-unchecked-exceptions) — a bug in the program is unchecked, a condition of the outside world or of input data is checked — a starter classification; the annotation audit confirms names and homes:

| Becomes `<: UncheckedException`                           | Stays checked                                                           |
| --------------------------------------------------------- | ----------------------------------------------------------------------- |
| `IllegalArgumentException`, `IllegalStateException`       | the `IOException` hierarchy (`std.io`, `std.fs`)                        |
| `IndexOutOfBoundsException`, `NegativeArraySizeException` | socket, connection, timeout errors (`std.net`)                          |
| `ArithmeticException`, `OverflowException`                | parse, format, decoding errors (`std.convert`, `encoding.*`)            |
| `NoneValueException`, `ConcurrentModificationException`   | charset/encoding errors; time parsing (`std.time`)                      |
| `UnsupportedException`                                    | `SqlException` (`std.database.sql`), `ProcessException` (`std.process`) |

`std.regex` is the one judgment call: pattern-compile errors from string literals are programmer errors, but dynamically supplied patterns are input data — classify **checked**, since the data-driven use exists and is what checking is for. Two asymmetries to exploit and announce: classification only affects checked consumers, so classify aggressively before stabilization — afterwards the checkedness of each standard exception is API; and third-party exceptions deriving from reclassified classes become unchecked automatically — intended, but silent, so release notes must call it out.

### 11.2 Annotation of standard APIs

The standard library ships annotated together with the compiler implementation: the release introducing `--enable-checked-exceptions` carries `throws` clauses on the effectful modules (`std.fs`, `std.io`, `std.net`, `std.time`, `std.convert`, `std.process`, `std.database.sql`, `encoding.json`, `std.regex`), compiled at the `error` level — the annotation audit is part of the feature's release criteria, and `error`-clean clauses are the criterion; Modal confinement of the library's higher-order APIs is not. A module ships either unannotated or `error`-clean; `warn` is a development state, not a shipping state. The same release reparents programmer-error exceptions under `UncheckedException` — expected to be source-compatible for code compiled with checking off, since inserting a superclass preserves every existing subtyping fact, subject to the corpus and ABI audits (direct-superclass reflection, class metadata, serialization); third-party subclasses of reparented classes become unchecked with them. Audit status as of 2026-08-21: 26 re-parentings and 90 clauses landed; remaining names and homes to be confirmed.

Higher-order functions additionally need Modal Cangjie mode annotations (e.g. `map`'s `@ local?` function parameter, [Higher-order functions](#212-higher-order-functions)) but no error-type polymorphism; these land when Modal Cangjie does and are additive. Interface policy: an interface whose real implementations predominantly throw a given exception declares it (streams declare `throws IOException`; in-memory implementations override with narrower lists per [Section 3.8](#38-overriding-and-redefinition)), while an interface whose implementations are predominantly pure stays clause-free, with effectful implementations using capability capture ([Capability capturing](#39-capability-capturing)). A further factor is instance lifetime: capture region-binds instances, so long-lived effectful types must declare. IO-backed iterators become capturing classes — a `File.lines()` iterator captures `CanThrow<IOException>` and is therefore `local!` — so `for-in` must accept `local!` iterators, a requirement to confirm with Modal Cangjie ([Section 4.7](#47-open-questions)). The audit must also keep deferred-execution APIs (timers, pools, callback registration) on plain escaping function types: a well-meaning `@ local?` there would be a soundness hole, not a convenience ([Lazy computations and `spawn`](#71-lazy-computations-and-spawn)). `Resource.close()` stays clause-free; a resource implementation that can fail with a checked exception on closing captures its close capability at construction ([Capability capturing](#39-capability-capturing)).

### 11.3 New `std.core` declarations

- `CanThrow<T>`, `T <: Exception` — not a `std.core` declaration but a compiler-known intrinsic ([Type of exception capabilities](#31-type-of-exception-capabilities)); must never implement `Copyable` (point 8 of [Section 4.2](#42-what-already-holds)).
- `interface Convertible<From, To> where From <: Exception, To <: Exception` — arrives with the [Exception conversions](#84-exception-conversions) extension. The standard library itself ships no public `Convertible` implementations in the initial release: conversions are an application-layer tool, and a std-shipped conversion would change downstream type checking globally.
- `open class UncheckedException <: Exception` ([Unchecked exceptions](#51-unchecked-exceptions)), with the reparentings of [Section 11.1](#111-classification-of-standard-exceptions).
- `class WrappedUncheckedException <: UncheckedException` — arrives with the [Section 8.5](#85-syntactic-sugar-for-handling) sugar as its builtin conversion target.
- `func unsafeCanThrow<E, R>(f: (() throws E -> R) @ local?): R where E <: Exception` — a compiler intrinsic with a library-visible signature ([The escape hatch](#513-the-escape-hatch)); without Modal Cangjie the parameter carries no mode. Its effect twin `unsafeCanPerform` ships with `--enable-checked-effects` (rule 2 of [Section 5.4](#54-effect-requirements)).
- `Exception.cause` and `Exception.suppressed`, generally useful and required by the conversion extension ([Exception conversions](#84-exception-conversions)): `cause` is set-once and mutable, `suppressed` is a read-only snapshot with `addSuppressed`, and the default printer learns the `Caused by:`/`Suppressed:` chains. Adding members to a widely-subclassed root risks name clashes in subclasses; a corpus survey is required before landing, and the set-once `mut prop` design must be confirmed against Cangjie property semantics. New exception classes adopt a `(message, cause)` constructor convention.

### 11.4 Concurrency and effects

- **Concurrency:** in the base design, blocks passed to `spawn` cannot let checked exceptions escape ([Lazy computations and `spawn`](#71-lazy-computations-and-spawn)); lifting this is [Capability-list polymorphism](#83-capability-list-polymorphism), whose defaulted list parameter keeps `Future<T>` source-compatible and whose runtime requirement — thread-boundary storage and re-raise at `get` — is stated in [Section 7.1](#71-lazy-computations-and-spawn).
- **Effects:** `CanPerform<C>`, `C <: Command<R>`, is a compiler-known intrinsic like `CanThrow` ([Effect requirements](#54-effect-requirements)); the standard library's effect-handler APIs acquire `performs` clauses when the library adopts `--enable-checked-effects` ([Section 6.1](#61-compatibility---checked-and-unchecked-code)); a first-class resumption type, should one arrive, needs the mode confinement of [Section 4.7](#47-open-questions). Evidence passing arrives with [Optimizing effect handlers](#81-optimizing-effect-handlers).

### 11.5 Toolchain surface

The `--enable-checked-exceptions warn|error` and `--enable-checked-effects warn|error` flags ([Section 6.1](#61-compatibility---checked-and-unchecked-code)); the closed-build verification mode of [Section 6.3.4](#634-scope-of-the-guarantee); the `checked-exceptions` and `checked-effects` warning groups; the `@AssumeThrows` and `@AssumePerforms` builtin annotations ([Section 6.3](#63-interoperability-between-checked-and-unchecked-code)); the clause-materializing fixer ([Section 6.4](#64-migrating-user-code)); and the lints of [Section 12](#12-todo).

## 12. TODO

Cross-cutting work items collected from the text. Section-local TODOs remain in their sections.

- **Redundant `throws` entry lint.** Warn when an entry of a `throws` list is subsumed by another entry of the same list (e.g. `throws Exception, IOException`).
- **Undischarged capability lint.** Warn when a declared capability cannot be exercised by the body (nothing can throw the exception). Must not fire, or must be suppressible, on public APIs that deliberately reserve capabilities for evolution ([API evolution](#216-api-evolution)).
- **Unchecked-boundary lint** (off by default). Report the sites that leave the guarantee silently — reflective invocation and construction, FFI callbacks, casts to parameter-typed generic targets ([Reflection and runtime casts](#3102-reflection-and-runtime-casts)) — computed from the throw-closure summary of [Section 8.14](#814-the-unreachable-catch-diagnostic) and available with that extension; the escape hatch has its own counting lint ([The escape hatch](#513-the-escape-hatch)).
- **Mechanized soundness proof — future work.** A core-calculus formalization of try-scoped capability regions proving the theorems of [Section 4.6](#46-exception-safety), in the mechanized style of the modal-types line ([Related work](#23-related-work)). Deliberately not a gate for the feature: the design proceeds on the stated rules.
- **Corpus study.** Run the clause-materializing fixer ([Section 6.4](#64-migrating-user-code)) over representative codebases to measure clause density and list depth — the empirical validation of the annotation-burden claims of [Section 2.1](#21-overview-of-issues-and-our-solutions) — and how often literals in synthesis positions need capability parameters, which the expected-type rule of [Section 5.3.1](#531-which-declarations-are-inferred) denies them.
- **Type-checker prototype.** A checking-only spike on the open compiler to validate the phase ordering of [Section 5.3.3](#533-phase-ordering) and the parsing analysis of [Section 10](#10-grammar-impact).
- **Default effect handler.** Determine whether the effect-handler design supplies a default handler around `main` for unhandled commands. Rule 3 of [Effect requirements](#54-effect-requirements) assumes it does not; if it does, `main` may carry a `performs` clause for the commands it handles, mirroring rule 5 of [Capability parameters in declarations](#32-capability-parameters-in-declarations), and the corresponding row of the [Section 9.1](#91-keyword-scheme-throws-performs-captures) table changes.
- **Formal grammar and judgments.** The parsing analysis of [Section 10](#10-grammar-impact) is prose over the implementation; normative acceptance needs formal grammar productions and typing judgments for the clause forms and resolution rules.

## 13. Glossary

One line per term; each is normative where its section defines it.

- **Capability** — erased compile-time evidence that a handler exists: `CanThrow<E>` ([Section 3.1](#31-type-of-exception-capabilities)), `CanPerform<C>` ([Section 5.4](#54-effect-requirements)).
- **Requirement** — a capability a callable needs from its call site; declared or inferred as its clause lists ([Section 3.2](#32-capability-parameters-in-declarations)).
- **Semantic form** — a list with duplicates and covered entries removed; the form every rule consumes (rule 2 of [Section 3.2](#32-capability-parameters-in-declarations)).
- **Capability scope** — a lexical region whose code may use a set of capabilities ([Section 3.3.2](#332-capability-scopes)).
- **Capability region / origin** — the dynamic lifetime of a handler; the origin of every capability it introduces ([Section 4.4](#44-capability-regions)).
- **Carrier** — a value holding capabilities: root (function object, capturing instance; prospectively a first-class resumption) or transitive (aggregate containing one) ([Section 4.4](#44-capability-regions)).
- **Origin set** — the origins of everything a carrier holds; unknown, never empty, for boundary-produced carriers ([Section 4.4](#44-capability-regions)).
- **Capturing type** — a class or struct with a `captures` clause; instances store capabilities and are `local!` ([Section 3.9](#39-capability-capturing)).
- **Checked / unchecked exception** — subtype of `Exception` outside / under `UncheckedException` ([Section 5.1](#51-unchecked-exceptions)); `Error` is untracked.
- **Checked / unchecked code** — compiled at `error` / with checking off; `warn` is unchecked for guarantee purposes ([Section 6.1](#61-compatibility---checked-and-unchecked-code)).
- **Verified / trusted** — recorded lists from `error` / from `warn` or assumptions; trusted facts are never theorem premises ([Section 6.1](#61-compatibility---checked-and-unchecked-code)).
- **Unchecked invocation boundary** — a runtime transition where requirements are not enforced: unchecked callers and callbacks, reflective invocation and construction, parameter-typed casts, unchecked implementations behind checked interfaces ([Section 6.3.4](#634-scope-of-the-guarantee)).
- **Checked root** — the entry whose caller supplies a real handler: `main` of a checked package ([Section 6.3.4](#634-scope-of-the-guarantee)).
