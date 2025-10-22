# Python + Mojo Hybrid Implementation

This folder demonstrates Python and Mojo interoperability.

## What's Inside

This implementation shows **Mojo calling Python code** - the Mojo runtime imports and uses the Python Grid class for computation.

### Files

- `gridv1_pure.py` - Pure Python Grid implementation
- `benchmark_mojo.mojo` - Mojo script that imports and benchmarks the Python Grid
- `gridv1.py` - Original attempt at Python calling Mojo (requires complex FFI setup)
- `grid_core/` - Mojo package (for reference)

## How to Run

### Mojo Calling Python

This demonstrates Mojo's ability to import and use Python libraries:

```bash
cd python_w_mojo
pixi run mojo benchmark_mojo.mojo
```

This runs the Python Grid evolution inside Mojo's runtime. Performance is similar to pure Python because the computation is still happening in Python code, but it demonstrates the interoperability.

### Pure Python Benchmark (for comparison)

```bash
cd python_w_mojo
pixi run python benchmark.py
```

Note: This currently fails because Python calling Mojo requires more complex setup (shared libraries/FFI).

## Performance

When Mojo calls Python code, performance is similar to pure Python (~1.7s for 100 iterations) because the actual computation happens in Python. The benefit of this approach is that you can:

1. Gradually migrate Python code to Mojo
2. Use existing Python libraries from Mojo
3. Mix Python and Mojo in the same codebase

For true performance gains, you need to rewrite the performance-critical parts in pure Mojo (see the `mojo/` folder for pure Mojo implementation).

## Notes

- **Mojo → Python**: Easy (shown here), use `Python.import_module()`
- **Python → Mojo**: Complex, requires compiling Mojo to shared library and using FFI
- For best performance: Use pure Mojo for compute-intensive code
