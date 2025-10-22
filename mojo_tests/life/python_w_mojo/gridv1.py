"""Python Grid implementation that uses Mojo for performance-critical operations"""
import random
from typing import Optional


class Grid:
    """Grid class for Conway's Game of Life with Mojo-accelerated evolve"""

    # Class-level Mojo module reference (lazy loaded)
    _mojo_module = None

    def __init__(self, rows: int, cols: int, data: list[list[int]]):
        self.rows = rows
        self.cols = cols
        self.data = data

    @classmethod
    def _get_mojo_module(cls):
        """Lazy load the Mojo module"""
        if cls._mojo_module is None:
            try:
                from importlib.util import find_spec
                import sys
                import os

                # Add current directory to path if not already there
                current_dir = os.path.dirname(os.path.abspath(__file__))
                if current_dir not in sys.path:
                    sys.path.insert(0, current_dir)

                # Try to import the Mojo module
                cls._mojo_module = __import__('grid_core')
            except ImportError as e:
                print(f"Warning: Could not load Mojo module: {e}")
                print("Falling back to pure Python implementation")
                cls._mojo_module = None
        return cls._mojo_module

    def __getitem__(self, pos: tuple[int, int]) -> int:
        row, col = pos
        return self.data[row][col]

    def __setitem__(self, pos: tuple[int, int], value: int) -> None:
        row, col = pos
        self.data[row][col] = value

    def __str__(self) -> str:
        result = []
        for row in range(self.rows):
            row_str = ""
            for col in range(self.cols):
                if self[row, col] == 1:
                    row_str += "*"
                else:
                    row_str += " "
            result.append(row_str)
        return "\n".join(result)

    @staticmethod
    def glider() -> 'Grid':
        glider = [
            [0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [1, 1, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0],
        ]
        return Grid(8, 8, glider)

    @staticmethod
    def random_grid(rows: int, cols: int, seed: Optional[int] = None) -> 'Grid':
        if seed is not None:
            random.seed(seed)
        else:
            random.seed()

        data = []
        for _row in range(rows):
            row_data = []
            for _col in range(cols):
                # Generate a random 0 or 1
                row_data.append(random.randint(0, 1))
            data.append(row_data)

        return Grid(rows, cols, data)

    def evolve(self) -> 'Grid':
        """
        Evolve the grid to the next generation using Mojo acceleration.
        Falls back to Python if Mojo module is not available.
        """
        mojo_module = self._get_mojo_module()
        # Call the Mojo function for performance-critical evolution
        next_data = mojo_module.evolve_grid(self.data, self.rows, self.cols)
        return Grid(self.rows, self.cols, next_data)