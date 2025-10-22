# File System Monitor

A fast, simple file system monitor that detects changes between runs by tracking file modification times.

Available in two implementations:
- **Python** (`file_monitor.py`) - Easy to use, no compilation needed
- **Go** (`file_monitor.go`) - 4-6x faster, requires compilation (see BUILD_GO.md)

## What It Does

- Scans a directory tree and records file modification times
- Compares against previous scan to detect added, removed, and modified files
- Uses a summary hash for instant "changed/unchanged" detection
- Stores state in a compact binary format (msgpack) for fast save/load

## Usage

### Basic monitoring
```bash
./file_monitor.py /path/to/monitor
```

On first run, creates a baseline. On subsequent runs, shows what changed.

### Monitor current directory
```bash
./file_monitor.py .
```

### With verbose output (show all changes)
```bash
./file_monitor.py /path/to/monitor -v
```

### Performance benchmark
```bash
./file_monitor.py /path/to/monitor --timing
```

Runs two complete scans to compare cold vs warm cache performance.

### Monitor system root (with exclusions)
```bash
./file_monitor.py /
```

Automatically excludes `/proc`, `/sys`, `/run`, `/tmp`, etc.

To include normally-excluded directories:
```bash
./file_monitor.py / --all
```

### Custom exclusions
```bash
./file_monitor.py /home --exclude Downloads --exclude .cache
```

## Options

| Flag | Description |
|------|-------------|
| `path` | Directory to monitor (default: current directory) |
| `-v, --verbose` | Show all changes without truncation |
| `--exclude PATTERN` | Exclude paths containing PATTERN (repeatable) |
| `--all` | Include noisy directories when monitoring root |
| `--timing` | Run performance benchmark |

## How It Works

1. **Scan:** Walk directory tree, collect file mtimes
2. **Hash:** Calculate summary hash of all file states
3. **Compare:** Check if hash matches previous run
   - Match → Done (no changes)
   - Differ → Compare files to find specific changes
4. **Report:** Show added, removed, and modified files
5. **Save:** Store current state for next run

State files are stored in `~/.config/file_monitor/`

## Performance

### Python Version
Typical performance for 469k files:
- File collection: ~7.5s (I/O bound)
- Summary hash: ~0.1s
- Load state: ~0.2s (msgpack binary format)
- Compare: ~0.5s
- Save state: ~1.5s
- **Total: ~10s**

### Go Version
Typical performance for 469k files (estimated):
- File collection: ~1-2s (parallel scanning with 16 workers)
- Summary hash: ~0.02s
- Load state: ~0.05s
- Compare: ~0.1s
- Save state: ~0.3s
- **Total: ~1.5-2.5s**

**Go is 4-6x faster** due to compilation and parallel I/O operations.

When nothing changed (hash match): both versions skip detailed comparison.

## Requirements

### Python Version
- Python 3.7+
- msgpack (optional but recommended): `pip install msgpack`
  - Without msgpack, falls back to JSON (5-10x slower)

### Go Version
- Go 1.21+ (see BUILD_GO.md for installation)
- Dependencies auto-installed via `go mod download`

## Example Output

```
Scanning: /home/jack/projects
Excluding: .git, __pycache__, .cache, node_modules

Scanning filesystem...
Files scanned: 12,458
Summary hash: a3f5b9c2...
State file: ~/.config/file_monitor/abc123_home_jack_projects.msgpack

============================================================
CHANGES SINCE LAST RUN
============================================================
Previous scan: 2025-10-22T10:30:15
Previous hash: a3f5b9c2...
Current hash:  b7d3e1a8...

Total changes: 5

[+] Added files (2):
    + src/new_feature.py
    + tests/test_new_feature.py

[*] Modified files (3):
    * src/main.py
    * README.md
    * package.json

State saved to: ~/.config/file_monitor/abc123_home_jack_projects.msgpack
```

## Default Exclusions

Always excluded:
- `.git`
- `__pycache__`
- `.cache`
- `node_modules`

When monitoring `/`:
- `/proc` (virtual filesystem)
- `/sys` (virtual filesystem)
- `/run` (volatile)
- `/tmp` (volatile)
- `/var/tmp` (volatile)
- `/var/cache` (volatile)

Use `--all` to include the volatile directories.
