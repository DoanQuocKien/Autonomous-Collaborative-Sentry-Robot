# XFeat (vendored)

Source: https://github.com/verlab/accelerated_features, commit `e92685f57f8318b18725c5c8c0bd28c7fe188d9a` (2025-01-15), Apache License 2.0 (`LICENSE` in this folder).
Paper: G. Potje, F. Cadar, A. Araujo, R. Martins, E. R. Nascimento, "XFeat: Accelerated Features for Lightweight Image Matching", CVPR 2024.

Files: `model.py` and `interpolator.py` are unchanged; `xfeat.py` is trimmed (see its docstring): only `detectAndCompute`, `match` and their helpers remain,
imports are relative, `tqdm`, `kornia`, LighterGlue and the dense / semi-dense code are removed, weights are loaded with `weights_only=True`.
The weights (`weights/xfeat.pt`, 6.2 MB, sha256 `0f5187fd7bedd26c7fe6acc9685444493a165a35ecc087b33c2db3627f3ea10b`) are NOT in git: `python -m tools.fetch_models`.
