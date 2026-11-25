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
import hashlib
import json
import os
import shutil
import sys
import tempfile
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
    """Fixed FP32 opset-11 export, checked with real ONNX Runtime inference.

    Export beside a temporary copy of the weights so Ultralytics cannot replace
    an earlier sibling ONNX. Refuse existing delivery files.
    """
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO
    import ultralytics
    source = ROOT / weights
    if not source.is_file():
        raise FileNotFoundError(source)
    OUT.mkdir(parents=True, exist_ok=True)
    target, metadata = OUT / (name + '.onnx'), OUT / (name + '.json')
    if target.exists() or metadata.exists():
        raise FileExistsError('choose a fresh --out directory; export already exists: ' + str(target))
    with tempfile.TemporaryDirectory(prefix='.yolo-export-', dir=OUT) as directory:
        staged = Path(directory) / source.name
        shutil.copyfile(source, staged)
        model = YOLO(str(staged))
        exported = Path(model.export(format='onnx', imgsz=size, opset=OPSET,
            simplify=False, dynamic=False, batch=1, half=False, nms=False, device='cpu', verbose=False))
        graph = onnx.load(str(exported))
        onnx.checker.check_model(graph)
        if {item.domain: item.version for item in graph.opset_import}.get('') != OPSET:
            raise ValueError('wrong ONNX opset')
        session = ort.InferenceSession(str(exported), providers=['CPUExecutionProvider'])
        inp = session.get_inputs()[0]
        if inp.shape != [1, 3, size, size] or inp.type != 'tensor(float)':
            raise ValueError('export must have fixed FP32 1x3xSxS input')
        random = np.random.RandomState(532)
        probes = [np.zeros(inp.shape, np.float32), random.rand(*inp.shape).astype(np.float32),
                  np.linspace(0, 1, np.prod(inp.shape), dtype=np.float32).reshape(inp.shape)]
        checks = []
        for x in probes:
            with torch.no_grad():
                expected = model.model(torch.from_numpy(x))
            if isinstance(expected, (list, tuple)):
                expected = expected[0]
            expected = expected.detach().cpu().numpy()
            got = session.run(None, {inp.name: x})[0]
            if got.shape != expected.shape or not np.isfinite(got).all():
                raise ValueError('invalid ONNX output')
            a, b = got.ravel().astype(np.float64), expected.ravel().astype(np.float64)
            denominator = np.linalg.norm(a) * np.linalg.norm(b)
            cosine = float(a @ b / denominator) if denominator else 0.0
            if cosine < .999 or not np.allclose(got, expected, rtol=1e-3, atol=1e-3):
                raise ValueError('ONNX output parity failed')
            checks.append(dict(max_abs_diff=float(np.max(np.abs(got - expected))), cosine=cosine))
        info = dict(model=name, task=model.task, opset=OPSET, input_name=inp.name,
            input_shape=inp.shape, output_shapes=[o.shape for o in session.get_outputs()],
            dtype='float32', dynamic=False, embedded_nms=False,
            weights_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            onnx_sha256=hashlib.sha256(exported.read_bytes()).hexdigest(),
            versions=dict(torch=torch.__version__, ultralytics=ultralytics.__version__,
                          onnx=onnx.__version__, onnxruntime=ort.__version__),
            parity=dict(provider=session.get_providers(), seed=532, probes=checks,
                        scope='three synthetic input tensors; not D1 accuracy or TensorRT parity'),
            tensorrt_built=False, edge_g2_accepted=False)
        with target.open('xb') as stream, exported.open('rb') as source_stream:
            shutil.copyfileobj(source_stream, stream)
        with metadata.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(info, indent=2, allow_nan=False) + '\n')
    print('  %s %.1f MB; ONNX Runtime parity verified' % (target.name, target.stat().st_size / 1e6))
    return info


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
    global OUT
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="+", choices=sorted(JOBS), help="default: all")
    ap.add_argument('--out', type=Path, default=OUT, help='output directory; YOLO delivery files must not exist')
    a = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    OUT = a.out.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    os.chdir(str(ROOT))
    failed = False
    for name in (a.only or sorted(JOBS)):
        print(name)
        try:
            JOBS[name]()
        except Exception as e:   # keep going: one model failing must not hide the others
            failed = True
            detail = (str(e).strip().splitlines() or ['no detail'])[-1][:160]
            print("  FAILED: %s: %s" % (type(e).__name__, detail))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
