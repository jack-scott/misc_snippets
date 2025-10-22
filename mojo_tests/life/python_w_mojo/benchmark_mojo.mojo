"""Mojo benchmark that can be called from Python"""
import time
from python import Python


fn main() raises:
    # Import the Python gridv1 module from current directory
    var sys = Python.import_module("sys")
    var os_module = Python.import_module("os")

    # Add current directory to Python path
    var current_dir = os_module.getcwd()
    _ = sys.path.insert(0, current_dir)

    var gridv1 = Python.import_module("gridv1_pure")
    var Grid = gridv1.Grid

    var iterations = 100
    var grid_size = 128

    print("Python + Mojo (Mojo calling Python) Benchmark")
    print("=" * 50)
    print("Grid size:", grid_size, "x", grid_size)
    print("Iterations:", iterations)
    print()

    # Create grid using Python
    var grid = Grid.random_grid(grid_size, grid_size, 42)

    # Time the evolution in Mojo
    var start_time = time.perf_counter()

    for _ in range(iterations):
        grid = grid.evolve()

    var end_time = time.perf_counter()
    var elapsed = end_time - start_time

    print("Total time:", elapsed, "seconds")
    print("Average time per iteration:", elapsed / iterations * 1000, "ms")
    print("Iterations per second:", iterations / elapsed)
