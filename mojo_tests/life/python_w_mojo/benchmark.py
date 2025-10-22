"""Benchmark script for Python + Mojo hybrid Game of Life"""
import time
from gridv1 import Grid


def benchmark(iterations: int, grid_size: int) -> float:
    """Run benchmark for specified iterations and grid size"""
    grid = Grid.random_grid(grid_size, grid_size, 42)

    start_time = time.perf_counter()

    for _ in range(iterations):
        grid = grid.evolve()

    end_time = time.perf_counter()
    elapsed = end_time - start_time

    return elapsed


def main():
    iterations = 100
    grid_size = 128

    print("Python + Mojo Hybrid Benchmark - Conway's Game of Life")
    print("=" * 50)
    print(f"Grid size: {grid_size} x {grid_size}")
    print(f"Iterations: {iterations}")
    print()

    # Warmup
    _ = benchmark(10, grid_size)

    # Actual benchmark
    elapsed = benchmark(iterations, grid_size)

    print(f"Total time: {elapsed:.4f} seconds")
    print(f"Average time per iteration: {elapsed / iterations * 1000:.4f} ms")
    print(f"Iterations per second: {iterations / elapsed:.2f}")


if __name__ == "__main__":
    main()
