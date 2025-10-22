#!/usr/bin/env python3
"""
Generate a list of files that differ between two checksum files.
Output is suitable for use with rsync --files-from or similar tools.
"""

import sys
import argparse


def read_checksums(filename, exclude_patterns=None):
    """
    Read a checksum file and return a dict of {filepath: hash}

    Args:
        filename: Path to checksum file
        exclude_patterns: List of path prefixes to exclude

    Returns:
        Dict mapping filepath to hash
    """
    if exclude_patterns is None:
        exclude_patterns = []

    checksums = {}
    excluded_count = 0

    print(f"Reading {filename}...", file=sys.stderr)

    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            # Parse line: "hash  /filepath" or "linenum→hash  /filepath"
            if '→' in line:
                line = line.split('→', 1)[1]

            parts = line.split(None, 1)
            if len(parts) != 2:
                continue

            file_hash, filepath = parts

            # Check exclusions
            excluded = False
            for pattern in exclude_patterns:
                if filepath.startswith(pattern):
                    excluded = True
                    excluded_count += 1
                    break

            if not excluded:
                checksums[filepath] = file_hash

            if line_num % 100000 == 0:
                print(f"  Processed {line_num:,} lines...", file=sys.stderr)

    print(f"  Loaded {len(checksums):,} files (excluded {excluded_count:,})", file=sys.stderr)
    return checksums


def find_differences(source_checksums, target_checksums, mode='all'):
    """
    Find files that differ between source and target.

    Args:
        source_checksums: Dict of source checksums
        target_checksums: Dict of target checksums
        mode: What to include - 'all', 'missing', 'modified', 'only-in-source'

    Returns:
        List of filepaths that differ
    """
    diff_files = []

    if mode in ('all', 'missing', 'only-in-source'):
        # Files only in source (missing from target)
        only_in_source = set(source_checksums.keys()) - set(target_checksums.keys())
        diff_files.extend(sorted(only_in_source))
        print(f"Files only in source: {len(only_in_source):,}", file=sys.stderr)

    if mode in ('all', 'modified'):
        # Files with different hashes
        modified = []
        for filepath in source_checksums:
            if filepath in target_checksums:
                if source_checksums[filepath] != target_checksums[filepath]:
                    modified.append(filepath)

        diff_files.extend(sorted(modified))
        print(f"Modified files: {len(modified):,}", file=sys.stderr)

    if mode in ('all',):
        # Files only in target (extra files)
        only_in_target = set(target_checksums.keys()) - set(source_checksums.keys())
        print(f"Files only in target: {len(only_in_target):,}", file=sys.stderr)

    return diff_files


def main():
    parser = argparse.ArgumentParser(
        description="Generate list of files that differ between two checksum files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate list of all differences (excluding /snap)
  python generate_diff_list.py ssd_checksums.txt nas_checksums.txt -o files_to_copy.txt

  # Only files missing from target
  python generate_diff_list.py ssd_checksums.txt nas_checksums.txt --mode missing

  # Exclude multiple paths
  python generate_diff_list.py ssd_checksums.txt nas_checksums.txt \\
    --exclude /snap --exclude /tmp -o files_to_copy.txt

  # Use with rsync (relative paths)
  rsync -av --files-from=files_to_copy.txt /source/path/ /target/path/

  # Use with rsync (absolute paths - need to use /)
  rsync -av --files-from=files_to_copy.txt / /target/path/
        """
    )

    parser.add_argument("source", help="Source checksum file")
    parser.add_argument("target", help="Target checksum file")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--exclude", action="append", default=[],
                        help="Exclude paths starting with this prefix (can be specified multiple times)")
    parser.add_argument("--mode", choices=['all', 'missing', 'modified', 'only-in-source'],
                        default='all',
                        help="What to include: all (default), missing (only in source), modified, only-in-source")
    parser.add_argument("--relative", action="store_true",
                        help="Output relative paths (strip leading /)")
    parser.add_argument("--stats", action="store_true",
                        help="Show detailed statistics")

    args = parser.parse_args()

    # Add /snap to exclusions if not already there
    if '/snap' not in args.exclude and '/snap/' not in args.exclude:
        args.exclude.append('/snap/')
        print("Auto-excluding /snap/", file=sys.stderr)

    # Read checksum files
    print("\n" + "=" * 80, file=sys.stderr)
    print("READING CHECKSUM FILES", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    source_checksums = read_checksums(args.source, args.exclude)
    target_checksums = read_checksums(args.target, args.exclude)

    # Find differences
    print("\n" + "=" * 80, file=sys.stderr)
    print("FINDING DIFFERENCES", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    diff_files = find_differences(source_checksums, target_checksums, args.mode)

    print(f"\nTotal files to copy: {len(diff_files):,}", file=sys.stderr)

    # Process output paths
    if args.relative:
        diff_files = [f.lstrip('/') for f in diff_files]

    # Write output
    if args.output:
        print(f"\nWriting to {args.output}...", file=sys.stderr)
        with open(args.output, 'w', encoding='utf-8') as f:
            for filepath in diff_files:
                f.write(filepath + '\n')
        print(f"Done! {len(diff_files):,} files written.", file=sys.stderr)
    else:
        # Output to stdout
        for filepath in diff_files:
            print(filepath)

    # Show statistics if requested
    if args.stats:
        print("\n" + "=" * 80, file=sys.stderr)
        print("STATISTICS", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(f"Source files: {len(source_checksums):,}", file=sys.stderr)
        print(f"Target files: {len(target_checksums):,}", file=sys.stderr)
        print(f"Files to copy: {len(diff_files):,}", file=sys.stderr)


if __name__ == "__main__":
    main()
