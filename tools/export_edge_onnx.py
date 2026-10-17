"""Export the project's models to ONNX for TensorRT 7.1 on the Jetson Nano (JetPack 4.5). Run on the LAPTOP (conda env `sentry`).

    python -m tools.export_edge_onnx                       # everything into data/models/onnx_export/
    python -m tools.export_edge_onnx --only osnet_x0_25 xfeat

Extra laptop-only dependency for the `scrfd` job: `pip install onnxsim`, then re-run `python tools/check_env.py` (it must still report only
`onnxruntime-gpu`; if plain `onnxruntime` appears, follow the uninstall step in docs/Setup.md).

Constraints of TensorRT 7.1 that shape the exports (found 2026-10-16, docs/Edge Deployment.md):
  * ONNX opset <= 11, fixed input shapes (the two insightface models are dynamic: give trtexec min = opt = max shapes).
  * no grid_sample, no bicubic Resize: the DINOv2 position embedding is computed once for the fixed grid and baked in.
  * Resize in the `sizes` form is computed WRONGLY (SCRFD neck: cosine 0.88 to 0.99 against ONNX Runtime in FP32 and FP16): nearest 2x
    upsampling is rewritten as a grouped ConvTranspose (2x2 ones, stride 2), which is mathematically identical.
  * no scaled_dot_product_attention at opset 11: DINOv2 attention is rewritten as matmul + softmax.
Each export is checked against PyTorch with ONNX Runtime (max |diff|); engines are built ON the robot with trtexec, never copied.
"""
import argparse
import os
import shutil
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "models" / "onnx_export"
OPSET = 11


def _check(path, x, ref):
    import numpy as np
    import onnx
    import onnxruntime as ort
    onnx.checker.check_model(onnx.load(str(path)))
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    got = sess.run(None, {sess.get_inputs()[0].name: x.numpy()})
    diffs = ["%.1e" % float(np.abs(a - b.numpy()).max()) for a, b in zip(got, ref)]
    print("  %-34s %6.1f MB  max|diff| vs torch %s" % (path.name, path.stat().st_size / 1e6, diffs))


def _export(name, model, x, out_names):
    import torch
    model = model.eval()
    with torch.no_grad():
        ref = model(x)
    ref = ref if isinstance(ref, (tuple, list)) else (ref,)
    path = OUT / (name + ".onnx")
    torch.onnx.export(model, x, str(path), opset_version=OPSET, input_names=["input"], output_names=out_names,
                      do_constant_folding=True, dynamo=False)
    _check(path, x, ref)


def yolo(weights, name, size=320):
    from ultralytics import YOLO
    p = YOLO(str(ROOT / weights)).export(format="onnx", imgsz=size, opset=OPSET, simplify=False, dynamic=False, batch=1, verbose=False)
    shutil.move(p, str(OUT / (name + ".onnx")))
    print("  %-34s %6.1f MB" % (name + ".onnx", (OUT / (name + ".onnx")).stat().st_size / 1e6))


def osnet(arch, weights):
    import torch
    import torchreid
    net = torchreid.models.build_model(name=arch, num_classes=1000, pretrained=False)
    have, saved = net.state_dict(), torch.load(str(ROOT / "weights" / weights), map_location="cpu", weights_only=True)
    net.load_state_dict({k: v for k, v in saved.items() if k in have and v.shape == have[k].shape}, strict=False)   # the id classifier is dataset-specific
    _export(arch + "_256x128", net, torch.randn(1, 3, 256, 128), ["embedding"])


def xfeat():
    import torch
    sys.path.insert(0, str(ROOT))
    from third_party.xfeat.model import XFeatModel
    m = XFeatModel()
    m.load_state_dict(torch.load(str(ROOT / "weights" / "xfeat.pt"), map_location="cpu", weights_only=True))
    _export("xfeat_backbone_480x640", m, torch.rand(1, 1, 480, 640), ["feats", "keypoints", "heatmap"])


def resize_to_deconv(model):
    """Replace every nearest 2x Resize (opset-11 `sizes` form) by a grouped ConvTranspose; returns the same ModelProto."""
    import numpy as np
    from onnx import helper, numpy_helper
    init = {i.name: numpy_helper.to_array(i) for i in model.graph.initializer}
    nodes = []
    for n in model.graph.node:
        if n.op_type != "Resize":
            nodes.append(n)
            continue
        sizes = init[n.input[3]]
        c = int(sizes[1])
        w = n.output[0] + "_ones"
        model.graph.initializer.append(numpy_helper.from_array(np.ones((c, 1, 2, 2), np.float32), w))
        nodes.append(helper.make_node("ConvTranspose", [n.input[0], w], [n.output[0]], kernel_shape=[2, 2], strides=[2, 2], group=c,
                                      name=n.name + "_deconv"))
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    return model


def scrfd(size=320):
    """insightface det_500m: fixed input, shape logic folded (onnxsim), Resize -> ConvTranspose; also copies the embedder."""
    import onnx
    from onnxsim import simplify
    src = Path.home() / ".insightface" / "models" / "buffalo_s"
    m, ok = simplify(onnx.load(str(src / "det_500m.onnx")), overwrite_input_shapes={"input.1": [1, 3, size, size]})
    assert ok, "onnxsim could not verify the simplified model"
    m = resize_to_deconv(m)
    onnx.checker.check_model(m)
    onnx.save(m, str(OUT / ("det_500m_deconv%d.onnx" % size)))
    print("  det_500m_deconv%d.onnx            fixed %dx%d input, Resize -> ConvTranspose (pip install onnxsim on the laptop)" % (size, size, size))
    shutil.copy(str(src / "w600k_mbf.onnx"), str(OUT / "w600k_mbf.onnx"))
    print("  w600k_mbf.onnx                     copied (dynamic batch: build with min = opt = max 1x3x112x112)")


def dino(size):
    import torch
    sys.path.insert(0, str(ROOT))
    from sentry.perception.entrance import DINO_REPO
    hub_dir = Path(torch.hub.get_dir()) / ("facebookresearch_dinov2_" + DINO_REPO.split(":")[1])
    sys.path.insert(0, str(hub_dir))
    from dinov2.layers import attention as A

    def manual_forward(self, x, attn_bias=None):
        b, n, c = x.shape
        qkv = self.qkv(x).reshape(b, n, 3, self.num_heads, c // self.num_heads).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0] * self.scale, qkv[1], qkv[2]
        return self.proj(((q @ k.transpose(-2, -1)).softmax(dim=-1) @ v).transpose(1, 2).reshape(b, n, c))
    for cls in [c for c in vars(A).values() if isinstance(c, type) and issubclass(c, A.Attention)]:
        cls.forward = manual_forward

    class Wrap(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, x):
            o = self.m.forward_features(x)
            return o["x_norm_clstoken"], o["x_norm_patchtokens"]

    hub = torch.hub.load(DINO_REPO, "dinov2_vit%s14" % size, trust_repo=True, verbose=False).eval()
    with torch.no_grad():
        pe = hub.interpolate_pos_encoding(torch.zeros(1, 1 + 24 * 32, hub.embed_dim), 448, 336).detach().clone()
    hub.interpolate_pos_encoding = lambda x, w, h: pe       # bicubic resize done once; TensorRT 7.1 has no bicubic Resize
    _export("dinov2_vit%s14_336x448" % size, Wrap(hub), torch.randn(1, 3, 336, 448), ["cls", "patch"])


JOBS = {
    "yolov8n_320": lambda: yolo("data/models/yolov8n.pt", "yolov8n_320_op11"),
    "yolov8n_416": lambda: yolo("data/models/yolov8n.pt", "yolov8n_416_op11", 416),
    "yolov8n_pose_320": lambda: yolo("yolov8n-pose.pt", "yolov8n-pose_320_op11"),
    "osnet_x0_25": lambda: osnet("osnet_x0_25", "osnet_x0_25_market1501.state.pt"),
    "osnet_ain_x1_0": lambda: osnet("osnet_ain_x1_0", "osnet_ain_x1_0_dg.state.pt"),
    "xfeat": xfeat,
    "scrfd": scrfd,
    "dinov2_s": lambda: dino("s"),
    "dinov2_b": lambda: dino("b"),
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*", choices=sorted(JOBS), help="default: all")
    a = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    OUT.mkdir(parents=True, exist_ok=True)
    os.chdir(str(ROOT))
    for name in (a.only or sorted(JOBS)):
        print(name)
        try:
            JOBS[name]()
        except Exception as e:   # keep going: one model failing must not hide the others
            print("  FAILED: %s: %s" % (type(e).__name__, str(e).strip().splitlines()[-1][:160]))


if __name__ == "__main__":
    main()
