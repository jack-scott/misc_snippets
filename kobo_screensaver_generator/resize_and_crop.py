import argparse
import os
from pathlib import Path

from PIL import Image


def resize_and_center_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize keeping aspect ratio so both sides >= target, then center-crop."""
    orig_w, orig_h = img.size

    # Scale so that min side meets target (so both are >= target after resize)
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(round(orig_w * scale))
    new_h = int(round(orig_h * scale))

    img_resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Center crop to target size
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    right = left + target_w
    bottom = top + target_h

    return img_resized.crop((left, top, right, bottom))


def process_path(input_path: Path, output_dir: Path, width: int, height: int) -> None:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}

    if input_path.is_file():
        paths = [input_path]
    else:
        paths = [p for p in input_path.iterdir() if p.suffix.lower() in image_exts]

    output_dir.mkdir(parents=True, exist_ok=True)

    for p in paths:
        try:
            with Image.open(p) as img:
                img = img.convert("RGB")  # optional: normalize mode
                out_img = resize_and_center_crop(img, width, height)

                out_name = p.stem + f"_{width}x{height}" + ".jpg"
                out_path = output_dir / out_name
                out_img.save(out_path, quality=95)
                print(f"Saved: {out_path}")
        except Exception as e:
            print(f"Error processing {p}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Resize images so both sides >= target size, then center-crop."
    )
    parser.add_argument("input", help="Input file or folder of images")
    parser.add_argument("--width", type=int, default=1072, help="Output width")
    parser.add_argument("--height", type=int, default=1448, help="Output height")
    parser.add_argument(
        "-o", "--output-dir", default="output", help="Directory to save processed images"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {input_path}")

    process_path(input_path, output_dir, args.width, args.height)


if __name__ == "__main__":
    main()
