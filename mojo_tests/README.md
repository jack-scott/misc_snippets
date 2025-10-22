# Mojo Tests

Experiments and performance comparisons with the Mojo programming language.

## Contents

- **life/** - Conway's Game of Life implementations comparing Python vs Mojo performance
  - Pure Python, pure Mojo, and Python/Mojo hybrid approaches
  - Benchmarking scripts to measure performance differences
  - See `life/python_w_mojo/README.md` for detailed interop notes

- **gpu-intro/** - Basic GPU programming examples in Mojo
  - Vector addition and GPU device detection

## Setup

### Install Pixi

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

Or visit [pixi.sh](https://pixi.sh) for other installation methods.

## Running Tests

### Game of Life Benchmarks

Pure Python version:
```bash
cd life/python
pixi run python benchmark.py
```

Pure Mojo version:
```bash
cd life/mojo
pixi run mojo benchmark.mojo
```

Python/Mojo hybrid (Mojo calling Python):
```bash
cd life/python_w_mojo
pixi run mojo benchmark_mojo.mojo
```

### GPU Examples

```bash
cd gpu-intro
pixi run mojo vector_addition.mojo
```

## Notes

Each subfolder has its own `pixi.toml` that manages dependencies. Pixi will automatically set up the environment when you run commands.
