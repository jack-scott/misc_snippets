# Building the Go Version

The Go implementation provides the same functionality as the Python version but with significantly better performance through compilation and parallel file scanning.

## Install Go

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install golang-go
```

### Or download from official site
```bash
wget https://go.dev/dl/go1.21.5.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.21.5.linux-amd64.tar.gz
export PATH=$PATH:/usr/local/go/bin
```

## Build

```bash
cd /home/jack/Documents/project/misc_snippets/file_monitor

# Download dependencies
go mod download

# Build the binary
go build -o file_monitor_go file_monitor.go

# Or build with optimizations
go build -ldflags="-s -w" -o file_monitor_go file_monitor.go
```

## Usage

Same as Python version:

```bash
# Basic monitoring
./file_monitor_go /path/to/monitor

# Timing benchmark
./file_monitor_go /path/to/monitor --timing

# Verbose output
./file_monitor_go /path/to/monitor -v

# With exclusions
./file_monitor_go /home --exclude Downloads --exclude .cache
```

## Performance Comparison

Expected performance improvements over Python (469k files):

| Operation | Python | Go (estimated) | Improvement |
|-----------|--------|----------------|-------------|
| File collection | 7.5s | 1-2s | **3-7x faster** |
| Summary hash | 0.1s | 0.02s | **5x faster** |
| Load state (msgpack) | 0.2s | 0.05s | **4x faster** |
| Compare | 0.5s | 0.1s | **5x faster** |
| Save state (msgpack) | 1.5s | 0.3s | **5x faster** |
| **Total** | **9.8s** | **1.5-2.5s** | **4-6x faster** |

## Why Go is Faster

1. **Compiled code** - No interpreter overhead
2. **Parallel file scanning** - 16 goroutines stat files concurrently
3. **Efficient memory** - No GIL, better memory management
4. **Fast serialization** - Native msgpack implementation
5. **Better I/O** - More efficient syscalls

## Key Differences

### Python Version
- Uses sequential `os.walk()`
- Single-threaded file stat operations
- GIL limits parallelism
- Runtime interpretation overhead

### Go Version
- Uses worker pool (16 goroutines)
- Parallel file stat operations
- No GIL - true parallelism
- Compiled native code

## State File Compatibility

The Go version uses a separate config directory:
- Python: `~/.config/file_monitor/`
- Go: `~/.config/file_monitor_go/`

Both use msgpack format, but maintain separate state files to avoid conflicts.
