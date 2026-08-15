{
  "summary": "Derive precise, verified fix plans for audit findings MF1, MF6, MF2 (capability loss through desugaring and inference write-back)",
  "agentCount": 7,
  "logs": [],
  "result": {
    "plans": 3,
    "guide": "# Merged implementation guide â MF6 + MF1 + MF2(Part A)

**Scope of this batch:** MF6 (primary-ctor `throws` dropped), MF1 (property-accessor `throws` dropped at use sites), MF2 **Part A only** (inferred lists written back into declaration types). **MF2 Part B (demand at function-value formation) is EXCLUDED** â see Unresolved #2; its central premise was disproved and one of its edits does not compile.

All anchors below were re-verified against the working tree at `858edc68` (branch `chexc`). Line numbers are current; where an edit shifts lines, the later edits in that file are anchored on text, and I give an apply order that avoids drift.

**Totals:** 9 source files, 18 edits, 1 ledger file, 12 new `.cj` tests.

---

## 1. Apply in this order

### Group 0 â AST clause copiers (prerequisites; must precede Group 2)

Both hand-enumerated `ThrowsClause` copiers have drifted on the same field. `ASTHasher::HashThrowsClause` (`src/Parse/ASTHasher.cpp:343-348`) is the correct reference field list: `{throwsPos, capTypes, hasEllipsis}`.

**E0.1 â `/home/penguin/Projs/effects-research/cangjie/cangjie_compiler/src/AST/Clone.cpp`**
*Anchor:* line 401, exactly `    ret->commaPosVector = node.commaPosVector;` inside `ASTCloner::CloneThrowsClause` (394-406).
*Write:* insert immediately after line 401, before the `for (auto& capType : node.capTypes)` loop:
```cpp
    // The `...` marker decides whether inference stays enabled for the declaration
    // (proposal 6.3.5); it is a plain ThrowsClause member, not a Node-level field, so
    // CopyNodeField does not carry it.
    ret->hasEllipsis = node.hasEllipsis;
```
*Why:* without it, MF6's clause transfer silently swallows `...` on `A(x: Int64) throws E, ...` and the ctor stops being inference-eligible â a quiet wrong answer replacing today's loud one.

> **Behaviour-change warning the engineer must record in the commit message.** This is not a no-op refactor. `CloneThrowsClause` is reached from five sites â `CloneFuncBody` (`Clone.cpp:1398-1400`), `CloneFuncType` (`:414-415`), the `capturesClause` clones in `CloneStructDecl`/`CloneClassDecl` (`:275`, `:293`), and `CloneNode`'s `ThrowsClause` arm (`:1553`). The only observable direction is "a cloned decl whose clause ends in `...` flips from ineligible to eligible", which **adds** inferred capabilities and can therefore **add** errors at call sites. Surface is `throws`-only: `ParseCapturesClause` (`src/Parse/ParseType.cpp:355-382`) has no ellipsis grammar and never sets the flag.

**E0.2 â `/home/penguin/.../cangjie_compiler/src/Sema/GenericInstantiation/PartialInstantiation.cpp`**
*Anchor:* line 483, exactly `    ret->commaPosVector = node.commaPosVector;` inside `InstantiateThrowsClause` (476-488).
*Write:* insert after line 483:
```cpp
    ret->hasEllipsis = node.hasEllipsis;
```
*Why:* provably unobservable today (CAPABILITY_CHECK precedes GENERIC_INSTANTIATION, `include/cangjie/Frontend/CompilerInstance.h:52-55`), but the defect class being fixed **is** "a hand-enumerated copier drifted"; leaving one un-fixed re-creates the latent state. Promoted from optional to required per the MF6 challenger.

---

### Group 1 â shared instantiation helper (must precede Groups 3 and 5)

**E1.1 â `.../src/Sema/TypeCheckUtil.h`**
*Anchor:* line 191, immediately after `std::vector<Ptr<AST::Ty>> GetFuncBodyCapTys(const AST::FuncBody& fb);`
*Write:*
```cpp
/**
 * Checked exceptions: the capability list of @p accessor (its elaborated 'throws' clause),
 * instantiated for a use site whose receiver has type @p receiverTy. @p receiverTy may be null
 * (unqualified reference), in which case the list is returned verbatim: the declaration's own
 * type parameters are already the ones in scope. Entries that failed elaboration are dropped.
 */
std::vector<Ptr<AST::Ty>> GetInstantiatedAccessorCapTys(
    TypeManager& tyMgr, const AST::FuncDecl& accessor, Ptr<AST::Ty> receiverTy);
```
*Why:* two modules need identical semantics (`Desugar/AfterTypeCheck.cpp` Ã3 and `CapabilityCheck.cpp`); both already `#include "TypeCheckUtil.h"` (`AfterTypeCheck.cpp:24`, `CapabilityCheck.cpp:45`) and `AfterTypeCheck.cpp:44` has `using namespace TypeCheckUtil;`.

**E1.2 â `.../src/Sema/TypeCheckUtil.cpp`**
*Anchor:* immediately after `GetFuncBodyCapTys`, whose closing `}` is line 328; before `GetDeclCapturesCapTys` at line 330.
*Write:*
```cpp
std::vector<Ptr<Ty>> GetInstantiatedAccessorCapTys(
    TypeManager& tyMgr, const FuncDecl& accessor, Ptr<Ty> receiverTy)
{
    if (!accessor.funcBody) {
        return {};
    }
    // Entries that failed elaboration are DROPPED, never forwarded: ExpandCapabilityEntry
    // (:275-280) emplaces InvalidTy for them, and FuncTy marks itself invalid when any capability
    // ty is incorrect (AST/Types.h:731-732). The desugared callee expressions this feeds have
    // never carried an invalid ty; introducing one would be a new error-recovery state for every
    // later PostTypeCheck pass and for cjd/LSP.
    std::vector<Ptr<Ty>> caps;
    bool anyGeneric = false;
    for (auto cap : GetFuncBodyCapTys(*accessor.funcBody)) {
        if (!Ty::IsTyCorrect(cap)) {
            continue;
        }
        anyGeneric = anyGeneric || cap->HasGeneric();
        caps.emplace_back(cap);
    }
    if (!anyGeneric || !Ty::IsTyCorrect(receiverTy)) {
        return caps;
    }
    // The accessor may be inherited from a supertype or reached through an extend
    // (FindValidPropAccessor, :584-608), so the mapping must come from the RECEIVER's type --
    // which walks extends and the whole inheritance chain -- not from accessor.outerDecl.
    // GenerateGenericMapping(MultiTypeSubst&, Ty&) (TypeManager.cpp:629-633) allocates no
    // placeholder ty vars, so it is safe after type check.
    MultiTypeSubst mts;
    tyMgr.GenerateGenericMapping(mts, *receiverTy);
    // Collapse to a single-valued substitution. GetBestInstantiatedTy would return
    // '*instTys.begin()' out of a pointer-ordered std::set (TypeManager.cpp:366-377), making
    // user-visible diagnostic text depend on heap addresses; an ambiguous ty var keeps the
    // un-instantiated entry instead.
    TypeSubst subst;
    for (auto& [tv, candidates] : mts) {
        if (candidates.size() == 1) {
            subst.emplace(tv, *candidates.begin());
        }
    }
    if (subst.empty()) {
        return caps;
    }
    for (auto& cap : caps) {
        // Per capability, never on the whole FuncTy: instantiation reduces against
        // GetAllGenericTys, which is typeArgs-only and therefore blind to capTys (MF3).
        auto inst = tyMgr.GetInstantiatedTy(cap, subst);
        if (Ty::IsTyCorrect(inst)) {
            cap = inst;
        }
    }
    return caps;
}
```
*Why:* one correct, deterministic, invalid-free source of an accessor's demanded list for all four consumers.
*Build detail:* uses `std::map`-based `TypeSubst`/`MultiTypeSubst` (`include/cangjie/Sema/CommonTypeAlias.h:82/87`) and `TypeManager::GetInstantiatedTy` (`TypeManager.h:116`). `TypeCheckUtil.cpp` includes only `<unordered_set>`, `<map>`, `<set>` (lines 13-19) â the code above deliberately uses a plain loop instead of `std::any_of` so **no new include is needed**. If you rewrite it with `<algorithm>` idioms, add the include explicitly. Confirm `cangjie/Sema/TypeManager.h` / `CommonTypeAlias.h` are reachable from `TypeCheckUtil.h`'s include set; if not, add `#include "cangjie/Sema/TypeManager.h"` to the `.cpp`.

---

### Group 2 â MF6: transfer the primary constructor's clause

**E2.1 â `.../src/Sema/Desugar/DesugarInTypeCheck.cpp`**
*Anchor:* `DesugarPrimaryCtor` (647-688). Insert between line 664 (`    }`, closing the `if (funcBody->retType)` block opened at 661) and line 665 (`    auto funcParamList = MakeOwned<FuncParamList>();`).
*Write:*
```cpp
    // Checked exceptions (experimental): the primary constructor's 'throws' clause belongs to the
    // synthesized 'init'. Every consumer reads the DESUGARED body -- GetFuncBodyCapTys (and thus
    // the ctor's FuncTy capTys, i.e. what construction sites demand), ChkThrowsClauseOfFuncBody
    // (clause validation) and CapabilityInferencer::IsEligible -- so without this the clause is
    // parsed and dropped. Cloned, not moved: the PrimaryCtorDecl keeps living in the AST (name
    // resolution, LSP/AST dump, incremental AST hashing all still read it), exactly as retType,
    // the parameters and the body statements are cloned above and below.
    funcBody->throwsClause = ASTCloner::Clone(fd.funcBody->throwsClause.get(), SetIsClonedSourceCode);
    if (fd.funcBody->throwsClause) {
        // Original user written source code should be ignored for LSP -- the same treatment
        // DesugarPrimaryCtorHandleParam gives the original params (:224-225).
        fd.funcBody->throwsClause->EnableAttr(Attribute::COMPILER_ADD);
    }
```
*Why:* the one required semantic edit for MF6. Placement is forced: `DesugarPrimaryCtorSetPrimaryFunc` moves `funcBody` into the new `FuncDecl`, so any write to `funcBody` must precede it.
*Notes:* no new includes â `ASTCloner::Clone` and `SetIsClonedSourceCode` are already used at line 660. **Do NOT** add `DisableAttr(Attribute::COMPILER_ADD)` on the clone (mirroring line 663): `CloneNode` sets both `IS_CLONED_SOURCE_CODE` and `COMPILER_ADD` (`Clone.cpp:1567-1568`) and `Node::ShouldDiagnose` (`src/AST/Node.cpp:424-433`) suppresses only COMPILER_ADD **without** IS_CLONED_SOURCE_CODE â the clone is already diagnosable at the user's source range, which is what Â§3.2 rule 5 needs. The second half (marking the *original*) is the challenger's Amendment 3; if you drop it, say so in the commit message and do **not** justify it with DiagnosticEngine dedup â that dedup keys on `(mainHint.range, severity)` with no message comparison (`include/cangjie/Basic/DiagnosticEngine.h:545-557`).

*No mirror change is needed in `src/Sema/IncrementalUtils.cpp:143`* â it is a second **caller** of the same function. `IncrementalCompilerInstance::PerformSema` (`src/FrontendTool/IncrementalCompilerInstance.cpp:285`, falling through to `return CompilerInstance::PerformSema();` at `:321`) still runs `PrepareTypeCheck`/`BuildSymbolTable` and `PreCheckUsage`/`ResolveNames` over the clone, so it is elaborated; re-entry is guarded by `hasDesugared` (`src/Sema/TypeChecker.cpp:1709-1711`).

---

### Group 3 â MF1: carry accessor clauses onto desugared callee types

All three edits are in `.../src/Sema/Desugar/AfterTypeCheck.cpp`. **Apply bottom-up (249 â 198 â 139)** so earlier line numbers stay valid.

**E3.1 â line 249, in `DesugarSetForPropDecl`**
*Anchor:* `    baseExpr->SetTy(tyMgr.GetFunctionTy({subExpr->GetTy()}, TypeManager::GetPrimitiveTy(TypeKind::TYPE_UNIT)));`
*Write:* replace with
```cpp
    Ptr<Ty> receiverTy = nullptr;
    if (subExpr->astKind == ASTKind::MEMBER_ACCESS) {
        if (auto recv = RawStaticCast<MemberAccess*>(subExpr)->baseExpr.get(); recv) {
            receiverTy = recv->GetTy();
        }
    }
    // 'setFunc' may be generic type, which need to be update to real used type.
    // Checked exceptions: the accessor's 'throws' clause must survive onto the callee type,
    // or the call site raises no demand (proposal 3.2/3.3).
    baseExpr->SetTy(tyMgr.GetFunctionTy({subExpr->GetTy()},
        TypeManager::GetPrimitiveTy(TypeKind::TYPE_UNIT), {},
        GetInstantiatedAccessorCapTys(tyMgr, *setFunc, receiverTy)));
```
*Why:* fixes `c.p = v` and the setter half of `c.p += x` / `c.p++`. The explicit null check replaces the plan's "known good by crash-first" argument (`ASTCloner::Clone` at :246 tolerates null; only `CreateMemberAccess` would fault).

**E3.2 â line 198, in `DesugarGetForPropDecl`**
*Anchor:* `    baseExpr->SetTy(tyMgr.GetFunctionTy({}, expr.GetTy()));`
*Write:* add `Ptr<Ty> receiverTy = nullptr;` immediately **before** the existing `OwnedPtr<Expr> baseExpr;` declaration at line 183, set it inside the existing `if (auto ma = DynamicCast<MemberAccess*>(&expr); ma)` branch (after the `if (!ma->baseExpr) { return; }` guard):
```cpp
        receiverTy = ma->baseExpr->GetTy();
```
then replace line 198 with
```cpp
    // 'getFunc' may be generic type, which need to be update to real used type.
    // Checked exceptions: see DesugarSetForPropDecl.
    baseExpr->SetTy(tyMgr.GetFunctionTy({}, expr.GetTy(), {},
        GetInstantiatedAccessorCapTys(tyMgr, *StaticCast<FuncDecl*>(getFunc), receiverTy)));
```
*Why:* fixes the plain-read path (`c.p`, `p`, `super.p`, `C.p`). `getFunc` is already guaranteed `FUNC_DECL` by the guard at 180-182 and is `StaticCast`-ed at 202.

**E3.3 â line 139, in `GetFuncArgsForDesugaredPropDecl`**
*Anchor:* `    leftBaseExpr->SetTy(tyMgr.GetFunctionTy({}, &propTy));`
*Write:*
```cpp
    // 'getFunc' may be generic type, which need to be update to real used type.
    // Checked exceptions: 'getFunc' may be a SUPERCLASS accessor found by FindValidPropAccessor
    // when the child overrides only 'set', which is why the mapping is receiver-based.
    leftBaseExpr->SetTy(tyMgr.GetFunctionTy({}, &propTy, {},
        GetInstantiatedAccessorCapTys(tyMgr, getFunc, mapExpr ? mapExpr->GetTy() : nullptr)));
```
*Why:* fixes the read half of the compound-assign / inc-dec path. **No signature change** â the parameter `mapExpr` (line 103) *is* the receiver expression (`basePtr`, set at :260 from the setter's `ma->baseExpr`, passed at :268), and `getFunc` is already `FuncDecl&`.

*Flag-off invariance:* with `--enable-chexc` off, `SeeingChexcClause` (`src/Parse/ParserImpl.h:200-203`) gates every clause parse, so `FuncBody::throwsClause` is always null, `GetInstantiatedAccessorCapTys` returns `{}`, and all three sites intern exactly the `FuncTy` they intern today.

*Deliberately NOT done:* the optional walker-threading edit (enclosing-nominal-ty fallback for the unqualified `p` form). It touches a walker shared with the Java/ObjC interop and effect-handler desugars, and its only symptom is a false reject printing an internal ty var name. Record as a residual (Group 7).

---

### Group 4 â MF2 Part A: header

All three edits in `.../include/cangjie/Sema/CapabilityCheck.h`.

**E4.1 â line 73 + its doc block (68-72)**
*Anchor:* `using InferredCapabilities = std::unordered_map<Ptr<const AST::Decl>, std::vector<Ptr<AST::Ty>>>;`
*Write:*
```cpp
/**
 * Capability lists inferred for declarations without an authoritative clause (proposal 6.3).
 * CompleteInferredCapabilityTypes writes each list into its declaration's functional type
 * (proposal 6.3.3), so the declaration's own type is the single source of its list. The map
 * remains the source at CALL SITES: a call's callee expression type was formed during type
 * check, before inference ran, and is never re-typed.
 */
using InferredCapabilities = std::unordered_map<Ptr<AST::FuncDecl>, std::vector<Ptr<AST::Ty>>>;
```
*Why:* only `FuncDecl`s are ever inferred (`CapabilityInferencer::order` is `std::vector<Ptr<FuncDecl>>`, `CapabilityCheck.cpp:834`); a non-const key lets the write-back be a loop over the map with zero re-traversal, so it cannot drift from what inference actually covered. All six existing uses still compile (`CapabilityCheck.cpp:68, 525, 570, 834, 854, 861`); `collectingFor` stays `Ptr<const Decl>` and is only compared.
*Fallback if the author objects to touching the alias:* keep `Ptr<const AST::Decl>` and `const_cast` inside the write-back.

**E4.2 â insert after line 83** (the closing `);` of the `InferCapabilities` declaration), before the `CheckCapabilities` doc comment at line 85:
```cpp
/**
 * Complete the clause components of the types of the declarations covered by @p inferred
 * (proposal 6.3.3: 'capability parameters -> clause components of types -> capability arguments';
 * notes/architecture.md:82-83 'write inferred lists into decl signatures, then run the checking
 * step uniformly'). Each declaration's functional type is re-interned through
 * TypeManager::GetFunctionTy with its inferred entries appended, so the declaration's own type
 * becomes the single source of its capability list. Expression types are deliberately NOT
 * completed: they were formed during type check, before inference ran, and re-typing them would
 * double-charge every call site (see HandleCall).
 */
void CompleteInferredCapabilityTypes(TypeManager& typeManager, const InferredCapabilities& inferred);
```

**E4.3 â the `CheckCapabilities` doc block (lines 85-91)**
*Anchor:* the sentence `The pass never mutates types; every unsatisfied demand is passed to @p missHandler.`
*Write:* replace with `Every unsatisfied demand is passed to @p missHandler; the checking walker itself mutates no type (declaration types were completed beforehand by CompleteInferredCapabilityTypes).`
*Why:* the statement becomes false at the stage level and must not mislead a reviewer into rejecting the write-back.

---

### Group 5 â MF2 Part A + merged MF1 fallback: `CapabilityCheck.cpp`

All in `.../src/Sema/CapabilityCheck/CapabilityCheck.cpp`. **Apply bottom-up (E5.7 â E5.1)** to keep line numbers stable, or anchor on text.

**E5.1 â file header comment, the "Demands"/purity paragraph (~lines 22-32)**
*Anchor:* `The pass never mutates types; unsatisfied demands go to a CapabilityMissHandler â the seam`
*Write:* replace that sentence with
```
 * The checking walker itself mutates no type; declaration types are completed beforehand by
 * CompleteInferredCapabilityTypes (proposal 6.3.3). Unsatisfied demands go to a
 * CapabilityMissHandler â the seam where capability-parameter inference (proposal 6.3)
 * collects residual demands.
```
*Why:* `notes/handoff-plan.md` Â§0.4 designates this header as the module's documented rule set, read first.

**E5.2 â line 171, in `CheckMembers`**
*Anchor:* `                ctorCapLists.emplace_back(TypeCheckUtil::GetFuncBodyCapTys(*fd->funcBody));`
*Write:* `                ctorCapLists.emplace_back(DeclaredCapTys(*fd->funcBody));`
*Why:* the every-constructor supply for instance field initializers (proposal 3.3) reads clauses only, so an **inferred** constructor list never supplies a field initializer. This is the one place Part A changes an observable verdict on its own â and MF6 makes it also pick up primary-ctor clauses.

**E5.3 â new private helper, insert immediately after `GetLiteralCapTys` (ends line 357)**
```cpp
    /// The capability list a callable body supplies: its declaration's COMPLETED type (proposal
    /// 6.3.3), falling back to the source clause when the type did not survive type check
    /// (PreCheck.cpp:1823-1824 sets FuncBody::ty only under IS_CHECK_VISITED).
    SupplyScope DeclaredCapTys(const FuncBody& fb) const
    {
        if (auto funcTy = DynamicCast<FuncTy*>(fb.GetTy()); funcTy && Ty::IsTyCorrect(funcTy)) {
            return funcTy->capTys;
        }
        return TypeCheckUtil::GetFuncBodyCapTys(fb);
    }
```
*Why:* collapses two sources into one at both consumers, and fails **loudly** if the write-back ever misses a decl kind (the body loses its own supply and immediately reports) rather than quietly, which is today's bug shape.

**E5.4 â the `FUNC_BODY` supply, lines 297-306**
*Anchor:* from `                auto caps = TypeCheckUtil::GetFuncBodyCapTys(fb);` (297) through the closing `}` of the `if (fb.funcDecl && fb.funcDecl != collectingFor)` block (306). Keep line 296 (`auto& fb = ...`) and line 307 (`supplies.emplace_back(std::move(caps));`).
*Write:*
```cpp
                // The declaration's COMPLETED type is the single source of its capability list
                // (proposal 6.3.3, written by CompleteInferredCapabilityTypes). Two exceptions,
                // both phase-independent by construction: while collecting a declaration's own
                // residual demands its in-flight list must not supply (proposal 6.3.2), so only
                // the written clause is read; and a lambda literal's FuncBody shares the
                // LambdaExpr's ty, already pushed by the LAMBDA_EXPR case.
                auto caps = (!fb.funcDecl || fb.funcDecl == collectingFor)
                    ? TypeCheckUtil::GetFuncBodyCapTys(fb)
                    : DeclaredCapTys(fb);
```
*Why:* removes the second source of truth. **Must land in the same commit as E5.6/E6.1** â without the write-back, every inferred declaration's body loses its own supply and the whole `inference/` group goes red.
*Verified safe:* nested local functions are never in `inferred` (`CollectEligible` walks `file->decls` and `GetMemberDecls()` only, never function bodies), so the `!fb.funcDecl`/`collectingFor` arms cover every case where the map used to differ from the completed type.

**E5.5 â `HandleCall`, lines 430-446 (MERGED MF1 fallback + MF2 union)**
*Anchor:* from `        for (auto cap : funcTy->capTys) {` (430) through the closing `}` of the `if (ce.resolvedFunction)` block (446). Leave `DemandConstructedCaptures(ce);` (447) untouched.
*Write:*
```cpp
        std::vector<Ptr<Ty>> demands = funcTy->capTys;
        // Defence in depth: a callee expression rebuilt by machinery that predates this feature
        // (property-accessor desugar and friends) can carry a capability-free functional type.
        // Recover from the callee's DECLARED CLAUSE -- never from its FuncTy::capTys, which
        // CompleteInferredCapabilityTypes also fills with the INFERRED entries that the union
        // below already contributes. Re-instantiated through the receiver so a generic accessor
        // demands 'MyExc<Int64>', not a bare 'MyExc<T>'.
        if (demands.empty() && ce.resolvedFunction) {
            Ptr<Ty> receiverTy = nullptr;
            if (auto ma = DynamicCast<MemberAccess*>(ce.baseFunc.get()); ma && ma->baseExpr) {
                receiverTy = ma->baseExpr->GetTy();
            }
            demands = TypeCheckUtil::GetInstantiatedAccessorCapTys(
                typeManager, *ce.resolvedFunction, receiverTy);
        }
        // A callee whose list was INFERRED (proposal 6.3) carries it beside the AST: this call
        // site's type was formed during type check, before inference ran, so completing the
        // declaration's type cannot reach it. UNIONED, not appended: MF4 will instantiate these
        // entries, after which they can become pointer-identical to 'funcTy->capTys'.
        if (ce.resolvedFunction) {
            auto it = inferred.find(ce.resolvedFunction);
            if (it != inferred.end()) {
                for (auto cap : it->second) {
                    if (!Utils::In(cap, demands)) {
                        demands.emplace_back(cap);
                    }
                }
            }
        }
        for (auto cap : demands) {
            if (Ty::IsTyCorrect(cap)) {
                Demand(cap, ce, DescribeCallee(ce));
            }
        }
```
*Why:* one block serves both findings. **The MF1 plan's `inferred.find(...) == inferred.end()` guard is deleted** â it was both unnecessary (the fallback reads the *clause*, which MF2 never writes) and actively harmful: `inferred[decl]` at line 800 uses `operator[]`, which default-constructs an entry for **every** eligible declaration even when its residual is empty, so that guard would have disabled the fallback across the entire private/internal surface (verified: `MergeInto(inferred[decl], residual)`). The `declTy && !declTy->capTys.empty()` gate is also deleted as MF2-fragile and redundant.
*Build detail:* `Utils::In` (`include/cangjie/Utils/Utils.h:185`) is reachable â `CapabilityCheck.cpp:50` includes `cangjie/Sema/TypeManager.h`, which includes `cangjie/Utils/Utils.h` at line 23. No new include.

**E5.6 â `WithCapTys` helper, insert in the anonymous namespace after `CollectingMissHandler` (ends line 547), before the `CapabilityInferencer` doc comment at 549**
```cpp
/// Re-interns @p ty with the entries of @p extra appended to its capability list. Returns @p ty
/// unchanged when nothing is added. Entries that failed elaboration or still carry a solver
/// placeholder are DROPPED: FuncTy marks itself invalid when any capability ty is incorrect
/// (AST/Types.h:731-732) and an invalid funcBody ty silently suppresses body export
/// (ASTWriter.cpp:1359); and a pooled placeholder ty var (MF3) would be interned PERMANENTLY into
/// a declaration's type identity, where a later reuse of that pooled ty var silently aliases.
Ptr<Ty> WithCapTys(TypeManager& typeManager, Ptr<Ty> ty, const std::vector<Ptr<Ty>>& extra)
{
    auto funcTy = DynamicCast<FuncTy*>(ty);
    if (!funcTy || !Ty::IsTyCorrect(funcTy)) {
        return ty;
    }
    auto caps = funcTy->capTys;
    for (auto cap : extra) {
        // Duplicates are not cosmetic: FuncTy::operator== compares the capTys VECTOR, so a
        // duplicated entry would intern a distinct type.
        if (Ty::IsTyCorrect(cap) && !cap->HasPlaceholder() && !Utils::In(cap, caps)) {
            caps.emplace_back(cap);
        }
    }
    if (caps.size() == funcTy->capTys.size()) {
        return ty;
    }
    return typeManager.GetFunctionTy(funcTy->paramTys, funcTy->retTy,
        {funcTy->isC, funcTy->isClosureTy, funcTy->hasVariableLenArg, funcTy->noCast}, caps);
}
```
*Why:* uses the existing defaulted 4th parameter of `GetFunctionTy` (`TypeManager.h:76-77`) â signature untouched, per the invariant. Copies **all four** `Config` fields including `noCast`; several existing call sites drop it, which is tolerable for freshly synthesised types but would silently change a declaration's type identity here (`TranslateCallExpr.cpp:592-593` reads `isC`/`hasVariableLenArg` straight off `resolvedFunction->GetTy()`). `isC` is read as the member, not `IsCFunc()`, so a CFunc decl re-interns identically. The `HasPlaceholder` filter (`include/cangjie/AST/Types.h:295`) is the MF3 interlock and is **not optional**.

**E5.7 â `CompleteInferredCapabilityTypes`, insert in `namespace Cangjie::Sema` between `InferCapabilities` (ends 858) and `CheckCapabilities` (starts 860)**
```cpp
void CompleteInferredCapabilityTypes(TypeManager& typeManager, const InferredCapabilities& inferred)
{
    // Proposal 6.3.2: an inferred list is attached to the declaration 'as if the user had written
    // it as an explicit throws clause'; 6.3.3 places this completion between parameter inference
    // and argument checking. Both holders of a declaration's functional type are re-pointed: the
    // decl and its funcBody (set together at TypeChecker.cpp:338-341/354-357/548-549 and
    // PreCheck.cpp:1810/1822-1824). No expression node is touched.
    //
    // Deterministic order matters: re-interning ALLOCATES Ty objects, and Ty pointer identity is
    // load-bearing downstream (GetIntersectionTy/GetUnionTy key on pointer-ordered std::set).
    // Iterating the unordered_map directly would make allocation order depend on heap layout.
    std::vector<Ptr<FuncDecl>> ordered;
    ordered.reserve(inferred.size());
    for (auto& [fd, caps] : inferred) {
        if (fd && !caps.empty()) {
            ordered.emplace_back(fd);
        }
    }
    std::sort(ordered.begin(), ordered.end(), [](Ptr<FuncDecl> a, Ptr<FuncDecl> b) {
        if (a->begin.fileID != b->begin.fileID) { return a->begin.fileID < b->begin.fileID; }
        if (a->begin.line != b->begin.line) { return a->begin.line < b->begin.line; }
        if (a->begin.column != b->begin.column) { return a->begin.column < b->begin.column; }
        return a->identifier.Val() < b->identifier.Val();
    });
    for (auto fd : ordered) {
        auto& caps = inferred.at(fd);
        fd->SetTy(WithCapTys(typeManager, fd->GetTy(), caps));
        if (fd->funcBody) {
            fd->funcBody->SetTy(WithCapTys(typeManager, fd->funcBody->GetTy(), caps));
        }
    }
}
```
*Why:* the missing Â§6.3.3 phase. The holder set is complete and was established by reading every writer of a declaration's `FuncTy`: nothing else holds it â `PropDecl` derives from `VarDecl` so its own ty is the property's value type and its accessors appear in the map in their own right; `FuncBody::retType` carries only `retTy`; `paramLists[0]->ty` is a `TupleTy`; `MacroDecl`/`MainDecl` are not `FuncDecl` and are never collected; `FuncParam::desugarDecl` default-value functions are never in the map; instantiated clones do not exist yet (GENERIC_INSTANTIATION is two stages later) and `PartialInstantiation` carries capTys through `TyInstantiator`; `Symbol` caches no ty.
*Build detail:* `<algorithm>` is already included (line 36).

---

### Group 6 â driver

**E6.1 â `.../src/Frontend/CompilerInstance.cpp`**
*Anchor:* insert a statement between line 731 (`        auto inferred = Sema::InferCapabilities(*typeManager, *importManager, *srcPkg, diag);`) and line 732 (`        Sema::CheckCapabilities(...)`).
*Write:*
```cpp
        // Proposal 6.3.3: the clause components of types are completed between capability-parameter
        // inference and capability-argument checking. Doing it here -- after inference has reached
        // its fixpoint, before any checking -- keeps the checking walker a pure check while making
        // each declaration's own type the single source of its capability list. Keep these three
        // calls adjacent: CheckCapabilities' FUNC_BODY supply now reads the COMPLETED type.
        Sema::CompleteInferredCapabilityTypes(*typeManager, inferred);
```
*Why:* named phase in the driver, where `notes/architecture.md` documents the stage order. Inside the per-package loop (the map is per-package). The whole stage short-circuits when the flag is off (`:718-720`), which confines every risk in this batch to `--enable-chexc` builds.

---

### Group 7 â ledger (`/home/penguin/Projs/effects-research/cangjie/notes/proposal-implementation-gaps.md`)

**E7.1 â line 42, row C4.** Currently: "`...` marker parse-rejected EVERYWHERE". **This is stale and must be corrected in this commit**, or a reviewer will reject E0.1 as unreachable dead code. `ParseThrowsClause`'s `diagnoseEllipsis` lambda (`src/Parse/ParseType.cpp:282-292`) sets `clause->hasEllipsis = true` whenever `isDeclClause`, and `ParseFuncBody` always passes `true` (`ParseDecl.cpp:2330`, `:2338`). Rewrite as: "`...` accepted on declarations (Â§6.3.5), rejected in functional types (Â§3.4) â as intended; **CLOSED**."

**E7.2 â rows MF6 (line 75) and MF1 (line 74):** mark FIXED. **Row MF2 (line 76):** keep OPEN with the note "write-back landed (Part A); the non-call demand rule (function values, joins, returns) remains â see Unresolved #2."

**E7.3 â add three new rows to section C:**
- **C12** â an inferred list is charged only at *call* sites; forming a function value from an inferred declaration (`let h = helper`, `apply(helper)`) still loses it. Workaround: write an explicit `throws` clause on the declaration. *(Note explicitly: annotating the **binding** does NOT help â `ChkRefExpr` records the candidate declaration's own type at `src/Sema/TypeCheckExpr/NameReferenceExpr.cpp:363`, not the target type.)*
- **C13** â a constructor's inferred list is never *grown* by an instance-field initializer's demands: inference walks `caller->funcBody` only (`BuildCallGraph`, `:642-664`), never field initializers. Sound (may under-supply), asymmetric with E5.2.
- **C14** â an *unqualified* reference (`p`, not `this.p`) to a property inherited from a generic parent with renamed type parameters demands the parent's raw type parameter, producing `Cannot find a capability for 'Class-MyExc<Generics-T-1>'`. False reject, never an escape; fix is the walker-threading edit deliberately deferred from Group 3.

**E7.4 â add a new row for the MF1ÃMF9 interlock** (see Unresolved #1): "an interface-property contract is always `throws ()` (an abstract property cannot carry a clause â `ParsePropMemberDecl` requires an accessor body, `ParseDecl.cpp:418-420`; `AddSetterGetterInProp` synthesizes clause-less accessors), and `CheckPropertyInheritance` never compares accessor lists, so a throwing accessor implementing an interface property is invisible at every `i.p` site."

---

## 2. Interactions

| # | Where | Findings | Resolution in this guide |
|---|---|---|---|
| **I1** | `CapabilityCheck.cpp:430-446` (`HandleCall`) | **MF1** wanted a declared-clause fallback loop; **MF2** wanted the two demand sources unioned and deduped | **Merged into the single edit E5.5.** Applying both plans literally would have produced two competing rewrites of the same 17 lines. Order inside the block matters: fallback first (only when `funcTy->capTys` is empty), then union the map. |
| **I2** | MF1's fallback source vs MF2's write-back | MF1's helper reads `GetFuncBodyCapTys` (the *clause*); MF2 writes inferred entries into `FuncTy::capTys` | **Structurally double-demand-proof.** Because the fallback never reads `fd->GetTy()->capTys`, a clause-less inferred decl yields `{}` from the fallback and is charged exactly once by the map union. The comment in E5.5 records this so a future "simplification" to read the type doesn't reintroduce the double. |
| **I3** | `CapabilityCheck.cpp:171` (`ctorCapLists`) | **MF2** E5.2 switches it to `DeclaredCapTys`; **MF6** makes the primary-derived `init` carry a clause | **Synergy, not conflict** â one edit, two payoffs. Watch the widening: `class A(let x: Int64) throws E { let y = mayThrowE() }` starts compiling (correct per Â§3.3, but new). |
| **I4** | MF1's desugar edits vs MF2's `HasGeneric` risk | Both flip `FuncTy::generic` / `FuncTy::invalid`, which `AST/Types.h:731-733` computes from `capTys` | Same mechanism, two entry points. Test both (tests 3 and 11 below). The invalid-flip is closed by construction: E1.2's filter and E5.6's filter both drop incorrect entries. |
| **I5** | MF6's `hasEllipsis` fix vs MF2's inference | `E0.1` makes `throws E, ...` primary ctors and cloned decls **inference-eligible**, feeding MF2's map and thence the write-back | Deliberate. It is why the ellipsis test (test 8) must exist and why E0.1 is labelled a behaviour change. |
| **I6** | MF1 desugar output vs `CapabilityCheck`'s walker | `Walker::Walk` visits `expr->desugarExpr` *and* the node's own children (`src/AST/Walker.cpp:58-62`); `VisitPre` skips neither `UNREACHABLE` nodes nor nodes carrying a `desugarExpr` | Pre-existing double-walk, now newly visible for **property reads on the RHS of a property assignment** (`GetFuncArgsForDesugaredPropDecl` clones `ae.rightExpr` at `AfterTypeCheck.cpp:110`). Write every new test with `// ASSERT: scan`, **never** with exact error counts. Real fix (skip `leftValue`/`rightExpr` when `desugarExpr` is set, or honour `Attribute::UNREACHABLE` in `VisitPre`) is a follow-up, not this batch. |
| **I7** | This batch vs **MF4** | MF4 rewrites the exact `HandleCall` block E5.5 owns, and will instantiate the map entries | E5.5 is written so MF4 has exactly one insertion point (`GetInstantiatedTy(cap, mapping)` inside the union loop) and the `Utils::In` pointer test is already the correct comparison once entries become pointer-identical. |
| **I8** | This batch vs **MF3** | MF3 leaks recycled placeholder `GenericsTy`s (returned to `TypeManager::tyVarPool`) into demands; today they die with the transient side map | Part A would **intern them permanently** into declaration identity and carry them into GENERIC_INSTANTIATION / MANGLING / SAVE_CJO. Closed by E5.6's `HasPlaceholder()` filter. If the author prefers, sequence MF3 before MF2-A instead â but do not ship Part A without one of the two. |
| **I9** | This batch vs **MF9** | Closing MF1 converts a uniform hole into a targeted, trivially exploitable one for interface-mediated property access | Unresolved #1. |
| **I10** | Already-landed batch 1 (MF5/MF7/MF10, commit `858edc68`) | They occupy `CapabilityCheck.cpp` lines 171-470 alongside E5.2-E5.5 | Already merged in the anchors above â all line numbers here are post-`858edc68`. Re-verify by text if anything else lands first. |

---

## 3. Regression risks

Gate (per `notes/handoff-plan.md` Â§0.3 rule 4): `fmt --check` clean; **one** compiler build; `ctest` 49/49; all `CheckedExceptions` groups at expected state; `./cj.py test llt --filter compiler/Parser compiler/Sema -j 8` = 3934/3934 (baseline `517ddc3c`).

| Risk | Mechanism | What catches it |
|---|---|---|
| **Base LLT moves at all** | Should be impossible: the whole stage returns early when the flag is off (`CompilerInstance.cpp:718-720`), and `SeeingChexcClause` (`ParserImpl.h:200-203`) makes every clause unparseable, so `GetFuncBodyCapTys` is `{}` and all four `GetFunctionTy` sites intern today's type. | **Mandatory flag-off invariance run:** full LLT **without** `--enable-chexc`. Any diff means a helper is reading something other than the `throwsClause`. |
| **Invalid `FuncTy` at a desugar site** (new error-recovery state) | `ExpandCapabilityList` emplaces `InvalidTy` for entries that failed elaboration; feeding one to `GetFunctionTy` flips `baseExpr->GetTy()` invalid, and `DesugarForPropDecl` runs mid-`PostTypeCheck` (`TypeChecker.cpp:2149`) so `CheckConstEvaluation` (:2150), `MarkImplicitUsedFunctions` (:2151), `PluginCheck` (:2157) and cjd/LSP then walk it. Closed by E1.2's filter. | **New test 5** (`prop_accessor_undefined_exc_neg.cj`). |
| **New errors at construction sites** | MF6 gives the primary-derived `init` a non-empty `capTys`, so `HandleCall` charges every `A(...)`, delegating `this(...)` and `super(...)`. | Whole `CheckedExceptions/` suite. **In-tree exposure is nil** â no existing test declares a clause-bearing primary ctor (`captures/captures_primary_ctor_neg.cj:12` has none and must stay red for its own reason: `ChkCapturesClauseOfDecl`, `TypeChecker.cpp:250-257`, scans `GetMemberDecls()` for `PRIMARY_CTOR_DECL`, and the desugar only *appends*). |
| **New errors at property use sites** | MF1 is the intended fix; every `c.p` on a throwing accessor outside a matching handler now errors. | `scopes/`, `types/` groups; new tests 1-4. |
| **`FuncTy::generic` flips** | `AST/Types.h:733` computes `generic` from `capTys`. A member of a generic class whose list mentions `T` goes non-generic â generic, consulted at `GenericInstantiationManagerImpl.cpp:119/125/134` (`ClearInstTysIsNeeded`) and `:1190` (`RearrangeCallExprReference`). | **New test 11**, which must **compile AND run** with two instantiations. Mitigating fact to cite in review: an *explicit* `throws GenExc<T>` already produces exactly that `FuncTy` from PreCheck onward, and `ClearInstTysIsNeeded` (`:114-140`) keys on `ce->desugarExpr->GetTy()` and `ma->target->GetTy()` â the accessor DECL ty, which already carries capTys today. `PartialInstantiation.cpp:1804-1816` (`Generalize`) handles capTys correctly. |
| **`IsCapTysSubsumed` in override matching after the write-back** | The one cap-sensitive comparison that runs *after* CAPABILITY_CHECK: `OverrideFunctionResolver` (`:227/229/262`) â `TypeManager::IsFuncTySubType` (`TypeManager.cpp:2033-2038`) â `IsCapTysSubsumed` (`:904-910`), called from GENERIC_INSTANTIATION. A member that gained an inferred list matched against a cap-free base member fails. Narrow (`IsEligible` excludes public/protected and interface members, and overrides must be public/protected), so only `static redef` reaches it. | **New test 12.** |
| **Nondeterministic output** | `GetBestInstantiatedTy` returns `*instTys.begin()` from a pointer-ordered `std::set`; the write-back allocates interned `Ty`s while iterating an `unordered_map`. Both closed (E1.2 single-valued collapse, E5.7 sort). | Build twice, diff diagnostics byte-for-byte on the new generic tests (3, 11). |
| **Mangling / CHIR / cjo drift** | `grep capTys src/Mangle src/CHIR src/CodeGen` is **empty**; `BaseMangler::MangleFuncType` (`:1087-1103`) mangles only `retTy`+`paramTys`; `CHIRType::TranslateFuncType` reads `retTy`/`paramTys`/`hasVariableLenArg`/`IsCFunc()`; `ASTWriter::SaveFuncTy` (`:1104-1122`) drops capTys. Structurally invisible. | Cheap detector worth running once: build the stdlib (chexc off) and diff mangled symbol names against a pre-change build. Note `ASTWriter.cpp:1359` gates body export on `Ty::IsTyCorrect(funcBody.GetTy())` â E5.6's filter is what keeps that safe. |
| **Duplicate diagnostics** | Two sources. (a) The pre-existing double walk (I6). (b) A live shape *today*: an eligible decl with `throws A, ...` whose `spawn` body throws `A` â `HandleSpawn` (`:404-419`) swaps out the whole supply stack and `MergeInto` (`:807-818`) compares the residual only against the **inferred** list, never the written clause, so `A` lands in both `funcTy->capTys` and the map. E5.5's union dedups this. | `// ASSERT: scan` only, never counts. Add the spawn+ellipsis probe (test 13). Note for the record: `MergeInto` **does** dedup by `IsSubtype`, so duplicates never propagate into outer inferred lists â only diagnostics duplicate. |
| **Discriminating existing tests** | `inference/infer_basic.cj`, `infer_recursion.cj` (pong must still infer `{B}` only), `infer_explicit_dots.cj`, `infer_lambda_boundary.cj`, `infer_public_neg.cj`, `types/subtype_neg.cj` (identical `mismatched types` message, no second diagnostic), `captures/captures_primary_ctor_neg.cj` (must stay red). |

**Deliberately out of scope (do not widen):** C1/C2 (cjo + incremental drop capTys â MF6 and MF2-A are intra-package, full-build only); C9 (`CjdCompilerInstance::PerformCapabilityCheck` is a no-op override, `include/cangjie/FrontendTool/CjdCompilerInstance.h:32-35`, so the write-back never runs in the cjd pipeline â record against TASK 7); the constructor-call hole where `HandleCall` returns early at `:426-429` on a non-`FuncTy` `baseFunc`, skipping `DemandConstructedCaptures` too (separate probe).

---

## 4. Tests to add

All under `/home/penguin/Projs/effects-research/cangjie/cangjie_test/testsuites/LLT/compiler/CheckedExceptions/`. Negative files use the `EXEC-PIPE-1` + `ASSERT: scan` form of `inference/infer_public_neg.cj`. **Start every `ASSERT` at bare `scan error`, run the compiler, then tighten to observed wording â do not guess diagnostic text, and never assert counts.**

### MF1

**1. `scopes/prop_accessor_demand_neg.cj`** â pins MF1 across all four dispatch kinds of `DesugarForPropDecl` and both accessors. `public` accessors so Â§6.3 inference cannot mask the result (`DeclAttributeChecker.cpp:137-138` does `fd->CloneAttrs(*fd->propDecl)`; `IsEligible` rejects PUBLIC at `CapabilityCheck.cpp:589`).
```cangjie
// Checked exceptions (Â§3.2/Â§3.3): a property accessor's 'throws' clause is demanded at every
// use site â read, write, compound assign and inc/dec, qualified and unqualified.

// EXEC-PIPE-1: %compiler %cmp_opt --experimental --enable-checked-exceptions %n.cj -o %output 2>&1 | compare %f
// ASSERT: scan Cannot find a capability for 'Class-GException'
// ASSERT: scan Cannot find a capability for 'Class-SException'

class GException <: Exception {}
class SException <: Exception {}

public class C {
    public mut prop p: Int64 {
        get() throws GException { throw GException() }
        set(x) throws SException { throw SException() }
    }
    func selfRead(): Int64 { p }        // unqualified RefExpr get -> GException
    func selfWrite(): Unit { p = 1 }    // unqualified RefExpr set -> SException
}

public func read(c: C): Int64 { c.p }       // MEMBER_ACCESS get  -> GException
public func write(c: C): Unit { c.p = 1 }   // ASSIGN_EXPR        -> SException
public func bump(c: C): Unit { c.p++ }      // INC_OR_DEC_EXPR    -> both (:139 + :249)
public func plus(c: C): Unit { c.p += 1 }   // compound ASSIGN    -> both (:139 + :249)

main() { return 0 }
```
Before the fix this compiles clean â that *is* the bug.

**2. `scopes/prop_accessor_demand.cj`** â positive twin: same accesses inside `try { ... } catch (e: GException) {} catch (e: SException) {}`, plus a caller propagating via its own `throws GException, SException`. `// EXEC:` + `// EXEC: %run %output`. Guards against over-demanding.

**3a. `types/prop_accessor_generic.cj`** (positive, `%run`) / **3b. `types/prop_accessor_generic_neg.cj`** â pin the instantiation half (E1.2): the demand must be `MyExc<Int64>`, not `MyExc<T>`. The `D <: P<Int64>` shape specifically exercises `GenerateGenericMapping` walking `inheritedTypes`, which owner-based `GenerateTypeMappingByTy(outerDecl->GetTy(), receiverTy)` would **not** have handled.
```cangjie
class MyExc<T> <: Exception {}
open class P<T> {
    public open prop q: Int64 { get() throws MyExc<T> { throw MyExc<T>() } }
}
class D <: P<Int64> {}
public func ok(d: D): Int64 { try { d.q } catch (e: MyExc<Int64>) { 0 } }    // positive file
public func bad(d: D): Int64 { try { d.q } catch (e: MyExc<String>) { 0 } }  // neg file
```

**4. `types/prop_accessor_inherited_setter.cj`** â exercises `FindValidPropAccessor`. **Assert the SET path, not the read path:** `AddMemberIfValidForLookup` (`src/Sema/LookUpImpl.cpp:141-155`) skips getter-less `PropDecl`s on read lookup, so "read through the child" is redirected by name resolution and never reaches `FindValidPropAccessor`. The path that genuinely needs it is `class C <: P { override mut prop p { set(x){...} } }` with `c.p += 1`: `propDecl` resolves to C's prop (setter lookup passes) and `GetUsableGetterForProperty` (`TypeCheckUtil.cpp:617-623`) walks up to P for the getter â exactly site `:139`, where `mapExpr` is the receiver. Must demand parent-get + child-set.

**5. `scopes/prop_accessor_undefined_exc_neg.cj`** â error recovery for E1.2's filter: `get() throws NoSuchExc { ... }`. Must report the undefined type and **not crash** through the rest of `PostTypeCheck`.

### MF6

**6. `parse/decl_primary_ctor.cj`** (positive, `%run`) â the Â§3.2 example shape; a struct primary ctor (same `DesugarPrimaryCtor` path); `throws ()` on a primary ctor; and an instance-field initializer discharged by the primary ctor's clause (E5.2's `ctorCapLists`).
```cangjie
// Checked exceptions (Â§3.2 rule 1): a primary constructor may carry a 'throws' clause.

// EXEC: %compiler %cmp_opt --experimental --enable-checked-exceptions %n.cj -o %output
// EXEC: %run %output

class CreationException <: Exception {}
class FieldException <: Exception {}
func mayThrowField(): Int64 throws FieldException { return 7 }

public class A {
    public A(let x: Int64) throws CreationException {
        if (x < 0) { throw CreationException() }
    }
}
public class B {
    let y: Int64 = mayThrowField()          // Â§3.3: every ctor's clause supplies it
    public B(let z: Int64) throws FieldException {}
}
public struct S {
    public S(let s: Int64) throws CreationException {
        if (s == 0) { throw CreationException() }
    }
}
public class E {
    public E(let e: Int64) throws () {}
}

main() {
    try { let a = A(1); let s = S(2); println(a.x + s.s) } catch (ex: CreationException) {}
    try { let b = B(3); println(b.y + b.z) } catch (ex: FieldException) {}
    let e = E(4)
    println(e.e)
    return 0
}
```
Baseline: today this **fails** â `throw CreationException()` in A's body reports "cannot find a capability". After the fix it must compile and run.

**7. `parse/decl_primary_ctor_neg.cj`** â the soundness half. (a) An **internal** primary ctor with authoritative `throws ()` whose body throws must error (verified: `SetDeclInternal`, `src/Sema/DeclAttributeChecker.cpp:152-159`, applies â the `EnableAttr(PUBLIC)` at `:206` is the enum-constructor path). (b) A construction site with no matching handler must error. `main` is never inference-eligible (`CollectEligible` skips `ASTKind::MAIN_DECL`). Both compile silently today.

**8. `parse/decl_primary_ctor_ellipsis_neg.cj`** â **the only committed test for E0.1**; do not skip it as a "manual check". Non-generic, per the MF3 warning.
```cangjie
// EXEC-PIPE-1: %compiler %cmp_opt --experimental --enable-checked-exceptions %n.cj -o %output 2>&1 | compare %f
// ASSERT: scan error

class CException <: Exception {}
class DException <: Exception {}
func sink(): Unit throws DException { throw DException() }
class C {                                   // internal -> inference-eligible
    C(let x: Int64) throws CException, ... { // '...' keeps inference ON
        throw CException()
        sink()
    }
}
main() { let c = C(1); println(c.x); return 0 }
```
Without E0.1 the `...` is swallowed, `IsEligible` returns false, `DException` is never inferred, and the site is charged only `CException`. Tighten the ASSERT to name `DException` once observed.

### MF2 Part A

**9. `inference/infer_ctor_field_supply.cj`** (positive, `%run`) â the one verdict Part A changes on its own (E5.2):
```cangjie
class AException <: Exception {}
func risky(): Int64 { throw AException() }   // inferred: throws AException
class C {
    let f: Int64 = risky()                   // accepted: EVERY ctor's INFERRED list covers it
    init() { }
    init(x: Int64) { }
}
main() { try { C() } catch (e: AException) {}; return 0 }
```
**10. `inference/infer_ctor_field_supply_neg.cj`** â same, with one ctor pinned `throws ()`; the field initializer must be rejected.

**11. `inference/infer_generic_writeback.cj`** â the `HasGeneric` flip; must **compile and run**:
```cangjie
class GenExc<T> <: Exception {}
class Holder<T> {
    func raise(): Unit { throw GenExc<T>() }     // inferred: [GenExc<T>] -> FuncTy becomes generic
    public func run(): Unit { try { raise() } catch (e: GenExc<T>) {} }
}
main() { Holder<Int64>().run(); Holder<String>().run(); return 0 }
```
Two instantiations force `PartialInstantiation` + `ClearInstTysIsNeeded` + `RearrangeCallExprReference` over a `FuncTy` whose `generic` flag the write-back flipped. A crash or wrong dispatch here is the instantiation risk, not a diagnostic.

**12. `inference/infer_redef_static.cj`** â a static `redef` inside a generic class (so instantiation actually runs `OverrideFunctionResolver`) where the child gained an inferred list and the base is cap-free. Must compile and run.

**13. `inference/infer_spawn_dots_neg.cj`** (probe, may reveal a pre-existing duplicate) â an eligible decl with `throws A, ...` whose `spawn` body throws `A`, called from `main`. Confirms E5.5's union dedups the `funcTy->capTys` â© map overlap. `// ASSERT: scan`, no counts.

### Manual one-off probes (not committed)

- **Multi-line clause.** Â§3.2 writes `A(let x: Int)` / newline / `throws CreationException {`. `SeeingChexcClause` does not itself skip newlines. Compile one throwaway; if it does not parse, file it as a separate soft-keyword/NL finding adjacent to MF11 â **not** part of MF6 â and keep the MF6 tests single-line.
- **Determinism.** Build the new generic tests twice, diff diagnostics byte-for-byte.
- **Debug assertions.** One `CJC_ASSERT`-heavy debug run: the synthesized primary-ctor clause is a new subtree the CapabilityCheck walker traverses (`Walker.cpp:193` descends into `FuncBody::throwsClause`); its `Type` nodes hit `VisitPre`'s `default:`. Low priority â the same subtree is already walked for every explicit `init() throws E`.

---

## 5. Unresolved

**U1 â MF9 interlock. This is the only true blocker, and it is an author call about landing granularity.**
Closing MF1 without MF9 converts a *uniform* silent hole into a *targeted, trivially exploitable* one: declare the throwing accessor in a class, call it through the interface. Verified mechanism: an abstract property can never carry a clause (`ParsePropMemberDecl` requires an accessor body â `DiagMissingBody`, `src/Parse/ParseDecl.cpp:418`; `AddSetterGetterInProp`, `src/Sema/TypeChecker.cpp:415-467`, synthesizes clause-less accessors), so an interface-property contract is *always* `throws ()`; and `CheckPropertyInheritance` (`src/Sema/InheritanceChecker/StructInheritanceChecker.cpp:1304-1332`) compares only `parent.ty != child.GetTy()`, `isVar`-ness, both-accessor implementation and visibility â `CheckThrowsClauseCompatible` (`:1356-1377`) is reached only from the func-override path at `:1413`.
**Recommendation: land this batch as specified, and make MF9 the very next batch** â do **not** improvise an MF9 edit into this build. No adversarially-verified MF9 plan exists yet, the batch is already 18 edits across 9 files, and an unverified `CheckPropertyInheritance` change would blur attribution on a very slow build. Mitigate by landing E7.4 (the ledger row) in the same commit so the targeted hole is on the record from the moment it opens. *If the author insists on one commit*, the minimal guard is: in `CheckPropertyInheritance`, after the type comparison at `:1312`, pair `parentProp->getters/setters` with `childProp->getters/setters` and require `IsCapTysSubsumed(child, parent)` on each pair â approximately 15 lines, anchor `StructInheritanceChecker.cpp:1315`.

**U2 â MF2 Part B is excluded. Confirm.**
Part B (demand at function-value formation) is out because its central premise is false in the code: `ChkRefExpr` does `refNode.SetTy(fdTy)` at `src/Sema/TypeCheckExpr/NameReferenceExpr.cpp:363` with the **candidate declaration's own** type, never the target/annotated type. Consequences: for an inferred declaration the reference's `carried` list is *always* empty, so `let h: () throws A -> Unit = helper` and `apply(helper)` would both be charged at the reference inside `main`'s empty scope; its documented workaround (annotate the binding) does not work; it does not close consequence (d) as claimed (the write-back has not run during `SolveComponent`, so `HandleFunctionValue` would contribute nothing during collect mode); and its edit calls `InstantiateCapTys(...)`, which does not exist in the tree.
**Recommendation: hold Part B until (a) the author rules on the semantics and (b) MF4 lands and supplies the instantiation helper.** Put the ruling request in the *corrected* terms: *"any non-call reference to an inferred declaration requires its whole inferred list at the reference site, with no annotation escape hatch â the only suppression is writing an explicit `throws` clause on the declaration. Accept, or leave MF2 open until a mechanism exists to re-check coercions?"* Keep the MF2 ledger row OPEN (E7.2) and record C12 (E7.3).

**U3 â MF3 sequencing.**
E5.6's `HasPlaceholder()` filter is what keeps a recycled placeholder ty var from being interned permanently into a declaration's type identity and carried into GENERIC_INSTANTIATION / MANGLING / SAVE_CJO. **Recommendation: keep the filter and land now.** Only if the author prefers a single mechanism should MF2-A wait for MF3; do not do neither.

**U4 â abstract-property grammar gap (Â§3.2 rule 1 lists "properties" among clause-bearing declarations).**
A throwing property can never be part of an interface contract today. Is this a grammar gap the proposal must close (`prop p: Int64 { get() throws E; set(x) throws F }` for abstract props), or an accepted restriction? **This decision changes what MF9 should diagnose.** **Recommendation:** record it as an accepted restriction in gaps section C for now and revisit with MF9; the proposal's Â§3.8 wording ("a method *or property accessor*") argues for eventually closing it.

**U5 â should the `inferred` map remain a `CheckCapabilities` parameter at all?**
After Part A, `fd->GetTy()->capTys` is a strict superset of the map, and the map is required only because *reference expression* types are stale. Once MF4 lands as "read the completed decl type and instantiate it" (rather than "instantiate the map entries"), `InferredCapabilities` could become purely inference-internal and drop out of `CheckCapabilities`'s signature entirely â removing the double-demand hazard structurally instead of by union. **Recommendation: decide this when MF4 is planned, not now**; E5.5 is written so either choice is a local edit.

**U6 â incremental probe (cheap, before Task 4/C).**
Does `InferCapabilities` see decls restored from the incremental cache for an unchanged part of the same package? If not, inferred lists silently vanish on incremental rebuilds and the write-back inherits the hole. Also note C2 stands: an unchanged ctor keeps its cached cap-free `FuncTy` (`if (Ty::IsTyCorrect(fd->GetTy())) continue;`, `src/Sema/PreCheck.cpp:1798-1799`) while a recompiled one gets capTys, so demand can differ between full and incremental builds for the same source. **Recommendation:** compile twice with `--incremental-compile` and diff the diagnostics; file separately, do not widen this batch.

**U7 â two risks I would downgrade before spending gate time on them.**
"Ctor-as-value subtyping" (`let f: (Int64) -> A = A`) â I found no evidence Cangjie admits a type name as a constructor function value; verify before writing a test, and if it is not expressible the risk is void. "Unqualified-reference false reject" (C14) â real but narrow, and the deferred walker edit is more blast radius than MF1's three desugar edits combined."
  },
  "workflowProgress": [
    {
      "type": "workflow_phase",
      "index": 1,
      "title": "Investigate"
    },
    {
      "type": "workflow_phase",
      "index": 2,
      "title": "Challenge"
    },
    {
      "type": "workflow_phase",
      "index": 3,
      "title": "Merge"
    },
    {
      "type": "workflow_agent",
      "index": 1,
      "label": "plan:MF1",
      "phaseIndex": 1,
      "phaseTitle": "Investigate",
      "agentId": "a5909878f48317d19",
      "model": "claude-opus-5[1m]",
      "state": "done",
      "startedAt": 1786754729311,
      "queuedAt": 1786754726163,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "MF1 CONFIRMED, and it is exactly as the audit describes â wâ¦",
      "promptPreview": "READ-ONLY. Do NOT edit, build or run tests â the main session owns the build tree and is
editing it concurrently. Use Read/Grep and read-only Bash (grep, sed -n, git show/log/diff).
Workdir /home/penguin/Projs/effects-research/cangjie; compiler /home/penguin/Projs/effects-research/cangjie/cangjie_compiler (branch chexc).
Normative spec: "/home/penguin/Projs/effects-research/cangjie/Checked exceptiâ¦",
      "lastProgressAt": 1786755630291,
      "tokens": 186691,
      "toolCalls": 100,
      "durationMs": 900978,
      "resultPreview": "{"finding":"MF1 CONFIRMED, and it is exactly as the audit describes â with four refinements established by reading the code.\n\n**(1) Every desugar site that builds an accessor callee type** â all three are in the anonymous namespace of `/home/penguin/Projs/effects-research/cangjie/cangjie_compiler/src/Sema/Desugar/AfterTypeCheck.cpp`, and all three call the 2-argument `GetFunctionTy`, i.e. `cfg={â¦"
    },
    {
      "type": "workflow_agent",
      "index": 2,
      "label": "plan:MF6",
      "phaseIndex": 1,
      "phaseTitle": "Investigate",
      "agentId": "a33423dd99244832a",
      "model": "claude-opus-5[1m]",
      "state": "done",
      "startedAt": 1786754729792,
      "queuedAt": 1786754726164,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "CONFIRMED, and narrower than the audit implies in one placeâ¦",
      "promptPreview": "READ-ONLY. Do NOT edit, build or run tests â the main session owns the build tree and is
editing it concurrently. Use Read/Grep and read-only Bash (grep, sed -n, git show/log/diff).
Workdir /home/penguin/Projs/effects-research/cangjie; compiler /home/penguin/Projs/effects-research/cangjie/cangjie_compiler (branch chexc).
Normative spec: "/home/penguin/Projs/effects-research/cangjie/Checked exceptiâ¦",
      "lastProgressAt": 1786755551812,
      "tokens": 166574,
      "toolCalls": 94,
      "durationMs": 821107,
      "resultPreview": "{"finding":"CONFIRMED, and narrower than the audit implies in one place, wider in another.\n\nConfirmed: `DesugarPrimaryCtor` (`/home/penguin/Projs/effects-research/cangjie/cangjie_compiler/src/Sema/Desugar/DesugarInTypeCheck.cpp:647-688`) builds a fresh `FuncBody` and copies only `retType` (`:660`), the param list (`:673` -> `DesugarPrimaryCtorHandleParam`), the super call (`:672`) and the remainâ¦"
    },
    {
      "type": "workflow_agent",
      "index": 3,
      "label": "plan:MF2",
      "phaseIndex": 1,
      "phaseTitle": "Investigate",
      "agentId": "a2216190caaa709c1",
      "model": "claude-opus-5[1m]",
      "state": "done",
      "startedAt": 1786754729782,
      "queuedAt": 1786754726164,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "MF2 confirmed, but the audit's one-line remedy is incompletâ¦",
      "promptPreview": "READ-ONLY. Do NOT edit, build or run tests â the main session owns the build tree and is
editing it concurrently. Use Read/Grep and read-only Bash (grep, sed -n, git show/log/diff).
Workdir /home/penguin/Projs/effects-research/cangjie; compiler /home/penguin/Projs/effects-research/cangjie/cangjie_compiler (branch chexc).
Normative spec: "/home/penguin/Projs/effects-research/cangjie/Checked exceptiâ¦",
      "lastProgressAt": 1786755831249,
      "tokens": 176030,
      "toolCalls": 72,
      "durationMs": 1100545,
      "resultPreview": "{"finding":"MF2 confirmed, but the audit's one-line remedy is incomplete, and the gap matters for how the work is scoped.\n\nVerified facts (current tree):\n1. `InferredCapabilities` (include/cangjie/Sema/CapabilityCheck.h:73) has exactly two readers â `CapabilityCheck.cpp:301-306` (FUNC_BODY supply push) and `:437-446` (resolved-call demand). Nothing writes the lists into any `Ty`. Confirmed by râ¦"
    },
    {
      "type": "workflow_agent",
      "index": 4,
      "label": "challenge:MF6",
      "phaseIndex": 2,
      "phaseTitle": "Challenge",
      "agentId": "a31a0e5c12a62463b",
      "model": "claude-opus-5[1m]",
      "state": "done",
      "startedAt": 1786755560406,
      "queuedAt": 1786755554644,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "needs-revision",
      "promptPreview": "READ-ONLY. Do NOT edit, build or run tests â the main session owns the build tree and is
editing it concurrently. Use Read/Grep and read-only Bash (grep, sed -n, git show/log/diff).
Workdir /home/penguin/Projs/effects-research/cangjie; compiler /home/penguin/Projs/effects-research/cangjie/cangjie_compiler (branch chexc).
Normative spec: "/home/penguin/Projs/effects-research/cangjie/Checked exceptiâ¦",
      "lastProgressAt": 1786756366167,
      "tokens": 144719,
      "toolCalls": 60,
      "durationMs": 805761,
      "resultPreview": "{"verdict":"needs-revision","problems":["Edit #1's blast radius is understated and mis-labelled. `CloneThrowsClause` (Clone.cpp:394-406) is reached from FIVE call sites, not one: `CloneFuncBody` (:1398-1400), `CloneFuncType` (:414-415), `CloneStructDecl`/`CloneClassDecl` capturesClause (:275, :293), and `CloneNode`'s ThrowsClause arm (:1553). Copying `hasEllipsis` therefore changes behaviour on EVâ¦"
    },
    {
      "type": "workflow_agent",
      "index": 5,
      "label": "challenge:MF1",
      "phaseIndex": 2,
      "phaseTitle": "Challenge",
      "agentId": "a2e714cf4c9a27c86",
      "model": "claude-opus-5[1m]",
      "state": "done",
      "startedAt": 1786755636037,
      "queuedAt": 1786755632877,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "needs-revision",
      "promptPreview": "READ-ONLY. Do NOT edit, build or run tests â the main session owns the build tree and is
editing it concurrently. Use Read/Grep and read-only Bash (grep, sed -n, git show/log/diff).
Workdir /home/penguin/Projs/effects-research/cangjie; compiler /home/penguin/Projs/effects-research/cangjie/cangjie_compiler (branch chexc).
Normative spec: "/home/penguin/Projs/effects-research/cangjie/Checked exceptiâ¦",
      "lastProgressAt": 1786756261522,
      "tokens": 115629,
      "toolCalls": 43,
      "durationMs": 625484,
      "resultPreview": "{"verdict":"needs-revision","problems":["BLOCKER D1 â Edit 2's helper can produce an INVALID FuncTy at all three desugar sites (new error-path state). include/cangjie/AST/Types.h:730-732 computes `invalid = !Ty::AreTysCorrect(typeArgs) || !Ty::IsTyCorrect(rType) || ... || !Ty::AreTysCorrect(capTys);`. src/Sema/TypeCheckUtil.cpp:306-316 (`ExpandCapabilityList`) and :275-280 (`ExpandCapabilityEntry`â¦"
    },
    {
      "type": "workflow_agent",
      "index": 6,
      "label": "challenge:MF2",
      "phaseIndex": 2,
      "phaseTitle": "Challenge",
      "agentId": "ad99f78eb506e726c",
      "model": "claude-opus-5[1m]",
      "state": "done",
      "startedAt": 1786755836915,
      "queuedAt": 1786755833791,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "needs-revision",
      "promptPreview": "READ-ONLY. Do NOT edit, build or run tests â the main session owns the build tree and is
editing it concurrently. Use Read/Grep and read-only Bash (grep, sed -n, git show/log/diff).
Workdir /home/penguin/Projs/effects-research/cangjie; compiler /home/penguin/Projs/effects-research/cangjie/cangjie_compiler (branch chexc).
Normative spec: "/home/penguin/Projs/effects-research/cangjie/Checked exceptiâ¦",
      "lastProgressAt": 1786756656540,
      "tokens": 156218,
      "toolCalls": 57,
      "durationMs": 819623,
      "resultPreview": "{"verdict":"needs-revision","problems":["BLOCKING â Part B's central premise about reference types is FALSE. `TypeChecker::TypeCheckerImpl::ChkRefExpr` (src/Sema/TypeCheckExpr/NameReferenceExpr.cpp:332-395) does `refNode.SetTy(fdTy)` at :363, where `fdTy` is the CANDIDATE DECLARATION's own (possibly generic-instantiated) type â never the target/annotated type. Sema accepts `helper` against `() thrâ¦"
    },
    {
      "type": "workflow_agent",
      "index": 7,
      "label": "merge",
      "phaseIndex": 3,
      "phaseTitle": "Merge",
      "agentId": "acc566d3f2e08eadf",
      "model": "claude-opus-5[1m]",
      "state": "done",
      "startedAt": 1786756662113,
      "queuedAt": 1786756658933,
      "attempt": 1,
      "lastToolName": "Bash",
      "lastToolSummary": "cd /home/penguin/Projs/effects-research/cangjie/cangjie_comâ¦",
      "promptPreview": "READ-ONLY. Do NOT edit, build or run tests â the main session owns the build tree and is
editing it concurrently. Use Read/Grep and read-only Bash (grep, sed -n, git show/log/diff).
Workdir /home/penguin/Projs/effects-research/cangjie; compiler /home/penguin/Projs/effects-research/cangjie/cangjie_compiler (branch chexc).
Normative spec: "/home/penguin/Projs/effects-research/cangjie/Checked exceptiâ¦",
      "lastProgressAt": 1786757252179,
      "tokens": 136202,
      "toolCalls": 32,
      "durationMs": 590065,
      "resultPreview": "# Merged implementation guide â MF6 + MF1 + MF2(Part A)

**Scope of this batch:** MF6 (primary-ctor `throws` dropped), MF1 (property-accessor `throws` dropped at use sites), MF2 **Part A only** (inferred lists written back into declaration types). **MF2 Part B (demand at function-value formation) is EXCLUDED** â see Unresolved #2; its central premise was disproved and one of its edits does not comâ¦"
    }
  ],
  "totalTokens": 1082063,
  "totalToolCalls": 458
}