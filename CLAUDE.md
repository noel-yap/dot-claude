> [!CAUTION]
> **ABSOLUTE RULE — NO EXCEPTIONS — OVERRIDES ALL OTHER BEHAVIOR**
>
> **NEVER derive a path from memory, context, or conversation text.**
> **ALWAYS obtain paths by running `pwd`, `ls`, `find`, or `git` commands and copying the output byte-for-byte.**
>
> Unicode characters in paths are NEVER interchangeable with visually similar ASCII characters.
> If you construct a path yourself instead of reading it from shell output, you WILL silently corrupt it.

# Shell Command Rules

## Path construction (MANDATORY — do this every time)

Before using any path in a shell command:
1. Run `ls` or `pwd` to get the exact name from the filesystem.
2. Copy that output verbatim — do not retype it.
3. Quote it with double quotes: `"$PWD/exact name from ls"`.

**Rationale:** Unicode characters look identical to ASCII in many fonts but are different bytes. `：`(U+FF1A) renders like `:` but is a different character. `⋯`(U+22EF) looks like `...` but is one character. Retyping from context substitutes the wrong bytes and silently breaks the command.

## Prohibited substitutions (examples — not exhaustive)

| Unicode (correct) | ASCII lookalike (FORBIDDEN) |
|---|---|
| `：` U+FF1A full-width colon | `:` U+003A |
| `．` U+FF0E full-width period | `.` U+002E |
| `⋯` U+22EF midline ellipsis | `...` three dots |
| `…` U+2026 horizontal ellipsis | `...` three dots |
| `é` `ñ` composed chars | `e` `n` stripped chars |
| U+00A0 no-break space | U+0020 regular space |
| `　` U+3000 ideographic space | U+0020 regular space |

## Self-check (required before every Bash path)

Ask yourself: "Did I type this path, or did I copy it from shell output?" If you typed it, stop — run `ls`/`pwd` first and use that output instead.
