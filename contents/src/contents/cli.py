"""contents: encode/decode a package's params or diagnostics YAML as an image label."""

import argparse
import sys

import docker

from . import core


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pkg", required=True, help="Package name")
    parser.add_argument("--field", required=True, choices=["params", "diagnostics"], help="Label field")


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="contents", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_parser = subparsers.add_parser("encode", help="Encode a YAML file into a label value")
    _add_common_args(encode_parser)
    encode_parser.add_argument("--canon", action="store_true", help="Canonicalize YAML formatting (drops comments)")
    encode_parser.add_argument("file", help="Path to the YAML file to encode")
    encode_parser.set_defaults(func=_cmd_encode)

    decode_parser = subparsers.add_parser("decode", help="Decode a label value back into the original YAML")
    _add_common_args(decode_parser)
    decode_parser.add_argument("image_ref", help="Image reference to read the label from")
    decode_parser.set_defaults(func=_cmd_decode)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
