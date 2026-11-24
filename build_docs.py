"""Build data/ccl-docs.json from Discern Explorer HTML documentation zip archives."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from bs4 import BeautifulSoup, Tag

SKIP_FUNCTION_FILES = {
    "index.html",
    "index-functions-only.html",
    "HHFUNCTIONS-Using-Discern-Explorer.html",
    "METASYMBOLS-Using-Discern-Explorer.html",
}

STATEMENT_KEYS = {
    "SELECT",
    "UPDATE",
    "INSERT",
    "DELETE",
    "IF",
    "FOR",
    "WHILE",
    "CASE",
    "EXECUTE",
    "DEFINE",
    "MODIFY",
    "REMOVE",
    "OUTERJOIN",
    "OPERATOR",
    "NOTRIM",
    "NULL",
    "GO TO",
    "GOTO",
    "CHECK",
    "CLASS",
    "CREATE",
    "DROP",
    "ALTER",
    "ORDERDIR",
    "MAXREC",
}

ALIAS_MAP = {
    "EVALUATE-2": ("EVALUATE2", "Function"),
    "CNVTTIME-Function": ("CNVTTIME", "Function"),
    "LIST-Function": ("LIST", "Function"),
    "GO-TO": ("GO TO", "Statement"),
    "SET-Variable": ("SET", "Command"),
}


def clean_ws(text: str) -> str:
    """Normalize non-breaking spaces and collapse whitespace to single spaces."""
    text = text.replace("\xa0", " ").replace("\r", "")
    return re.sub(r"[ \t\n]+", " ", text).strip()


def clean_pre(text: str) -> str:
    """Normalize <pre> text while preserving line breaks."""
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def truncate_text(text: str, max_len: int) -> str:
    """Truncate text cleanly at a sentence or word boundary."""
    if len(text) <= max_len:
        return text
    snippet = text[:max_len]
    dots = [m.start() + 1 for m in re.finditer(r"\.(?:\s|$)", snippet) if m.start() + 1 >= max_len // 2]
    if dots:
        return snippet[: dots[-1]].strip()
    cut = snippet.rsplit(" ", 1)[0].rstrip(",;:")
    return f"{cut}..."


def truncate_lines(text: str, max_lines: int) -> str:
    """Cap multi-line examples/syntax cleanly."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines] + ["..."])


def heading_kind(text: str) -> str:
    """Classify section heading text."""
    low = clean_ws(text).lower()
    if "syntax" in low:
        return "syntax"
    if "metasymbol" in low or "metesymbol" in low:
        return "metasymbols"
    if "example" in low:
        return "examples"
    if "exception" in low:
        return "exceptions"
    return "other"


def extract_markdown_table(table_tag: Tag, max_rows: int = 12) -> str | None:
    """Convert an HTML table into a compact Markdown table capped at max_rows data rows."""
    trs = table_tag.find_all("tr")
    if len(trs) < 2:
        return None

    first_has_th = bool(trs[0].find("th"))
    rows: list[list[str]] = []
    for tr in trs:
        cells = [
            clean_ws(cell.get_text(" ", strip=True)).replace("|", "\\|")
            for cell in tr.find_all(["th", "td"])
        ]
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        return None

    col_count = max(len(r) for r in rows)
    if col_count == 0 or col_count > 6:
        return None

    norm_rows = [r + [""] * (col_count - len(r)) for r in rows]
    if first_has_th:
        header = norm_rows[0]
        data_rows = norm_rows[1:]
    elif col_count == 2:
        header = ["Value", "Description"]
        data_rows = norm_rows
    else:
        # Multi-column headerless tables (e.g., command grids in IF/FOR/WHILE) are layout noise
        return None

    truncated = len(data_rows) > max_rows
    if truncated:
        data_rows = data_rows[:max_rows]

    def fmt_cell(c: str) -> str:
        return truncate_text(c, 100)

    lines = [
        "| " + " | ".join(fmt_cell(c) for c in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for r in data_rows:
        lines.append("| " + " | ".join(fmt_cell(c) for c in r) + " |")
    if truncated:
        lines.append("| " + " | ".join(["..."] + [""] * (col_count - 1)) + " |")
    return "\n".join(lines)


def split_sections(container: Tag) -> dict[str, list[Tag]]:
    """Group top-level children of a Confluence wiki-content block by heading."""
    inner = container.find("div", class_="wiki-content", recursive=False)
    root = inner if inner else container

    sections: dict[str, list[Tag]] = {"intro": []}
    current = "intro"
    inline_headings = {
        "syntax",
        "record command syntax",
        "metasymbol",
        "metasymbols",
        "metesymbols",
        "example",
        "examples",
    }
    for child in root.children:
        if not isinstance(child, Tag):
            continue
        if child.name == "h1" and current == "intro" and not sections["intro"]:
            # Skip leading page title <h1> so intro paragraphs stay in "intro"
            continue
        if child.name in {"h1", "h2", "h3", "h4"}:
            current = heading_kind(child.get_text(" ", strip=True))
            sections.setdefault(current, [])
        elif child.name == "p" and clean_ws(child.get_text(" ", strip=True)).lower() in inline_headings:
            current = heading_kind(child.get_text(" ", strip=True))
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(child)
    return sections


def parse_intro_summary(tags: list[Tag]) -> str:
    """Extract a concise summary from intro tags, skipping Confluence Note panels when possible."""
    paragraphs: list[str] = []
    fallback: list[str] = []
    for idx, tag in enumerate(tags):
        classes = " ".join(tag.get("class", []))
        text = clean_ws(tag.get_text(" ", strip=True))
        if not text:
            continue
        if "confluence-information-macro" in classes or text.startswith("Note "):
            fallback.append(text)
            continue
        if re.match(r"^the syntax of .* is shown below\.?$", text, re.I):
            continue
        if tag.name == "p":
            if text.endswith(":") and idx + 1 < len(tags) and tags[idx + 1].name in {"ul", "ol"}:
                items = [clean_ws(li.get_text(" ", strip=True)).rstrip(".") for li in tags[idx + 1].find_all("li")]
                if items:
                    paragraphs.append(f"{text} {'; '.join(items[:4])}.")
                    continue
            paragraphs.append(text)
        elif tag.name in {"ul", "ol"} and not paragraphs:
            items = [clean_ws(li.get_text(" ", strip=True)) for li in tag.find_all("li")]
            if items:
                fallback.append("; ".join(items[:4]))
    chosen = paragraphs if paragraphs else fallback
    joined = " ".join(chosen[:2]).strip()
    return truncate_text(joined, 450)


def parse_pre_blocks(tags: list[Tag]) -> list[str]:
    """Extract cleaned <pre> text blocks from a list of tags."""
    out: list[str] = []
    for tag in tags:
        if tag.name == "pre":
            txt = clean_pre(tag.get_text())
            if txt:
                out.append(txt)
        else:
            for pre in tag.find_all("pre"):
                txt = clean_pre(pre.get_text())
                if txt:
                    out.append(txt)
    return out


def extract_syntax_text(tags: list[Tag]) -> str:
    """Extract syntax from <pre>, falling back to <p> or syntax <table>."""
    pre_blocks = parse_pre_blocks(tags)
    if pre_blocks:
        return truncate_lines("\n".join(pre_blocks), 10).strip()

    # Fallback 1: <p> syntax line (e.g., BLOBGET, BLOBGETLEN)
    p_lines = [clean_ws(t.get_text(" ", strip=True)) for t in tags if t.name == "p" and clean_ws(t.get_text())]
    if p_lines:
        return truncate_lines("\n".join(p_lines[:3]), 6)

    # Fallback 2: syntax table (e.g., CNVTTIMESTAMP)
    for tag in tags:
        tbl = tag if tag.name == "table" else tag.find("table")
        if tbl:
            sigs: list[str] = []
            for tr in tbl.find_all("tr")[1:]:
                first_cell = tr.find(["th", "td"])
                if first_cell:
                    sig = clean_ws(first_cell.get_text(" ", strip=True))
                    if sig:
                        sigs.append(sig)
            if sigs:
                return truncate_lines("\n".join(sigs[:6]), 6)
    return ""


def parse_metasymbols(tags: list[Tag]) -> tuple[list[dict[str, str]], str | None]:
    """Extract parameter descriptions and an optional compact table from Metasymbols section."""
    params: list[dict[str, str]] = []
    seen_names: set[str] = set()
    table_md: str | None = None

    pending_name: str | None = None
    for tag in tags:
        if tag.name == "div" and "table-wrap" in " ".join(tag.get("class", [])):
            if table_md is None:
                tbl = tag.find("table")
                if tbl:
                    table_md = extract_markdown_table(tbl)
            pending_name = None
            continue
        if tag.name == "table":
            if table_md is None:
                table_md = extract_markdown_table(tag)
            pending_name = None
            continue

        # Handle <div class="metasymbol"><strong>name</strong><br/>desc</div> (e.g., ABS)
        if tag.name == "div" and "metasymbol" in " ".join(tag.get("class", [])):
            strong = tag.find("strong")
            full_text = clean_ws(tag.get_text(" ", strip=True))
            if strong:
                pname = clean_ws(strong.get_text(" ", strip=True)).strip(":,")
                if pname and full_text.startswith(pname):
                    rest = full_text[len(pname):].strip(" :-")
                    if len(rest) >= 4 and pname.lower() not in seen_names:
                        seen_names.add(pname.lower())
                        params.append({"name": pname, "description": truncate_text(rest, 250)})
            continue

        if tag.name != "p":
            continue

        ems = tag.find_all("em", recursive=False)
        if not ems:
            first_em = tag.find("em")
            if first_em and clean_ws(tag.get_text(" ", strip=True)).startswith(clean_ws(first_em.get_text())):
                ems = [first_em]

        full_text = clean_ws(tag.get_text(" ", strip=True))
        if not full_text:
            continue

        if ems and len(ems) == 1:
            em_text = clean_ws(ems[0].get_text(" ", strip=True))
            pname = em_text.strip(":,")
            if pname and len(pname) <= 45 and not pname.endswith("."):
                # Case A: <p><em>param</em> description</p>
                if full_text.startswith(em_text) and len(full_text) > len(em_text):
                    rest = full_text[len(em_text):].strip(" :-")
                    if len(rest) >= 4 and pname.lower() not in seen_names:
                        seen_names.add(pname.lower())
                        params.append({"name": pname, "description": truncate_text(rest, 250)})
                    pending_name = None
                    continue
                # Case B: <p><em>param</em></p> or <p>$<em>param</em></p> followed by <p>description</p>
                if full_text == em_text or full_text == f"${em_text}":
                    pending_name = full_text.strip(":,")
                    continue

        if pending_name:
            key = pending_name.lower()
            if len(full_text) >= 4 and key not in seen_names:
                seen_names.add(key)
                params.append({"name": pending_name, "description": truncate_text(full_text, 250)})
            pending_name = None

    return params, table_md


def line_matches_key(line: str, key: str) -> bool:
    """Return True if `line` uses `key` outside a DROP/CREATE PROGRAM header."""
    stripped = line.strip()
    if not stripped or stripped.startswith(";"):
        return False
    if re.match(r"^(?:DROP|CREATE)\s+PROGRAM\b", stripped, re.I):
        return False

    norm_line = stripped.replace("MPAGES_SVC_ EVENT", "MPAGES_SVC_EVENT")
    candidates = [key]
    if " " in key:
        candidates.append(key.split()[-1])
    for cand in candidates:
        pat = r"(?i)(?<![A-Za-z0-9_])" + re.escape(cand).replace(r"\ ", r"\s+") + r"(?![A-Za-z0-9_])"
        if re.search(pat, norm_line):
            return True
    return False


def is_prose_only_pre(block: str) -> bool:
    """Detect prose sentences accidentally placed inside <pre> tags in Cerner Wiki."""
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if len(lines) == 1:
        ln = lines[0]
        if re.match(r"^(?:The following example|In (?:this|the) example)\b", ln, re.I):
            return True
    return False


def focus_example_block(block: str, key: str, max_lines: int = 12) -> str:
    """Extract a focused window around the actual usage of `key` in a long example."""
    lines = block.splitlines()
    if len(lines) <= max_lines:
        return block

    hit_idx = next((i for i, ln in enumerate(lines) if line_matches_key(ln, key)), None)
    if hit_idx is None:
        return truncate_lines(block, max_lines)

    if hit_idx < max_lines - 3:
        end = max_lines
        # Extend slightly if a closing END* keyword is right around the cutoff
        for j in range(end, min(len(lines), end + 4)):
            if re.match(r"^\s*(?:ENDIF|ENDFOR|ENDWHILE|ENDCASE)\b", lines[j], re.I):
                end = j + 1
                break
        out = lines[:end]
        if end < len(lines):
            out.append("; ...")
        return "\n".join(out)

    start = max(0, hit_idx - 2)
    end = min(len(lines), start + max_lines)
    for j in range(end, min(len(lines), end + 4)):
        if re.match(r"^\s*(?:ENDIF|ENDFOR|ENDWHILE|ENDCASE)\b", lines[j], re.I):
            end = j + 1
            break

    out: list[str] = []
    if start > 0:
        out.append("; ...")
    out.extend(lines[start:end])
    if end < len(lines):
        out.append("; ...")
    return "\n".join(out)


def select_best_example(tags: list[Tag], key: str) -> str:
    """Choose the best example <pre> block that actually demonstrates `key`."""
    blocks = [b for b in parse_pre_blocks(tags) if not is_prose_only_pre(b)]
    if not blocks:
        return ""

    # Normalize the known Cerner Wiki typo "MPAGES_SVC_ EVENT" -> "MPAGES_SVC_EVENT"
    blocks = [b.replace("MPAGES_SVC_ EVENT", "MPAGES_SVC_EVENT") for b in blocks]

    matching = [b for b in blocks if any(line_matches_key(ln, key) for ln in b.splitlines())]
    if matching:
        # Prefer the first block whose usage is a real CCL usage (not just a JSON/XML payload)
        return focus_example_block(matching[0], key)

    # Allow debugger abbreviations like "S R 12" / "S T 10" / "S W 1" for SET * commands
    if key.startswith("SET "):
        abbrev_pat = re.compile(rf"(?i)^\s*S\s+{re.escape(key[4])}\b")
        if any(abbrev_pat.search(ln) for b in blocks for ln in b.splitlines()):
            return truncate_lines(blocks[0], 12)

    return ""


def resolve_function_key(filename: str) -> tuple[str, str]:
    """Map a filename in ccl_functions.zip to (canonical_key, category)."""
    stem = filename
    for suffix in (
        "-Using-Discern-Explorer-Debugger.html",
        "-Using-Discern-Explorer.html",
        ".html",
    ):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    if stem in ALIAS_MAP:
        return ALIAS_MAP[stem]
    if stem.startswith("CALL-"):
        return f"CALL {stem[5:].upper()}", "CALL Command"
    if stem.startswith("SET-"):
        return f"SET {stem[4:].upper()}", "SET Command"

    key = stem.upper()
    if key in STATEMENT_KEYS:
        return key, "Statement"
    return key, "Function"


def parse_function_page(raw_html: str, key: str, category: str) -> dict:
    """Parse one HTML page into a structured doc entry."""
    soup = BeautifulSoup(raw_html, "html.parser")
    mc = soup.find(id="main-content") or soup.find("body") or soup
    sections = split_sections(mc)

    summary = parse_intro_summary(sections.get("intro", []))
    syntax = extract_syntax_text(sections.get("syntax", []))
    params, table_md = parse_metasymbols(sections.get("metasymbols", []))
    example = select_best_example(sections.get("examples", []), key)

    entry: dict = {"category": category}
    if syntax:
        entry["syntax"] = syntax
    if summary:
        entry["summary"] = summary
    if params:
        entry["params"] = params
    if table_md:
        entry["table"] = table_md
    if example:
        entry["example"] = example
    return entry


def parse_reference_archive(ref_zip_path: Path, docs: dict[str, dict]) -> None:
    """Extract Data Types, Directives, Operators, Clauses, and MPages routines from reference zip."""
    with zipfile.ZipFile(ref_zip_path) as zf:
        names = set(zf.namelist())

        dt_file = "Data-Types-Using-Discern-Explorer.html"
        if dt_file in names:
            soup = BeautifulSoup(zf.read(dt_file).decode("utf-8", errors="replace"), "html.parser")
            tables = soup.find_all("table")
            if tables:
                for tr in tables[0].find_all("tr")[1:]:
                    cells = [clean_ws(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
                    if len(cells) >= 3:
                        raw_type, usage, desc = cells[0], cells[1], cells[2]
                        key = raw_type.upper()
                        if key.startswith("N<LEN>") or key.startswith("P<PACK>"):
                            continue
                        if desc and desc[0].islower():
                            desc = desc[0].upper() + desc[1:]
                        docs[key] = {
                            "category": "Data Type",
                            "syntax": raw_type,
                            "summary": f"{desc} (Usage: {usage})",
                        }

        dir_file = "Using-Directives-in-Discern-Explorer.html"
        if dir_file in names:
            soup = BeautifulSoup(zf.read(dir_file).decode("utf-8", errors="replace"), "html.parser")
            tables = soup.find_all("table")
            if tables:
                for tr in tables[0].find_all("tr")[1:]:
                    cells = [clean_ws(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
                    if len(cells) >= 2:
                        name_cell, desc = cells[0], cells[1]
                        m = re.match(r"^(%#?[A-Z]+)(?:\s*\((%[A-Z]+)\))?", name_cell, re.I)
                        if m:
                            primary = m.group(1).upper()
                            alias = m.group(2).upper() if m.group(2) else None
                            entry = {
                                "category": "Directive",
                                "syntax": name_cell,
                                "summary": desc,
                            }
                            docs[primary] = entry
                            if alias:
                                docs[alias] = {**entry}

        extra_pages = [
            ("APPLINK-Using-Discern-Explorer.html", "APPLINK", "Function"),
            ("CCLEVENT-Using-Discern-Explorer.html", "CCLEVENT", "Function"),
            ("CCLLINK-Using-Discern-Explorer.html", "CCLLINK", "Function"),
            ("CCLLINKPOPUP-Using-Discern-Explorer.html", "CCLLINKPOPUP", "Function"),
            ("CCLNEWSESSIONWINDOW-Using-Discern-Explorer.html", "CCLNEWSESSIONWINDOW", "Function"),
            ("MPAGES_EVENT-Using-Discern-Explorer.html", "MPAGES_EVENT", "Function"),
            ("MPAGES_SVC_EVENT-Using-Discern-Explorer.html", "MPAGES_SVC_EVENT", "Function"),
            ("The-HEAD-REPORT-Clause-Using-Discern-Explorer.html", "HEAD REPORT", "Reportwriter Clause"),
            ("The-FOOT-REPORT-Clause-Using-Discern-Explorer.html", "FOOT REPORT", "Reportwriter Clause"),
            ("The-HEAD-PAGE-Clause-Using-Discern-Explorer.html", "HEAD PAGE", "Reportwriter Clause"),
            ("The-FOOT-PAGE-Clause-Using-Discern-Explorer.html", "FOOT PAGE", "Reportwriter Clause"),
            ("The-DETAIL-Clause-Using-Discern-Explorer.html", "DETAIL", "Reportwriter Clause"),
            ("GROUP-BY-Clause-in-Discern-Explorer.html", "GROUP BY", "SQL Clause"),
            ("HAVING-Clause-in-Discern-Explorer.html", "HAVING", "SQL Clause"),
            ("Defining-Control-Options-Using-the-WITH-Clause-Using-Discern-Explorer.html", "WITH", "SQL Clause"),
            ("Defining-a-Record-Structure-Using-Discern-Explorer.html", "RECORD", "Command"),
            ("Defining-Prompts-Using-Discern-Explorer.html", "PROMPT", "Command"),
            ("Discern-Explorer-DONTCARE-Using-Discern-Explorer.html", "DONTCARE", "Control Option"),
            ("Using-the-DUMMYT-Table-in-Discern-Explorer.html", "DUMMYT", "Built-in Table"),
        ]
        for fname, key, category in extra_pages:
            if fname in names and key not in docs:
                raw = zf.read(fname).decode("utf-8", errors="replace")
                entry = parse_function_page(raw, key, category)
                if "syntax" not in entry:
                    soup = BeautifulSoup(raw, "html.parser")
                    mc = soup.find(id="main-content") or soup.find("body") or soup
                    pre = mc.find("pre")
                    if pre:
                        pre_txt = truncate_lines(clean_pre(pre.get_text()), 8)
                        if pre_txt:
                            entry["syntax"] = pre_txt
                docs[key] = entry

        op_file = "Where-Clause-Relational-Operators-Using-Discern-Explorer.html"
        if op_file in names:
            soup = BeautifulSoup(zf.read(op_file).decode("utf-8", errors="replace"), "html.parser")
            for tbl in soup.find_all("table"):
                for tr in tbl.find_all("tr")[1:]:
                    cells = [clean_ws(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
                    if len(cells) >= 3 and cells[0].upper() in {"BETWEEN", "IN"}:
                        op_key = cells[0].upper()
                        if op_key not in docs:
                            docs[op_key] = {
                                "category": "Relational Operator",
                                "summary": cells[1],
                                "example": cells[2],
                            }


EXAMPLE_OVERRIDES: dict[str, str] = {
    "IF": (
        "IF (person_id_var > 0.0)\n"
        '    CALL ECHO("Valid person")\n'
        "ELSEIF (encntr_id_var > 0.0)\n"
        '    CALL ECHO("Valid encounter")\n'
        "ELSE\n"
        '    CALL ECHO("Missing ID")\n'
        "ENDIF"
    ),
    "FOR": (
        "FOR (idx = 1 TO SIZE(rec->list, 5))\n"
        "    CALL ECHO(rec->list[idx].name)\n"
        "ENDFOR"
    ),
    "WHILE": (
        "WHILE (idx <= 10)\n"
        "    SET idx = idx + 1\n"
        "ENDWHILE"
    ),
    "CASE": (
        "CASE (status_flag)\n"
        '    OF 1: SET label = "Active"\n'
        '    OF 2: SET label = "Inactive"\n'
        '    ELSE: SET label = "Unknown"\n'
        "ENDCASE"
    ),
}


CURATED_ENTRIES: dict[str, dict] = {
    "CALL": {
        "category": "Statement",
        "syntax": "CALL command_or_subroutine(arg1, arg2, ...)",
        "summary": "Invokes a Discern Explorer CALL command (e.g., CALL ECHO, CALL PARSER, CALL ECHORECORD) or a user-defined SUBROUTINE without capturing a return value.",
    },
    "DECLARE": {
        "category": "Statement",
        "syntax": "DECLARE var_name = data_type [WITH scope_option, noconstant(val) | constant(val)]\nDECLARE sub_name(param1 = type, ...) = return_type",
        "summary": "Explicitly declares a variable or forward-declares a subroutine with its data type, scope (e.g., PROTECT), and initial or constant value.",
        "example": "declare v_idx = i4 with protect, noconstant(0)\ndeclare my_sub(p_id = f8) = i2",
    },
    "SUBROUTINE": {
        "category": "Statement",
        "syntax": "SUBROUTINE sub_name(param1, param2)\n  ...\n  RETURN(value)\nEND",
        "summary": "Defines a reusable subroutine block terminated by END. Subroutines are typically forward-declared with DECLARE and invoked with CALL or inside expressions.",
    },
    "FREE": {
        "category": "Command",
        "syntax": "FREE RECORD record_name\nFREE SET var_name\nFREE DEFINE macro_name",
        "summary": "Releases memory or removes an existing record structure, variable, or macro definition before re-declaring it.",
    },
    "FREE RECORD": {
        "category": "Command",
        "syntax": "FREE RECORD record_name",
        "summary": "Deallocates an existing record structure and frees its memory before a new RECORD definition.",
    },
    "ENDIF": {
        "category": "Statement",
        "syntax": "IF (condition)\n  ...\nENDIF",
        "summary": "Closes an IF / ELSEIF / ELSE conditional block.",
    },
    "ENDFOR": {
        "category": "Statement",
        "syntax": "FOR (var = start TO stop [STEP n])\n  ...\nENDFOR",
        "summary": "Closes a FOR loop block.",
    },
    "ENDWHILE": {
        "category": "Statement",
        "syntax": "WHILE (condition)\n  ...\nENDWHILE",
        "summary": "Closes a WHILE loop block.",
    },
    "ENDCASE": {
        "category": "Statement",
        "syntax": "CASE (expr)\n  OF val: ...\n  ELSE: ...\nENDCASE",
        "summary": "Closes a CASE selection block.",
    },
    "ELSE": {
        "category": "Statement",
        "syntax": "IF (condition)\n  ...\nELSE\n  ...\nENDIF",
        "summary": "Executes the fallback branch when preceding IF / ELSEIF conditions evaluate to false (or default branch in CASE).",
    },
    "ELSEIF": {
        "category": "Statement",
        "syntax": "ELSEIF (condition)",
        "summary": "Tests an additional condition inside an IF block when earlier IF / ELSEIF branches are false.",
    },
    "GO": {
        "category": "Command",
        "syntax": "command ... GO",
        "summary": "Terminates and executes top-level Discern Explorer commands (such as SELECT, DROP PROGRAM, CREATE PROGRAM, UPDATE, DELETE, SET TRACE) outside a program block.",
    },
    "DROP PROGRAM": {
        "category": "Command",
        "syntax": "DROP PROGRAM program_name[:group] GO",
        "summary": "Removes an existing compiled CCL program object from the object library before recompiling with CREATE PROGRAM.",
    },
    "CREATE PROGRAM": {
        "category": "Command",
        "syntax": "CREATE PROGRAM program_name[:group]\n  ...\nEND GO",
        "summary": "Begins a compiled CCL program definition terminated by END GO.",
    },
    "PLAN": {
        "category": "SQL Clause",
        "syntax": "PLAN table_alias [WHERE qualification]",
        "summary": "Specifies the driving table and qualification order for a multi-table SELECT query.",
    },
    "JOIN": {
        "category": "SQL Clause",
        "syntax": "JOIN table_alias WHERE qualification",
        "summary": "Joins an additional table to a previously planned table in a SELECT query.",
    },
    "PROTECT": {
        "category": "Scope Option",
        "syntax": "DECLARE var = type WITH PROTECT",
        "summary": "Restricts a variable or record structure's visibility to the current program or subroutine so it does not leak or collide with caller/child scripts.",
    },
    "NOCONSTANT": {
        "category": "Declaration Option",
        "syntax": "DECLARE var = type WITH NOCONSTANT(initial_value)",
        "summary": "Initializes a mutable declared variable with the specified starting value.",
    },
    "CONSTANT": {
        "category": "Declaration Option",
        "syntax": "DECLARE var = type WITH CONSTANT(value)",
        "summary": "Declares a read-only constant variable whose value cannot be reassigned.",
    },
    "UAR_GET_CODE_BY": {
        "category": "UAR Function",
        "syntax": "UAR_GET_CODE_BY(match_type, code_set, match_value)",
        "summary": "Looks up a Cerner Millennium code_value (F8) from the CODE_VALUE cache by MEANING, DISPLAYKEY, DISPLAY, or DESCRIPTION.",
        "params": [
            {"name": "match_type", "description": 'Lookup key type: "MEANING", "DISPLAYKEY", "DISPLAY", or "DESCRIPTION".'},
            {"name": "code_set", "description": "Integer code set number (I4)."},
            {"name": "match_value", "description": "String value to match within the code set."},
        ],
        "example": 'declare mrn_cd = f8 with protect, constant(uar_get_code_by("MEANING", 4, "MRN"))',
    },
    "UAR_GET_CODE_DISPLAY": {
        "category": "UAR Function",
        "syntax": "UAR_GET_CODE_DISPLAY(code_value)",
        "summary": "Returns the display text (VC) for a Millennium code_value (F8).",
        "params": [{"name": "code_value", "description": "Numeric code_value (F8)."}],
    },
    "UAR_GET_CODE_MEANING": {
        "category": "UAR Function",
        "syntax": "UAR_GET_CODE_MEANING(code_value)",
        "summary": "Returns the CDF meaning (C12/VC) for a Millennium code_value (F8).",
        "params": [{"name": "code_value", "description": "Numeric code_value (F8)."}],
    },
    "UAR_GET_CODE_DESCRIPTION": {
        "category": "UAR Function",
        "syntax": "UAR_GET_CODE_DESCRIPTION(code_value)",
        "summary": "Returns the description text (VC) for a Millennium code_value (F8).",
        "params": [{"name": "code_value", "description": "Numeric code_value (F8)."}],
    },
    "UAR_GET_CODE_BY_CKI": {
        "category": "UAR Function",
        "syntax": "UAR_GET_CODE_BY_CKI(cki_string)",
        "summary": "Returns the code_value (F8) matching a Cerner Knowledge Index (CKI) string.",
        "params": [{"name": "cki_string", "description": 'CKI string (e.g., "CKI.CODEVALUE!...").'}],
    },
    "UAR_GET_MEANING_BY_CODESET": {
        "category": "UAR Function",
        "syntax": "UAR_GET_MEANING_BY_CODESET(code_set, meaning, occurrence, code_value)",
        "summary": "Retrieves a code_value by code set and CDF meaning when multiple code values may share the same meaning.",
        "params": [
            {"name": "code_set", "description": "Integer code set number (I4)."},
            {"name": "meaning", "description": "CDF meaning string (VC)."},
            {"name": "occurrence", "description": "1-based index of the matching code_value (I4)."},
            {"name": "code_value", "description": "Output F8 variable receiving the code_value."},
        ],
    },
    "UAR_GET_DISPLAYKEY": {
        "category": "UAR Function",
        "syntax": "UAR_GET_DISPLAYKEY(code_value)",
        "summary": "Returns the uppercase alphanumeric display_key (VC) for a Millennium code_value (F8).",
        "params": [{"name": "code_value", "description": "Numeric code_value (F8)."}],
    },
    "UAR_FMT_ACCESSION": {
        "category": "UAR Function",
        "syntax": "UAR_FMT_ACCESSION(accession, format_ind)",
        "summary": "Formats a raw accession number string for display or storage.",
        "params": [
            {"name": "accession", "description": "Raw or formatted accession string (VC)."},
            {"name": "format_ind", "description": "0 to format for display (hyphenated), 1 to unformat for storage."},
        ],
    },
    "CURDATE": {
        "category": "System Variable",
        "summary": "Built-in system variable containing the current date (number of days since Dec 31, 1840).",
    },
    "CURTIME": {
        "category": "System Variable",
        "summary": "Built-in system variable containing the current time in HHMM integer format.",
    },
    "CURTIME2": {
        "category": "System Variable",
        "summary": "Built-in system variable containing the current time in HHMMSS integer format.",
    },
    "CURTIME3": {
        "category": "System Variable",
        "summary": "Built-in system variable containing the current time in HHMMSSCC (hundredths of a second) integer format.",
    },
    "CURQUAL": {
        "category": "System Variable",
        "summary": "Built-in system variable containing the number of rows qualified/processed by the most recent SELECT, UPDATE, INSERT, or DELETE.",
    },
    "CURUSER": {
        "category": "System Variable",
        "summary": "Built-in system variable containing the current Millennium username.",
    },
    "CURDOMAIN": {
        "category": "System Variable",
        "summary": "Built-in system variable containing the current Millennium domain/environment name.",
    },
    "CURREV": {
        "category": "System Variable",
        "summary": "Built-in system variable containing the current Discern Explorer / CCL revision string.",
    },
    "CURSYS": {
        "category": "System Variable",
        "summary": "Built-in system variable identifying the current operating system (e.g., AIX, WIN, VMS, LNX).",
    },
    "CURSYS2": {
        "category": "System Variable",
        "summary": "Built-in system variable identifying the extended operating system platform.",
    },
    "CURUTC": {
        "category": "System Variable",
        "summary": "Built-in system variable indicating whether UTC mode is enabled (1 = UTC enabled, 0 = disabled).",
    },
    "SYSDATE": {
        "category": "System Variable",
        "summary": "Represents the current RDBMS system date/time.",
    },
    "OUTDEV": {
        "category": "System Variable",
        "summary": "Standard output device parameter ($OUTDEV) passed into CCL reports and Discern Explorer scripts.",
    },
}


def build_all_docs(functions_zip: Path, reference_zip: Path) -> dict[str, dict]:
    """Parse both zip archives and merge curated CCL entries."""
    docs: dict[str, dict] = {}

    with zipfile.ZipFile(functions_zip) as zf:
        for name in sorted(zf.namelist()):
            if name in SKIP_FUNCTION_FILES or not name.endswith(".html"):
                continue
            key, category = resolve_function_key(name)
            raw = zf.read(name).decode("utf-8", errors="replace")
            docs[key] = parse_function_page(raw, key, category)

    if "GO TO" in docs and "GOTO" not in docs:
        docs["GOTO"] = {**docs["GO TO"]}

    for key in list(docs.keys()):
        if key.startswith("CALL "):
            cmd = key[5:]
            if cmd not in docs:
                docs[cmd] = {**docs[key]}

    parse_reference_archive(reference_zip, docs)

    for key, entry in CURATED_ENTRIES.items():
        if key not in docs:
            docs[key] = entry

    for key, ex in EXAMPLE_OVERRIDES.items():
        if key in docs:
            docs[key]["example"] = ex

    return dict(sorted(docs.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data/ccl-docs.json from CCL HTML zip archives.")
    parser.add_argument("--functions-zip", required=True, help="Path to ccl_functions.zip")
    parser.add_argument("--reference-zip", required=True, help="Path to ccl_programming_reference.zip")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "data" / "ccl-docs.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    docs = build_all_docs(Path(args.functions_zip), Path(args.reference_zip))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(docs, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    size_kb = out_path.stat().st_size / 1024
    print(f"Generated {out_path} with {len(docs)} entries ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
