#!/usr/bin/env python3
"""
Verify that files copied to NAS match their original checksums.
"""

import hashlib
import sys
import os
from pathlib import Path


def md5_file(filepath):
    """Calculate MD5 hash of a file"""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        return None, str(e)


def read_original_checksums(checksum_file, files_to_check):
    """Read original checksums for specific files"""
    print(f"Reading original checksums from {checksum_file}...", file=sys.stderr)

    # Convert files_to_check to absolute paths for matching
    files_set = set()
    for f in files_to_check:
        # Convert relative path to absolute
        if not f.startswith('/'):
            f = '/' + f
        files_set.add(f)

    checksums = {}
    with open(checksum_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Parse line
            if '→' in line:
                line = line.split('→', 1)[1]

            parts = line.split(None, 1)
            if len(parts) != 2:
                continue

            file_hash, filepath = parts

            if filepath in files_set:
                checksums[filepath] = file_hash

    print(f"  Found {len(checksums)} original checksums", file=sys.stderr)
    return checksums


def verify_files(files_list, source_base, target_base, original_checksums):
    """
    Verify files on target match original checksums.

    Args:
        files_list: List of relative file paths
        source_base: Base path for source (to get original checksums)
        target_base: Base path for target (NAS)
        original_checksums: Dict of original checksums

    Returns:
        Dict with verification results
    """
    results = {
        'matched': [],
        'mismatched': [],
        'missing': [],
        'errors': []
    }

    total = len(files_list)

    for idx, rel_path in enumerate(files_list, 1):
        # Create absolute path for lookup
        abs_path = '/' + rel_path.lstrip('/')

        # Target file path
        target_path = os.path.join(target_base, rel_path)

        print(f"[{idx}/{total}] Checking: {rel_path}", file=sys.stderr)

        # Check if file exists on target
        if not os.path.exists(target_path):
            results['missing'].append(rel_path)
            print(f"  ✗ MISSING on target", file=sys.stderr)
            continue

        # Calculate hash of target file
        target_hash = md5_file(target_path)

        if isinstance(target_hash, tuple):  # Error occurred
            results['errors'].append({
                'file': rel_path,
                'error': target_hash[1]
            })
            print(f"  ✗ ERROR: {target_hash[1]}", file=sys.stderr)
            continue

        # Get original hash
        original_hash = original_checksums.get(abs_path)

        if not original_hash:
            results['errors'].append({
                'file': rel_path,
                'error': 'No original checksum found'
            })
            print(f"  ? No original checksum found", file=sys.stderr)
            continue

        # Compare hashes
        if target_hash == original_hash:
            results['matched'].append(rel_path)
            print(f"  ✓ OK ({target_hash})", file=sys.stderr)
        else:
            results['mismatched'].append({
                'file': rel_path,
                'original': original_hash,
                'target': target_hash
            })
            print(f"  ✗ MISMATCH: original={original_hash}, target={target_hash}", file=sys.stderr)

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify files copied to NAS match original checksums",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python verify_copied_files.py \\
    --file-list files_to_copy.txt \\
    --original-checksums ssd_checksums.txt \\
    --source-base /mnt/old-ssd/home/jack \\
    --target-base /mnt/nas/backup \\
    -o verification_report.txt
        """
    )

    parser.add_argument("--file-list", required=True,
                        help="File containing list of files to verify (relative paths)")
    parser.add_argument("--original-checksums", required=True,
                        help="Original checksum file (ssd_checksums.txt)")
    parser.add_argument("--source-base", required=True,
                        help="Source base path (e.g., /mnt/old-ssd/home/jack)")
    parser.add_argument("--target-base", required=True,
                        help="Target base path on NAS (e.g., /mnt/nas/backup)")
    parser.add_argument("-o", "--output", help="Output report file")

    args = parser.parse_args()

    # Read file list
    print("\n" + "=" * 80, file=sys.stderr)
    print("READING FILE LIST", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    with open(args.file_list, 'r') as f:
        files_to_check = [line.strip() for line in f if line.strip()]

    print(f"Files to verify: {len(files_to_check)}", file=sys.stderr)

    # Read original checksums
    print("\n" + "=" * 80, file=sys.stderr)
    print("READING ORIGINAL CHECKSUMS", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    original_checksums = read_original_checksums(args.original_checksums, files_to_check)

    # Verify files
    print("\n" + "=" * 80, file=sys.stderr)
    print("VERIFYING FILES", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    results = verify_files(files_to_check, args.source_base, args.target_base, original_checksums)

    # Print summary
    print("\n" + "=" * 80, file=sys.stderr)
    print("VERIFICATION SUMMARY", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    print(f"✓ Matched:     {len(results['matched']):>6}", file=sys.stderr)
    print(f"✗ Mismatched:  {len(results['mismatched']):>6}", file=sys.stderr)
    print(f"- Missing:     {len(results['missing']):>6}", file=sys.stderr)
    print(f"! Errors:      {len(results['errors']):>6}", file=sys.stderr)
    print(f"  Total:       {len(files_to_check):>6}", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    # Success rate
    success_rate = (len(results['matched']) / len(files_to_check) * 100) if files_to_check else 0
    print(f"\nSuccess rate: {success_rate:.1f}%", file=sys.stderr)

    # Write detailed report if requested
    if args.output:
        print(f"\nWriting detailed report to {args.output}...", file=sys.stderr)
        with open(args.output, 'w') as f:
            f.write("FILE VERIFICATION REPORT\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Total files checked: {len(files_to_check)}\n")
            f.write(f"Matched: {len(results['matched'])}\n")
            f.write(f"Mismatched: {len(results['mismatched'])}\n")
            f.write(f"Missing: {len(results['missing'])}\n")
            f.write(f"Errors: {len(results['errors'])}\n")
            f.write(f"Success rate: {success_rate:.1f}%\n\n")

            if results['mismatched']:
                f.write("\n" + "=" * 80 + "\n")
                f.write("MISMATCHED FILES\n")
                f.write("=" * 80 + "\n")
                for item in results['mismatched']:
                    f.write(f"\nFile: {item['file']}\n")
                    f.write(f"  Original: {item['original']}\n")
                    f.write(f"  Target:   {item['target']}\n")

            if results['missing']:
                f.write("\n" + "=" * 80 + "\n")
                f.write("MISSING FILES\n")
                f.write("=" * 80 + "\n")
                for file in results['missing']:
                    f.write(f"  {file}\n")

            if results['errors']:
                f.write("\n" + "=" * 80 + "\n")
                f.write("ERRORS\n")
                f.write("=" * 80 + "\n")
                for item in results['errors']:
                    f.write(f"\nFile: {item['file']}\n")
                    f.write(f"  Error: {item['error']}\n")

            if results['matched']:
                f.write("\n" + "=" * 80 + "\n")
                f.write("SUCCESSFULLY VERIFIED FILES\n")
                f.write("=" * 80 + "\n")
                for file in results['matched']:
                    f.write(f"  ✓ {file}\n")

        print("Report written successfully", file=sys.stderr)

    # Exit with error code if there were problems
    if results['mismatched'] or results['missing'] or results['errors']:
        sys.exit(1)
    else:
        print("\n✓ All files verified successfully!", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
