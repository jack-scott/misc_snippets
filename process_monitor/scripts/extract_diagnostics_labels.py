#!/usr/bin/env python3
"""Build a diagnostic_aggregator params file from a compose stack's images.

Each node image carries its own analyzer config in the `diagnostics.analyzers`
LABEL (set at build time — see compose.yaml's `build.labels` and
scripts/compose_build_with_diagnostics_label.py). This reads every service's
image out of a compose file, pulls that label from each, merges the analyzer
fragments together, and writes a single params file the diagnostic_aggregator
node can be launched with.

Usage:
    python3 scripts/extract_diagnostics_labels.py compose.yaml
    python3 scripts/extract_diagnostics_labels.py compose.yaml -o diagnostic_aggregator/analyzers.generated.yaml
"""

import argparse
import json
import subprocess
import sys

import yaml

LABEL_NAME = "diagnostics.analyzers"


def resolve_compose_images(compose_file: str) -> dict[str, str]:
    """Return {service_name: image} for a compose file, fully resolved (env interpolation, defaults, etc.)."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", compose_file, "config", "--format", "json"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"'docker compose -f {compose_file} config' failed: {e.stderr.strip()}") from e

    config = json.loads(result.stdout)
    return {
        name: service["image"]
        for name, service in config.get("services", {}).items()
        if service.get("image")
    }


def read_label(image: str) -> str | None:
    """Return the diagnostics.analyzers label value for an image, or None if unset."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", f'{{{{ index .Config.Labels "{LABEL_NAME}" }}}}', image],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"docker inspect failed for image '{image}': {e.stderr.strip()}") from e

    value = result.stdout.strip()
    return value or None


def parse_fragment(service_name: str, raw_label: str) -> dict:
    fragment = yaml.safe_load(raw_label)

    if not isinstance(fragment, dict):
        raise ValueError(f"'{LABEL_NAME}' label on service '{service_name}' did not parse to a YAML mapping")

    return fragment


def merge_fragments(fragments_by_service: dict[str, dict]) -> dict:
    merged: dict = {}

    for service_name, fragment in fragments_by_service.items():
        for analyzer_name, analyzer_config in fragment.items():
            if analyzer_name in merged:
                raise ValueError(
                    f"analyzer name '{analyzer_name}' from service '{service_name}' collides with "
                    f"one already contributed by another service — rename one of them"
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
    parser.add_argument("compose_file", help="Path to the compose.yaml describing the stack")
    parser.add_argument("-o", "--output", help="Write the combined params file here (default: stdout)")
    args = parser.parse_args()

    images_by_service = resolve_compose_images(args.compose_file)

    fragments_by_service = {}
    for service_name, image in images_by_service.items():
        raw_label = read_label(image)
        if raw_label is None:
            print(f"warning: service '{service_name}' ({image}) has no '{LABEL_NAME}' label, skipping", file=sys.stderr)
            continue
        fragments_by_service[service_name] = parse_fragment(service_name, raw_label)

    merged_analyzers = merge_fragments(fragments_by_service)
    params = build_params(merged_analyzers)
    output_yaml = yaml.safe_dump(params, sort_keys=False, default_flow_style=False)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_yaml)
    else:
        print(output_yaml, end="")


if __name__ == "__main__":
    main()
