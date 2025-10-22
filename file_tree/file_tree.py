#!/usr/bin/env python3
"""
Merkle Tree File System Monitor

Creates a Merkle tree of file modification times to efficiently detect
changes between subsequent runs.
"""

import os
import hashlib
import json
import argparse
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class MerkleNode:
    """Represents a node in the Merkle tree."""

    def __init__(self, hash_value: str, left=None, right=None, file_path: Optional[str] = None):
        self.hash = hash_value
        self.left = left
        self.right = right
        self.file_path = file_path  # Only set for leaf nodes

    def is_leaf(self) -> bool:
        return self.file_path is not None


class MerkleTree:
    """Builds and manages a Merkle tree of file mtimes."""

    def __init__(self, root_path: str, exclude_patterns: List[str] = None):
        self.root_path = Path(root_path).resolve()
        self.exclude_patterns = exclude_patterns or ['.git', '__pycache__', '.cache', 'node_modules']
        self.root = None
        self.file_hashes: Dict[str, str] = {}

    def get_state_file_path(self) -> Path:
        """
        Get the path to the state file for this directory.
        Stores in ~/.config/merkle_tree/ with a filename based on the target path hash.
        """
        # Create config directory
        config_dir = Path.home() / '.config' / 'merkle_tree'
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create a unique filename based on the target path
        path_str = str(self.root_path)
        path_hash = hashlib.sha256(path_str.encode('utf-8')).hexdigest()[:16]

        # Create a readable filename: hash_safe-path.json
        # Replace / with _ for readability
        safe_path = path_str.replace('/', '_').replace(' ', '-')
        if len(safe_path) > 50:
            safe_path = safe_path[:50]

        filename = f"{path_hash}_{safe_path}.json"
        return config_dir / filename

    def _should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded."""
        path_str = str(path)
        for pattern in self.exclude_patterns:
            if pattern in path_str:
                return True
        return False

    def collect_files(self) -> List[Tuple[str, float, int, int]]:
        """
        Traverse the file system and collect file information.
        Returns a sorted list of tuples: (path, mtime, mode, rdev)
        - For regular files: mtime is used
        - For device files: rdev (major/minor) is used
        """
        files = []

        try:
            # Don't follow symlinks to avoid circular references
            for root, dirs, filenames in os.walk(self.root_path, followlinks=False):
                root_path = Path(root)

                # Filter out excluded directories
                dirs[:] = [d for d in dirs if not self._should_exclude(root_path / d)]

                for filename in filenames:
                    file_path = root_path / filename

                    if self._should_exclude(file_path):
                        continue

                    try:
                        # Use lstat to not follow symlinks
                        stat_info = file_path.lstat()
                        # Store relative path for portability
                        rel_path = str(file_path.relative_to(self.root_path))
                        files.append((rel_path, stat_info.st_mtime, stat_info.st_mode, stat_info.st_rdev))
                    except (PermissionError, FileNotFoundError, OSError):
                        # Skip files we can't access or have issues
                        continue
        except PermissionError:
            print(f"Permission denied accessing {self.root_path}")

        # Sort for consistent tree structure
        files.sort(key=lambda x: x[0])
        return files

    def _hash_leaf(self, file_path: str, mtime: float, mode: int, rdev: int) -> str:
        """
        Create a hash for a leaf node (file).
        For device files (block/char devices), use rdev (major/minor) instead of mtime.
        For regular files, use mtime.
        """
        import stat

        if stat.S_ISBLK(mode) or stat.S_ISCHR(mode):
            # Device file - hash path + device type + major/minor numbers
            major = os.major(rdev)
            minor = os.minor(rdev)
            dev_type = "block" if stat.S_ISBLK(mode) else "char"
            data = f"{file_path}:dev:{dev_type}:{major}:{minor}".encode('utf-8')
        else:
            # Regular file, symlink, etc - use mtime
            data = f"{file_path}:{mtime}".encode('utf-8')

        return hashlib.sha256(data).hexdigest()

    def _hash_internal(self, left_hash: str, right_hash: str) -> str:
        """Create a hash for an internal node."""
        data = f"{left_hash}{right_hash}".encode('utf-8')
        return hashlib.sha256(data).hexdigest()

    def build_tree(self) -> MerkleNode:
        """
        Build the Merkle tree from collected files.
        Returns the root node.
        """
        files = self.collect_files()

        if not files:
            # Empty tree
            empty_hash = hashlib.sha256(b"empty").hexdigest()
            self.root = MerkleNode(empty_hash)
            return self.root

        # Create leaf nodes
        nodes = []
        for file_path, mtime, mode, rdev in files:
            hash_value = self._hash_leaf(file_path, mtime, mode, rdev)
            self.file_hashes[file_path] = hash_value
            node = MerkleNode(hash_value, file_path=file_path)
            nodes.append(node)

        # Build tree bottom-up
        while len(nodes) > 1:
            next_level = []

            # Process pairs of nodes
            for i in range(0, len(nodes), 2):
                left = nodes[i]

                if i + 1 < len(nodes):
                    right = nodes[i + 1]
                    hash_value = self._hash_internal(left.hash, right.hash)
                    parent = MerkleNode(hash_value, left, right)
                else:
                    # Odd number of nodes, promote the last one
                    hash_value = self._hash_internal(left.hash, left.hash)
                    parent = MerkleNode(hash_value, left, left)

                next_level.append(parent)

            nodes = next_level

        self.root = nodes[0]
        return self.root

    def get_root_hash(self) -> str:
        """Get the root hash of the tree."""
        if self.root is None:
            self.build_tree()
        return self.root.hash

    def _serialize_tree(self, node: MerkleNode) -> Dict:
        """Serialize a tree node to a dictionary."""
        if node.is_leaf():
            return {
                'hash': node.hash,
                'file_path': node.file_path,
                'is_leaf': True
            }
        else:
            return {
                'hash': node.hash,
                'is_leaf': False,
                'left': self._serialize_tree(node.left) if node.left else None,
                'right': self._serialize_tree(node.right) if node.right else None
            }

    def _deserialize_tree(self, data: Dict) -> MerkleNode:
        """Deserialize a dictionary to a tree node."""
        if data['is_leaf']:
            return MerkleNode(data['hash'], file_path=data['file_path'])
        else:
            left = self._deserialize_tree(data['left']) if data.get('left') else None
            right = self._deserialize_tree(data['right']) if data.get('right') else None
            return MerkleNode(data['hash'], left, right)

    def save_state(self, output_file: str):
        """Save the current state to a JSON file."""
        if self.root is None:
            self.build_tree()

        state = {
            'root_path': str(self.root_path),
            'timestamp': datetime.now().isoformat(),
            'root_hash': self.root.hash,
            'file_count': len(self.file_hashes),
            'file_hashes': self.file_hashes,
            'tree_structure': self._serialize_tree(self.root) if self.root else None
        }

        with open(output_file, 'w') as f:
            json.dump(state, f, indent=2)

    def load_state(self, input_file: str) -> Dict:
        """Load a previous state from a JSON file."""
        with open(input_file, 'r') as f:
            return json.load(f)

    def _find_changed_subtrees(self, current: MerkleNode, previous: MerkleNode, path: str = "root") -> List[str]:
        """
        Recursively find changed subtrees by comparing hashes.
        Returns list of paths to changed subtrees.
        """
        changed_paths = []

        # If hashes match, this entire subtree is unchanged
        if current.hash == previous.hash:
            return changed_paths

        # Hashes differ - this subtree has changes
        if current.is_leaf() and previous.is_leaf():
            # Both are leaves, record the file path
            changed_paths.append(current.file_path)
        elif current.is_leaf() or previous.is_leaf():
            # Structure changed (one is leaf, other is not)
            # This happens when files are added/removed
            if current.is_leaf():
                changed_paths.append(current.file_path)
            else:
                # Previous was a leaf, current is internal - traverse current
                changed_paths.extend(self._collect_all_leaves(current))
        else:
            # Both are internal nodes, recurse
            if current.left and previous.left:
                changed_paths.extend(self._find_changed_subtrees(current.left, previous.left, f"{path}.L"))
            elif current.left:
                changed_paths.extend(self._collect_all_leaves(current.left))

            if current.right and previous.right:
                changed_paths.extend(self._find_changed_subtrees(current.right, previous.right, f"{path}.R"))
            elif current.right:
                changed_paths.extend(self._collect_all_leaves(current.right))

        return changed_paths

    def _collect_all_leaves(self, node: MerkleNode) -> List[str]:
        """Collect all leaf file paths under a node."""
        if node.is_leaf():
            return [node.file_path]

        leaves = []
        if node.left:
            leaves.extend(self._collect_all_leaves(node.left))
        if node.right:
            leaves.extend(self._collect_all_leaves(node.right))
        return leaves

    def compare_with_previous(self, previous_state: Dict) -> Dict:
        """
        Compare current state with a previous state.
        Returns a dict with added, removed, and modified files.
        """
        if self.root is None:
            self.build_tree()

        current_files = set(self.file_hashes.keys())
        previous_files = set(previous_state['file_hashes'].keys())

        added = current_files - previous_files
        removed = previous_files - current_files
        modified = set()

        # Check for modifications in files that exist in both states
        for file_path in current_files & previous_files:
            if self.file_hashes[file_path] != previous_state['file_hashes'][file_path]:
                modified.add(file_path)

        return {
            'added': sorted(list(added)),
            'removed': sorted(list(removed)),
            'modified': sorted(list(modified)),
            'total_changes': len(added) + len(removed) + len(modified)
        }

    def compare_trees_incremental(self, previous_state: Dict) -> Dict:
        """
        Compare current tree with previous tree using incremental traversal.
        Only examines subtrees where hashes differ.
        Returns same format as compare_with_previous but with stats on skipped subtrees.
        """
        if self.root is None:
            self.build_tree()

        # Quick check: if root hashes match, no changes at all
        if self.root.hash == previous_state['root_hash']:
            return {
                'added': [],
                'removed': [],
                'modified': [],
                'total_changes': 0,
                'subtrees_skipped': 1,
                'files_skipped': len(self.file_hashes)
            }

        # Load previous tree structure
        previous_tree = None
        if 'tree_structure' in previous_state:
            previous_tree = self._deserialize_tree(previous_state['tree_structure'])

        if not previous_tree:
            # Fall back to regular comparison if no tree structure
            result = self.compare_with_previous(previous_state)
            result['subtrees_skipped'] = 0
            result['files_skipped'] = 0
            return result

        # Find files in changed subtrees
        changed_files = set(self._find_changed_subtrees(self.root, previous_tree))

        current_files = set(self.file_hashes.keys())
        previous_files = set(previous_state['file_hashes'].keys())

        added = current_files - previous_files
        removed = previous_files - current_files
        modified = changed_files - added - removed

        files_checked = len(changed_files) + len(added) + len(removed)
        files_skipped = len(current_files) - len(changed_files)

        return {
            'added': sorted(list(added)),
            'removed': sorted(list(removed)),
            'modified': sorted(list(modified)),
            'total_changes': len(added) + len(removed) + len(modified),
            'files_checked': files_checked,
            'files_skipped': max(0, files_skipped)
        }


def analyze_security_relevance(file_path: str, change_type: str) -> Dict:
    """
    Analyze if a file change is security-relevant.
    Returns dict with: is_suspicious, severity, reasons
    """
    reasons = []
    severity = 0  # 0=normal, 1=watch, 2=suspicious, 3=critical

    # Critical system directories
    critical_dirs = [
        'etc/', 'boot/', 'root/', 'usr/bin/', 'usr/sbin/', 'bin/', 'sbin/',
        'lib/systemd/', 'etc/systemd/', 'etc/cron', 'etc/init.d/',
        'home/', '.ssh/', 'etc/pam.d/', 'etc/security/', 'usr/local/bin/',
        'usr/local/sbin/', 'opt/'
    ]

    # Authentication/security files
    auth_files = [
        'etc/passwd', 'etc/shadow', 'etc/sudoers', 'etc/group',
        'etc/ssh/sshd_config', '.ssh/authorized_keys', 'etc/pam.d/',
        'etc/security/'
    ]

    # Check for critical authentication files
    for auth in auth_files:
        if auth in file_path:
            severity = max(severity, 3)
            reasons.append(f"Authentication/security file: {auth}")

    # Check for critical system directories
    for crit_dir in critical_dirs:
        if file_path.startswith(crit_dir):
            severity = max(severity, 2)
            reasons.append(f"Critical directory: /{crit_dir}")
            break

    # Check for executable files
    if any(file_path.startswith(d) for d in ['bin/', 'sbin/', 'usr/bin/', 'usr/sbin/', 'usr/local/bin/']):
        if change_type == 'added':
            severity = max(severity, 2)
            reasons.append("New executable in system path")
        elif change_type == 'modified':
            severity = max(severity, 3)
            reasons.append("Modified system executable")

    # Check for suspicious extensions
    suspicious_exts = ['.so', '.ko', '.service', '.timer', '.socket', '.py', '.sh', '.pl']
    if any(file_path.endswith(ext) for ext in suspicious_exts):
        if any(file_path.startswith(d) for d in ['etc/', 'usr/lib/', 'lib/']):
            severity = max(severity, 2)
            reasons.append(f"Executable/module in system location")

    # Hidden files in home directories
    if '/..' in file_path or file_path.startswith('home/') and '/.' in file_path:
        if change_type == 'added':
            severity = max(severity, 1)
            reasons.append("Hidden file in home directory")

    # Boot directory changes
    if file_path.startswith('boot/'):
        severity = max(severity, 3)
        reasons.append("Boot directory modification")

    # Cron/systemd changes
    if any(x in file_path for x in ['cron', 'systemd/system', 'systemd/user', 'init.d']):
        severity = max(severity, 2)
        reasons.append("Scheduled task or service configuration")

    # Device files
    if file_path.startswith('dev/'):
        severity = max(severity, 1)
        reasons.append("Device file change")

    # Temporary directory new executables
    if change_type == 'added' and any(file_path.startswith(d) for d in ['tmp/', 'var/tmp/']):
        if any(file_path.endswith(ext) for ext in ['.sh', '.py', '.pl', '.elf', '']):
            severity = max(severity, 1)
            reasons.append("New file in temporary directory")

    return {
        'is_suspicious': severity >= 2,
        'severity': severity,
        'reasons': reasons,
        'level': ['normal', 'watch', 'suspicious', 'critical'][severity]
    }


def group_by_directory(files: List[str], max_depth: int = 3) -> Dict[str, List[str]]:
    """
    Group files by their common directory prefix.
    Returns dict of {directory: [files in that directory]}
    """
    from collections import defaultdict
    groups = defaultdict(list)

    for file in files:
        parts = Path(file).parts

        # Find the appropriate grouping level
        if len(parts) <= max_depth:
            # File is shallow enough, use its parent directory
            if len(parts) == 1:
                groups[file].append(file)
            else:
                parent = str(Path(*parts[:-1])) if len(parts) > 1 else parts[0]
                groups[parent].append(file)
        else:
            # File is deep, use max_depth prefix
            prefix = str(Path(*parts[:max_depth]))
            groups[prefix].append(file)

    return dict(groups)


def format_grouped_changes(files: List[str], change_symbol: str, max_depth: int = 3, max_display: int = 20, expand_all: bool = False) -> List[str]:
    """
    Format file changes grouped by directory.
    Returns list of formatted strings ready for printing.

    Args:
        files: List of file paths to format
        change_symbol: Symbol to use (+, -, *)
        max_depth: How many directory levels to use for grouping
        max_display: Maximum number of output lines before truncating
        expand_all: If True, expand all files in each directory group
    """
    if not files:
        return []

    groups = group_by_directory(files, max_depth)
    output = []
    total_shown = 0

    # Sort by directory name
    for directory in sorted(groups.keys()):
        dir_files = groups[directory]

        if len(dir_files) == 1:
            # Single file, show the full path
            output.append(f"    {change_symbol} {dir_files[0]}")
            total_shown += 1
        elif expand_all or len(dir_files) <= 3:
            # Show directory with individual files indented (relative to directory)
            output.append(f"    {change_symbol} {directory}/ ({len(dir_files)} files):")
            for f in sorted(dir_files):
                # Remove the directory prefix to show only the relative path
                relative_path = f
                if f.startswith(directory + '/'):
                    relative_path = f[len(directory) + 1:]
                output.append(f"        {change_symbol} {relative_path}")
            total_shown += len(dir_files)
        else:
            # Many files, just show directory with count
            output.append(f"    {change_symbol} {directory}/ ({len(dir_files)} files)")
            total_shown += len(dir_files)

        if len(output) >= max_display:
            remaining = len(files) - total_shown
            if remaining > 0:
                output.append(f"    ... and {remaining} more files in other directories")
            break

    return output


def run_timing_benchmark(target_path: Path, exclude_patterns: List[str]):
    """
    Run timing benchmark: two full scans to compare fresh vs cached performance.
    """
    print("\n" + "="*60)
    print("TIMING BENCHMARK")
    print("="*60)
    print(f"Target: {target_path}")
    print("Running 2 iterations to compare fresh vs cached performance\n")

    timings = {'run1': {}, 'run2': {}}

    for run_num in [1, 2]:
        run_key = f'run{run_num}'
        print(f"--- Run {run_num} {'(Fresh - cold cache)' if run_num == 1 else '(Warm cache)'} ---")

        tree = MerkleTree(target_path, exclude_patterns=exclude_patterns)
        state_file = tree.get_state_file_path()

        # File collection
        t_start = time.perf_counter()
        files = tree.collect_files()
        t_collect = time.perf_counter() - t_start
        timings[run_key]['collect_files'] = t_collect
        print(f"  File collection: {t_collect:.4f}s ({len(files)} files)")

        # Tree building (includes leaf hashing)
        t_start = time.perf_counter()
        tree.build_tree()
        t_build = time.perf_counter() - t_start
        timings[run_key]['build_tree'] = t_build
        print(f"  Tree building:   {t_build:.4f}s")

        # Get root hash (should be instant since tree is built)
        t_start = time.perf_counter()
        root_hash = tree.get_root_hash()
        t_hash = time.perf_counter() - t_start
        timings[run_key]['get_root_hash'] = t_hash
        print(f"  Get root hash:   {t_hash:.6f}s")

        # State operations
        if state_file.exists():
            t_start = time.perf_counter()
            previous_state = tree.load_state(str(state_file))
            t_load = time.perf_counter() - t_start
            timings[run_key]['load_state'] = t_load
            print(f"  Load state:      {t_load:.6f}s")

            # Full comparison (checks every file)
            t_start = time.perf_counter()
            changes = tree.compare_with_previous(previous_state)
            t_compare_full = time.perf_counter() - t_start
            timings[run_key]['compare_full'] = t_compare_full
            print(f"  Compare (full):  {t_compare_full:.6f}s ({changes['total_changes']} changes)")

            # Incremental comparison (uses Merkle tree to skip unchanged subtrees)
            t_start = time.perf_counter()
            changes_inc = tree.compare_trees_incremental(previous_state)
            t_compare_inc = time.perf_counter() - t_start
            timings[run_key]['compare_incremental'] = t_compare_inc
            skipped = changes_inc.get('files_skipped', 0)
            checked = changes_inc.get('files_checked', len(files))
            print(f"  Compare (incr):  {t_compare_inc:.6f}s ({changes_inc['total_changes']} changes, skipped {skipped}/{len(files)} files)")

        # Save state
        t_start = time.perf_counter()
        tree.save_state(str(state_file))
        t_save = time.perf_counter() - t_start
        timings[run_key]['save_state'] = t_save
        print(f"  Save state:      {t_save:.6f}s")

        # Total time (using incremental comparison)
        total = t_collect + t_build + t_hash + timings[run_key].get('load_state', 0) + \
                timings[run_key].get('compare_incremental', 0) + t_save
        timings[run_key]['total'] = total
        print(f"  Total:           {total:.4f}s")
        print()

    # Comparison
    print("="*60)
    print("PERFORMANCE COMPARISON")
    print("="*60)
    print(f"{'Operation':<23} {'Run 1 (Cold)':<15} {'Run 2 (Warm)':<15} {'Speedup':<10}")
    print("-"*60)

    for op in ['collect_files', 'build_tree', 'get_root_hash', 'load_state', 'compare_full', 'compare_incremental', 'save_state', 'total']:
        if op in timings['run1'] and op in timings['run2']:
            t1 = timings['run1'][op]
            t2 = timings['run2'][op]
            speedup = t1 / t2 if t2 > 0 else float('inf')
            print(f"{op:<23} {t1:>12.4f}s  {t2:>12.4f}s  {speedup:>8.2f}x")

    print("\n" + "="*60)
    print(f"Root hash: {tree.get_root_hash()}")
    print(f"Files scanned: {len(tree.file_hashes)}")
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Build a Merkle tree of file mtimes to detect changes between runs'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Root path to scan (default: current directory)'
    )
    parser.add_argument(
        '--exclude',
        action='append',
        help='Additional patterns to exclude (can be used multiple times)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Include noisy directories (/run, /tmp, /var/tmp, /var/cache). Only virtual filesystems (/proc, /sys) are excluded.'
    )
    parser.add_argument(
        '--security',
        action='store_true',
        help='Highlight security-relevant changes (critical system files, executables, auth files, etc.)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show all changed files (not limited to 20), fully expanded under directory nesting'
    )
    parser.add_argument(
        '--timing',
        action='store_true',
        help='Run timing benchmark: perform two full scans to compare fresh vs cached performance'
    )

    args = parser.parse_args()

    # Build the tree
    exclude_patterns = ['.git', '__pycache__', '.cache', 'node_modules']

    # Add system directories to exclude when scanning from root
    target_path = Path(args.path).resolve()
    system_dirs_excluded = []
    virtual_fs_excluded = []

    if str(target_path) == '/':
        # Always exclude virtual filesystems (they're not real files)
        virtual_fs_excluded = ['/proc', '/sys']
        exclude_patterns.extend(virtual_fs_excluded)

        # Exclude noisy directories unless --all is used
        if not args.all:
            system_dirs_excluded = ['/run', '/tmp', '/var/tmp', '/var/cache', '/var/run']
            exclude_patterns.extend(system_dirs_excluded)

    if args.exclude:
        exclude_patterns.extend(args.exclude)

    # If timing benchmark requested, run it and exit
    if args.timing:
        print(f"Scanning: {target_path}")
        print(f"\nExcluding patterns:")
        for pattern in exclude_patterns:
            print(f"  - {pattern}")

        if virtual_fs_excluded:
            print(f"\n  Virtual filesystems (always excluded): {', '.join(virtual_fs_excluded)}")
        if system_dirs_excluded:
            print(f"  Noisy directories (excluded by default, use --all to include): {', '.join(system_dirs_excluded)}")
        elif str(target_path) == '/' and args.all:
            print(f"  --all flag: Including /run, /tmp, /var/tmp, /var/cache, /dev")
            print(f"  Note: /dev will track device presence (not mtime)")

        run_timing_benchmark(target_path, exclude_patterns)
        return 0

    print(f"Scanning: {target_path}")
    print(f"\nExcluding patterns:")
    for pattern in exclude_patterns:
        print(f"  - {pattern}")

    if virtual_fs_excluded:
        print(f"\n  Virtual filesystems (always excluded): {', '.join(virtual_fs_excluded)}")
    if system_dirs_excluded:
        print(f"  Noisy directories (excluded by default, use --all to include): {', '.join(system_dirs_excluded)}")
    elif str(target_path) == '/' and args.all:
        print(f"  --all flag: Including /run, /tmp, /var/tmp, /var/cache, /dev")
        print(f"  Note: /dev will track device presence (not mtime)")
    print()

    tree = MerkleTree(target_path, exclude_patterns=exclude_patterns)
    state_file = tree.get_state_file_path()
    print(f"State file: {state_file}")

    # Check if previous state exists
    previous_state = None
    if state_file.exists():
        print(f"Loading previous state...\n")
        previous_state = tree.load_state(str(state_file))

        # Verify the path matches
        if previous_state.get('root_path') != str(target_path):
            print(f"Warning: State file path mismatch!")
            print(f"  Expected: {target_path}")
            print(f"  Found: {previous_state.get('root_path')}")
            print("  Treating as first run.\n")
            previous_state = None

    if not previous_state:
        print("No previous state found - this is the first run\n")

    # Build current tree
    print("Building Merkle tree...")
    tree.build_tree()

    print(f"Files scanned: {len(tree.file_hashes)}")
    print(f"Root hash: {tree.get_root_hash()}")

    # Compare with previous state if it exists
    if previous_state:
        # Use incremental comparison (leverages Merkle tree structure)
        changes = tree.compare_trees_incremental(previous_state)

        print("\n" + "="*60)
        print("CHANGES SINCE LAST RUN")
        print("="*60)

        prev_hash = previous_state['root_hash']
        prev_time = previous_state.get('timestamp', 'unknown')
        curr_hash = tree.get_root_hash()

        print(f"Previous scan: {prev_time}")
        print(f"Previous root hash: {prev_hash}")
        print(f"Current root hash:  {curr_hash}")

        if prev_hash == curr_hash:
            print("\nNo changes detected (root hashes match)")
            print(f"Skipped detailed comparison of {len(tree.file_hashes)} files")
        else:
            print(f"\nTotal changes: {changes['total_changes']}")
            if 'files_skipped' in changes and changes['files_skipped'] > 0:
                print(f"Files skipped by Merkle tree optimization: {changes['files_skipped']}/{len(tree.file_hashes)}")

            if not args.verbose:
                print("(Limited to 20 directory groups. Use -v/--verbose to see all changes)\n")

            # Security analysis if requested
            if args.security:
                print("\n" + "="*60)
                print("SECURITY ANALYSIS")
                print("="*60)

                critical_changes = []
                suspicious_changes = []
                watch_changes = []

                # Analyze all changes
                for change_type, files in [('added', changes['added']),
                                          ('modified', changes['modified']),
                                          ('removed', changes['removed'])]:
                    for file in files:
                        analysis = analyze_security_relevance(file, change_type)
                        if analysis['severity'] == 3:
                            critical_changes.append((change_type, file, analysis))
                        elif analysis['severity'] == 2:
                            suspicious_changes.append((change_type, file, analysis))
                        elif analysis['severity'] == 1:
                            watch_changes.append((change_type, file, analysis))

                # Display critical changes
                if critical_changes:
                    print(f"\n🔴 CRITICAL ({len(critical_changes)}):")
                    for change_type, file, analysis in critical_changes:
                        symbol = {'added': '+', 'modified': '*', 'removed': '-'}[change_type]
                        print(f"    {symbol} {file}")
                        for reason in analysis['reasons']:
                            print(f"        → {reason}")

                # Display suspicious changes
                if suspicious_changes:
                    print(f"\n🟠 SUSPICIOUS ({len(suspicious_changes)}):")
                    for change_type, file, analysis in suspicious_changes[:15]:
                        symbol = {'added': '+', 'modified': '*', 'removed': '-'}[change_type]
                        print(f"    {symbol} {file}")
                        for reason in analysis['reasons']:
                            print(f"        → {reason}")
                    if len(suspicious_changes) > 15:
                        print(f"    ... and {len(suspicious_changes) - 15} more")

                # Display watch list
                if watch_changes and args.verbose:
                    print(f"\n🟡 WATCH ({len(watch_changes)}):")
                    for change_type, file, analysis in watch_changes[:10]:
                        symbol = {'added': '+', 'modified': '*', 'removed': '-'}[change_type]
                        print(f"    {symbol} {file}")
                    if len(watch_changes) > 10:
                        print(f"    ... and {len(watch_changes) - 10} more")

                if not critical_changes and not suspicious_changes:
                    print("\n✅ No critical or suspicious changes detected")

                print("\n" + "="*60)
                print("ALL CHANGES")
                print("="*60)

            # Show all changes (grouped by directory, verbose shows all)
            max_display = 999999 if args.verbose else 20
            expand_all = args.verbose

            if changes['added']:
                print(f"\n[+] Added files ({len(changes['added'])}):")
                grouped = format_grouped_changes(changes['added'], '+', max_depth=3, max_display=max_display, expand_all=expand_all)
                for line in grouped:
                    print(line)

            if changes['removed']:
                print(f"\n[-] Removed files ({len(changes['removed'])}):")
                grouped = format_grouped_changes(changes['removed'], '-', max_depth=3, max_display=max_display, expand_all=expand_all)
                for line in grouped:
                    print(line)

            if changes['modified']:
                print(f"\n[*] Modified files ({len(changes['modified'])}):")
                grouped = format_grouped_changes(changes['modified'], '*', max_depth=3, max_display=max_display, expand_all=expand_all)
                for line in grouped:
                    print(line)

    # Save current state
    tree.save_state(str(state_file))
    print(f"\nState saved to: {state_file}")

    return 0


if __name__ == '__main__':
    exit(main())
