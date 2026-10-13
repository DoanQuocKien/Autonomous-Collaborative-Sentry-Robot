import math, glob, csv, numpy as np, cv2
src = open("../rt_test.py").read().split("go = threading.Event()")[0]
exec(src)                                                           # live, fixed, truth_and_pixel, ... (the live pitch object is replaced per variant)
meta = list(csv.DictReader(open("../run_rec/meta.csv")))
imgs = [cv2.imread("../run_rec/f%04d.jpg" % int(m["i"])) for m in meta]
ts = np.array([float(m["t"]) for m in meta])
und = [live.undistort(im) for im in imgs]
truth = [truth_and_pixel(u) for u in und]
def run(n, max_jump=5.0, min_samples=5):
    g = CameraGeometry.from_files("calib/camera.json", "calib/camera_pose_tilt_ref.json")
    l = LiveTilt.from_config(g, cfg, every=1, n=n, max_jump_deg=max_jump)
    out = []
    for u, tr in zip(und, truth):
        l(u)
        if tr is None: out.append(None); continue
        p = g.ground_point(tr["u"], tr["v"]); out.append((tr["fwd"], p.forward_m if p else float("nan"), math.degrees(g.pitch)))
    return out
fx = fixed
fb = [ (fixed.ground_point(tr["u"], tr["v"]).forward_m if tr and fixed.ground_point(tr["u"], tr["v"]) else float("nan")) for tr in truth]
def summarise(name, out):
    rows = [(i, o) for i, o in enumerate(out) if o is not None and np.isfinite(o[1])]
    tru = np.array([o[0] for _, o in rows]); bel = np.array([o[1] for _, o in rows]); idx = np.array([i for i, _ in rows])
    moving = (tru < 2.2) & (tru > 0.62); still = tru >= 2.2
    e = bel - tru
    f = np.array([fb[i] for i in idx]) - tru
    def med(m, x): return np.median(abs(x[m])) if m.sum() else float("nan")
    print("%-22s still: med|err| %.3f   moving(%3d fr): med|err| %.3f  (rel %.0f%%)  signed %+.3f" % (name, med(still, e), moving.sum(), med(moving, e), 100*np.median(abs(e[moving])/tru[moving]), np.median(e[moving])))
    return f, moving, still, tru
f, moving, still, tru = summarise("window 15 (current)", run(15))
print("%-22s still: med|err| %.3f   moving: med|err| %.3f  (rel %.0f%%)  signed %+.3f" % ("FIXED 5.03 deg", np.median(abs(f[still])), np.median(abs(f[moving])), 100*np.median(abs(f[moving])/tru[moving]), np.median(f[moving])))
for n in (9, 5, 3, 1):
    summarise("window %d" % n, run(n, min_samples=min(5, n)))
