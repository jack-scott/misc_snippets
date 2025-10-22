#!/usr/bin/env python3
"""
Merkle Tree Builder for File Checksums
Builds a hierarchical tree structure from checksum files and computes
Merkle hashes at each directory level.
"""

import hashlib
import json
from typing import Dict, Optional


class MerkleNode:
    """Represents a node in the Merkle tree (either a file or directory)"""

    def __init__(self, name: str, is_dir: bool = False):
        self.name = name
        self.is_dir = is_dir
        self.file_hash: Optional[str] = None  # Original file hash (for files)
        self.merkle_hash: Optional[str] = None  # Computed Merkle hash
        self.children: Dict[str, 'MerkleNode'] = {}  # For directories
        self.file_count = 0
        self.total_size = 0

    def add_child(self, name: str, node: 'MerkleNode'):
        """Add a child node to this directory"""
        self.children[name] = node

    def compute_merkle_hash(self) -> str:
        """
        Recursively compute the Merkle hash for this node.
        For files: use the original file hash
        For directories: hash the concatenation of sorted children's hashes
        """
        if not self.is_dir:
            # For files, the Merkle hash is just the file hash
            self.merkle_hash = self.file_hash
            self.file_count = 1
            return self.merkle_hash

        # For directories, compute hash from children
        if not self.children:
            # Empty directory
            self.merkle_hash = hashlib.md5(b"empty_directory").hexdigest()
            self.file_count = 0
            return self.merkle_hash

        # Recursively compute children hashes first
        child_hashes = []
        total_files = 0

        for name in sorted(self.children.keys()):
            child = self.children[name]
            child_hash = child.compute_merkle_hash()
            child_hashes.append(f"{name}:{child_hash}")
            total_files += child.file_count

        # Combine all child hashes
        combined = "|".join(child_hashes)
        self.merkle_hash = hashlib.md5(combined.encode('utf-8')).hexdigest()
        self.file_count = total_files

        return self.merkle_hash

    def to_dict(self, include_children: bool = True) -> dict:
        """Convert node to dictionary representation"""
        result = {
            "name": self.name,
            "is_dir": self.is_dir,
            "merkle_hash": self.merkle_hash,
            "file_count": self.file_count,
        }

        if not self.is_dir:
            result["file_hash"] = self.file_hash

        if self.is_dir and include_children and self.children:
            result["children"] = {
                name: child.to_dict(include_children)
                for name, child in sorted(self.children.items())
            }

        return result


class MerkleTree:
    """Builds and manages a Merkle tree from checksum data"""

    def __init__(self):
        self.root = MerkleNode("/", is_dir=True)
        self.file_count = 0

    def add_file(self, filepath: str, file_hash: str):
        """Add a file to the tree with its hash"""
        # Remove leading slash and split path
        path_parts = filepath.strip('/').split('/')

        # Navigate/create the directory structure
        current_node = self.root

        # Process directory parts
        for part in path_parts[:-1]:
            if not part:  # Skip empty parts
                continue

            if part not in current_node.children:
                current_node.children[part] = MerkleNode(part, is_dir=True)

            current_node = current_node.children[part]

        # Add the file
        filename = path_parts[-1]
        if filename:  # Make sure filename is not empty
            file_node = MerkleNode(filename, is_dir=False)
            file_node.file_hash = file_hash
            current_node.children[filename] = file_node
            self.file_count += 1

    def build_from_checksum_file(self, checksum_file: str, progress_interval: int = 10000):
        """Build tree from a checksum file"""
        print(f"Reading checksum file: {checksum_file}")

        with open(checksum_file, 'r', encoding='utf-8', errors='ignore') as f:
            line_num = 0
            for line in f:
                line_num += 1
                line = line.strip()

                if not line:
                    continue

                # Parse line: "hash  /filepath" or "linenum→hash  /filepath"
                if '→' in line:
                    # Remove line number prefix
                    line = line.split('→', 1)[1]

                parts = line.split(None, 1)  # Split on whitespace, max 2 parts
                if len(parts) != 2:
                    continue

                file_hash, filepath = parts
                self.add_file(filepath, file_hash)

                if line_num % progress_interval == 0:
                    print(f"  Processed {line_num:,} lines, {self.file_count:,} files...")

        print(f"Completed: {self.file_count:,} files loaded")

    def compute_all_hashes(self):
        """Compute Merkle hashes for all nodes in the tree"""
        print("Computing Merkle hashes...")
        self.root.compute_merkle_hash()
        print(f"Merkle tree complete: {self.root.file_count:,} files")

    def save_to_json(self, output_file: str):
        """Save the tree structure to a JSON file"""
        print(f"Saving tree to: {output_file}")

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.root.to_dict(), f, indent=2)

        print("Tree saved successfully")

    def get_node_by_path(self, path: str) -> Optional[MerkleNode]:
        """Get a node by its path"""
        if path == "/" or path == "":
            return self.root

        path_parts = path.strip('/').split('/')
        current_node = self.root

        for part in path_parts:
            if not part:
                continue
            if part not in current_node.children:
                return None
            current_node = current_node.children[part]

        return current_node


def build_merkle_tree(checksum_file: str, output_json: str = None) -> MerkleTree:
    """
    Build a Merkle tree from a checksum file.

    Args:
        checksum_file: Path to the checksum file
        output_json: Optional path to save the tree as JSON

    Returns:
        MerkleTree object
    """
    tree = MerkleTree()
    tree.build_from_checksum_file(checksum_file)
    tree.compute_all_hashes()

    if output_json:
        tree.save_to_json(output_json)

    return tree


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python merkle_tree.py <checksum_file> [output_json]")
        print("\nExample:")
        print("  python merkle_tree.py ssd_checksums.txt ssd_merkle.json")
        sys.exit(1)

    checksum_file = sys.argv[1]
    output_json = sys.argv[2] if len(sys.argv) > 2 else None

    tree = build_merkle_tree(checksum_file, output_json)
    print(f"\nRoot Merkle hash: {tree.root.merkle_hash}")
    print(f"Total files: {tree.root.file_count:,}")
