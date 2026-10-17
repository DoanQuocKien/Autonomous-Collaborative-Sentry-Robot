# offline check of the servo logic with a fake robot (no motion): a plant that turns RATE deg per packet with noise
import sys, random; sys.argv = ["x"]

sys.path.insert(0, "..")
import importlib.util
spec = importlib.util.spec_from_file_location("tt", "../turn_test.py"); tt = importlib.util.module_from_spec(spec); spec.loader.exec_module(tt)
for rate, start in ((tt.NOM_DEG, 25.0), (0.7 * tt.NOM_DEG, -30.0), (1.3 * tt.NOM_DEG, 12.0)):
    st = {"b": start}; rnd = random.Random(1)
    def measure(): return st["b"] + rnd.gauss(0, 0.2)
    def pulse(w, n): st["b"] -= (1 if w > 0 else -1) * n * rate * (1 + rnd.gauss(0, 0.05))
    cy = tt.servo(measure, pulse, lambda: None, log=lambda s: None)
    print("plant %.1f deg/packet (nominal %.1f), start %+5.1f deg -> %d cycles, final %+.2f deg" % (rate, tt.NOM_DEG, start, len(cy), st["b"]))
    assert abs(st["b"]) < 0.65 * tt.NOM_DEG and len(cy) <= 6
print("logic ok; nominal turn per packet = %.2f deg at w=%.1f" % (tt.NOM_DEG, tt.W))
