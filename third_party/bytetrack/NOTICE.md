# ByteTrack (vendored)

Source: https://github.com/ifzhang/ByteTrack (MIT License, `LICENSE` in this folder).
Paper: Y. Zhang, P. Sun, Y. Dong, Z. Wang, L. Jiang, T. Zhang, Q. Huang, Y. Chen, F. Liu, X. Wang, J. Sun, "ByteTrack: Multi-Object Tracking by Associating Every Detection Box", *European Conference on Computer Vision (ECCV)*, 2022.

Vendored modifications for autonomous sentry edge deployment (Python 3.6 on Jetson Nano):
- Python 3.6 syntax compatibility verified via `ast.parse(..., feature_version=(3, 6))`.
- Pure numpy and scipy implementation: linear assignment uses `scipy.optimize.linear_sum_assignment` (with optional `lap.lapjv` fast path if present), eliminating compiled C++ dependencies on edge devices.
- Removed PyTorch, torch, torchvision, cython, and cython-bbox dependencies.
- Standardized track output format matching the project's PersonTrack representation.
