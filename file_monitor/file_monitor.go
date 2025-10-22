package main

import (
	"crypto/sha256"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/vmihailenco/msgpack/v5"
)

// FileInfo stores metadata for a single file
type FileInfo struct {
	Mtime float64 `json:"mtime" msgpack:"mtime"`
	Mode  uint32  `json:"mode" msgpack:"mode"`
	Rdev  uint64  `json:"rdev" msgpack:"rdev"`
}

// State represents the saved state
type State struct {
	RootPath    string              `json:"root_path" msgpack:"root_path"`
	Timestamp   string              `json:"timestamp" msgpack:"timestamp"`
	FileCount   int                 `json:"file_count" msgpack:"file_count"`
	SummaryHash string              `json:"summary_hash" msgpack:"summary_hash"`
	Files       map[string]FileInfo `json:"files" msgpack:"files"`
}

// FileMonitor handles file system monitoring
type FileMonitor struct {
	rootPath        string
	excludePatterns []string
	files           map[string]FileInfo
	useMsgpack      bool
}

// NewFileMonitor creates a new file monitor
func NewFileMonitor(rootPath string, excludePatterns []string) *FileMonitor {
	absPath, err := filepath.Abs(rootPath)
	if err != nil {
		absPath = rootPath
	}

	return &FileMonitor{
		rootPath:        absPath,
		excludePatterns: excludePatterns,
		files:           make(map[string]FileInfo),
		useMsgpack:      true,
	}
}

// shouldExclude checks if a path should be excluded
func (fm *FileMonitor) shouldExclude(path string) bool {
	for _, pattern := range fm.excludePatterns {
		if strings.Contains(path, pattern) {
			return true
		}
	}
	return false
}

// CollectFiles scans the filesystem and collects file metadata
func (fm *FileMonitor) CollectFiles() error {
	// Use worker pool for parallel file stat operations
	type fileJob struct {
		path string
		rel  string
	}

	jobs := make(chan fileJob, 1000)
	results := make(chan struct {
		rel  string
		info FileInfo
	}, 1000)

	// Start worker goroutines
	var wg sync.WaitGroup
	numWorkers := 16
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for job := range jobs {
				info, err := os.Lstat(job.path)
				if err != nil {
					continue
				}

				stat, ok := info.Sys().(*syscall.Stat_t)
				if !ok {
					continue
				}

				results <- struct {
					rel  string
					info FileInfo
				}{
					rel: job.rel,
					info: FileInfo{
						Mtime: float64(stat.Mtim.Sec) + float64(stat.Mtim.Nsec)/1e9,
						Mode:  stat.Mode,
						Rdev:  stat.Rdev,
					},
				}
			}
		}()
	}

	// Collect results
	go func() {
		wg.Wait()
		close(results)
	}()

	// Walk filesystem and send jobs
	go func() {
		filepath.Walk(fm.rootPath, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return nil
			}

			if fm.shouldExclude(path) {
				if info.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}

			if !info.IsDir() {
				rel, err := filepath.Rel(fm.rootPath, path)
				if err == nil {
					jobs <- fileJob{path: path, rel: rel}
				}
			}

			return nil
		})
		close(jobs)
	}()

	// Collect results
	for result := range results {
		fm.files[result.rel] = result.info
	}

	return nil
}

// CalculateSummaryHash computes a hash representing all file states
func (fm *FileMonitor) CalculateSummaryHash() string {
	// Sort keys for deterministic hash
	keys := make([]string, 0, len(fm.files))
	for k := range fm.files {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	hasher := sha256.New()
	for _, path := range keys {
		info := fm.files[path]

		// For device files, use rdev; for regular files, use mtime
		var data string
		if (info.Mode & syscall.S_IFMT) == syscall.S_IFBLK ||
			(info.Mode & syscall.S_IFMT) == syscall.S_IFCHR {
			major := (info.Rdev >> 8) & 0xff
			minor := info.Rdev & 0xff
			data = fmt.Sprintf("%s:dev:%d:%d", path, major, minor)
		} else {
			data = fmt.Sprintf("%s:%f", path, info.Mtime)
		}

		io.WriteString(hasher, data)
	}

	return fmt.Sprintf("%x", hasher.Sum(nil))
}

// GetStateFilePath returns the path to the state file
func (fm *FileMonitor) GetStateFilePath() string {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		homeDir = "."
	}

	configDir := filepath.Join(homeDir, ".config", "file_monitor_go")
	os.MkdirAll(configDir, 0755)

	// Create unique filename based on path + excludes
	pathStr := fm.rootPath + strings.Join(fm.excludePatterns, "")
	hasher := sha256.New()
	io.WriteString(hasher, pathStr)
	pathHash := fmt.Sprintf("%x", hasher.Sum(nil))[:16]

	// Create readable filename
	safePath := strings.ReplaceAll(fm.rootPath, "/", "_")
	safePath = strings.ReplaceAll(safePath, " ", "-")
	if len(safePath) > 50 {
		safePath = safePath[:50]
	}

	ext := ".msgpack"
	if !fm.useMsgpack {
		ext = ".json"
	}

	return filepath.Join(configDir, pathHash+"_"+safePath+ext)
}

// SaveState saves the current state to a file
func (fm *FileMonitor) SaveState(stateFile string) error {
	state := State{
		RootPath:    fm.rootPath,
		Timestamp:   time.Now().Format(time.RFC3339),
		FileCount:   len(fm.files),
		SummaryHash: fm.CalculateSummaryHash(),
		Files:       fm.files,
	}

	var data []byte
	var err error

	if fm.useMsgpack {
		data, err = msgpack.Marshal(&state)
	} else {
		data, err = json.Marshal(&state)
	}

	if err != nil {
		return err
	}

	return os.WriteFile(stateFile, data, 0644)
}

// LoadState loads a previous state from a file
func (fm *FileMonitor) LoadState(stateFile string) (*State, error) {
	data, err := os.ReadFile(stateFile)
	if err != nil {
		return nil, err
	}

	var state State

	// Try msgpack first
	err = msgpack.Unmarshal(data, &state)
	if err != nil {
		// Fall back to JSON
		err = json.Unmarshal(data, &state)
		if err != nil {
			return nil, err
		}
	}

	return &state, nil
}

// CompareStates compares current state with previous state
func (fm *FileMonitor) CompareStates(previous *State) map[string][]string {
	currentFiles := make(map[string]bool)
	for k := range fm.files {
		currentFiles[k] = true
	}

	previousFiles := make(map[string]bool)
	for k := range previous.Files {
		previousFiles[k] = true
	}

	added := []string{}
	removed := []string{}
	modified := []string{}

	// Find added and modified
	for path := range currentFiles {
		if !previousFiles[path] {
			added = append(added, path)
		} else {
			curr := fm.files[path]
			prev := previous.Files[path]
			if curr.Mtime != prev.Mtime || curr.Rdev != prev.Rdev {
				modified = append(modified, path)
			}
		}
	}

	// Find removed
	for path := range previousFiles {
		if !currentFiles[path] {
			removed = append(removed, path)
		}
	}

	sort.Strings(added)
	sort.Strings(removed)
	sort.Strings(modified)

	return map[string][]string{
		"added":    added,
		"removed":  removed,
		"modified": modified,
	}
}

// GroupByDirectory groups files by directory prefix
func groupByDirectory(files []string, maxDepth int) map[string][]string {
	groups := make(map[string][]string)

	for _, file := range files {
		parts := strings.Split(file, string(filepath.Separator))

		var prefix string
		if len(parts) <= maxDepth {
			if len(parts) == 1 {
				prefix = file
			} else if len(parts) > 1 {
				prefix = strings.Join(parts[:len(parts)-1], string(filepath.Separator))
			} else {
				prefix = parts[0]
			}
		} else {
			prefix = strings.Join(parts[:maxDepth], string(filepath.Separator))
		}

		groups[prefix] = append(groups[prefix], file)
	}

	return groups
}

// FormatGroupedChanges formats file changes grouped by directory
func formatGroupedChanges(files []string, symbol string, maxDisplay int, expandAll bool) []string {
	if len(files) == 0 {
		return []string{}
	}

	groups := groupByDirectory(files, 3)
	output := []string{}
	totalShown := 0

	// Sort directory names
	dirs := make([]string, 0, len(groups))
	for dir := range groups {
		dirs = append(dirs, dir)
	}
	sort.Strings(dirs)

	for _, dir := range dirs {
		dirFiles := groups[dir]

		if len(dirFiles) == 1 {
			output = append(output, fmt.Sprintf("    %s %s", symbol, dirFiles[0]))
			totalShown++
		} else if expandAll || len(dirFiles) <= 3 {
			output = append(output, fmt.Sprintf("    %s %s/ (%d files):", symbol, dir, len(dirFiles)))
			sort.Strings(dirFiles)
			for _, f := range dirFiles {
				relative := f
				if strings.HasPrefix(f, dir+string(filepath.Separator)) {
					relative = f[len(dir)+1:]
				}
				output = append(output, fmt.Sprintf("        %s %s", symbol, relative))
			}
			totalShown += len(dirFiles)
		} else {
			output = append(output, fmt.Sprintf("    %s %s/ (%d files)", symbol, dir, len(dirFiles)))
			totalShown += len(dirFiles)
		}

		if len(output) >= maxDisplay {
			remaining := len(files) - totalShown
			if remaining > 0 {
				output = append(output, fmt.Sprintf("    ... and %d more files", remaining))
			}
			break
		}
	}

	return output
}

func main() {
	// Command line flags (must come before positional arguments)
	verbosePtr := flag.Bool("v", false, "Show all changed files")
	allPtr := flag.Bool("all", false, "Include noisy directories when scanning root")
	timingPtr := flag.Bool("timing", false, "Run timing benchmark")

	var excludes []string
	flag.Func("exclude", "Additional patterns to exclude (repeatable)", func(s string) error {
		excludes = append(excludes, s)
		return nil
	})

	flag.Parse()

	// Get path from positional argument or default to current directory
	path := "."
	if flag.NArg() > 0 {
		path = flag.Arg(0)
	}

	verbose := *verbosePtr
	all := *allPtr
	timing := *timingPtr

	// Build exclude patterns
	excludePatterns := []string{".git", "__pycache__", ".cache", "node_modules"}

	absPath, _ := filepath.Abs(path)
	if absPath == "/" {
		excludePatterns = append(excludePatterns, "/proc", "/sys")
		if !all {
			excludePatterns = append(excludePatterns, "/run", "/tmp", "/var/tmp", "/var/cache", "/var/run")
		}
	}

	excludePatterns = append(excludePatterns, excludes...)

	// Timing benchmark
	if timing {
		runTimingBenchmark(absPath, excludePatterns)
		return
	}

	// Normal operation
	fmt.Printf("Scanning: %s\n", absPath)
	fmt.Printf("Excluding: %s\n\n", strings.Join(excludePatterns, ", "))

	monitor := NewFileMonitor(path, excludePatterns)
	stateFile := monitor.GetStateFilePath()

	fmt.Println("Scanning filesystem...")
	start := time.Now()
	if err := monitor.CollectFiles(); err != nil {
		fmt.Fprintf(os.Stderr, "Error collecting files: %v\n", err)
		os.Exit(1)
	}
	scanTime := time.Since(start)

	summaryHash := monitor.CalculateSummaryHash()

	fmt.Printf("Files scanned: %d (%.3fs)\n", len(monitor.files), scanTime.Seconds())
	fmt.Printf("Summary hash: %s\n", summaryHash)
	fmt.Printf("State file: %s\n", stateFile)

	// Load previous state
	previousState, err := monitor.LoadState(stateFile)

	if err != nil || previousState == nil {
		fmt.Println("\nNo previous state found - this is the first run")
	} else {
		// Verify path matches
		if previousState.RootPath != absPath {
			fmt.Printf("\nWarning: State file path mismatch!\n")
			fmt.Printf("  Expected: %s\n", absPath)
			fmt.Printf("  Found: %s\n", previousState.RootPath)
			previousState = nil
		}
	}

	if previousState != nil {
		prevHash := previousState.SummaryHash
		prevTime := previousState.Timestamp

		fmt.Println("\n" + strings.Repeat("=", 60))
		fmt.Println("CHANGES SINCE LAST RUN")
		fmt.Println(strings.Repeat("=", 60))
		fmt.Printf("Previous scan: %s\n", prevTime)
		fmt.Printf("Previous hash: %s\n", prevHash)
		fmt.Printf("Current hash:  %s\n", summaryHash)

		if prevHash == summaryHash {
			fmt.Println("\n✓ No changes detected (hash match)")
		} else {
			// Detailed comparison
			changes := monitor.CompareStates(previousState)

			totalChanges := len(changes["added"]) + len(changes["removed"]) + len(changes["modified"])
			fmt.Printf("\nTotal changes: %d\n", totalChanges)

			if !verbose && totalChanges > 0 {
				fmt.Println("(Limited to 20 directory groups. Use -v/--verbose to see all)\n")
			}

			maxDisplay := 999999
			if !verbose {
				maxDisplay = 20
			}

			if len(changes["added"]) > 0 {
				fmt.Printf("\n[+] Added files (%d):\n", len(changes["added"]))
				for _, line := range formatGroupedChanges(changes["added"], "+", maxDisplay, verbose) {
					fmt.Println(line)
				}
			}

			if len(changes["removed"]) > 0 {
				fmt.Printf("\n[-] Removed files (%d):\n", len(changes["removed"]))
				for _, line := range formatGroupedChanges(changes["removed"], "-", maxDisplay, verbose) {
					fmt.Println(line)
				}
			}

			if len(changes["modified"]) > 0 {
				fmt.Printf("\n[*] Modified files (%d):\n", len(changes["modified"]))
				for _, line := range formatGroupedChanges(changes["modified"], "*", maxDisplay, verbose) {
					fmt.Println(line)
				}
			}
		}
	}

	// Save current state
	if err := monitor.SaveState(stateFile); err != nil {
		fmt.Fprintf(os.Stderr, "Error saving state: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("\nState saved to: %s\n", stateFile)
}

func runTimingBenchmark(rootPath string, excludePatterns []string) {
	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("TIMING BENCHMARK")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("Target: %s\n\n", rootPath)

	for run := 1; run <= 2; run++ {
		fmt.Printf("--- Run %d %s ---\n", run, map[bool]string{true: "(Cold cache)", false: "(Warm cache)"}[run == 1])

		monitor := NewFileMonitor(rootPath, excludePatterns)
		stateFile := monitor.GetStateFilePath()

		// File collection
		start := time.Now()
		monitor.CollectFiles()
		collectTime := time.Since(start)
		fmt.Printf("  File collection: %.4fs (%d files)\n", collectTime.Seconds(), len(monitor.files))

		// Summary hash
		start = time.Now()
		summaryHash := monitor.CalculateSummaryHash()
		hashTime := time.Since(start)
		fmt.Printf("  Summary hash:    %.6fs\n", hashTime.Seconds())

		// Load state
		var loadTime time.Duration
		var compareTime time.Duration
		var previousState *State

		start = time.Now()
		previousState, _ = monitor.LoadState(stateFile)
		loadTime = time.Since(start)
		if previousState != nil {
			fmt.Printf("  Load state:      %.6fs\n", loadTime.Seconds())

			if previousState.SummaryHash == summaryHash {
				fmt.Printf("  Quick check:     No changes (hash match)\n")
			} else {
				start = time.Now()
				changes := monitor.CompareStates(previousState)
				compareTime = time.Since(start)
				totalChanges := len(changes["added"]) + len(changes["removed"]) + len(changes["modified"])
				fmt.Printf("  Compare:         %.6fs (%d changes)\n", compareTime.Seconds(), totalChanges)
			}
		}

		// Save state
		start = time.Now()
		monitor.SaveState(stateFile)
		saveTime := time.Since(start)
		fmt.Printf("  Save state:      %.6fs\n", saveTime.Seconds())

		totalTime := collectTime + hashTime + loadTime + compareTime + saveTime
		fmt.Printf("  Total:           %.4fs\n\n", totalTime.Seconds())
	}

	fmt.Println(strings.Repeat("=", 60))
}
