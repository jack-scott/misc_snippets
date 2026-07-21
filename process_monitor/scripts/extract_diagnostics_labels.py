#!/usr/bin/env python3
"""Build a diagnostic_aggregator params file from a compose stack's images.

Each node image carries its own analyzer config in a contents-encoded
io.ros.pkg.<service>.diagnostics label (set at build time — see
compose.yaml's build.args and docker/build.sh). This reads every service's
image out of a compose file, decodes that label via `contents decode`
(assumes the contents --pkg name matches the compose service name), merges
the analyzer fragments together, and writes a single params file the
diagnostic_aggregator node can be launched with.

Usage:
    python3 scripts/extract_diagnostics_labels.py compose.yaml
    python3 scripts/extract_diagnostics_labels.py compose.yaml -o diagnostic_aggregator/analyzers.generated.yaml
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

# TODO: once contents is published to jacks-channel and added as a
# dependency of this project, replace this with a plain ["contents", ...]
# invocation.
CONTENTS_MANIFEST = Path(__file__).resolve().parent.parent.parent / "contents" / "pixi.toml"
CONTENTS_CMD = ["pixi", "run", "--manifest-path", str(CONTENTS_MANIFEST), "contents"]


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


def decode_diagnostics(service_name: str, image: str) -> dict | None:
    """Return the decoded diagnostics fragment for a service's image, or None if it has no such label."""
    result = subprocess.run(
        [*CONTENTS_CMD, "decode", "--pkg", service_name, "--field", "diagnostics", image],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"warning: service '{service_name}' ({image}): {result.stderr.strip()}, skipping", file=sys.stderr)
        return None

    fragment = yaml.safe_load(result.stdout)
    if not isinstance(fragment, dict):
        raise ValueError(f"decoded diagnostics for service '{service_name}' did not parse to a YAML mapping")

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
        fragment = decode_diagnostics(service_name, image)
        if fragment is not None:
            fragments_by_service[service_name] = fragment

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
