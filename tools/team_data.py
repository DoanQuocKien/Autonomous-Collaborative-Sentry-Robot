"""Share local datasets with an explicitly supplied password.

The password is read from ``--password``, ``TEAM_DATA_PASSWORD``, or an
interactive prompt. It is never stored in source code.
"""

import argparse
import getpass
import os
from pathlib import Path

import pyzipper


def resolve_password(value):
    return value or os.environ.get("TEAM_DATA_PASSWORD") or getpass.getpass(
        "Team data password: "
    )


def pack(src, out, password):
    """Folder -> AES-256 zip (deflate)."""
    src, out = Path(src), Path(out)
    if not src.is_dir():
        raise SystemExit("not a folder: %s" % src)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with pyzipper.AESZipFile(
        str(out), "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as z:
        z.setpassword(password.encode())
        for file_path in sorted(path for path in src.rglob("*") if path.is_file()):
            z.write(str(file_path), file_path.relative_to(src).as_posix())
            n += 1
    return n


def unpack(zip_path, dest, password):
    """Encrypted zip -> folder, rejecting paths outside the destination."""
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    with pyzipper.AESZipFile(str(zip_path)) as z:
        z.setpassword(password.encode())
        for name in z.namelist():
            target = (dest / name).resolve()
            if os.path.commonpath([str(dest), str(target)]) != str(dest):
                raise SystemExit("unsafe path in the zip: %s" % name)
            z.extract(name, str(dest))
            n += 1
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    pack_parser = subparsers.add_parser("pack")
    pack_parser.add_argument("src")
    pack_parser.add_argument("out")
    unpack_parser = subparsers.add_parser("unpack")
    unpack_parser.add_argument("zip")
    unpack_parser.add_argument("dest")
    for subparser in (pack_parser, unpack_parser):
        subparser.add_argument("--password")
    args = parser.parse_args()
    password = resolve_password(args.password)
    if args.cmd == "pack":
        print(
            "packed %d files into %s (%.1f MB)"
            % (pack(args.src, args.out, password), args.out, os.path.getsize(args.out) / 1e6)
        )
    else:
        print("unpacked %d files into %s" % (unpack(args.zip, args.dest, password), args.dest))


if __name__ == "__main__":
    main()
