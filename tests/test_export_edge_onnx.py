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
