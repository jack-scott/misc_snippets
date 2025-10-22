# File System Merkle Tree Monitor - Technical Specification

## Algorithm Overview

Merkle tree construction from file system state to detect file changes between runs. Uses modification times (mtime) for regular files and device identifiers (rdev major/minor) for device files.

## Core Data Structures

### MerkleNode
- `hash`: string (SHA-256 hex digest)
- `left`: MerkleNode or null
- `right`: MerkleNode or null
- `file_path`: string or null (only set for leaf nodes)
- `is_leaf()`: returns boolean (true if file_path is not null)

### MerkleTree
- `root_path`: resolved absolute path
- `exclude_patterns`: list of strings for path filtering
- `root`: MerkleNode or null
- `file_hashes`: dictionary mapping file paths to their hash values

## File Collection Algorithm

### collect_files()
**Returns:** List of tuples `(relative_path: str, mtime: float, mode: int, rdev: int)`

**Algorithm:**
1. Traverse directory tree using depth-first walk (does not follow symlinks)
2. Filter directories in-place to exclude patterns (prevents traversal into excluded dirs)
3. For each file:
   - Use lstat() to avoid following symlinks
   - Skip if matches exclude patterns
   - Store relative path from root
   - Capture: st_mtime, st_mode, st_rdev
4. Sort results by path for deterministic tree structure
5. Skip files on PermissionError/FileNotFoundError/OSError

### _should_exclude(path)
**Returns:** boolean

**Algorithm:**
- Check if any exclude pattern substring appears in path string

## Hashing Algorithm

### _hash_leaf(file_path, mtime, mode, rdev)
**Returns:** string (SHA-256 hex digest)

**Algorithm:**
1. If file is block device (S_ISBLK) or character device (S_ISCHR):
   - Extract major number from rdev
   - Extract minor number from rdev
   - Hash format: `"{path}:dev:{type}:{major}:{minor}"`
2. Otherwise (regular files, symlinks, etc):
   - Hash format: `"{path}:{mtime}"`
3. Apply SHA-256 to UTF-8 encoded string

### _hash_internal(left_hash, right_hash)
**Returns:** string (SHA-256 hex digest)

**Algorithm:**
- Concatenate left_hash and right_hash strings
- Apply SHA-256 to UTF-8 encoded concatenation

## Tree Building Algorithm

### build_tree()
**Returns:** MerkleNode (root)

**Algorithm:**
1. Collect all files via collect_files()
2. If no files: create single node with hash of "empty"
3. Create leaf nodes:
   - For each file, compute hash via _hash_leaf()
   - Store in file_hashes dictionary
   - Create MerkleNode with hash and file_path
4. Bottom-up tree construction:
   - While more than one node exists:
     - Process nodes in pairs (indices 0-1, 2-3, 4-5, etc)
     - For each pair:
       - If pair exists: create parent with _hash_internal(left.hash, right.hash)
       - If odd node at end: create parent with _hash_internal(left.hash, left.hash)
     - Replace current level with parent nodes
5. Final single node is root

### get_root_hash()
**Returns:** string

**Algorithm:**
- Build tree if not already built
- Return root.hash

## State Persistence

### get_state_file_path()
**Returns:** Path object

**Algorithm:**
1. Base directory: `~/.config/merkle_tree/`
2. Filename construction:
   - Hash target path with SHA-256, take first 16 hex chars
   - Sanitize path: replace `/` with `_`, space with `-`, truncate to 50 chars
   - Format: `{hash}_{sanitized_path}.json`
3. Create directory if not exists

### _serialize_tree(node)
**Returns:** Dictionary representing tree structure

**Algorithm (Recursive):**
1. If node is leaf:
   - Return {hash, file_path, is_leaf: true}
2. If node is internal:
   - Return {hash, is_leaf: false, left: serialize(left), right: serialize(right)}

### _deserialize_tree(data)
**Returns:** MerkleNode

**Algorithm (Recursive):**
1. If data['is_leaf'] == true:
   - Create leaf node with hash and file_path
2. Otherwise:
   - Recursively deserialize left and right children
   - Create internal node with hash and children

### save_state(output_file)
**Returns:** void

**Algorithm:**
- Build tree if not built
- Create JSON object:
  - `root_path`: string
  - `timestamp`: ISO 8601 string
  - `root_hash`: string
  - `file_count`: integer
  - `file_hashes`: dictionary {path: hash}
  - `tree_structure`: serialized tree via _serialize_tree()
- Write to file with 2-space indent

### load_state(input_file)
**Returns:** Dictionary with keys: root_path, timestamp, root_hash, file_count, file_hashes, tree_structure

**Algorithm:**
- Parse JSON from file
- Return dictionary

## Comparison Algorithms

### compare_with_previous(previous_state)
**Returns:** Dictionary with keys: added, removed, modified, total_changes

**Algorithm (Full comparison - checks every file):**
1. Build current tree if not built
2. Extract file sets:
   - current_files = set of keys from self.file_hashes
   - previous_files = set of keys from previous_state['file_hashes']
3. Set operations:
   - added = current_files - previous_files
   - removed = previous_files - current_files
4. Find modifications:
   - For each file in intersection of current and previous:
     - If hash differs: add to modified set
5. Return sorted lists with total count

### compare_trees_incremental(previous_state)
**Returns:** Dictionary with keys: added, removed, modified, total_changes, files_checked, files_skipped

**Algorithm (Incremental - leverages Merkle tree structure):**
1. Build current tree if not built
2. Quick check: if root.hash == previous_state['root_hash']:
   - Return immediately with zero changes and files_skipped = total files
3. Deserialize previous tree structure from previous_state['tree_structure']
4. Call _find_changed_subtrees(current_root, previous_root) to identify changed files
5. Compute added/removed/modified sets from changed files
6. Return results with files_skipped count

### _find_changed_subtrees(current, previous, path)
**Returns:** List of file paths that changed

**Algorithm (Recursive tree traversal with early termination):**
1. If current.hash == previous.hash:
   - Return empty list (entire subtree unchanged - skip)
2. If both are leaf nodes:
   - Return [current.file_path] (file was modified)
3. If structure changed (one leaf, one internal):
   - If current is leaf: return [current.file_path]
   - Otherwise: collect all leaves from current subtree
4. If both are internal nodes:
   - Recursively check left subtree (if both have left children)
   - Recursively check right subtree (if both have right children)
   - Collect all leaves from new children (if tree structure changed)
5. Return combined list of changed file paths

### _collect_all_leaves(node)
**Returns:** List of file paths under node

**Algorithm:**
- If leaf: return [node.file_path]
- Otherwise: recursively collect from left and right children

## Security Analysis

### analyze_security_relevance(file_path, change_type)
**Returns:** Dictionary with keys: is_suspicious, severity, reasons, level

**Parameters:**
- file_path: string
- change_type: enum string ("added", "modified", "removed")

**Algorithm:**
Severity levels: 0=normal, 1=watch, 2=suspicious, 3=critical

**Rules (maximum severity wins):**
1. Authentication files (passwd, shadow, sudoers, ssh configs, pam.d): severity=3
2. Critical system directories (boot, etc, root, bin, sbin, systemd, cron, init.d, home, .ssh, pam.d, security, opt): severity=2
3. System executables:
   - New executable in bin/sbin paths: severity=2
   - Modified executable in bin/sbin paths: severity=3
4. Suspicious extensions (.so, .ko, .service, .timer, .socket, .py, .sh, .pl) in system locations (etc, usr/lib, lib): severity=2
5. Hidden files in home directories (added only): severity=1
6. Boot directory changes: severity=3
7. Cron/systemd/init.d changes: severity=2
8. Device file changes (dev/): severity=1
9. New files in tmp/var/tmp with executable extensions: severity=1

**Returns:**
- is_suspicious: boolean (severity >= 2)
- severity: integer (0-3)
- reasons: list of strings describing why flagged
- level: string ("normal", "watch", "suspicious", "critical")

## File Grouping

### group_by_directory(files, max_depth)
**Returns:** Dictionary {directory_prefix: [files]}

**Parameters:**
- files: list of strings (file paths)
- max_depth: integer (default 3)

**Algorithm:**
1. For each file path:
   - Split into path components
   - If depth <= max_depth:
     - If single component: group by itself
     - Otherwise: group by parent directory
   - If depth > max_depth:
     - Group by first max_depth components
2. Return dictionary mapping prefixes to file lists

### format_grouped_changes(files, change_symbol, max_depth, max_display, expand_all)
**Returns:** List of formatted strings

**Parameters:**
- files: list of strings
- change_symbol: string ("+", "-", "*")
- max_depth: integer
- max_display: integer (line limit)
- expand_all: boolean

**Algorithm:**
1. Group files via group_by_directory()
2. For each group (sorted by directory name):
   - If 1 file: format as single line with full path
   - If expand_all=true OR <= 3 files:
     - Show directory header with count
     - Show each file indented (with directory prefix removed)
   - Otherwise:
     - Show directory with count only
3. Truncate output if exceeds max_display lines
4. Add "... and N more files" message if truncated

## Command Line Interface

### Arguments
- `path` (positional, optional): Root path to scan (default: ".")
- `--exclude`: Additional exclude patterns (repeatable)
- `--all`: Include /run, /tmp, /var/tmp, /var/cache (default: excluded when scanning root)
- `--security`: Enable security analysis output
- `-v/--verbose`: Show all files without truncation, fully expanded groups
- `--timing`: Run performance benchmark (two full scans comparing cold vs warm cache and full vs incremental comparison)

### Default Exclusions
Base: `.git`, `__pycache__`, `.cache`, `node_modules`

When scanning `/`:
- Always exclude: `/proc`, `/sys` (virtual filesystems)
- Exclude unless --all: `/run`, `/tmp`, `/var/tmp`, `/var/cache`, `/var/run`

### Main Execution Flow
1. Parse arguments and build exclude list
2. If --timing flag: run run_timing_benchmark() and exit
3. Create MerkleTree instance with root path and exclusions
4. Determine state file path
5. Load previous state if exists (verify path matches)
6. Build current tree
7. If previous state exists:
   - Compare states using compare_trees_incremental()
   - If root hash matches: report no changes and files skipped
   - Otherwise: display files_skipped count if > 0
   - If --security: run security analysis and display by severity (critical/suspicious/watch)
   - Display changes grouped by directory
   - Apply truncation unless --verbose
8. Save current state (includes tree structure)
9. Return 0

### run_timing_benchmark(target_path, exclude_patterns)
**Returns:** void

**Algorithm:**
1. For each of 2 runs:
   - Create fresh MerkleTree instance
   - Time each operation with perf_counter():
     - collect_files()
     - build_tree()
     - get_root_hash()
     - load_state() (if state exists)
     - compare_with_previous() (full comparison)
     - compare_trees_incremental() (Merkle-optimized comparison)
     - save_state()
   - Calculate total time
   - Display timings and file counts
2. After both runs:
   - Display comparison table with Run 1 vs Run 2
   - Calculate speedup ratio for each operation
   - Show root hash and final file count

### Output Format
- Security analysis: Groups by severity with symbols 🔴 CRITICAL, 🟠 SUSPICIOUS, 🟡 WATCH
- Change symbols: `+` (added), `-` (removed), `*` (modified)
- Display limits: 15 suspicious items, 10 watch items, 20 directory groups (unless --verbose)
