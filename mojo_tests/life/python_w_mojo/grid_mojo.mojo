"""Mojo implementation with pure Mojo Grid for performance"""
import random
from collections import Optional


@value
struct Grid:
    """Grid struct for Conway's Game of Life."""
    var rows: Int
    var cols: Int
    var data: List[List[Int]]

    fn __getitem__(self, row: Int, col: Int) -> Int:
        return self.data[row][col]

    fn __setitem__(mut self, row: Int, col: Int, value: Int) -> None:
        self.data[row][col] = value

    @staticmethod
    fn random_grid(rows: Int, cols: Int, seed: Optional[Int] = None) -> Self:
        if seed:
            random.seed(seed.value())
        else:
            random.seed()

        var data = List[List[Int]]()
        for _row in range(rows):
            var row_data = List[Int]()
            for _col in range(cols):
                row_data.append(Int(random.random_si64(0, 1)))
            data.append(row_data^)

        return Self(rows, cols, data^)

    fn evolve(self) -> Self:
        """Evolve the grid to the next generation."""
        var next_generation = List[List[Int]]()

        for row in range(self.rows):
            var row_data = List[Int]()

            # Calculate neighboring row indices, handling "wrap-around"
            var row_above = (row - 1) % self.rows
            var row_below = (row + 1) % self.rows

            for col in range(self.cols):
                # Calculate neighboring column indices, handling "wrap-around"
                var col_left = (col - 1) % self.cols
                var col_right = (col + 1) % self.cols

                # Determine number of populated cells around the current cell
                var num_neighbors = (
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
                var new_state = 0
                if self[row, col] == 1 and (num_neighbors == 2 or num_neighbors == 3):
                    new_state = 1
                elif self[row, col] == 0 and num_neighbors == 3:
                    new_state = 1
                row_data.append(new_state)

            next_generation.append(row_data^)

        return Self(self.rows, self.cols, next_generation^)

    fn to_python_list(self) -> object:
        """Convert Grid data to Python list."""
        from python import Python

        var builtins = Python.import_module("builtins")
        var py_list = builtins.list()

        for row in range(self.rows):
            var py_row = builtins.list()
            for col in range(self.cols):
                _ = py_row.append(self[row, col])
            _ = py_list.append(py_row)

        return py_list^
