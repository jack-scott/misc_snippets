#!/usr/bin/env python3
"""Assert an image's contents-encoded label decodes to non-empty, valid YAML.

A CI sanity check, not an exact-value assertion — the label's exact bytes
are already covered by contents' own encode/decode round-trip; this just
checks the label exists on the image and contains something meaningful.

Usage:
    python3 scripts/check_diagnostics_label.py --pkg cadvisor_monitor --field diagnostics cadvisor_prod:prod
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

# TODO: once contents is published to jacks-channel and added as a
# dependency of this project, replace this with a plain ["contents", ...]
# invocation.
CONTENTS_MANIFEST = Path(__file__).resolve().parent.parent.parent / "contents" / "pixi.toml"
CONTENTS_CMD = ["pixi", "run", "--manifest-path", str(CONTENTS_MANIFEST), "contents"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pkg", required=True, help="Package name")
    parser.add_argument("--field", required=True, choices=["params", "diagnostics"], help="Label field")
    parser.add_argument("image", help="Image reference to check")
    args = parser.parse_args()

    result = subprocess.run(
        [*CONTENTS_CMD, "decode", "--pkg", args.pkg, "--field", args.field, args.image],
        capture_output=True,
    )
    if result.returncode != 0:
        sys.exit(result.stderr.decode().strip())

    try:
        data = yaml.safe_load(result.stdout)
    except yaml.YAMLError as e:
        sys.exit(f"{args.pkg}/{args.field} label on '{args.image}' is not valid YAML: {e}")

    if not data:
        sys.exit(f"{args.pkg}/{args.field} label on '{args.image}' decoded to empty content")

    print(f"{args.pkg}/{args.field} label on '{args.image}' is valid, non-empty YAML")


if __name__ == "__main__":
    main()
