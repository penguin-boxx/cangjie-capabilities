# patches/ — the whole prototype as a patch series

The submodules are the primary form of this result; this directory is the same content
in a form that survives the disappearance of any repository. Each series is
`git format-patch` output taken from the upstream commit the work branched from up to
the pinned head, so applying a series to its base reproduces the submodule's tree
exactly — checked, for `stdx`, by applying it and comparing tree hashes.

| series | upstream base | pinned head | commits | delta |
|---|---|---|---|---|
| `compiler/` | `098c1b26` (`cangjie_compiler` main) | `cd0b3f4f` | 44 | 80 files, +4435 −97 |
| `test/` | `a85fe3b9` (`cangjie_test` main) | `0e131d8a` | 43 | 166 files, +4804 −1 |
| `runtime/` | `8600a6d2` (`cangjie_runtime` main) | `3caa9430` | 6 | 35 files, +184 −118 |
| `stdx/` | `51ae667b` (`cangjie_stdx` main) | `4eb1cd8c` | 4 | 22 files, +315 −156 |

Upstream lives at `https://gitcode.com/Cangjie/<repo>.git`.

## Applying

```sh
git clone https://gitcode.com/Cangjie/cangjie_compiler.git
git -C cangjie_compiler checkout -b chexc 098c1b26
git -C cangjie_compiler am /path/to/patches/compiler/*.patch
```

The same three lines apply to the other three, with the base from the table. `git am`
reports whitespace warnings on the stdx and runtime series — the annotated stdlib files
carry the upstream indentation, and the warnings are cosmetic.

The commits are review-sized and ordered; a series read front to back is the development
history, and `notes/gap-analysis.md` is the running record of what each round closed.
