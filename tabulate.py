#!/usr/bin/env python3
"""
tabulate - Convert messy data into organized CSV tables

A lightweight CLI tool that transforms arrays, lists, JSON, key-value pairs,
and other messy text data into clean CSV format.

Usage:
    python tabulate.py [OPTIONS] [INPUT_FILE]
    cat data.txt | python tabulate.py
    python tabulate.py --from-clipboard

Examples:
    python tabulate.py data.json
    python tabulate.py --format jsonl logs.txt
    python tabulate.py --from-clipboard --to-clipboard
    echo '["a", "b", "c"]' | python tabulate.py
"""

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
from typing import Any, Optional


# =============================================================================
# Clipboard Operations
# =============================================================================

def get_clipboard() -> str:
    """Read text from system clipboard."""
    if sys.platform == "darwin":
        result = subprocess.run(["pbpaste"], capture_output=True, text=True)
        return result.stdout
    elif sys.platform == "win32":
        result = subprocess.run(
            ["powershell", "-command", "Get-Clipboard"],
            capture_output=True, text=True
        )
        return result.stdout
    else:  # Linux
        for cmd in [["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout
            except FileNotFoundError:
                continue
        raise RuntimeError("No clipboard tool found. Install xclip or xsel.")


def set_clipboard(text: str) -> None:
    """Write text to system clipboard."""
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    elif sys.platform == "win32":
        subprocess.run(
            ["powershell", "-command", "Set-Clipboard", "-Value", text],
            check=True
        )
    else:  # Linux
        for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
            try:
                subprocess.run(cmd, input=text.encode(), check=True)
                return
            except FileNotFoundError:
                continue
        raise RuntimeError("No clipboard tool found. Install xclip or xsel.")


# =============================================================================
# Format Detection
# =============================================================================

def detect_format(text: str) -> str:
    """Auto-detect the format of the input text."""
    text = text.strip()
    if not text:
        return "empty"
    
    # Check for JSON array
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                if all(isinstance(item, dict) for item in data):
                    return "json-array-objects"
                return "json-array"
        except json.JSONDecodeError:
            pass
    
    # Check for JSON object
    if text.startswith("{"):
        try:
            json.loads(text)
            return "json-object"
        except json.JSONDecodeError:
            pass
    
    # Check for JSONL (each line is valid JSON)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        json_lines = 0
        for line in lines[:20]:  # Sample first 20 lines
            try:
                json.loads(line)
                json_lines += 1
            except json.JSONDecodeError:
                pass
        if json_lines / len(lines[:20]) >= 0.7:
            return "jsonl"
    
    # Check for Python-style dict/list notation: ['key']: ['value']
    if re.search(r"\['.+?'\]\s*:\s*\['.+?'\]", text):
        return "python-kv"
    
    # Check for key-value pairs (key: value or key = value)
    kv_pattern = r"^[^:=]+[:=].+"
    kv_matches = sum(1 for line in lines if re.match(kv_pattern, line))
    if kv_matches / len(lines) >= 0.5:
        return "kv"
    
    # Check for bullet/numbered lists
    list_pattern = r"^(\s*[-*•]\s+|\s*\d+\.\s+|\s*\[[ x]\]\s+)"
    list_matches = sum(1 for line in lines if re.match(list_pattern, line))
    if list_matches / len(lines) >= 0.5:
        return "list"
    
    # Check for delimiter-separated values
    for delim, name in [("\t", "tsv"), (",", "csv"), ("|", "psv"), (";", "ssv")]:
        counts = [line.count(delim) for line in lines[:10] if line]
        if counts and min(counts) > 0 and max(counts) - min(counts) <= 1:
            return f"delim:{delim}"
    
    # Default to lines
    return "lines"


# =============================================================================
# Parsers
# =============================================================================

def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten a nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        elif isinstance(v, list):
            if all(isinstance(i, (str, int, float, bool, type(None))) for i in v):
                items.append((new_key, ", ".join(str(i) for i in v)))
            else:
                items.append((new_key, json.dumps(v)))
        else:
            items.append((new_key, v))
    return dict(items)


def parse_json_array_objects(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse JSON array of objects."""
    data = json.loads(text)
    if not data:
        return [], []
    
    # Flatten and collect all columns
    flattened = [flatten_dict(item) if isinstance(item, dict) else {"value": item} for item in data]
    all_keys = []
    seen = set()
    for item in flattened:
        for key in item.keys():
            if key not in seen:
                all_keys.append(key)
                seen.add(key)
    
    rows = []
    for item in flattened:
        row = [str(item.get(key, "")) for key in all_keys]
        rows.append(row)
    
    return all_keys, rows


def parse_json_array(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse JSON array of primitives."""
    data = json.loads(text)
    return ["value"], [[str(item)] for item in data]


def parse_json_object(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse single JSON object."""
    data = json.loads(text)
    flattened = flatten_dict(data)
    return list(flattened.keys()), [[str(v) for v in flattened.values()]]


def parse_jsonl(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse JSON Lines format."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    all_keys = []
    seen = set()
    flattened_items = []
    
    for line in lines:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                flattened = flatten_dict(item)
            else:
                flattened = {"value": item}
            flattened_items.append(flattened)
            for key in flattened.keys():
                if key not in seen:
                    all_keys.append(key)
                    seen.add(key)
        except json.JSONDecodeError:
            continue
    
    rows = [[str(item.get(key, "")) for key in all_keys] for item in flattened_items]
    return all_keys, rows


def parse_python_kv(text: str) -> tuple[list[str], list[list[str]]]:
    """
    Parse Python-style key-value notation like:
    "['asv']: ['asv123'], ['env']: ['qa']"
    
    Produces a row per combination or expands into columns.
    """
    # Extract all ['key']: ['value'] pairs
    pattern = r"\['([^']+)'\]\s*:\s*\['([^']+)'\]"
    matches = re.findall(pattern, text)
    
    if not matches:
        # Try alternative patterns
        # key: [value1, value2] or key: value
        alt_pattern = r"(\w+)\s*:\s*\[?([^\],\[]+)\]?"
        matches = re.findall(alt_pattern, text)
    
    if not matches:
        return ["value"], [[text]]
    
    # Group by key
    key_values: dict[str, list[str]] = {}
    for key, value in matches:
        key = key.strip()
        value = value.strip().strip("'\"")
        if key not in key_values:
            key_values[key] = []
        key_values[key].append(value)
    
    # Create columns from keys
    columns = list(key_values.keys())
    
    # Find max number of values
    max_values = max(len(v) for v in key_values.values()) if key_values else 1
    
    # Create rows (one per combination or pad shorter lists)
    rows = []
    for i in range(max_values):
        row = []
        for col in columns:
            values = key_values[col]
            row.append(values[i] if i < len(values) else "")
        rows.append(row)
    
    return columns, rows


def parse_kv(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse key-value pairs (key: value or key = value)."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    rows = []
    
    for line in lines:
        if ":" in line:
            key, _, value = line.partition(":")
        elif "=" in line:
            key, _, value = line.partition("=")
        else:
            continue
        rows.append([key.strip(), value.strip()])
    
    return ["key", "value"], rows


def parse_list(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse bullet or numbered lists."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    pattern = r"^(\s*[-*•]\s+|\s*\d+\.\s+|\s*\[[ x]\]\s+)"
    
    rows = []
    for line in lines:
        cleaned = re.sub(pattern, "", line).strip()
        if cleaned:
            rows.append([cleaned])
    
    return ["item"], rows


def parse_delimited(text: str, delimiter: str) -> tuple[list[str], list[list[str]]]:
    """Parse delimiter-separated values."""
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = list(reader)
    
    if not all_rows:
        return [], []
    
    # Assume first row is header
    headers = all_rows[0]
    rows = all_rows[1:] if len(all_rows) > 1 else []
    
    # Normalize row lengths
    max_cols = len(headers)
    normalized_rows = []
    for row in rows:
        if len(row) < max_cols:
            row = row + [""] * (max_cols - len(row))
        elif len(row) > max_cols:
            row = row[:max_cols]
        normalized_rows.append(row)
    
    return headers, normalized_rows


def parse_lines(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse as simple lines."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return ["value"], [[line] for line in lines]


def parse_array_string(value: str) -> list[str]:
    """Parse array-like strings into a list of values.
    
    Handles:
    - JSON arrays: ["a", "b"]
    - Python-style: ['a', 'b']
    - Simple comma-separated: a, b, c
    """
    value = value.strip()
    
    # Try JSON first
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        
        # Try Python-style: ['a', 'b']
        # Convert single quotes to double quotes for JSON parsing
        try:
            converted = value.replace("'", '"')
            parsed = json.loads(converted)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        
        # Manual extraction: ['a', 'b'] or [a, b]
        inner = value[1:-1] if value.endswith("]") else value[1:]
        pattern = r"'([^']+)'|\"([^\"]+)\"|([^,\[\]'\"]+)"
        matches = re.findall(pattern, inner)
        items = []
        for match in matches:
            item = (match[0] or match[1] or match[2]).strip()
            if item:
                items.append(item)
        if items:
            return items
    
    # Fallback: comma-separated
    if "," in value:
        return [item.strip() for item in value.split(",") if item.strip()]
    
    # Single value
    return [value] if value else []


def extract_column_arrays(text: str, column_name: str, delimiter: str = ",") -> tuple[list[str], list[list[str]]]:
    """Extract a specific column from CSV and expand array values.
    
    Returns a table with (row, value) for each item in each row's array.
    """
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = list(reader)
    
    if not all_rows:
        return [], []
    
    headers = all_rows[0]
    
    # Find column index
    try:
        col_idx = headers.index(column_name)
    except ValueError:
        # Try case-insensitive match
        lower_headers = [h.lower() for h in headers]
        try:
            col_idx = lower_headers.index(column_name.lower())
        except ValueError:
            raise ValueError(f"Column '{column_name}' not found. Available: {', '.join(headers)}")
    
    result_rows = []
    for row_num, row in enumerate(all_rows[1:], start=1):
        if col_idx >= len(row):
            continue
        
        cell_value = row[col_idx]
        items = parse_array_string(cell_value)
        
        for item in items:
            result_rows.append([str(row_num), item])
    
    return ["row", "value"], result_rows


def parse_input(text: str, format_override: Optional[str] = None, extract_column: Optional[str] = None) -> tuple[list[str], list[list[str]]]:
    """Parse input text into columns and rows."""
    
    # Handle column extraction mode
    if extract_column:
        return extract_column_arrays(text, extract_column)
    
    if format_override:
        fmt = format_override
    else:
        fmt = detect_format(text)
    
    if fmt == "empty":
        return [], []
    elif fmt == "json-array-objects":
        return parse_json_array_objects(text)
    elif fmt == "json-array":
        return parse_json_array(text)
    elif fmt == "json-object":
        return parse_json_object(text)
    elif fmt == "jsonl":
        return parse_jsonl(text)
    elif fmt == "python-kv":
        return parse_python_kv(text)
    elif fmt == "kv":
        return parse_kv(text)
    elif fmt == "list":
        return parse_list(text)
    elif fmt.startswith("delim:"):
        delimiter = fmt.split(":", 1)[1]
        return parse_delimited(text, delimiter)
    else:
        return parse_lines(text)


# =============================================================================
# Output
# =============================================================================

def to_csv(columns: list[str], rows: list[list[str]]) -> str:
    """Convert columns and rows to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue()


def preview_table(columns: list[str], rows: list[list[str]], limit: int = 10) -> str:
    """Create a formatted preview table."""
    if not columns:
        return "(empty table)"
    
    preview_rows = rows[:limit]
    all_data = [columns] + preview_rows
    
    # Calculate column widths
    widths = []
    for i in range(len(columns)):
        col_values = [str(row[i]) if i < len(row) else "" for row in all_data]
        widths.append(min(max(len(v) for v in col_values), 40))
    
    # Build table
    lines = []
    
    # Header
    header = " | ".join(str(columns[i]).ljust(widths[i])[:widths[i]] for i in range(len(columns)))
    lines.append(header)
    lines.append("-+-".join("-" * w for w in widths))
    
    # Rows
    for row in preview_rows:
        line = " | ".join(str(row[i] if i < len(row) else "").ljust(widths[i])[:widths[i]] for i in range(len(columns)))
        lines.append(line)
    
    if len(rows) > limit:
        lines.append(f"... and {len(rows) - limit} more rows")
    
    lines.append(f"\nTotal: {len(columns)} columns, {len(rows)} rows")
    
    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="tabulate",
        description="Convert messy data into organized CSV tables",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tabulate.py data.json              # Parse JSON file to CSV
  python tabulate.py --format jsonl logs.txt  # Force JSONL format
  cat list.txt | python tabulate.py         # Read from stdin
  python tabulate.py --from-clipboard       # Read from clipboard
  python tabulate.py -o output.csv input.txt  # Write to file
  python tabulate.py --preview data.json    # Preview without full output

Supported formats (auto-detected):
  - JSON arrays/objects
  - JSONL (newline-delimited JSON)
  - Python-style dicts: ['key']: ['value']
  - Key-value pairs (key: value, key = value)
  - Bullet/numbered lists
  - CSV/TSV/delimited text
  - Plain lines
        """
    )
    
    parser.add_argument("input", nargs="?", help="Input file (default: stdin)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--from-clipboard", action="store_true", help="Read from clipboard")
    parser.add_argument("--to-clipboard", action="store_true", help="Write to clipboard")
    parser.add_argument("-f", "--format", choices=[
        "json", "jsonl", "kv", "list", "csv", "tsv", "lines", "python-kv", "auto"
    ], default="auto", help="Force input format (default: auto-detect)")
    parser.add_argument("--preview", action="store_true", help="Show preview table instead of CSV")
    parser.add_argument("--preview-rows", type=int, default=10, help="Number of rows in preview")
    parser.add_argument("--no-header", action="store_true", help="Treat first row as data, not header (for delimited)")
    parser.add_argument("--extract-column", metavar="NAME", help="Extract a column containing arrays and expand into rows")
    parser.add_argument("--inspect", action="store_true", help="Show detected format and schema")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Read input
    try:
        if args.from_clipboard:
            text = get_clipboard()
            if args.verbose:
                print(f"Read {len(text)} chars from clipboard", file=sys.stderr)
        elif args.input:
            with open(args.input, "r", encoding="utf-8") as f:
                text = f.read()
            if args.verbose:
                print(f"Read {len(text)} chars from {args.input}", file=sys.stderr)
        else:
            if sys.stdin.isatty():
                parser.print_help()
                sys.exit(0)
            text = sys.stdin.read()
            if args.verbose:
                print(f"Read {len(text)} chars from stdin", file=sys.stderr)
    except Exception as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Detect format
    detected = detect_format(text)
    if args.verbose or args.inspect:
        print(f"Detected format: {detected}", file=sys.stderr)
    
    # Map CLI format to internal format
    format_map = {
        "json": None,  # Will auto-detect json-array vs json-object
        "jsonl": "jsonl",
        "kv": "kv",
        "list": "list",
        "csv": "delim:,",
        "tsv": "delim:\t",
        "lines": "lines",
        "python-kv": "python-kv",
        "auto": None,
    }
    format_override = format_map.get(args.format)
    
    # Parse
    try:
        columns, rows = parse_input(text, format_override, extract_column=args.extract_column)
    except Exception as e:
        print(f"Error parsing input: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.inspect:
        print(f"Columns ({len(columns)}): {', '.join(columns)}", file=sys.stderr)
        print(f"Rows: {len(rows)}", file=sys.stderr)
        if rows:
            print(f"Sample row: {rows[0]}", file=sys.stderr)
        sys.exit(0)
    
    # Output
    if args.preview:
        output = preview_table(columns, rows, args.preview_rows)
    else:
        output = to_csv(columns, rows)
    
    try:
        if args.to_clipboard:
            set_clipboard(output)
            print(f"Wrote {len(rows)} rows to clipboard", file=sys.stderr)
        elif args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(output)
            print(f"Wrote {len(rows)} rows to {args.output}", file=sys.stderr)
        else:
            print(output, end="")
    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
