"""Run CPU/replay tests with provenance and a Linux test-only Windows beep shim."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import types


def main() -> int:
    import pytest
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(root/'data/ultralytics'))
    os.environ.setdefault('YOLO_AUTOINSTALL', 'false')
    if sys.platform != 'win32':
        sys.modules['winsound'] = types.SimpleNamespace(Beep=lambda *args: None)
    packages = {}
    for name in ('pytest', 'torch', 'ultralytics', 'numpy', 'scipy', 'pyzmq', 'opencv-python', 'pyzipper'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    meta = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), cwd=str(root),
                commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                tree=subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
                status=subprocess.check_output(['git', 'status', '--porcelain'], text=True).splitlines(),
                interpreter=sys.executable, python=platform.python_version(), packages=packages,
                shim='test-only winsound.Beep no-op on non-Windows', gpu_hil=False)
    print(json.dumps(meta, indent=2), flush=True)
    return pytest.main(['-m', 'not gpu and not hil', '-q', *sys.argv[1:]])


if __name__ == '__main__':
    raise SystemExit(main())
