#!/usr/bin/env python3
"""
Merkle Tree Implementation

A Merkle tree (hash tree) is a binary tree where:
- Each leaf node is a hash of data
- Each internal node is a hash of its children's hashes
- The root hash represents the entire dataset

Used in: Git, Bitcoin, IPFS, BitTorrent, etc.
"""

import hashlib
from typing import List, Tuple, Optional


class MerkleNode:
    """Represents a node in the Merkle tree."""

    def __init__(self, hash_value: str, left=None, right=None, data: Optional[str] = None):
        self.hash = hash_value
        self.left = left
        self.right = right
        self.data = data  # Only set for leaf nodes

    def is_leaf(self) -> bool:
        return self.data is not None


class MerkleTree:
    """Builds and manages a Merkle tree."""

    def __init__(self):
        self.root = None

    @staticmethod
    def _hash_data(data: str) -> str:
        """Hash a piece of data (leaf node)."""
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    @staticmethod
    def _hash_pair(left_hash: str, right_hash: str) -> str:
        """Hash a pair of hashes (internal node)."""
        combined = f"{left_hash}{right_hash}".encode('utf-8')
        return hashlib.sha256(combined).hexdigest()

    def build_from_data(self, data_items: List[str]) -> 'MerkleNode':
        """
        Build a Merkle tree from a list of data items.

        Args:
            data_items: List of strings to hash into the tree

        Returns:
            Root node of the tree
        """
        if not data_items:
            # Empty tree
            empty_hash = hashlib.sha256(b"empty").hexdigest()
            self.root = MerkleNode(empty_hash)
            return self.root

        # Create leaf nodes
        nodes = []
        for item in data_items:
            hash_value = self._hash_data(item)
            node = MerkleNode(hash_value, data=item)
            nodes.append(node)

        # Build tree bottom-up by pairing nodes
        while len(nodes) > 1:
            next_level = []

            # Process pairs of nodes
            for i in range(0, len(nodes), 2):
                left = nodes[i]

                if i + 1 < len(nodes):
                    # We have a pair
                    right = nodes[i + 1]
                    hash_value = self._hash_pair(left.hash, right.hash)
                    parent = MerkleNode(hash_value, left, right)
                else:
                    # Odd number of nodes, duplicate the last one
                    hash_value = self._hash_pair(left.hash, left.hash)
                    parent = MerkleNode(hash_value, left, left)

                next_level.append(parent)

            nodes = next_level

        self.root = nodes[0]
        return self.root

    def get_root_hash(self) -> str:
        """Get the root hash of the tree."""
        if self.root is None:
            raise ValueError("Tree not built yet")
        return self.root.hash

    def verify_leaf(self, data: str, proof: List[Tuple[str, str]]) -> bool:
        """
        Verify that a piece of data is in the tree using a Merkle proof.

        Args:
            data: The data item to verify
            proof: List of (hash, position) where position is 'left' or 'right'
                  These are the sibling hashes along the path to root

        Returns:
            True if data is in tree, False otherwise
        """
        current_hash = self._hash_data(data)

        for sibling_hash, position in proof:
            if position == 'left':
                current_hash = self._hash_pair(sibling_hash, current_hash)
            else:  # right
                current_hash = self._hash_pair(current_hash, sibling_hash)

        return current_hash == self.root.hash

    def get_proof(self, data: str) -> Optional[List[Tuple[str, str]]]:
        """
        Generate a Merkle proof for a data item.

        Args:
            data: The data item to generate proof for

        Returns:
            List of (sibling_hash, position) pairs, or None if data not found
        """
        def find_proof(node: MerkleNode, target_hash: str, proof: List) -> bool:
            if node.is_leaf():
                return node.hash == target_hash

            # Try left subtree
            if node.left and find_proof(node.left, target_hash, proof):
                if node.right:
                    proof.append((node.right.hash, 'right'))
                return True

            # Try right subtree
            if node.right and find_proof(node.right, target_hash, proof):
                if node.left:
                    proof.append((node.left.hash, 'left'))
                return True

            return False

        if self.root is None:
            return None

        target_hash = self._hash_data(data)
        proof = []

        if find_proof(self.root, target_hash, proof):
            return proof  # Already in leaf-to-root order

        return None


def merkle_root_from_files(file_data: List[Tuple[str, str]]) -> str:
    """
    Calculate Merkle root from a list of (filepath, content) tuples.

    This is a convenience function for the common use case of hashing files.

    Args:
        file_data: List of (filepath, file_content_or_metadata) tuples

    Returns:
        Hex string of the root hash
    """
    tree = MerkleTree()

    # Combine filepath and content for each item
    items = [f"{path}:{content}" for path, content in file_data]

    # Sort for deterministic ordering
    items.sort()

    tree.build_from_data(items)
    return tree.get_root_hash()


if __name__ == '__main__':
    # Example usage
    print("Merkle Tree Example\n" + "="*50)

    # Example 1: Simple data
    print("\n1. Simple data items:")
    tree = MerkleTree()
    data = ["apple", "banana", "cherry", "date"]
    tree.build_from_data(data)
    print(f"   Data: {data}")
    print(f"   Root hash: {tree.get_root_hash()}")

    # Example 2: Merkle proof
    print("\n2. Verify 'banana' is in the tree:")
    proof = tree.get_proof("banana")
    print(f"   Proof: {proof}")
    is_valid = tree.verify_leaf("banana", proof)
    print(f"   Valid: {is_valid}")

    # Example 3: Try to verify data that's not in tree
    print("\n3. Verify 'grape' is in the tree:")
    fake_proof = tree.get_proof("grape")
    print(f"   Proof: {fake_proof}")

    # Example 4: File metadata
    print("\n4. Merkle root from file metadata:")
    files = [
        ("file1.txt", "mtime:1234567890"),
        ("file2.txt", "mtime:1234567891"),
        ("file3.txt", "mtime:1234567892"),
    ]
    root = merkle_root_from_files(files)
    print(f"   Files: {files}")
    print(f"   Root hash: {root}")

    # Show that changing one file changes root
    print("\n5. Change one file's mtime:")
    files[1] = ("file2.txt", "mtime:9999999999")
    new_root = merkle_root_from_files(files)
    print(f"   New root hash: {new_root}")
    print(f"   Roots match: {root == new_root}")
