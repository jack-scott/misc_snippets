#!/usr/bin/env python3
"""
Merkle Tree Comparison Tool
Compare two Merkle trees and display differences in a hierarchical format.
This makes it easy to see which directories have changes without listing
every single file.
"""

import sys
from typing import Dict, Set, Tuple, List
from dataclasses import dataclass
from enum import Enum
from merkle_tree import MerkleTree, MerkleNode


class DiffType(Enum):
    """Types of differences between trees"""
    IDENTICAL = "identical"
    MODIFIED = "modified"
    ONLY_IN_SOURCE = "only_in_source"
    ONLY_IN_TARGET = "only_in_target"


@dataclass
class DiffStats:
    """Statistics about differences"""
    identical_dirs: int = 0
    modified_dirs: int = 0
    only_in_source_dirs: int = 0
    only_in_target_dirs: int = 0
    identical_files: int = 0
    modified_files: int = 0
    only_in_source_files: int = 0
    only_in_target_files: int = 0

    def total_differences(self) -> int:
        """Calculate total number of differences"""
        return (self.modified_dirs + self.only_in_source_dirs + self.only_in_target_dirs +
                self.modified_files + self.only_in_source_files + self.only_in_target_files)

    def print_summary(self):
        """Print a summary of the differences"""
        print("\n" + "=" * 80)
        print("COMPARISON SUMMARY")
        print("=" * 80)

        print(f"\nDirectories:")
        print(f"  ✓ Identical:        {self.identical_dirs:>8,}")
        print(f"  ✗ Modified:         {self.modified_dirs:>8,}")
        print(f"  - Only in source:   {self.only_in_source_dirs:>8,}")
        print(f"  + Only in target:   {self.only_in_target_dirs:>8,}")

        print(f"\nFiles:")
        print(f"  ✓ Identical:        {self.identical_files:>8,}")
        print(f"  ✗ Modified:         {self.modified_files:>8,}")
        print(f"  - Only in source:   {self.only_in_source_files:>8,}")
        print(f"  + Only in target:   {self.only_in_target_files:>8,}")

        total_diff = self.total_differences()
        print(f"\nTotal differences: {total_diff:,}")

        if total_diff == 0:
            print("\n✓ Trees are identical!")
        print("=" * 80)


class MerkleTreeComparator:
    """Compare two Merkle trees and generate hierarchical diff"""

    def __init__(self, source_tree: MerkleTree, target_tree: MerkleTree,
                 source_name: str = "source", target_name: str = "target"):
        self.source_tree = source_tree
        self.target_tree = target_tree
        self.source_name = source_name
        self.target_name = target_name
        self.stats = DiffStats()

    def compare(self, max_depth: int = None, show_identical: bool = False,
                only_show_dirs: bool = False) -> List[str]:
        """
        Compare the two trees and return formatted diff output.

        Args:
            max_depth: Maximum depth to show in the tree (None = unlimited)
            show_identical: Whether to show identical nodes
            only_show_dirs: Only show directory-level differences

        Returns:
            List of formatted output lines
        """
        output = []
        output.append("\n" + "=" * 80)
        output.append(f"MERKLE TREE COMPARISON: {self.source_name} vs {self.target_name}")
        output.append("=" * 80)

        # Compare from root
        self._compare_nodes(
            path="/",
            source_node=self.source_tree.root,
            target_node=self.target_tree.root,
            output=output,
            depth=0,
            max_depth=max_depth,
            show_identical=show_identical,
            only_show_dirs=only_show_dirs
        )

        return output

    def _compare_nodes(self, path: str, source_node: MerkleNode, target_node: MerkleNode,
                       output: List[str], depth: int, max_depth: int,
                       show_identical: bool, only_show_dirs: bool):
        """Recursively compare nodes and build output"""

        # Check depth limit
        if max_depth is not None and depth > max_depth:
            return

        indent = "  " * depth
        prefix = ""
        status_symbol = ""

        # Determine difference type
        if source_node is None and target_node is None:
            return  # Both missing, shouldn't happen

        elif source_node is None:
            # Only in target
            diff_type = DiffType.ONLY_IN_TARGET
            status_symbol = "+"
            prefix = f"{indent}{status_symbol} "

            if target_node.is_dir:
                self.stats.only_in_target_dirs += 1
                output.append(f"{prefix}{target_node.name}/ ({target_node.file_count:,} files) [target only]")
            else:
                self.stats.only_in_target_files += 1
                if not only_show_dirs:
                    output.append(f"{prefix}{target_node.name} [target only]")

        elif target_node is None:
            # Only in source
            diff_type = DiffType.ONLY_IN_SOURCE
            status_symbol = "-"
            prefix = f"{indent}{status_symbol} "

            if source_node.is_dir:
                self.stats.only_in_source_dirs += 1
                output.append(f"{prefix}{source_node.name}/ ({source_node.file_count:,} files) [source only]")
            else:
                self.stats.only_in_source_files += 1
                if not only_show_dirs:
                    output.append(f"{prefix}{source_node.name} [source only]")

        elif source_node.merkle_hash == target_node.merkle_hash:
            # Identical
            diff_type = DiffType.IDENTICAL
            status_symbol = "✓"

            if source_node.is_dir:
                self.stats.identical_dirs += 1
            else:
                self.stats.identical_files += 1

            if show_identical:
                prefix = f"{indent}{status_symbol} " 
                if source_node.is_dir:
                    output.append(f"{prefix}{source_node.name}/ ({source_node.file_count:,} files) [identical]")
                elif not only_show_dirs:
                    output.append(f"{prefix}{source_node.name} [identical]")
            return  # Don't recurse into identical directories

        else:
            # Modified (hashes differ)
            diff_type = DiffType.MODIFIED
            status_symbol = "✗"
            prefix = f"{indent}{status_symbol} "

            if source_node.is_dir:
                self.stats.modified_dirs += 1
                file_diff = target_node.file_count - source_node.file_count
                file_diff_str = f"{file_diff:+,}" if file_diff != 0 else "same count"
                output.append(
                    f"{prefix}{source_node.name}/ "
                    f"(source: {source_node.file_count:,} files, "
                    f"target: {target_node.file_count:,} files, "
                    f"diff: {file_diff_str}) [MODIFIED]"
                )
            else:
                self.stats.modified_files += 1
                if not only_show_dirs:
                    output.append(
                        f"{prefix}{source_node.name} "
                        f"[MODIFIED - source: {source_node.file_hash[:8]}..., "
                        f"target: {target_node.file_hash[:8]}...]"
                    )

        # Recurse into directories
        if source_node and source_node.is_dir and diff_type == DiffType.MODIFIED:
            # Get all child names from both nodes
            all_children = set()
            if source_node:
                all_children.update(source_node.children.keys())
            if target_node:
                all_children.update(target_node.children.keys())

            # Compare each child
            for child_name in sorted(all_children):
                child_path = f"{path}{child_name}/" if path == "/" else f"{path}/{child_name}/"

                source_child = source_node.children.get(child_name) if source_node else None
                target_child = target_node.children.get(child_name) if target_node else None

                self._compare_nodes(
                    path=child_path,
                    source_node=source_child,
                    target_node=target_child,
                    output=output,
                    depth=depth + 1,
                    max_depth=max_depth,
                    show_identical=show_identical,
                    only_show_dirs=only_show_dirs
                )


def compare_trees(source_checksum: str, target_checksum: str,
                  source_name: str = "SSD", target_name: str = "NAS",
                  max_depth: int = None, show_identical: bool = False,
                  only_show_dirs: bool = True, output_file: str = None):
    """
    Compare two checksum files using Merkle trees.

    Args:
        source_checksum: Path to source checksum file
        target_checksum: Path to target checksum file
        source_name: Name for source (for display)
        target_name: Name for target (for display)
        max_depth: Maximum tree depth to display (None = all)
        show_identical: Show identical nodes
        only_show_dirs: Only show directory-level differences
        output_file: Optional file to write output to
    """

    print("\n" + "=" * 80)
    print("BUILDING MERKLE TREES")
    print("=" * 80)

    # Build source tree
    print(f"\n[1/2] Building source tree ({source_name})...")
    source_tree = MerkleTree()
    source_tree.build_from_checksum_file(source_checksum)
    source_tree.compute_all_hashes()
    print(f"  Root hash: {source_tree.root.merkle_hash}")

    # Build target tree
    print(f"\n[2/2] Building target tree ({target_name})...")
    target_tree = MerkleTree()
    target_tree.build_from_checksum_file(target_checksum)
    target_tree.compute_all_hashes()
    print(f"  Root hash: {target_tree.root.merkle_hash}")

    # Compare trees
    print("\n" + "=" * 80)
    print("COMPARING TREES")
    print("=" * 80)

    comparator = MerkleTreeComparator(source_tree, target_tree, source_name, target_name)
    output_lines = comparator.compare(
        max_depth=max_depth,
        show_identical=show_identical,
        only_show_dirs=only_show_dirs
    )

    # Print output
    for line in output_lines:
        print(line)

    # Print statistics
    comparator.stats.print_summary()

    # Save to file if requested
    if output_file:
        print(f"\nSaving comparison to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
            f.write('\n\n')
            f.write("=" * 80 + '\n')
            f.write("STATISTICS\n")
            f.write("=" * 80 + '\n')

            # Redirect stats to file
            import io
            from contextlib import redirect_stdout

            stats_buffer = io.StringIO()
            with redirect_stdout(stats_buffer):
                comparator.stats.print_summary()

            f.write(stats_buffer.getvalue())
        print(f"Comparison saved successfully")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compare two checksum files using Merkle trees",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare with default settings (directories only, unlimited depth)
  python compare_merkle_trees.py ssd_checksums.txt nas_checksums.txt

  # Show top 3 levels only
  python compare_merkle_trees.py ssd_checksums.txt nas_checksums.txt --max-depth 3

  # Show individual file differences
  python compare_merkle_trees.py ssd_checksums.txt nas_checksums.txt --show-files

  # Show identical directories too
  python compare_merkle_trees.py ssd_checksums.txt nas_checksums.txt --show-identical

  # Save output to file
  python compare_merkle_trees.py ssd_checksums.txt nas_checksums.txt -o diff_report.txt
        """
    )

    parser.add_argument("source", help="Source checksum file")
    parser.add_argument("target", help="Target checksum file")
    parser.add_argument("--source-name", default="SSD", help="Name for source (default: SSD)")
    parser.add_argument("--target-name", default="NAS", help="Name for target (default: NAS)")
    parser.add_argument("--max-depth", type=int, help="Maximum depth to show (default: unlimited)")
    parser.add_argument("--show-identical", action="store_true",
                        help="Show identical directories/files")
    parser.add_argument("--show-files", action="store_true",
                        help="Show individual file differences (not just directories)")
    parser.add_argument("-o", "--output", help="Save comparison to file")

    args = parser.parse_args()

    compare_trees(
        source_checksum=args.source,
        target_checksum=args.target,
        source_name=args.source_name,
        target_name=args.target_name,
        max_depth=args.max_depth,
        show_identical=args.show_identical,
        only_show_dirs=not args.show_files,
        output_file=args.output
    )
