import urllib.request
from bs4 import BeautifulSoup
import json
import re

def get_items(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        html = response.read()
    soup = BeautifulSoup(html, 'html.parser')
    
    items = set()
    for a in soup.find_all('a'):
        text = a.get_text(strip=True)
        if text and len(text) > 1 and not text.startswith('Discern Explorer') and not text.startswith('Command Syntax'):
            # Only keep ones that look like commands/functions (mostly uppercase or camelCase)
            if re.match(r'^[A-Za-z0-9_ ]+$', text):
                items.add(text)
    return items

functions_url = "https://neoversionsix.github.io/wh-bookmarks/ccl_functions/index.html"
ref_url = "https://neoversionsix.github.io/wh-bookmarks/ccl_programming_reference/index.html"

print("Fetching functions...")
functions = get_items(functions_url)

keywords = list(functions)
keywords.sort()

# Also add some common SQL/CCL keywords manually just in case
common = ["SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP BY", "ORDER BY", "HAVING", "UPDATE", "SET", "DELETE", "INSERT", "INTO", "VALUES", "CREATE", "DROP", "ALTER", "TABLE", "INDEX", "VIEW", "DECLARE", "BEGIN", "END", "IF", "THEN", "ELSE", "ELSEIF", "WHILE", "DO", "FOR", "TO", "STEP", "GO TO", "RETURN", "CALL", "EXECUTE", "COMMIT", "ROLLBACK", "WITH", "AS", "AND", "OR", "NOT", "IN", "LIKE", "BETWEEN", "IS", "NULL", "TRUE", "FALSE", "EVALUATE", "DETAIL", "FOOTING", "HEADING", "REPORT", "HEAD"]

for c in common:
    if c not in keywords:
        keywords.append(c)

# Build a regex string for keywords
keywords_regex = r'(?i)\b(' + '|'.join(sorted([k.replace(' ', r'\s+') for k in keywords], key=len, reverse=True)) + r')\b'

grammar = {
    "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
    "name": "Cerner CCL",
    "patterns": [
        {
            "include": "#comments"
        },
        {
            "include": "#strings"
        },
        {
            "include": "#keywords"
        },
        {
            "include": "#variables"
        },
        {
            "include": "#numbers"
        }
    ],
    "repository": {
        "comments": {
            "patterns": [
                {
                    "name": "comment.line.ccl",
                    "match": ";.*$"
                },
                {
                    "name": "comment.block.ccl",
                    "begin": "/\\*",
                    "end": "\\*/"
                }
            ]
        },
        "strings": {
            "patterns": [
                {
                    "name": "string.quoted.double.ccl",
                    "begin": "\"",
                    "end": "\"",
                    "patterns": [
                        {
                            "name": "constant.character.escape.ccl",
                            "match": "\\\\."
                        }
                    ]
                },
                {
                    "name": "string.quoted.single.ccl",
                    "begin": "'",
                    "end": "'",
                    "patterns": [
                        {
                            "name": "constant.character.escape.ccl",
                            "match": "\\\\."
                        }
                    ]
                }
            ]
        },
        "keywords": {
            "patterns": [
                {
                    "name": "keyword.control.ccl",
                    "match": keywords_regex
                }
            ]
        },
        "variables": {
            "patterns": [
                {
                    "name": "variable.other.ccl",
                    "match": "(?i)\\b[a-z_][a-z0-9_]*\\b"
                }
            ]
        },
        "numbers": {
            "patterns": [
                {
                    "name": "constant.numeric.ccl",
                    "match": "\\b\\d+(\\.\\d+)?\\b"
                }
            ]
        }
    },
    "scopeName": "source.ccl"
}

with open("syntaxes/ccl.tmLanguage.json", "w") as f:
    json.dump(grammar, f, indent=4)

print("Generated syntaxes/ccl.tmLanguage.json")
