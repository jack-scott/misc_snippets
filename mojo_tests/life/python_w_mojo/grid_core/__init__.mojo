"""Mojo module with performance-critical Grid functions for Python interop"""
from python import Python, PythonObject


fn evolve_grid(grid_data: PythonObject, rows: Int, cols: Int) raises -> PythonObject:
    """
    High-performance evolve function that takes Python list and returns evolved grid.

    Args:
        grid_data: Python 2D list representing the grid.
        rows: Number of rows in the grid.
        cols: Number of columns in the grid.

    Returns:
        New Python 2D list with the next generation.
    """
    # Create the next generation grid
    var builtins = Python.import_module("builtins")
    var next_generation = builtins.list()

    for row in range(rows):
        var row_data = builtins.list()

        # Calculate neighboring row indices, handling "wrap-around"
        var row_above = (row - 1) % rows
        var row_below = (row + 1) % rows

        for col in range(cols):
            # Calculate neighboring column indices, handling "wrap-around"
            var col_left = (col - 1) % cols
            var col_right = (col + 1) % cols

            # Determine number of populated cells around the current cell
            var num_neighbors = (
                Int(grid_data[row_above][col_left])
                + Int(grid_data[row_above][col])
                + Int(grid_data[row_above][col_right])
                + Int(grid_data[row][col_left])
                + Int(grid_data[row][col_right])
                + Int(grid_data[row_below][col_left])
                + Int(grid_data[row_below][col])
                + Int(grid_data[row_below][col_right])
            )

            # Determine the state of the current cell for the next generation
            var new_state = 0
            var current_cell = Int(grid_data[row][col])
            if current_cell == 1 and (num_neighbors == 2 or num_neighbors == 3):
                new_state = 1
            elif current_cell == 0 and num_neighbors == 3:
                new_state = 1

            _ = row_data.append(new_state)

        _ = next_generation.append(row_data)

    return next_generation
