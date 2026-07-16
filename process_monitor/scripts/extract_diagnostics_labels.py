#!/usr/bin/env python3
"""Build a diagnostic_aggregator params file from image LABELs.

Each node image carries its analyzer config in the `diagnostics.analyzers`
LABEL (set in its Dockerfile, newlines escaped as literal \\n since Docker
doesn't interpret escapes in label values). This pulls that label out of one
or more images, merges the analyzer fragments together, and writes a single
params file the diagnostic_aggregator node can be launched with.

Usage:
    python3 scripts/extract_diagnostics_labels.py cadvisor_prod:prod [other_image ...]
    python3 scripts/extract_diagnostics_labels.py cadvisor_prod:prod -o diagnostic_aggregator/analyzers.generated.yaml
"""

import argparse
import subprocess
import sys

import yaml

LABEL_NAME = "diagnostics.analyzers"


def read_label(image: str) -> str | None:
    """Return the raw (still \\n-escaped) label value for an image, or None if unset."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", f'{{{{ index .Config.Labels "{LABEL_NAME}" }}}}', image],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"docker inspect failed for image '{image}': {e.stderr.strip()}") from e

    value = result.stdout.strip()
    return value or None


def parse_fragment(image: str, raw_label: str) -> dict:
    unescaped = raw_label.replace("\\n", "\n")
    fragment = yaml.safe_load(unescaped)

    if not isinstance(fragment, dict):
        raise ValueError(f"'{LABEL_NAME}' label on '{image}' did not parse to a YAML mapping")

    return fragment


def merge_fragments(fragments_by_image: dict[str, dict]) -> dict:
    merged: dict = {}

    for image, fragment in fragments_by_image.items():
        for analyzer_name, analyzer_config in fragment.items():
            if analyzer_name in merged:
                raise ValueError(
                    f"analyzer name '{analyzer_name}' from image '{image}' collides with "
                    f"one already contributed by another image — rename one of them"
                )
            merged[analyzer_name] = analyzer_config

    return merged


def build_params(merged_analyzers: dict) -> dict:
    return {
        "analyzers": {
            "ros__parameters": {
                "path": "Aggregation",
                **merged_analyzers,
            }
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", help="Image names/tags to read the diagnostics label from")
    parser.add_argument("-o", "--output", help="Write the combined params file here (default: stdout)")
    args = parser.parse_args()

    fragments_by_image = {}
    for image in args.images:
        raw_label = read_label(image)
        if raw_label is None:
            print(f"warning: '{image}' has no '{LABEL_NAME}' label, skipping", file=sys.stderr)
            continue
        fragments_by_image[image] = parse_fragment(image, raw_label)

    merged_analyzers = merge_fragments(fragments_by_image)
    params = build_params(merged_analyzers)
    output_yaml = yaml.safe_dump(params, sort_keys=False, default_flow_style=False)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_yaml)
    else:
        print(output_yaml, end="")


if __name__ == "__main__":
    main()
