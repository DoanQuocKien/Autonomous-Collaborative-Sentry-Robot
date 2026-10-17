"""Minimal TensorRT 7.1 engine runner for the Jetson Nano (Python 3.6, tensorrt + pycuda from the JetBot container).

    eng = TrtEngine("/workspace/trt/y320_fp16.engine")
    outs = eng.infer(blob)          # blob: float32 array with the engine's input shape -> list of float32 arrays

One engine = one CUDA stream, page-locked host buffers, explicit batch (engines built with trtexec --onnx). Not thread-safe:
use one TrtEngine per thread. Engines are tied to the TensorRT version and GPU: build them on the robot (docs/Edge Feasibility.md).
"""
import numpy as np
import pycuda.autoinit  # noqa: F401  (creates the CUDA context)
import pycuda.driver as cuda
import tensorrt as trt

_LOGGER = trt.Logger(trt.Logger.WARNING)
trt.init_libnvinfer_plugins(_LOGGER, "")   # InstanceNorm (OSNet-AIN, XFeat) is a plugin in TensorRT 7.1; trtexec registers it, Python must do it


class TrtEngine(object):
    def __init__(self, path, input_shape=None):
        """input_shape: only for engines built from a dynamic-shape ONNX (min = opt = max profile): the shape to run at."""
        with open(path, "rb") as f, trt.Runtime(_LOGGER) as rt:
            self.engine = rt.deserialize_cuda_engine(f.read())
        if self.engine is None:
            raise RuntimeError("could not load %s (built with another TensorRT version?)" % path)
        self.ctx = self.engine.create_execution_context()
        self.stream = cuda.Stream()
        self.inputs, self.outputs, self.bindings = [], [], []
        for i in range(self.engine.num_bindings):
            if self.engine.binding_is_input(i) and input_shape is not None and any(d < 0 for d in self.engine.get_binding_shape(i)):
                self.ctx.set_binding_shape(i, tuple(input_shape))
        for i in range(self.engine.num_bindings):
            shape = tuple(self.ctx.get_binding_shape(i))
            if any(d < 0 for d in shape):
                raise RuntimeError("binding %s has a dynamic shape %s: pass input_shape=" % (self.engine.get_binding_name(i), shape))
            dtype = trt.nptype(self.engine.get_binding_dtype(i))
            host = cuda.pagelocked_empty(int(np.prod(shape)), dtype)
            dev = cuda.mem_alloc(host.nbytes)
            self.bindings.append(int(dev))
            (self.inputs if self.engine.binding_is_input(i) else self.outputs).append((host, dev, shape))
        self.input_shape = self.inputs[0][2]

    def infer(self, blob):
        host, dev, shape = self.inputs[0]
        if tuple(blob.shape) != tuple(shape):
            raise ValueError("input %s, engine expects %s" % (blob.shape, shape))
        np.copyto(host, blob.ravel().astype(host.dtype, copy=False))
        cuda.memcpy_htod_async(dev, host, self.stream)
        self.ctx.execute_async_v2(self.bindings, self.stream.handle)
        for h, d, _ in self.outputs:
            cuda.memcpy_dtoh_async(h, d, self.stream)
        self.stream.synchronize()
        return [h.reshape(s).copy() for h, _, s in self.outputs]
