# Clauses on properties (E-19) — design note

**Author's ruling, 2026-08-30:** support both forms — a clause on an abstract accessor, and a
clause on the property itself.

```swift
interface StreamingSocket {
    prop localAddress: SocketAddress
    throws SocketException                    // form 2: on the property

    mut prop readTimeout: ?Duration {         // form 1: per accessor
        get()
        set(value) throws IllegalArgumentException
    }
}
```

## What exists today

`ParsePropDecl` (`src/Parse/Parser.cpp`) parses `prop name : Type`, then either a `{ … }` body
(`ParsePropBody` → `ParsePropMemberDecl` per accessor) or, in a class-like scope, marks the
property `ABSTRACT` and stops. `ParsePropMemberDecl` parses each accessor through `ParseFuncBody`
— which already parses a capability clause — and then **requires a body**
(`DiagMissingBody`). For an `ABSTRACT` property, `AddSetterGetterInProp`
(`src/Sema/TypeChecker.cpp`) synthesizes accessors with an empty `FuncBody` and no clause.

So the clause machinery is already in place for accessors; what is missing is (a) a bodyless
accessor being legal where a bodyless method is, and (b) somewhere to put the property-level
clause between the type and the body.

## The two forms

**Form 1 — per accessor, bodyless.** `get()` / `set(x)` may carry a clause and omit the body
exactly where an abstract method may omit it: interface members, and `abstract class` members.
Elsewhere the existing "body is missing" diagnostic stands. A property whose accessors are all
bodyless is `ABSTRACT`, as if it had no body block at all — that is the flag `CanBeAbstract`
already computes, extended to this shape.

**Form 2 — on the property.** After the type, before the body or the end of the declaration, in
the position `where` would take. It is a **shorthand**: the clause is distributed to every
accessor that does not carry one of its own.

Distribution, not union, is what makes the two forms compose: the property-level clause is the
default, an accessor's own clause replaces it for that accessor. So

```swift
mut prop v: Int64
throws E {
    get() { … }                       // requires E
    set(x) throws F { … }             // requires F, not E and F
}
```

The alternative — forbidding form 2 wherever an accessor carries form 1 — is simpler to specify
and was considered; distribution wins because the common shape is "the getter can fail, the setter
cannot", which under a ban would force every property to spell both accessors even when one is
trivial. **Open question Q14 for the author:** confirm distribution over prohibition.

## Where the clause lives in the AST

A new `PropDecl::throwsClause` field, not a reuse of an accessor's. Reason: for an abstract
property written in form 2 the accessors do not exist yet at parse time — they are synthesized in
`AddSetterGetterInProp` — so the clause has nowhere else to wait. `performsClause` follows the same
shape for symmetry, though effects on properties are not otherwise special.

A new AST field is the expensive part of this change: **every** visitor must learn it — Walker,
Clone, PrintNode, ASTChecker, ASTHasher (both the signature and the member-signature hash),
Collector, PartialInstantiation — plus `ASTKind.inc`'s SIZE column and the count in
`unittests/Utils/CastASTTests.cpp`. That list is in `architecture.md` for exactly this reason.

## Distribution point

In `AddSetterGetterInProp` for the synthesized case (form 2 on an abstract property with no body),
and at the end of `ParsePropBody` for the written case (form 2 with a body block): each accessor
without its own clause gets a clone of the property's. Cloning rather than sharing keeps every
`FuncBody` the owner of its clause, which is what `GetFuncBodyCapTys` assumes.

After distribution nothing downstream changes: an accessor's clause reaches `FuncTy::capTys`
through the ordinary path, overrides compare per accessor as they already do
(`CheckThrowsClauseCompatible` is called for accessor pairs), the `.cjo` records accessor types as
it already does, and inference treats an accessor as the exported member its property's visibility
makes it.

## What it closes

`std.net`'s `StreamingSocket.localAddress` / `.remoteAddress` (documented `@throws
SocketException`, implementations throw exactly that) stop being permanent coverage violations —
the interface can finally state its contract, and `TcpSocket`'s accessors narrow to it. The same
applies to `DatagramSocket`. That is the whole practical surface found in std and stdx today: six
properties, of which four document an unchecked exception and need nothing.

## Plan

| step | work |
|---|---|
| 1 | `PropDecl::throwsClause` / `::performsClause` + every visitor + the two size counts |
| 2 | `ParsePropDecl`: parse the clause after the type, before `{` or end of declaration |
| 3 | `ParsePropMemberDecl`: allow a bodyless accessor in interface / `abstract class`; mark the property `ABSTRACT` when all its accessors are bodyless |
| 4 | Distribution: `ParsePropBody` (written accessors) and `AddSetterGetterInProp` (synthesized) |
| 5 | Diagnostics: a bodyless accessor outside an abstract context keeps the existing message; a clause on a property of a `struct`/`enum` where properties cannot be abstract follows the same rule as methods |
| 6 | Tests: both forms; distribution with and without an accessor clause; narrowing override; bodyless accessor rejected in a concrete class; `.cjo` round-trip of an interface property clause; the `mut` setter case |
| 7 | `std.net`: annotate the two socket interfaces, and check that the implementations narrow rather than violate |

Size: **M**, one to two compiler builds plus a std build. The AST field is the bulk; parsing and
distribution are small, and nothing downstream needs to change.

## Open questions

- **Q14** Distribution vs prohibition when both forms appear on one property (recommended:
  distribution, above).
- **Q15** Does a property-level clause belong in the text's grammar section as sugar, or as a
  first-class form? It affects whether the `.cjo` should record the property-level clause at all,
  or only the distributed accessor ones (recommended: distributed only — the property-level clause
  has no meaning after elaboration).
