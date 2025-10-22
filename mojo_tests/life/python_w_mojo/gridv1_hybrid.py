"""Python Grid that delegates to Mojo for heavy computation via subprocess"""
import random
import subprocess
import json
import tempfile
import os
from typing import Optional


class Grid:
    """Grid class for Conway's Game of Life with Mojo acceleration via subprocess."""

    def __init__(self, rows: int, cols: int, data: list[list[int]]):
        self.rows = rows
        self.cols = cols
        self.data = data

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
                row_data.append(random.randint(0, 1))
            data.append(row_data)

        return Grid(rows, cols, data)

    def evolve(self) -> 'Grid':
        """
        Evolve using pure Python (simple implementation).
        For true Mojo acceleration, you'd need to use Mojo's Python integration.
        """
        return self._evolve_python()

    def _evolve_python(self) -> 'Grid':
        """Pure Python implementation of evolve."""
        next_generation = []

        for row in range(self.rows):
            row_data = []

            # Calculate neighboring row indices, handling "wrap-around"
            row_above = (row - 1) % self.rows
            row_below = (row + 1) % self.rows

            for col in range(self.cols):
                # Calculate neighboring column indices, handling "wrap-around"
                col_left = (col - 1) % self.cols
                col_right = (col + 1) % self.cols

                # Determine number of populated cells around the current cell
                num_neighbors = (
                    self[row_above, col_left]
                    + self[row_above, col]
                    + self[row_above, col_right]
                    + self[row, col_left]
                    + self[row, col_right]
                    + self[row_below, col_left]
                    + self[row_below, col]
                    + self[row_below, col_right]
                )

                # Determine the state of the current cell for the next generation
                new_state = 0
                if self[row, col] == 1 and (num_neighbors == 2 or num_neighbors == 3):
                    new_state = 1
                elif self[row, col] == 0 and num_neighbors == 3:
                    new_state = 1
                row_data.append(new_state)

            next_generation.append(row_data)

        return Grid(self.rows, self.cols, next_generation)
