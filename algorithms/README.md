# Algorithms

Reference implementations of common algorithms.

## Merkle Tree

**File:** `merkle_tree.py`

A binary hash tree where each leaf is a hash of data and each internal node is a hash of its children. The root hash represents the entire dataset.

### Use Cases

- **Distributed systems:** Git, BitTorrent, IPFS
- **Blockchains:** Bitcoin, Ethereum (transaction verification)
- **Databases:** Cassandra (replica synchronization)
- **CDNs:** Content integrity verification

### Key Properties

1. **Tamper-evident:** Any change to data changes the root hash
2. **Efficient proofs:** Verify data inclusion with O(log n) hashes
3. **Partial verification:** Don't need entire dataset to verify one item

### When NOT to Use

- Local-only operations (no remote verification needed)
- Need to know ALL changes (not just "changed/unchanged")
- Both states are trusted (no adversary)

→ Use simple hash of sorted data instead: `sha256(json.dumps(sorted(data)))`

### Example

```python
from merkle_tree import MerkleTree

# Build tree from data
tree = MerkleTree()
tree.build_from_data(["apple", "banana", "cherry"])

# Get root hash (represents all data)
root = tree.get_root_hash()

# Generate proof that "banana" is in tree
proof = tree.get_proof("banana")

# Verify proof (without rebuilding tree)
is_valid = tree.verify_leaf("banana", proof)
```

### Run Example

```bash
python merkle_tree.py
```
