# ByteTrack (Vendored)

Source: https://github.com/ifzhang/ByteTrack (MIT License, see `LICENSE` in this directory).
Paper: Y. Zhang, P. Sun, Y. Dong, Z. Wang, L. Jiang, T. Zhang, Q. Huang, Y. Chen, F. Liu, X. Wang, J. Sun, "ByteTrack: Multi-Object Tracking by Associating Every Detection Box", *European Conference on Computer Vision (ECCV)*, 2022.

Vendored modifications for autonomous sentry edge deployment (Python 3.6 on Jetson Nano):
- Python 3.6 syntax compatibility verified via `ast.parse(..., feature_version=(3, 6))`.
- Standalone pure NumPy and SciPy implementation: linear assignment uses standard `scipy.optimize.linear_sum_assignment`, eliminating compiled C++ dependencies (`lap`) on edge devices.
- Removed PyTorch, torchvision, Cython, and `cython-bbox` dependencies.
- Completely clean MIT lineage: independent of Ultralytics (AGPL-3.0); takes standard NumPy arrays `[x1, y1, x2, y2, score, ...]`.
- Output tracks formatted for drop-in integration with `sentry.perception.tracker.PersonTrack`.
