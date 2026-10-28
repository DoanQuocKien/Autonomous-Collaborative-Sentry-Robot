"""Share a local dataset (faces, recordings) inside the team: a password-protected AES zip committed to team_data/ (team protocol of 2026-10-28, docs/Team Data Sharing.md).

  python -m tools.team_data pack   data/D2/1028  team_data/D2_1028.zip      # sender: folder -> encrypted zip (then commit the zip in a PR)
  python -m tools.team_data unpack team_data/D2_1028.zip  data/D2/1028      # receiver: after git pull; the unzipped data stays in git-ignored data/

The password is the team's standard one (PASSWORD below, also written in the doc): it keeps the files unreadable for anyone who only finds the zip (a stray download, a
search), it is NOT a secret inside the team and not strong protection: the zip stays in the git history of the private repository forever, so the repository is deleted or
archived after grading. Never commit the unzipped folder.
"""
import argparse
import os
from pathlib import Path

import pyzipper

PASSWORD = "12345678"


def pack(src, out, password=PASSWORD):
    """Folder -> AES-256 zip (deflate). Paths inside the zip are relative to src. Returns the number of files."""
    src, out = Path(src), Path(out)
    if not src.is_dir():
        raise SystemExit("not a folder: %s" % src)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with pyzipper.AESZipFile(str(out), "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as z:
        z.setpassword(password.encode())
        for f in sorted(p for p in src.rglob("*") if p.is_file()):
            z.write(str(f), f.relative_to(src).as_posix())
            n += 1
    return n


def unpack(zip_path, dest, password=PASSWORD):
    """Encrypted zip -> folder. Refuses entries that would land outside dest. Returns the number of files."""
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("src")
    p.add_argument("out")
    u = sub.add_parser("unpack")
    u.add_argument("zip")
    u.add_argument("dest")
    for s in (p, u):
        s.add_argument("--password", default=PASSWORD)
    a = ap.parse_args()
    if a.cmd == "pack":
        print("packed %d files into %s (%.1f MB)" % (pack(a.src, a.out, a.password), a.out, os.path.getsize(a.out) / 1e6))
    else:
        print("unpacked %d files into %s" % (unpack(a.zip, a.dest, a.password), a.dest))


if __name__ == "__main__":
    main()
