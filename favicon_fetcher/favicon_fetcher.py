#!/usr/bin/env python3
"""
Favicon Fetcher - Finds favicons from websites
Uses justhtml for HTML parsing
"""

import sys
import argparse
import warnings
from urllib.parse import urljoin, urlparse, urlunparse
from pathlib import Path
from io import BytesIO
import requests
from requests.exceptions import SSLError
from justhtml import JustHTML
from PIL import Image


def clean_url(url):
    """Remove query parameters and fragments from URL to get the base URL"""
    parsed = urlparse(url)
    # Reconstruct URL without query params and fragment
    cleaned = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        '',  # params
        '',  # query
        ''   # fragment
    ))
    return cleaned


def fetch_html(url, verify_ssl=True):
    """Fetch HTML content from URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(url, headers=headers, timeout=10, verify=verify_ssl)
    response.raise_for_status()
    return response.text


def get_image_dimensions(url, verify_ssl=True):
    """Get the dimensions of an image in pixels (width, height)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5, allow_redirects=True, verify=verify_ssl)
        response.raise_for_status()

        # Open image from bytes
        img = Image.open(BytesIO(response.content))
        return img.size  # Returns (width, height)
    except Exception as e:
        return None


def get_image_size(url, verify_ssl=True):
    """Get the size of an image in bytes"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.head(url, headers=headers, timeout=5, allow_redirects=True, verify=verify_ssl)
        if 'content-length' in response.headers:
            return int(response.headers['content-length'])
        # If HEAD doesn't work, try GET with streaming
        response = requests.get(url, headers=headers, timeout=5, stream=True, verify=verify_ssl)
        response.raw.read(1)  # Read a byte to trigger download
        if 'content-length' in response.headers:
            return int(response.headers['content-length'])
        return 0
    except Exception as e:
        print(f"Error getting size for {url}: {e}", file=sys.stderr)
        return 0


def find_favicon(html, base_url, verify_ssl=True):
    """
    Parse HTML and find favicon URLs
    Returns a tuple: (list of (display_url, fetch_url) tuples, all_images)
    """
    doc = JustHTML(html)
    favicon_urls = []

    # Look for favicon in common link tags
    favicon_rels = ['icon', 'shortcut icon', 'apple-touch-icon', 'apple-touch-icon-precomposed']

    for link in doc.query('link'):
        rel = link.attrs.get('rel', '')
        href = link.attrs.get('href', '')

        if rel in favicon_rels and href:
            full_url = urljoin(base_url, href)
            cleaned_url = clean_url(full_url)
            # Store both cleaned URL for display and full URL for fetching
            if cleaned_url not in [url[0] for url in favicon_urls]:
                favicon_urls.append((cleaned_url, full_url))
                print(f"Found favicon via <link rel='{rel}'>: {cleaned_url}")

    # If no favicon found in link tags, try default /favicon.ico
    if not favicon_urls:
        default_favicon = urljoin(base_url, '/favicon.ico')
        try:
            response = requests.head(default_favicon, timeout=5, allow_redirects=True, verify=verify_ssl)
            if response.status_code == 200:
                cleaned_url = clean_url(response.url)  # Use final URL after redirects
                favicon_urls.append((cleaned_url, response.url))
                print(f"Found favicon at default location: {cleaned_url}")
        except:
            pass

    # Collect all images for fallback
    all_images = []

    # Find all img tags
    for img in doc.query('img'):
        src = img.attrs.get('src', '')
        if src:
            img_url = urljoin(base_url, src)
            all_images.append(img_url)

    # Find all link tags with images (like PNG icons)
    for link in doc.query('link'):
        href = link.attrs.get('href', '')
        if href and any(ext in href.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg']):
            img_url = urljoin(base_url, href)
            if img_url not in all_images:
                all_images.append(img_url)

    return favicon_urls, all_images


def generate_image_report(images, base_url, output_file='image_report.html', verify_ssl=True):
    """Generate HTML report with all images sorted by size"""
    print(f"\nFetching sizes for {len(images)} images...")

    # Get sizes for all images
    image_data = []
    for img_url in images:
        size = get_image_size(img_url, verify_ssl=verify_ssl)
        image_data.append({
            'url': img_url,
            'size': size,
            'size_kb': size / 1024 if size > 0 else 0
        })

    # Sort by size (smallest to largest)
    image_data.sort(key=lambda x: x['size'])

    # Generate HTML
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Image Report - {base_url}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 20px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
        }}
        .image-container {{
            background: white;
            margin: 15px 0;
            padding: 15px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        .image-preview {{
            flex-shrink: 0;
        }}
        .image-preview img {{
            max-width: 100px;
            max-height: 100px;
            border: 1px solid #ddd;
            border-radius: 3px;
        }}
        .image-info {{
            flex-grow: 1;
        }}
        .image-url {{
            color: #0066cc;
            word-break: break-all;
            font-family: monospace;
            font-size: 12px;
            margin: 5px 0;
        }}
        .image-size {{
            color: #666;
            font-size: 14px;
        }}
        .size-badge {{
            display: inline-block;
            background: #4CAF50;
            color: white;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <h1>Image Report for {base_url}</h1>
    <p>Found {len(image_data)} images, sorted from smallest to largest</p>
    <div id="images">
"""

    for idx, img in enumerate(image_data, 1):
        html_content += f"""
        <div class="image-container">
            <div class="image-preview">
                <img src="{img['url']}" alt="Image {idx}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22%3E%3Crect width=%22100%22 height=%22100%22 fill=%22%23ddd%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 font-family=%22Arial%22 font-size=%2212%22 fill=%22%23999%22%3EError%3C/text%3E%3C/svg%3E'">
            </div>
            <div class="image-info">
                <div class="image-size">
                    <span class="size-badge">{img['size_kb']:.2f} KB</span>
                    ({img['size']} bytes)
                </div>
                <div class="image-url">
                    <a href="{img['url']}" target="_blank">{img['url']}</a>
                </div>
            </div>
        </div>
"""

    html_content += """
    </div>
</body>
</html>
"""

    # Write to file
    output_path = Path(output_file)
    output_path.write_text(html_content)
    print(f"\nGenerated report: {output_path.absolute()}")
    return str(output_path.absolute())


def main():
    parser = argparse.ArgumentParser(description='Fetch favicon from a website')
    parser.add_argument('url', help='Website URL to fetch favicon from')
    parser.add_argument('-o', '--output', default='image_report.html',
                        help='Output HTML file for image report (default: image_report.html)')
    parser.add_argument('-f', '--force-report', action='store_true',
                        help='Generate image report even if favicon is found')
    parser.add_argument('-k', '--no-verify-ssl', action='store_true',
                        help='Disable SSL certificate verification (useful for self-signed certs)')

    args = parser.parse_args()

    # SSL verification setting
    verify_ssl = not args.no_verify_ssl

    # Suppress SSL warnings if verification is disabled
    if not verify_ssl:
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')

    # Ensure URL has scheme
    url = args.url
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    print(f"Fetching {url}...")

    try:
        html = fetch_html(url, verify_ssl=verify_ssl)
        favicon_urls, all_images = find_favicon(html, url, verify_ssl=verify_ssl)

        if favicon_urls and not args.force_report:
            print(f"\n✓ Found {len(favicon_urls)} favicon(s):")
            for display_url, fetch_url in favicon_urls:
                dimensions = get_image_dimensions(fetch_url, verify_ssl=verify_ssl)
                if dimensions:
                    width, height = dimensions
                    print(f"  • {display_url} ({width}x{height}px)")
                else:
                    print(f"  • {display_url} (dimensions unknown)")
            return 0
        elif not favicon_urls:
            print("\n✗ No obvious favicon found")

        if all_images:
            print(f"\nGenerating report with {len(all_images)} images...")
            report_path = generate_image_report(all_images, url, args.output, verify_ssl=verify_ssl)
            # Create a clickable terminal link
            file_url = f"file://{report_path}"
            clickable_link = f"\033]8;;{file_url}\033\\{report_path}\033]8;;\033\\"
            print(f"\nOpen this file in your browser: {clickable_link}")
        else:
            print("\n✗ No images found on the page")
            return 1

        return 0

    except SSLError as e:
        print(f"\n✗ SSL Certificate Verification Failed", file=sys.stderr)
        print("\nℹ️  This usually happens with self-signed certificates on local servers.", file=sys.stderr)
        print("   Try running with the -k flag to disable SSL verification:", file=sys.stderr)
        print(f"   pixi run fetch {args.url} -k", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
