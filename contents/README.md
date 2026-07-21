# contents

Encode a package's params/diagnostics YAML into a deterministic image label, and decode it back out.

## Install

```
pixi install
```

## Usage

Encode a file into a label value (prints `NAME=value` for use as a Dockerfile `ARG`):

```
pixi run contents encode --pkg cadvisor_monitor --field diagnostics config/analyzers.yaml
# CADVISOR_MONITOR_DIAGNOSTICS=raw64:Y2Fkdmlzb3JfbW9uaXRvcjoK...
```

Bake it into an image, e.g. in a Dockerfile:

```dockerfile
ARG CADVISOR_MONITOR_DIAGNOSTICS=""
LABEL io.ros.pkg.cadvisor_monitor.diagnostics=$CADVISOR_MONITOR_DIAGNOSTICS
```

```
docker build --build-arg CADVISOR_MONITOR_DIAGNOSTICS="$(pixi run contents encode --pkg cadvisor_monitor --field diagnostics config/analyzers.yaml | cut -d= -f2-)" .
```

Decode it back out of a built image (reads labels via the Docker SDK, prints the original bytes to stdout):

```
pixi run contents decode --pkg cadvisor_monitor --field diagnostics my-image:latest
```

Use `--canon` on `encode` to canonicalize formatting (drops comments, sorts keys) instead of an exact byte round-trip.

List what's on an image — packages, or a package's fields:

```
pixi run contents list my-image:latest                       # package names
pixi run contents list -v my-image:latest                    # packages with their fields
pixi run contents list cadvisor_monitor my-image:latest       # that package's fields
```

## Fields

`--field` is `params` or `diagnostics` for `encode`; `decode` also accepts `cmd`. `cmd` is authored by hand in the Dockerfile as a plain string (not YAML) — `contents` can read it back but never encodes it from a file.
