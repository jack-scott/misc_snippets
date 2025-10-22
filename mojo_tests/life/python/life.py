"""Python implementation of Conway's Game of Life with pygame display"""
import time
from gridv1 import Grid


def run_display(
    grid: Grid,
    window_height: int = 600,
    window_width: int = 600,
    background_color: str = "black",
    cell_color: str = "green",
    pause: float = 0.1,
) -> None:
    import pygame

    # Initialize pygame modules
    pygame.init()

    # Create a window and set its title
    window = pygame.display.set_mode((window_height, window_width))
    pygame.display.set_caption("Conway's Game of Life")

    cell_height = window_height / grid.rows
    cell_width = window_width / grid.cols
    border_size = 1
    cell_fill_color = pygame.Color(cell_color)
    background_fill_color = pygame.Color(background_color)

    running = True
    while running:
        # Poll for events
        event = pygame.event.poll()
        if event.type == pygame.QUIT:
            # Quit if the window is closed
            running = False
        elif event.type == pygame.KEYDOWN:
            # Also quit if the user presses <Escape> or 'q'
            if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                running = False

        # Clear the window by painting with the background color
        window.fill(background_fill_color)

        # Draw each live cell in the grid
        for row in range(grid.rows):
            for col in range(grid.cols):
                if grid[row, col]:
                    x = col * cell_width + border_size
                    y = row * cell_height + border_size
                    width = cell_width - border_size
                    height = cell_height - border_size
                    pygame.draw.rect(
                        window,
                        cell_fill_color,
                        (x, y, width, height),
                    )

        # Update the display
        pygame.display.flip()

        # Pause to let the user appreciate the scene
        time.sleep(pause)

        # Next generation
        grid = grid.evolve()

    # Shut down pygame cleanly
    pygame.quit()


def main():
    start = Grid.random_grid(128, 128)
    run_display(start)


if __name__ == "__main__":
    main()
