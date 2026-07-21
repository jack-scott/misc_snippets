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

Decode it back out of a built image (reads labels via the Docker SDK, prints the original YAML bytes to stdout):

```
pixi run contents decode --pkg cadvisor_monitor --field diagnostics my-image:latest
```

Use `--canon` on `encode` to canonicalize formatting (drops comments, sorts keys) instead of an exact byte round-trip.

## Fields

`--field` is `params` or `diagnostics`. `cmd` is a third label a package may carry, but it's authored by hand in the Dockerfile — `contents` doesn't touch it.
