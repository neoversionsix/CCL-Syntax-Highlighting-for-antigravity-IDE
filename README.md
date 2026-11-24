# Cerner CCL Language Support

Provides syntax highlighting, language configuration, and code snippets for Cerner Command Language (CCL) files (`.prg`, `.inc`, `.ccl`) in VS Code / Open VSX.

## Features

- **Comments**: `;` and `!` single-line comments (without interfering with `!=`), and `/* ... */` block comments.
- **Strings**: `"..."`, `'...'`, `^...^`, and `~...~` string literals (treating `\` as a literal character rather than an escape sequence, matching CCL compiler behavior).
- **Keywords, Types & Built-ins**: CCL control flow (`IF`/`ENDIF`, `FOR`/`ENDFOR`, `WHILE`/`ENDWHILE`, `SELECT`/`PLAN`/`JOIN`/`WITH`, `RECORD`, `SUBROUTINE`, `DROP/CREATE PROGRAM`), data types (`f4`, `f8`, `i1`, `i2`, `i4`, `w8`, `dq8`, `vc`, `gvc`, `cN`), built-in functions, `uar_*` calls, member access (`->` / `.`), and `%` directives.
- **Language Configuration & Snippets**: Auto-closing pairs, indentation rules, and snippets for `select`, `update`, `delete`, `declare`, `if`, `ifelse`, `for`, `while`, `subroutine`, `record`, and `program`.

## Development & Packaging

Regenerate the TextMate grammar:

```bash
python generate_grammar.py
```

Package the extension into a `.vsix` file:

```bash
npx @vscode/vsce package
```
