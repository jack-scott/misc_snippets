# Favicon Fetcher

A Python script that fetches favicons from websites and generates an image report if no obvious favicon is found.

## Installation

This project uses [pixi](https://pixi.sh) for dependency management.

```bash
pixi install
```

## Usage

Basic usage:
```bash
pixi run fetch example.com
```

Or use pixi shell:
```bash
pixi shell
python favicon_fetcher.py example.com
```

With https:
```bash
pixi run fetch https://example.com
```

Force generate image report even if favicon is found:
```bash
pixi run fetch example.com --force-report
```

Custom output file:
```bash
pixi run fetch example.com -o my_report.html
```

## How it works

1. Fetches the HTML from the given URL
2. Parses the HTML using the `justhtml` library
3. Looks for favicon in common locations:
   - `<link rel="icon">`
   - `<link rel="shortcut icon">`
   - `<link rel="apple-touch-icon">`
   - `/favicon.ico` (default fallback)
4. If no obvious favicon is found, generates an HTML report with all images found on the page
5. Images in the report are sorted from smallest to largest by file size
6. Each image includes its URL and size information

## Example Output

When a favicon is found:
```
Fetching https://example.com...
Found favicon via <link rel='icon'>: https://example.com/favicon.ico

✓ Favicon URL: https://example.com/favicon.ico
```

When no favicon is found:
```
Fetching https://example.com...

✗ No obvious favicon found

Generating report with 15 images...
Fetching sizes for 15 images...

Generated report: /path/to/image_report.html

Open this file in your browser: /path/to/image_report.html
```
