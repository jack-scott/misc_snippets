"""contents: encode/decode a package's params or diagnostics YAML as an image label."""

import argparse
import sys

import docker

from . import core

# cmd is authored by hand in the Dockerfile (a plain string, not YAML) — it
# can be decoded/listed but never encoded from a file.
ENCODABLE_FIELDS = ["params", "diagnostics"]
ALL_FIELDS = ["params", "diagnostics", "cmd"]


def _add_pkg_field_args(parser: argparse.ArgumentParser, field_choices: list[str]) -> None:
    parser.add_argument("--pkg", required=True, help="Package name")
    parser.add_argument("--field", required=True, choices=field_choices, help="Label field")


def _cmd_encode(args: argparse.Namespace) -> None:
    value = core.encode(args.file, canon=args.canon)
    name = core.env_var_name(args.pkg, args.field)
    print(f"{name}={value}")


def _cmd_decode(args: argparse.Namespace) -> None:
    try:
        data = core.decode(args.image_ref, args.pkg, args.field)
    except docker.errors.ImageNotFound:
        sys.exit(f"contents: image not found: {args.image_ref}")
    except KeyError:
        sys.exit(f"contents: label not found on image: {core.label_key(args.pkg, args.field)}")
    except ValueError:
        sys.exit(f"contents: malformed label value on image: {core.label_key(args.pkg, args.field)}")

    sys.stdout.buffer.write(data)


def _cmd_list(args: argparse.Namespace) -> None:
    try:
        packages = core.list_packages(args.image_ref)
    except docker.errors.ImageNotFound:
        sys.exit(f"contents: image not found: {args.image_ref}")

    if args.pkg:
        if args.pkg not in packages:
            sys.exit(f"contents: no package '{args.pkg}' found on image: {args.image_ref}")
        for field in sorted(packages[args.pkg]):
            print(field)
        return

    for pkg in sorted(packages):
        if args.verbose:
            print(f"{pkg}: {', '.join(sorted(packages[pkg]))}")
        else:
            print(pkg)


def main() -> None:
    parser = argparse.ArgumentParser(prog="contents", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_parser = subparsers.add_parser("encode", help="Encode a YAML file into a label value")
    _add_pkg_field_args(encode_parser, ENCODABLE_FIELDS)
    encode_parser.add_argument("--canon", action="store_true", help="Canonicalize YAML formatting (drops comments)")
    encode_parser.add_argument("file", help="Path to the YAML file to encode")
    encode_parser.set_defaults(func=_cmd_encode)

    decode_parser = subparsers.add_parser("decode", help="Decode a label value back into the original YAML")
    _add_pkg_field_args(decode_parser, ALL_FIELDS)
    decode_parser.add_argument("image_ref", help="Image reference to read the label from")
    decode_parser.set_defaults(func=_cmd_decode)

    list_parser = subparsers.add_parser("list", help="List packages (or a package's fields) on an image")
    list_parser.add_argument("pkg", nargs="?", default=None, help="Package name (omit to list all packages)")
    list_parser.add_argument("-v", "--verbose", action="store_true", help="With no pkg, also show each package's fields")
    list_parser.add_argument("image_ref", help="Image reference to inspect")
    list_parser.set_defaults(func=_cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
