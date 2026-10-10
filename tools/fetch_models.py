"""Fetch the pretrained models the project needs, skipping files that are already there.

    python -m tools.fetch_models

Re-ID weights go to weights/ (gitignored); the InsightFace face detector + embedder go to ~/.insightface/models/buffalo_s/.
YOLO weights are downloaded by ultralytics on first use. The campus network can be very slow
(10 KB/s on a bad day): each download is retried, and files are renamed only when complete, so just run it again.

NOTE: torchreid's `pretrained=True` gives ImageNet-only weights, NOT re-identification weights. The OSNet files here are
trained for re-ID (torchreid model zoo). osnet_ain_x1_0 (multi-source, domain generalisation: Rank-1 73 % on Market1501
without seeing it) is the default choice for a new camera and new people; osnet_x0_25 (Market1501: 91 % same-domain,
much lower across domains) is the small, fast alternative.
"""
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACE_DIR = Path.home() / ".insightface" / "models" / "buffalo_s"

DRIVE = [  # (file, Google Drive id, what it is)
    ("osnet_ain_x1_0_dg.pth", "1nIrszJVYSHf3Ej8-j6DTFdWz8EnO42PB", "OSNet-AIN x1.0, multi-source domain generalisation (default)"),
    ("osnet_x0_25_market1501.pth", "1z1UghYvOTtjx7kEoRfmqSMu-z62J6MAj", "OSNet x0.25, Market1501 (small and fast, same-domain)"),
]
HTTP = [  # (destination, url, what it is)
    (FACE_DIR / "det_500m.onnx", "https://huggingface.co/immich-app/buffalo_s/resolve/main/detection/model.onnx", "InsightFace face detector"),
    (FACE_DIR / "w600k_mbf.onnx", "https://huggingface.co/immich-app/buffalo_s/resolve/main/recognition/model.onnx", "InsightFace face embedder (MobileFaceNet)"),
]


def have(path):
    return path.exists() and path.stat().st_size > 100_000


def fetch_curl(dest, url, tries=6):
    """curl follows Drive's redirect and resumes; python `requests`/gdown timed out on the same network. Rejects HTML error pages."""
    import subprocess
    part = dest.with_suffix(dest.suffix + ".part")
    for i in range(tries):
        rc = subprocess.call(["curl", "-L", "-s", "-C", "-", "--retry", "5", "--retry-all-errors", "--connect-timeout", "30",
                              "--max-time", "600", "-o", str(part), url])
        if rc == 0 and part.exists() and part.stat().st_size > 100_000:
            head = part.read_bytes()[:16]
            if head.lstrip().startswith(b"<"):  # an HTML page (quota / confirmation), not a weights file
                print("   got an HTML page instead of a file; Drive refused (quota?)")
                part.unlink()
                return False
            part.replace(dest)
            return True
        print("   attempt %d failed (curl exit %d)" % (i + 1, rc))
        time.sleep(3)
    return False


def fetch_http(dest, url, tries=8):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for i in range(tries):
        try:
            urllib.request.urlretrieve(url, part)
            part.replace(dest)
            return True
        except Exception as e:  # noqa: BLE001 - network errors are many kinds; retry them all
            print("   attempt %d failed (%s)" % (i + 1, type(e).__name__))
            time.sleep(3)
    return False


def safe_state_dict(path):
    """Load a torchreid checkpoint WITHOUT turning off torch's weights_only safety: allow only the numpy types it names.
    (The checkpoints carry numpy scalars as metadata, which torch >= 2.6 refuses by default.)"""
    import importlib
    import re
    import torch
    allowed = []
    for _ in range(12):
        try:
            with torch.serialization.safe_globals(allowed):
                ckpt = torch.load(str(path), map_location="cpu", weights_only=True)
            break
        except Exception as e:  # noqa: BLE001
            # two message shapes: "Unsupported global: GLOBAL a.b.c was not ..." and "... but got <class 'a.b.C'>"
            m = re.search(r"Unsupported global: GLOBAL ([\w.]+)\.(\w+) was not", str(e)) or re.search(r"but got <class '([\w.]+)\.(\w+)'>", str(e))
            if not m or not m.group(1).startswith("numpy"):
                raise  # anything that is not a numpy type stays refused
            obj = getattr(importlib.import_module(m.group(1)), m.group(2))
            allowed.append((obj, "%s.%s" % (m.group(1), m.group(2))))  # register under the name the FILE uses (numpy moved its modules)
    else:
        raise RuntimeError("could not load %s even with the numpy types it names allowed" % path)
    sd = ckpt.get("state_dict", ckpt)
    return {(k[7:] if k.startswith("module.") else k): v for k, v in sd.items()}


def convert_weights():
    """weights/<name>.pth (pickle with metadata) -> weights/<name>.state.pt (tensors only, loads with weights_only=True)."""
    import torch
    for p in sorted((ROOT / "weights").glob("*.pth")):
        out = p.with_suffix("").with_suffix(".state.pt")
        if out.exists():
            continue
        sd = safe_state_dict(p)
        torch.save(sd, out)
        print("converted %-28s -> %s (%d tensors)" % (p.name, out.name, len(sd)))


def main():
    (ROOT / "weights").mkdir(exist_ok=True)
    failed = []
    for name, gid, what in DRIVE:
        dest = ROOT / "weights" / name
        if have(dest):
            print("have  %-30s %s" % (name, what))
            continue
        print("fetch %-30s %s" % (name, what))
        # files under about 100 MB are served directly by Drive, without the virus-scan confirmation page
        if not fetch_curl(dest, "https://drive.google.com/uc?export=download&id=" + gid):
            failed.append(name)
    for dest, url, what in HTTP:
        if have(dest):
            print("have  %-30s %s" % (dest.name, what))
            continue
        print("fetch %-30s %s" % (dest.name, what))
        if not fetch_http(dest, url):
            failed.append(dest.name)
    try:
        convert_weights()
    except Exception as e:  # noqa: BLE001
        print("conversion failed: %s: %s" % (type(e).__name__, str(e)[:200]))
        failed.append("conversion")
    for p in sorted((ROOT / "weights").glob("*.pth")) + sorted((ROOT / "weights").glob("*.state.pt")) + [d for d, _, _ in HTTP]:
        if have(p):
            print("  %6.1f MB  %s" % (p.stat().st_size / 1e6, p))
    print("\nALL PRESENT" if not failed else "\nMISSING: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
