#!/usr/bin/env python3
"""
Simple File System Monitor

Tracks file modification times to detect changes between runs.
Uses a fast binary format (msgpack) for state persistence.
"""

import os
import hashlib
import argparse
import time
from pathlib import Path
from typing import Dict, Set, Optional
from datetime import datetime

try:
    import msgpack
except ImportError:
    print("Warning: msgpack not installed. Install with: pip install msgpack")
    print("Falling back to slower JSON format.")
    import json
    msgpack = None


class FileMonitor:
    """Simple file system monitor using file hashes."""

    def __init__(self, root_path: str, exclude_patterns: list = None):
        self.root_path = Path(root_path).resolve()
        self.exclude_patterns = exclude_patterns or ['.git', '__pycache__', '.cache', 'node_modules']
        self.files: Dict[str, dict] = {}

    def get_state_file_path(self) -> Path:
        """Get path to state file in ~/.config/file_monitor/"""
        config_dir = Path.home() / '.config' / 'file_monitor'
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create unique filename based on target path
        path_str = str(self.root_path)
        if self.exclude_patterns:
            hash_str = path_str + ''.join(sorted(self.exclude_patterns))
        path_hash = hashlib.sha256(hash_str.encode('utf-8')).hexdigest()[:16]

        # Readable filename
        safe_path = path_str.replace('/', '_').replace(' ', '-')
        if len(safe_path) > 50:
            safe_path = safe_path[:50]

        ext = '.msgpack' if msgpack else '.json'
        filename = f"{path_hash}_{safe_path}{ext}"
        return config_dir / filename

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        path_str = str(path)
        for pattern in self.exclude_patterns:
            if pattern in path_str:
                return True
        return False

    def collect_files(self) -> Dict[str, dict]:
        """
        Scan filesystem and collect file metadata.
        Returns dict of {relative_path: {mtime, mode, rdev}}
        """
        files = {}

        try:
            for root, dirs, filenames in os.walk(self.root_path, followlinks=False):
                root_path = Path(root)

                # Filter out excluded directories
                dirs[:] = [d for d in dirs if not self._should_exclude(root_path / d)]

                for filename in filenames:
                    file_path = root_path / filename

                    if self._should_exclude(file_path):
                        continue

                    try:
                        stat_info = file_path.lstat()
                        rel_path = str(file_path.relative_to(self.root_path))

                        files[rel_path] = {
                            'mtime': stat_info.st_mtime,
                            'mode': stat_info.st_mode,
                            'rdev': stat_info.st_rdev
                        }
                    except (PermissionError, FileNotFoundError, OSError):
                        continue

        except PermissionError:
            print(f"Permission denied accessing {self.root_path}")

        return files

    def calculate_summary_hash(self) -> str:
        """Calculate a single hash representing all file states."""
        # Sort items for deterministic hash
        sorted_items = sorted(self.files.items())

        # Create hash from all file data
        hasher = hashlib.sha256()
        for path, info in sorted_items:
            # For device files, use rdev; for regular files, use mtime
            import stat
            if stat.S_ISBLK(info['mode']) or stat.S_ISCHR(info['mode']):
                major = os.major(info['rdev'])
                minor = os.minor(info['rdev'])
                data = f"{path}:dev:{major}:{minor}"
            else:
                data = f"{path}:{info['mtime']}"

            hasher.update(data.encode('utf-8'))

        return hasher.hexdigest()

    def save_state(self, state_file: Path):
        """Save current state to file."""
        state = {
            'root_path': str(self.root_path),
            'timestamp': datetime.now().isoformat(),
            'file_count': len(self.files),
            'summary_hash': self.calculate_summary_hash(),
            'files': self.files
        }

        if msgpack:
            # Use msgpack for fast binary serialization
            with open(state_file, 'wb') as f:
                msgpack.pack(state, f, use_bin_type=True)
        else:
            # Fallback to JSON
            with open(state_file, 'w') as f:
                json.dump(state, f)

    def load_state(self, state_file: Path) -> Optional[dict]:
        """Load previous state from file."""
        if not state_file.exists():
            return None

        try:
            if msgpack and state_file.suffix == '.msgpack':
                with open(state_file, 'rb') as f:
                    return msgpack.unpack(f, raw=False)
            else:
                with open(state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading state: {e}")
            return None

    def compare_states(self, previous_state: dict) -> dict:
        """
        Compare current state with previous state.
        Returns dict with added, removed, modified files.
        """
        current_files = set(self.files.keys())
        previous_files = set(previous_state['files'].keys())

        added = current_files - previous_files
        removed = previous_files - current_files
        modified = set()

        # Check for modifications in files that exist in both states
        for file_path in current_files & previous_files:
            current_info = self.files[file_path]
            previous_info = previous_state['files'][file_path]

            # Compare mtime (for regular files) or rdev (for device files)
            if current_info['mtime'] != previous_info['mtime'] or \
               current_info['rdev'] != previous_info['rdev']:
                modified.add(file_path)

        return {
            'added': sorted(list(added)),
            'removed': sorted(list(removed)),
            'modified': sorted(list(modified)),
            'total_changes': len(added) + len(removed) + len(modified)
        }


def group_by_directory(files: list, max_depth: int = 3) -> dict:
    """Group files by their common directory prefix."""
    from collections import defaultdict
    groups = defaultdict(list)

    for file in files:
        parts = Path(file).parts

        if len(parts) <= max_depth:
            if len(parts) == 1:
                groups[file].append(file)
            else:
                parent = str(Path(*parts[:-1])) if len(parts) > 1 else parts[0]
                groups[parent].append(file)
        else:
            prefix = str(Path(*parts[:max_depth]))
            groups[prefix].append(file)

    return dict(groups)


def format_grouped_changes(files: list, change_symbol: str, max_display: int = 20, expand_all: bool = False) -> list:
    """Format file changes grouped by directory."""
    if not files:
        return []

    groups = group_by_directory(files, max_depth=3)
    output = []
    total_shown = 0

    for directory in sorted(groups.keys()):
        dir_files = groups[directory]

        if len(dir_files) == 1:
            output.append(f"    {change_symbol} {dir_files[0]}")
            total_shown += 1
        elif expand_all or len(dir_files) <= 3:
            output.append(f"    {change_symbol} {directory}/ ({len(dir_files)} files):")
            for f in sorted(dir_files):
                relative_path = f
                if f.startswith(directory + '/'):
                    relative_path = f[len(directory) + 1:]
                output.append(f"        {change_symbol} {relative_path}")
            total_shown += len(dir_files)
        else:
            output.append(f"    {change_symbol} {directory}/ ({len(dir_files)} files)")
            total_shown += len(dir_files)

        if len(output) >= max_display:
            remaining = len(files) - total_shown
            if remaining > 0:
                output.append(f"    ... and {remaining} more files")
            break

    return output


def run_timing_benchmark(root_path: Path, exclude_patterns: list):
    """Run timing benchmark comparing old and new format."""
    print("\n" + "="*60)
    print("TIMING BENCHMARK")
    print("="*60)
    print(f"Target: {root_path}\n")

    timings = {'run1': {}, 'run2': {}}

    for run_num in [1, 2]:
        run_key = f'run{run_num}'
        print(f"--- Run {run_num} {'(Cold cache)' if run_num == 1 else '(Warm cache)'} ---")

        monitor = FileMonitor(root_path, exclude_patterns)
        state_file = monitor.get_state_file_path()

        # File collection
        t_start = time.perf_counter()
        monitor.files = monitor.collect_files()
        t_collect = time.perf_counter() - t_start
        timings[run_key]['collect'] = t_collect
        print(f"  File collection: {t_collect:.4f}s ({len(monitor.files)} files)")

        # Summary hash calculation
        t_start = time.perf_counter()
        summary_hash = monitor.calculate_summary_hash()
        t_hash = time.perf_counter() - t_start
        timings[run_key]['summary_hash'] = t_hash
        print(f"  Summary hash:    {t_hash:.6f}s")

        # Load state
        if state_file.exists():
            t_start = time.perf_counter()
            previous_state = monitor.load_state(state_file)
            t_load = time.perf_counter() - t_start
            timings[run_key]['load'] = t_load
            print(f"  Load state:      {t_load:.6f}s")

            # Quick hash comparison
            if previous_state and previous_state.get('summary_hash') == summary_hash:
                print(f"  Quick check:     No changes (hash match)")
            else:
                # Detailed comparison
                t_start = time.perf_counter()
                changes = monitor.compare_states(previous_state)
                t_compare = time.perf_counter() - t_start
                timings[run_key]['compare'] = t_compare
                print(f"  Compare:         {t_compare:.6f}s ({changes['total_changes']} changes)")

        # Save state
        t_start = time.perf_counter()
        monitor.save_state(state_file)
        t_save = time.perf_counter() - t_start
        timings[run_key]['save'] = t_save
        print(f"  Save state:      {t_save:.6f}s")

        # Total
        total = sum(timings[run_key].values())
        timings[run_key]['total'] = total
        print(f"  Total:           {total:.4f}s")
        print()

    # Comparison
    print("="*60)
    print("PERFORMANCE COMPARISON")
    print("="*60)
    print(f"{'Operation':<20} {'Run 1 (Cold)':<15} {'Run 2 (Warm)':<15} {'Speedup':<10}")
    print("-"*60)

    for op in ['collect', 'summary_hash', 'load', 'compare', 'save', 'total']:
        if op in timings['run1'] and op in timings['run2']:
            t1 = timings['run1'][op]
            t2 = timings['run2'][op]
            speedup = t1 / t2 if t2 > 0 else float('inf')
            print(f"{op:<20} {t1:>12.4f}s  {t2:>12.4f}s  {speedup:>8.2f}x")

    print("\n" + "="*60)
    print(f"Summary hash: {summary_hash}")
    print(f"Files scanned: {len(monitor.files)}")
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Simple file system monitor using file modification times'
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
        help='Include noisy directories (/run, /tmp, etc) when scanning root'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show all changed files (not limited to 20 groups)'
    )
    parser.add_argument(
        '--timing',
        action='store_true',
        help='Run timing benchmark'
    )

    args = parser.parse_args()

    # Build exclude patterns
    exclude_patterns = ['.git', '__pycache__', '.cache', 'node_modules']

    target_path = Path(args.path).resolve()

    if str(target_path) == '/':
        # Always exclude virtual filesystems
        exclude_patterns.extend(['/proc', '/sys'])

        # Exclude noisy directories unless --all
        if not args.all:
            exclude_patterns.extend(['/run', '/tmp', '/var/tmp', '/var/cache', '/var/run'])

    if args.exclude:
        exclude_patterns.extend(args.exclude)

    # Timing benchmark
    if args.timing:
        run_timing_benchmark(target_path, exclude_patterns)
        return 0

    # Normal operation
    print(f"Scanning: {target_path}")
    print(f"Excluding: {', '.join(exclude_patterns)}\n")

    monitor = FileMonitor(target_path, exclude_patterns)
    state_file = monitor.get_state_file_path()

    # Collect current state
    print("Scanning filesystem...")
    monitor.files = monitor.collect_files()
    summary_hash = monitor.calculate_summary_hash()

    print(f"Files scanned: {len(monitor.files)}")
    print(f"Summary hash: {summary_hash}")
    print(f"State file: {state_file}")

    # Load previous state
    previous_state = monitor.load_state(state_file)

    if previous_state:
        # Verify path matches
        if previous_state.get('root_path') != str(target_path):
            print(f"\nWarning: State file path mismatch!")
            print(f"  Expected: {target_path}")
            print(f"  Found: {previous_state.get('root_path')}")
            previous_state = None

    if not previous_state:
        print("\nNo previous state found - this is the first run")
    else:
        # Quick check using summary hash
        prev_hash = previous_state.get('summary_hash')
        prev_time = previous_state.get('timestamp', 'unknown')

        print("\n" + "="*60)
        print("CHANGES SINCE LAST RUN")
        print("="*60)
        print(f"Previous scan: {prev_time}")
        print(f"Previous hash: {prev_hash}")
        print(f"Current hash:  {summary_hash}")

        if prev_hash == summary_hash:
            print("\n✓ No changes detected (hash match)")
        else:
            # Detailed comparison
            changes = monitor.compare_states(previous_state)

            print(f"\nTotal changes: {changes['total_changes']}")

            if not args.verbose and changes['total_changes'] > 0:
                print("(Limited to 20 directory groups. Use -v/--verbose to see all)\n")

            max_display = 999999 if args.verbose else 20
            expand_all = args.verbose

            if changes['added']:
                print(f"\n[+] Added files ({len(changes['added'])}):")
                for line in format_grouped_changes(changes['added'], '+', max_display, expand_all):
                    print(line)

            if changes['removed']:
                print(f"\n[-] Removed files ({len(changes['removed'])}):")
                for line in format_grouped_changes(changes['removed'], '-', max_display, expand_all):
                    print(line)

            if changes['modified']:
                print(f"\n[*] Modified files ({len(changes['modified'])}):")
                for line in format_grouped_changes(changes['modified'], '*', max_display, expand_all):
                    print(line)

    # Save current state
    monitor.save_state(state_file)
    print(f"\nState saved to: {state_file}")

    return 0


if __name__ == '__main__':
    exit(main())
