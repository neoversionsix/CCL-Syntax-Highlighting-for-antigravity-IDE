"use strict";

const docs = require("./data/ccl-docs.json");

const PARAMETERIZED_TYPE_RE = /^(C|VC|GC|GVC|ZC|ZVC|ZGC|ZGVC)([1-9]\d*)$/;

/**
 * Scan a single line up to `limit` (clamped to line length) and return the
 * lexical state at `limit`. In Cerner CCL, backslash (\) is a literal character
 * inside strings, NOT an escape character.
 */
function getLineContext(lineText, limit, initialBlockComment = false) {
    const end = Math.max(0, Math.min(limit, lineText.length));
    let inString = null;
    let inBlockComment = initialBlockComment;
    let inLineComment = false;

    for (let i = 0; i < end; i++) {
        const ch = lineText[i];
        const next = lineText[i + 1];

        if (inLineComment) {
            break;
        }
        if (inBlockComment) {
            if (ch === "*" && next === "/") {
                inBlockComment = false;
                i++;
            }
            continue;
        }
        if (inString) {
            if (ch === inString) {
                inString = null;
            }
            continue;
        }
        if (ch === ";") {
            inLineComment = true;
            break;
        }
        if (ch === "!" && next !== "=") {
            inLineComment = true;
            break;
        }
        if (ch === "/" && next === "*") {
            inBlockComment = true;
            i++;
            continue;
        }
        if (ch === '"' || ch === "'" || ch === "^" || ch === "~") {
            inString = ch;
        }
    }

    return {
        inString: inString !== null,
        inBlockComment,
        inLineComment,
        inCommentOrString: inString !== null || inBlockComment || inLineComment,
    };
}

/**
 * Determine whether `position` lies inside a multi-line block comment opened on an earlier line.
 */
function isPrecededByOpenBlockComment(document, lineNumber) {
    const startLine = Math.max(0, lineNumber - 500);
    let inBlockComment = false;
    for (let ln = startLine; ln < lineNumber; ln++) {
        const ctx = getLineContext(document.lineAt(ln).text, Number.MAX_SAFE_INTEGER, inBlockComment);
        inBlockComment = ctx.inBlockComment;
    }
    return inBlockComment;
}

/**
 * Find the token span around `charIndex` matching `regex`.
 */
function findSpanAt(lineText, charIndex, regex) {
    let fallback = null;
    for (const match of lineText.matchAll(regex)) {
        const start = match.index;
        const end = start + match[0].length;
        if (charIndex >= start && charIndex < end) {
            return { text: match[0], start, end };
        }
        if (charIndex === end) {
            fallback = { text: match[0], start, end };
        }
    }
    return fallback;
}

function isMemberAccessed(prefix) {
    return /(?:->\s*|\.)$/.test(prefix);
}

/**
 * Resolve documentation entry for the CCL token at `charIndex` in `lineText`.
 * Returns `{ key, entry, range: [start, end] }` or `null`.
 */
function resolveDocAtPosition(lineText, charIndex, docMap = docs, initialBlockComment = false) {
    if (charIndex < 0 || charIndex > lineText.length) {
        return null;
    }
    const ctx = getLineContext(lineText, charIndex, initialBlockComment);
    if (ctx.inCommentOrString) {
        return null;
    }

    // 1. Directives (%i, %include, %#ifdef, ...)
    const dirSpan = findSpanAt(lineText, charIndex, /%#?[A-Za-z]+/g);
    if (dirSpan) {
        const key = dirSpan.text.toUpperCase();
        if (Object.prototype.hasOwnProperty.call(docMap, key)) {
            return { key, entry: docMap[key], range: [dirSpan.start, dirSpan.end] };
        }
        return null;
    }

    // 2. Identifier / keyword token
    const wordSpan = findSpanAt(lineText, charIndex, /[A-Za-z_][A-Za-z0-9_]*/g);
    if (!wordSpan) {
        return null;
    }

    const before = lineText.slice(0, wordSpan.start);
    const after = lineText.slice(wordSpan.end);

    // Skip record fields and table columns (e.g., REPLY->TEXT, p.format)
    if (isMemberAccessed(before)) {
        return null;
    }

    const upper = wordSpan.text.toUpperCase();

    // 3. Two-word phrases with previous word (e.g., CALL ECHO, SET TRACE, HEAD REPORT)
    const prevMatch = before.match(/([A-Za-z_][A-Za-z0-9_]*)\s+$/);
    if (prevMatch) {
        const prevStart = wordSpan.start - prevMatch[0].length;
        const beforePrev = lineText.slice(0, prevStart);
        if (!isMemberAccessed(beforePrev)) {
            const phrase = `${prevMatch[1].toUpperCase()} ${upper}`;
            if (Object.prototype.hasOwnProperty.call(docMap, phrase)) {
                return { key: phrase, entry: docMap[phrase], range: [prevStart, wordSpan.end] };
            }
        }
    }

    // 4. Two-word phrases with next word (e.g., hovering CALL in CALL ECHO, HEAD in HEAD REPORT)
    const nextMatch = after.match(/^\s+([A-Za-z_][A-Za-z0-9_]*)/);
    if (nextMatch) {
        const phrase = `${upper} ${nextMatch[1].toUpperCase()}`;
        if (Object.prototype.hasOwnProperty.call(docMap, phrase)) {
            const nextEnd = wordSpan.end + nextMatch[0].length;
            return { key: phrase, entry: docMap[phrase], range: [wordSpan.start, nextEnd] };
        }
    }

    // 5. Exact word match (guard single-letter 'H' data type to assignment/declaration context)
    if (Object.prototype.hasOwnProperty.call(docMap, upper)) {
        if (upper === "H") {
            const isTypePos = /=\s*$/.test(before) && !/^\s*(?:\.|->|\(|\[)/.test(after);
            if (!isTypePos) {
                return null;
            }
        }
        return { key: upper, entry: docMap[upper], range: [wordSpan.start, wordSpan.end] };
    }

    // 6. Parameterized character data types (C10, VC100, GC20, etc.) only after '='
    const paramTypeMatch = upper.match(PARAMETERIZED_TYPE_RE);
    if (paramTypeMatch && /=\s*$/.test(before) && !/^\s*(?:\.|->|\(|\[)/.test(after)) {
        const typeKey = `${paramTypeMatch[1]}<LEN>`;
        if (Object.prototype.hasOwnProperty.call(docMap, typeKey)) {
            return { key: typeKey, entry: docMap[typeKey], range: [wordSpan.start, wordSpan.end] };
        }
    }

    return null;
}

/**
 * Split parameter list string from a CCL syntax signature into clean parameter labels.
 */
function extractSignatureParameters(syntaxLine) {
    const openIdx = syntaxLine.indexOf("(");
    if (openIdx === -1) {
        return [];
    }

    let depth = 0;
    let closeIdx = -1;
    for (let i = openIdx; i < syntaxLine.length; i++) {
        if (syntaxLine[i] === "(") {
            depth++;
        } else if (syntaxLine[i] === ")") {
            depth--;
            if (depth === 0) {
                closeIdx = i;
                break;
            }
        }
    }
    const rawArgs = (closeIdx !== -1 ? syntaxLine.slice(openIdx + 1, closeIdx) : syntaxLine.slice(openIdx + 1)).trim();
    if (!rawArgs) {
        return [];
    }

    // Normalize "[,opt]" -> ", [opt]" so optional arguments split cleanly on commas
    const normalized = rawArgs.replace(/\[\s*,\s*/g, ", [").replace(/\{\s*,\s*/g, ", {");

    const parts = [];
    let current = "";
    let pDepth = 0;
    for (let i = 0; i < normalized.length; i++) {
        const ch = normalized[i];
        if (ch === "(") {
            pDepth++;
            current += ch;
        } else if (ch === ")") {
            if (pDepth > 0) {
                pDepth--;
            }
            current += ch;
        } else if (ch === "," && pDepth === 0) {
            parts.push(current.trim());
            current = "";
        } else {
            current += ch;
        }
    }
    if (current.trim()) {
        parts.push(current.trim());
    }

    return parts
        .map((part) => {
            // Balance stray trailing ']' or '}' left over from nested optional brackets
            let s = part;
            const openSq = (s.match(/\[/g) || []).length;
            const closeSq = (s.match(/\]/g) || []).length;
            if (openSq > closeSq) {
                s = s + "]".repeat(openSq - closeSq);
            } else if (closeSq > openSq) {
                s = s.replace(new RegExp(`\\]{1,${closeSq - openSq}}$`), "");
            }
            const openCurly = (s.match(/\{/g) || []).length;
            const closeCurly = (s.match(/\}/g) || []).length;
            if (openCurly > closeCurly) {
                s = s + "}".repeat(openCurly - closeCurly);
            } else if (closeCurly > openCurly) {
                s = s.replace(new RegExp(`\\}{1,${closeCurly - openCurly}}$`), "");
            }
            return s.trim();
        })
        .filter(Boolean);
}

function normalizeParamName(name) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

/**
 * Resolve SignatureHelp details for the active call enclosing `charIndex` on `lineText`.
 */
function resolveSignatureAtPosition(lineText, charIndex, docMap = docs, initialBlockComment = false) {
    if (charIndex < 0 || charIndex > lineText.length) {
        return null;
    }
    const ctx = getLineContext(lineText, charIndex, initialBlockComment);
    if (ctx.inCommentOrString) {
        return null;
    }

    const stack = [];
    let inString = null;
    let inBlockComment = initialBlockComment;

    for (let i = 0; i < charIndex; i++) {
        const ch = lineText[i];
        const next = lineText[i + 1];

        if (inBlockComment) {
            if (ch === "*" && next === "/") {
                inBlockComment = false;
                i++;
            }
            continue;
        }
        if (inString) {
            if (ch === inString) {
                inString = null;
            }
            continue;
        }
        if (ch === ";" || (ch === "!" && next !== "=")) {
            return null;
        }
        if (ch === "/" && next === "*") {
            inBlockComment = true;
            i++;
            continue;
        }
        if (ch === '"' || ch === "'" || ch === "^" || ch === "~") {
            inString = ch;
            continue;
        }
        if (ch === "(") {
            stack.push({ openIdx: i, commaCount: 0 });
        } else if (ch === ")" && stack.length > 0) {
            stack.pop();
        } else if (ch === "," && stack.length > 0) {
            stack[stack.length - 1].commaCount++;
        }
    }

    while (stack.length > 0) {
        const frame = stack.pop();
        const beforeParen = lineText.slice(0, frame.openIdx);
        const fnMatch = beforeParen.match(/([A-Za-z_][A-Za-z0-9_]*)\s*$/);
        if (!fnMatch) {
            continue;
        }
        const fnStart = frame.openIdx - fnMatch[0].length;
        const beforeFn = lineText.slice(0, fnStart);
        if (isMemberAccessed(beforeFn)) {
            continue;
        }

        const fnUpper = fnMatch[1].toUpperCase();
        let key = null;
        let entry = null;

        if (/\bCALL\s+$/i.test(beforeFn)) {
            const callKey = `CALL ${fnUpper}`;
            if (Object.prototype.hasOwnProperty.call(docMap, callKey)) {
                key = callKey;
                entry = docMap[callKey];
            }
        }
        if (!entry && Object.prototype.hasOwnProperty.call(docMap, fnUpper)) {
            key = fnUpper;
            entry = docMap[fnUpper];
        }
        if (!entry || !entry.syntax || !entry.syntax.includes("(")) {
            continue;
        }

        const firstLine = entry.syntax.split("\n")[0].trim();
        const paramLabels = extractSignatureParameters(firstLine);
        if (paramLabels.length === 0) {
            continue;
        }

        const paramDocByNorm = new Map();
        if (Array.isArray(entry.params)) {
            for (const p of entry.params) {
                paramDocByNorm.set(normalizeParamName(p.name), p.description);
            }
        }

        const parameters = paramLabels.map((label) => {
            const norm = normalizeParamName(label);
            let docText = paramDocByNorm.get(norm);
            if (!docText) {
                for (const [k, v] of paramDocByNorm.entries()) {
                    if (norm.includes(k) || k.includes(norm)) {
                        docText = v;
                        break;
                    }
                }
            }
            return { label, documentation: docText || undefined };
        });

        return {
            key,
            label: firstLine,
            activeParameter: Math.min(frame.commaCount, parameters.length - 1),
            parameters,
            entry,
        };
    }

    return null;
}

function buildHoverMarkdown(vscode, key, entry) {
    const md = new vscode.MarkdownString();
    const category = entry.category ? ` *(CCL ${entry.category})*` : "";
    md.appendMarkdown(`**${key}**${category}\n\n`);

    if (entry.syntax) {
        md.appendCodeblock(entry.syntax, "ccl");
    }
    if (entry.summary) {
        md.appendMarkdown(`${entry.summary}\n\n`);
    }
    if (Array.isArray(entry.params) && entry.params.length > 0) {
        md.appendMarkdown("**Parameters**\n");
        for (const p of entry.params) {
            md.appendMarkdown(`- \`${p.name}\`: ${p.description}\n`);
        }
        md.appendMarkdown("\n");
    }
    if (entry.table) {
        md.appendMarkdown(`${entry.table}\n\n`);
    }
    if (entry.example) {
        md.appendMarkdown("**Example**\n");
        md.appendCodeblock(entry.example, "ccl");
    }
    return md;
}

function activate(context) {
    const vscode = require("vscode");

    const hoverProvider = vscode.languages.registerHoverProvider("ccl", {
        provideHover(document, position) {
            const lineText = document.lineAt(position.line).text;
            const inBlock = isPrecededByOpenBlockComment(document, position.line);
            const resolved = resolveDocAtPosition(lineText, position.character, docs, inBlock);
            if (!resolved) {
                return null;
            }
            const range = new vscode.Range(
                position.line,
                resolved.range[0],
                position.line,
                resolved.range[1]
            );
            return new vscode.Hover(buildHoverMarkdown(vscode, resolved.key, resolved.entry), range);
        },
    });

    const signatureProvider = vscode.languages.registerSignatureHelpProvider(
        "ccl",
        {
            provideSignatureHelp(document, position) {
                const lineText = document.lineAt(position.line).text;
                const inBlock = isPrecededByOpenBlockComment(document, position.line);
                const sigInfo = resolveSignatureAtPosition(lineText, position.character, docs, inBlock);
                if (!sigInfo) {
                    return null;
                }

                const sig = new vscode.SignatureInformation(sigInfo.label, sigInfo.entry.summary || "");
                sig.parameters = sigInfo.parameters.map(
                    (p) => new vscode.ParameterInformation(p.label, p.documentation || "")
                );

                const help = new vscode.SignatureHelp();
                help.signatures = [sig];
                help.activeSignature = 0;
                help.activeParameter = sigInfo.activeParameter;
                return help;
            },
        },
        "(",
        ","
    );

    context.subscriptions.push(hoverProvider, signatureProvider);
}

function deactivate() {}

module.exports = {
    activate,
    deactivate,
    getLineContext,
    resolveDocAtPosition,
    resolveSignatureAtPosition,
    extractSignatureParameters,
};
