# tabulate

A lightweight, single-file CLI tool that converts messy data into organized CSV tables.

## Features

- **Auto-detects format** - JSON, JSONL, key-value pairs, bullet lists, delimited text, and more
- **Multiple input sources** - files, stdin, or clipboard
- **Clipboard support** - read from and write to system clipboard
- **Preview mode** - see formatted table before committing to CSV
- **Zero dependencies** - pure Python 3, runs anywhere

## Installation

Just copy `tabulate.py` to your PATH:

```bash
# Make it executable
chmod +x tabulate.py

# Option 1: Run directly
./tabulate.py data.json

# Option 2: Copy to PATH
cp tabulate.py /usr/local/bin/tabulate
```

## Usage

```bash
# From file
python tabulate.py data.json

# From stdin
cat data.txt | python tabulate.py

# From clipboard
python tabulate.py --from-clipboard

# Output to file
python tabulate.py -o output.csv input.txt

# Output to clipboard
python tabulate.py --to-clipboard input.json

# Preview mode (see formatted table)
python tabulate.py --preview data.json

# Force format
python tabulate.py --format jsonl logs.txt

# Inspect detected format
python tabulate.py --inspect data.txt
```

## Supported Formats

| Format | Auto-detect | Example |
|--------|-------------|---------|
| JSON Array of Objects | ✅ | `[{"name": "Alice"}, {"name": "Bob"}]` |
| JSON Array | ✅ | `["a", "b", "c"]` |
| JSON Object | ✅ | `{"host": "server1", "port": 8080}` |
| JSONL | ✅ | `{"id": 1}\n{"id": 2}` |
| Python-style KV | ✅ | `['key']: ['value']` |
| Key-Value | ✅ | `key: value` or `key = value` |
| Bullet Lists | ✅ | `- item` or `* item` or `1. item` |
| CSV/TSV | ✅ | Comma or tab-separated |
| Plain Lines | ✅ | One value per line |

## Examples

### JSON Array of Objects

```bash
echo '[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]' | python tabulate.py
```

Output:
```csv
name,age
Alice,30
Bob,25
```

### Messy Python-style Data

```bash
echo "['asv']: ['asv123'], ['env']: ['qa']" | python tabulate.py --preview
```

Output:
```
asv    | env
-------+----
asv123 | qa
```

### Bullet List

```bash
echo -e "- Buy milk\n- Walk dog\n- Call mom" | python tabulate.py
```

Output:
```csv
item
Buy milk
Walk dog
Call mom
```

### Key-Value Config

```bash
echo -e "host: server1\nport: 8080\nenv: prod" | python tabulate.py
```

Output:
```csv
key,value
host,server1
port,8080
env,prod
```

### Nested JSON (Flattened)

```bash
echo '[{"user": {"name": "Alice", "id": 1}}]' | python tabulate.py
```

Output:
```csv
user.name,user.id
Alice,1
```

## CLI Options

| Option | Description |
|--------|-------------|
| `INPUT` | Input file (optional, defaults to stdin) |
| `-o, --output FILE` | Write to file instead of stdout |
| `--from-clipboard` | Read from system clipboard |
| `--to-clipboard` | Write to system clipboard |
| `-f, --format FORMAT` | Force format: `json`, `jsonl`, `kv`, `list`, `csv`, `tsv`, `lines`, `python-kv`, `auto` |
| `--preview` | Show formatted preview table |
| `--preview-rows N` | Number of rows in preview (default: 10) |
| `--inspect` | Show detected format and schema |
| `-v, --verbose` | Verbose output |

## License

MIT
