#!/bin/bash
# Build script to compile Mojo module for Python import

echo "Building Mojo module for Python interop..."
mojo package grid_core.mojo -o grid_core.mojopkg

echo "Mojo module built successfully!"
echo "You can now import it from Python with: import grid_core"
