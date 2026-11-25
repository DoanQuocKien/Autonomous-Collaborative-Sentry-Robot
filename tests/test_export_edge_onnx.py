import numpy as np
import pytest

onnx = pytest.importorskip("onnx")
ort = pytest.importorskip("onnxruntime")
from onnx import TensorProto, helper, numpy_helper  # noqa: E402

from tools.export_edge_onnx import resize_to_deconv  # noqa: E402


def _model():
    sizes = numpy_helper.from_array(np.array([1, 3, 8, 12], np.int64), "sizes")
    empty = numpy_helper.from_array(np.array([], np.float32), "empty")
    node = helper.make_node("Resize", ["x", "empty", "empty", "sizes"], ["y"], mode="nearest",
                            coordinate_transformation_mode="asymmetric", nearest_mode="floor")
    g = helper.make_graph([node], "g", [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 3, 4, 6])],
                          [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 3, 8, 12])], [sizes, empty])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 11)])
    m.ir_version = 8                      # onnx.helper stamps the newest IR; ONNX Runtime 1.23 reads up to 11
    return m


def test_nearest_2x_resize_becomes_an_identical_grouped_deconv():
    m = _model()
    x = np.random.RandomState(0).randn(1, 3, 4, 6).astype(np.float32)
    ref = ort.InferenceSession(m.SerializeToString(), providers=["CPUExecutionProvider"]).run(None, {"x": x})[0]
    out = resize_to_deconv(m)
    assert [n.op_type for n in out.graph.node] == ["ConvTranspose"]
    got = ort.InferenceSession(out.SerializeToString(), providers=["CPUExecutionProvider"]).run(None, {"x": x})[0]
    assert np.array_equal(got, ref) and got.shape == (1, 3, 8, 12)


def test_cli_failure_is_nonzero_and_later_jobs_still_run(monkeypatch, tmp_path):
    from tools import export_edge_onnx as exporter
    called = []
    def fail():
        raise ValueError('fixture export failed')
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    monkeypatch.setattr(exporter, 'OUT', tmp_path/'original')
    monkeypatch.setattr(exporter, 'JOBS', {'bad': fail, 'good': lambda: called.append('good')})
    monkeypatch.chdir(tmp_path)
    assert exporter.main(['--only', 'bad', 'good', '--out', str(tmp_path/'failed')]) == 1
    assert called == ['good']
    assert exporter.main(['--only', 'good', '--out', str(tmp_path/'ok')]) == 0


def test_yolo_export_refuses_to_replace_existing_evidence(monkeypatch, tmp_path):
    from tools import export_edge_onnx as exporter
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    monkeypatch.setattr(exporter, 'OUT', tmp_path)
    (tmp_path/'model.pt').write_bytes(b'fixture')
    target = tmp_path/'model.onnx'
    target.write_bytes(b'existing export')
    with pytest.raises(FileExistsError):
        exporter.yolo('model.pt', 'model')
    assert target.read_bytes() == b'existing export'
