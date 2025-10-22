"""Benchmark script for Mojo Game of Life"""
import time
from gridv1 import Grid


def benchmark(iterations: Int, grid_size: Int) -> Float64:
    """Run benchmark for specified iterations and grid size"""
    var grid = Grid.random(grid_size, grid_size, 42)

    start_time = time.perf_counter()

    for _ in range(iterations):
        grid = grid.evolve()

    end_time = time.perf_counter()
    elapsed = end_time - start_time

    return elapsed


def main():
    iterations = 100
    grid_size = 128

    print("Mojo Benchmark - Conway's Game of Life")
    print("=" * 50)
    print("Grid size:", grid_size, "x", grid_size)
    print("Iterations:", iterations)
    print()

    # Warmup
    _ = benchmark(10, grid_size)

    # Actual benchmark
    elapsed = benchmark(iterations, grid_size)

    print("Total time:", elapsed, "seconds")
    print("Average time per iteration:", elapsed / iterations * 1000, "ms")
    print("Iterations per second:", iterations / elapsed)
