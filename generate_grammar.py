"""Generate syntaxes/ccl.tmLanguage.json for Cerner Command Language (CCL)."""

import json
import re
from pathlib import Path


def build_word_alternation(words: list[str]) -> str:
    """Sort words longest-first and join into a regex alternation with \\s+ for spaces."""
    unique = sorted(set(words), key=lambda w: (-len(w), w))
    return "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in unique)


def validate_regexes(node: object, path: str = "root") -> None:
    """Recursively compile all regex strings in the grammar to catch syntax errors."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"match", "begin", "end", "while"} and isinstance(value, str):
                try:
                    re.compile(value)
                except re.error as exc:
                    raise ValueError(f"Invalid regex at {path}.{key}: {value!r} -> {exc}") from exc
            else:
                validate_regexes(value, f"{path}.{key}")
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            validate_regexes(item, f"{path}[{idx}]")


def build_grammar() -> dict:
    """Construct the TextMate grammar dictionary for Cerner CCL."""
    control_keywords = [
        # Multi-word clauses and commands
        "CREATE PROGRAM",
        "DROP PROGRAM",
        "FREE RECORD",
        "FREE DEFINE",
        "FREE SET",
        "HEAD REPORT",
        "FOOT REPORT",
        "HEAD PAGE",
        "FOOT PAGE",
        "ORDER BY",
        "GROUP BY",
        "ELSE IF",
        "END GO",
        "GO TO",
        # Block delimiters & control flow
        "SUBROUTINE",
        "ENDSELECT",
        "ENDWHILE",
        "ENDCASE",
        "ENDFOR",
        "ENDIF",
        "ENDGO",
        "ELSEIF",
        "RETURN",
        "CONTINUE",
        "BREAK",
        "EXIT",
        "GOTO",
        "WHILE",
        "BEGIN",
        "CASE",
        "ELSE",
        "THEN",
        "FOR",
        "END",
        "IF",
        "DO",
        "TO",
        "GO",
        "OF",
        # Program / query / declaration keywords
        "PERSISTSCRIPT",
        "NOCONSTANT",
        "SKIPREPORT",
        "NOCOUNTER",
        "OUTERJOIN",
        "DONTJOIN",
        "SEPARATOR",
        "CONSTANT",
        "DISTINCT",
        "ROLLBACK",
        "DONTJOIN",
        "DONTWAIT",
        "MAXQUAL",
        "HEADING",
        "FOOTING",
        "DECLARE",
        "EXECUTE",
        "PERSIST",
        "PRIVATE",
        "PROTECT",
        "COUNTER",
        "MAXREC",
        "NOTRIM",
        "PROMPT",
        "PUBLIC",
        "RECORD",
        "REPORT",
        "SELECT",
        "UPDATE",
        "VALUES",
        "COMMIT",
        "CREATE",
        "DELETE",
        "DETAIL",
        "HAVING",
        "INSERT",
        "MODIFY",
        "DEFINE",
        "REMOVE",
        "CANCEL",
        "PROGRAM",
        "ALTER",
        "CHECK",
        "CLASS",
        "INDEX",
        "TABLE",
        "UNION",
        "WHERE",
        "FROM",
        "FOOT",
        "HEAD",
        "INTO",
        "JOIN",
        "PAGE",
        "PLAN",
        "STEP",
        "TIME",
        "VIEW",
        "WITH",
        "CALL",
        "DESC",
        "DROP",
        "FREE",
        "ASC",
        "MAP",
        "SET",
        "BY",
        "ON",
    ]

    logical_operators = [
        "OPERATOR",
        "BETWEEN",
        "EXISTS",
        "LIKE",
        "AND",
        "NOT",
        "IN",
        "IS",
        "OR",
        "AS",
    ]

    language_constants = [
        "CURTIMEZONEAPP",
        "CURCODECOVER",
        "SYSTIMESTAMP",
        "CURACCEPT",
        "CURDOMAIN",
        "CURLOCALE",
        "CURALIAS",
        "CURSCOPE",
        "CURTIME2",
        "CURTIME3",
        "CURDATE",
        "CURFILE",
        "CURHELP",
        "CURPROG",
        "CURQUAL",
        "CURSYS2",
        "CURTIME",
        "CURUSER",
        "SYSDATE",
        "CURLOB",
        "CURMEM",
        "CURREV",
        "CURSUB",
        "CURSYS",
        "CURUTC",
        "OUTDEV",
        "FALSE",
        "NULL",
        "TRUE",
        "ZERO",
    ]

    builtin_functions = [
        # Date / Time / Conversion
        "DATETIMEZONEBYINDEX",
        "DATEDECEASEDFORMAT",
        "DATETIMEZONEBYNAME",
        "DATETIMEZONEFORMAT",
        "CNVTDATETIMEUTC2",
        "CNVTDATETIMEUTC3",
        "CNVTAGEDATETIME",
        "CNVTDATETIMERDB",
        "CNVTDATETIMEUTC",
        "DATEBIRTHFORMAT",
        "DATETIMEZONEUTC",
        "CNVTLOOKBEHIND",
        "DATETIMECMPUTC",
        "CNVTRECTOJSON",
        "CNVTJSONTOREC",
        "CNVTTIMESTAMP",
        "CNVTDATETIME2",
        "CNVTLOOKAHEAD",
        "CNVTRECTOXML",
        "CNVTXMLTOREC",
        "CNVTSTRINGCHK",
        "DATETIMETRUNC",
        "TIMESTAMPDIFF",
        "CNVTALPHANUM",
        "CNVTDATETIME",
        "DATETIMEDIFF",
        "DATETIMEFIND",
        "DATETIMEPART",
        "DATETIMEZONE",
        "DATETIMEADD",
        "DATETIMECMP",
        "DATETIMESUB",
        "CNVTNLSSORT",
        "CNVTB10B16",
        "CNVTB10B36",
        "CNVTB16B10",
        "CNVTB36B10",
        "CNVTHEXRAW",
        "CNVTRAWHEX",
        "CNVTSTRING",
        "CNVTALIAS",
        "CNVTDATE2",
        "CNVTLOWER",
        "CNVTPHONE",
        "CNVTTIME2",
        "CNVTTIME3",
        "CNVTUPPER",
        "CNVTAGE2",
        "CNVTBOOL",
        "CNVTDATE",
        "CNVTLONG",
        "CNVTMIN2",
        "CNVTREAL",
        "CNVTTIME",
        "CNVTACC",
        "CNVTAGE",
        "CNVTCAP",
        "CNVTINT",
        "CNVTMIN",
        "CNVTNLS",
        "WEEKDAY",
        "JULIAN",
        "MINUTE",
        "MONTH",
        "HOUR",
        "YEAR",
        "DAY",
        # String / Regex / Formatting
        "REGEXPREPLACE",
        "REGEXPSUBSTR",
        "REGEXPMATCH",
        "REGEXPCOUNT",
        "REGEXPINSTR",
        "NOPATSTRING",
        "FILLSTRING",
        "FINDSTRING",
        "MOVESTRING",
        "PATSTRING",
        "SUBSTRING",
        "CCLREGEXP",
        "BUILD2CHK",
        "TEXTLEN",
        "REPLACE",
        "SOUNDEX",
        "CONCAT",
        "BUILD2",
        "BUILD3",
        "CCLFMT",
        "FORMAT",
        "NULLFMT",
        "BUILD",
        "ICHAR",
        "PIECE",
        "CHAR",
        "TEXT",
        "TRIM",
        # List / Record / Array / Memory
        "LOCATEVALSORT",
        "MOVERECLIST",
        "ARRAYSPLIT",
        "MEMREALLOC",
        "ARRAYJOIN",
        "ALTERLIST",
        "INITARRAY",
        "LOCATEVAL",
        "RENAMEREC",
        "MEMALLOC",
        "COPYREC",
        "INITREC",
        "MEMFREE",
        "MOVEREC",
        "EXPAND",
        "ALTER2",
        "ALTER3",
        "LIST",
        "SIZE",
        # Math / Aggregation / Analytics / Bitwise
        "PERCENTILE_CONT",
        "PERCENTILE_DISC",
        "PERCENT_RANK",
        "DENSE_RANK",
        "PERCENTILE",
        "ROW_NUMBER",
        "CUME_DIST",
        "ISNUMERIC",
        "EVALUATE2",
        "VARIANCE",
        "GREATEST",
        "EVALUATE",
        "PERCENT",
        "DECODE",
        "MAXVAL",
        "MEDIAN",
        "MINVAL",
        "NEGATE",
        "STDDEV",
        "BSHIFT",
        "LEAST",
        "LOG10",
        "NTILE",
        "ROUND",
        "FLOOR",
        "BTEST",
        "BAND",
        "BNOT",
        "BXOR",
        "CEIL",
        "EVEN",
        "RAND",
        "RANK",
        "CUBE",
        "ROLLUP",
        "ABS",
        "AVG",
        "BOR",
        "EXP",
        "LOG",
        "MAX",
        "MIN",
        "MOD",
        "SEQ",
        "SUM",
        "COUNT",
        # I/O / System / Diagnostics / Screen / Crypto / MPages
        "CCLNEWSESSIONWINDOW",
        "MPAGES_SVC_EVENT",
        "AESDECRYPTFILE",
        "AESENCRYPTFILE",
        "CCLLINKPOPUP",
        "MPAGES_EVENT",
        "SCROLLDOWN",
        "SCROLLINIT",
        "SCROLLTEXT",
        "SCROLLUP",
        "PRINTIMAGE",
        "ECHORECORD",
        "AESDECRYPT",
        "AESENCRYPT",
        "BLOBGETLEN",
        "CHECKQUEUE",
        "PARAMETER2",
        "REPORTINFO",
        "RECTRAVERSE",
        "SORTSEARCH",
        "SQLPASSTHRU",
        "TDBEXECUTE",
        "WTMODCHECK",
        "NULLCHECK",
        "PRINTTEXT",
        "PRINTFILE",
        "PROXYUSER",
        "REPORTROW",
        "PARAMETER",
        "CCLTIMER",
        "CHECKDIC",
        "CHECKFUN",
        "CHECKPRG",
        "ECHOJSON",
        "FINDFILE",
        "MODCHECK",
        "NORDBBIND",
        "NULLTERM",
        "TRIMBIND",
        "VALIDATE",
        "APPLINK",
        "CCLEVENT",
        "CCLLINK",
        "ECHOXML",
        "ASSIGN2",
        "ASSIGN3",
        "BLOBGET",
        "CALCPOS",
        "CALLPRG",
        "COMPILE",
        "LOGICAL",
        "NULLIND",
        "NULLVAL",
        "RDBBIND",
        "REFLECT",
        "LISTAGG",
        "ASSIGN",
        "CCLIO",
        "CENTER",
        "ACCEPT",
        "PARSER",
        "CALLR",
        "CLEAR",
        "COST",
        "DEBUG",
        "ERROR",
        "PAUSE",
        "PRINT",
        "SOUND",
        "TRACE",
        "VALUE",
        "VIDEO",
        "ASIS",
        "ECHO",
        "EDIT",
        "LINE",
        "SORT",
        "BOX",
        "COL",
        "DCL",
        "ROW",
    ]

    grammar = {
        "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
        "name": "Cerner CCL",
        "scopeName": "source.ccl",
        "patterns": [
            {"include": "#comments"},
            {"include": "#strings"},
            {"include": "#directives"},
            {"include": "#member-access"},
            {"include": "#declarations"},
            {"include": "#keywords"},
            {"include": "#constants"},
            {"include": "#types"},
            {"include": "#functions"},
            {"include": "#operators"},
            {"include": "#numbers"},
            {"include": "#variables"},
        ],
        "repository": {
            "comments": {
                "patterns": [
                    {
                        "name": "comment.line.semicolon.ccl",
                        "match": ";.*$",
                    },
                    {
                        "name": "comment.line.exclamation.ccl",
                        "match": "!(?!=).*$",
                    },
                    {
                        "name": "comment.block.ccl",
                        "begin": "/\\*",
                        "beginCaptures": {
                            "0": {"name": "punctuation.definition.comment.ccl"}
                        },
                        "end": "\\*/",
                        "endCaptures": {
                            "0": {"name": "punctuation.definition.comment.ccl"}
                        },
                    },
                ]
            },
            # NOTE: In Cerner CCL, backslash (\) is a literal character inside strings,
            # NOT an escape character. Do not add \\. escape rules here.
            "strings": {
                "patterns": [
                    {
                        "name": "string.quoted.double.ccl",
                        "begin": "\"",
                        "beginCaptures": {
                            "0": {"name": "punctuation.definition.string.begin.ccl"}
                        },
                        "end": "\"",
                        "endCaptures": {
                            "0": {"name": "punctuation.definition.string.end.ccl"}
                        },
                    },
                    {
                        "name": "string.quoted.single.ccl",
                        "begin": "'",
                        "beginCaptures": {
                            "0": {"name": "punctuation.definition.string.begin.ccl"}
                        },
                        "end": "'",
                        "endCaptures": {
                            "0": {"name": "punctuation.definition.string.end.ccl"}
                        },
                    },
                    {
                        "name": "string.quoted.other.caret.ccl",
                        "begin": "\\^",
                        "beginCaptures": {
                            "0": {"name": "punctuation.definition.string.begin.ccl"}
                        },
                        "end": "\\^",
                        "endCaptures": {
                            "0": {"name": "punctuation.definition.string.end.ccl"}
                        },
                    },
                    {
                        "name": "string.quoted.other.tilde.ccl",
                        "begin": "~",
                        "beginCaptures": {
                            "0": {"name": "punctuation.definition.string.begin.ccl"}
                        },
                        "end": "~",
                        "endCaptures": {
                            "0": {"name": "punctuation.definition.string.end.ccl"}
                        },
                    },
                ]
            },
            "directives": {
                "patterns": [
                    {
                        "match": "(?i)^\\s*(%#?[a-z]+)\\b",
                        "captures": {
                            "1": {"name": "keyword.control.directive.ccl"}
                        },
                    }
                ]
            },
            "member-access": {
                "patterns": [
                    {
                        "match": "(->)\\s*([A-Za-z_][A-Za-z0-9_]*)",
                        "captures": {
                            "1": {"name": "punctuation.accessor.ccl"},
                            "2": {"name": "variable.other.property.ccl"},
                        },
                    },
                    {
                        "match": "(\\.)([A-Za-z_][A-Za-z0-9_]*)",
                        "captures": {
                            "1": {"name": "punctuation.accessor.ccl"},
                            "2": {"name": "variable.other.property.ccl"},
                        },
                    },
                ]
            },
            "declarations": {
                "patterns": [
                    {
                        "match": "(?i)\\b(subroutine)\\s+(?:\\(\\s*)?([a-z_][a-z0-9_]*)\\s*(?=\\()",
                        "captures": {
                            "1": {"name": "keyword.control.ccl"},
                            "2": {"name": "entity.name.function.ccl"},
                        },
                    },
                    {
                        "match": "(?i)\\b(drop\\s+program|create\\s+program)\\s+([a-z_][a-z0-9_]*(?::[a-z_][a-z0-9_]*)?)",
                        "captures": {
                            "1": {"name": "keyword.control.ccl"},
                            "2": {"name": "entity.name.type.ccl"},
                        },
                    },
                ]
            },
            "keywords": {
                "patterns": [
                    {
                        "name": "keyword.control.ccl",
                        "match": f"(?i)\\b({build_word_alternation(control_keywords)})\\b",
                    },
                    {
                        "name": "keyword.control.ccl",
                        "match": "(?i)\\bFORMAT\\b(?!\\s*\\()",
                    },
                    {
                        "name": "keyword.operator.logical.ccl",
                        "match": f"(?i)\\b({build_word_alternation(logical_operators)})\\b",
                    },
                ]
            },
            "constants": {
                "patterns": [
                    {
                        "name": "constant.language.ccl",
                        "match": f"(?i)\\b({build_word_alternation(language_constants)})\\b",
                    }
                ]
            },
            "types": {
                "patterns": [
                    {
                        "match": "(?i)(=)\\s*((?:c|vc|gc|gvc|zc|zvc|zgc|zgvc)[1-9]\\d*)\\b(?!\\s*(?:\\.|->|\\(|\\[))",
                        "captures": {
                            "1": {"name": "keyword.operator.ccl"},
                            "2": {"name": "storage.type.ccl"},
                        },
                    },
                    {
                        "name": "storage.type.ccl",
                        "match": "(?i)\\b(f4|f8|i1|ui1|i2|ui2|i4|ui4|w8|uw8|dq8|dm12|dm14|vc|gvc|zvc|zgvc)\\b(?!\\s*(?:\\.|->|\\())",
                    },
                ]
            },
            "functions": {
                "patterns": [
                    {
                        "name": "support.function.ccl",
                        "match": "(?i)\\buar_[a-z0-9_]+\\b(?=\\s*\\()",
                    },
                    {
                        "name": "support.function.ccl",
                        "match": f"(?i)\\b({build_word_alternation(builtin_functions)})\\b(?=\\s*\\()",
                    },
                    {
                        "match": "(?i)\\b([a-z_][a-z0-9_]*)(?=\\s*\\()",
                        "captures": {
                            "1": {"name": "entity.name.function.ccl"}
                        },
                    },
                ]
            },
            "operators": {
                "patterns": [
                    {
                        "name": "keyword.operator.ccl",
                        "match": "(->|!=|<>|<=|>=|\\*\\*|[=<>+\\-*/])",
                    }
                ]
            },
            "numbers": {
                "patterns": [
                    {
                        "name": "constant.numeric.ccl",
                        "match": "\\b\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b|(?<!\\w)\\.\\d+(?:[eE][+-]?\\d+)?\\b",
                    }
                ]
            },
            "variables": {
                "patterns": [
                    {
                        "name": "variable.other.ccl",
                        "match": "(?i)\\b[a-z_][a-z0-9_]*\\b",
                    }
                ]
            },
        },
    }

    validate_regexes(grammar)
    return grammar


def main() -> None:
    grammar = build_grammar()
    out_path = Path(__file__).resolve().parent / "syntaxes" / "ccl.tmLanguage.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(grammar, f, indent=4)
        f.write("\n")
    print(f"Generated {out_path}")


if __name__ == "__main__":
    main()
