#!/bin/bash
# Compare Python vs Go performance

set -e

TARGET="${1:-.}"
echo "Comparing Python vs Go on: $TARGET"
echo ""

# Check if Go binary exists
if [ ! -f "./file_monitor_go" ]; then
    echo "Go binary not found. Building..."
    if command -v go &> /dev/null; then
        go build -ldflags="-s -w" -o file_monitor_go file_monitor.go
        echo "✓ Go binary built"
        echo ""
    else
        echo "Go not installed. Skipping Go version."
        echo "Install Go: sudo apt install golang-go"
        echo ""
        GO_AVAILABLE=false
    fi
else
    GO_AVAILABLE=true
fi

# Check if Python has msgpack
if python3 -c "import msgpack" 2>/dev/null; then
    echo "✓ Python msgpack available"
else
    echo "⚠ Python msgpack not installed (will be slower)"
    echo "Install: pip3 install msgpack"
fi

echo ""
echo "================================"
echo "Python Version"
echo "================================"
time ./file_monitor.py "$TARGET"

if [ "$GO_AVAILABLE" != "false" ]; then
    echo ""
    echo "================================"
    echo "Go Version"
    echo "================================"
    time ./file_monitor_go "$TARGET"

    echo ""
    echo "================================"
    echo "Summary"
    echo "================================"
    echo "Both versions completed successfully."
    echo "Check 'time' output above to compare performance."
fi
