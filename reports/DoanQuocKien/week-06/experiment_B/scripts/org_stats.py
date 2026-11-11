import collections
import glob
import json

import cv2
import numpy as np

R = r"D:\CS532\Autonomous Collaborative Sentry Robot\data\ORG"
names = collections.Counter()
sizes = []
for split in ("train", "test"):
    fs = glob.glob(R + r"\gtCoarse\%s\*\*_obstacles.json" % split)
    c = collections.Counter()
    for f in fs:
        d = json.load(open(f))
        ob = d.get("objects", [])
        objs = ob if isinstance(ob, list) else [ob]
        for o in objs:
            c[(o["type_ID"], o["name"])] += 1
            if len(o["boundingbox"]) != 4:
                continue
            x, y, w, h = o["boundingbox"]
            sizes.append((split, w, h))
    print(split, "images with obstacle json:", len(fs), "objects:", sum(c.values()), "classes:", len(c))
    print("  ", sorted(c.items(), key=lambda kv: -kv[1])[:14])
for split in ("train", "test"):
    s = [(w, h) for sp, w, h in sizes if sp == split]
    print(split, "object size px at 1920x1080: median w %d h %d | 10th percentile w %d h %d | 90th w %d h %d" % (np.median([a for a, _ in s]), np.median([b for _, b in s]), np.percentile([a for a, _ in s], 10), np.percentile([b for _, b in s], 10), np.percentile([a for a, _ in s], 90), np.percentile([b for _, b in s], 90)))
m = cv2.imread(sorted(glob.glob(R + r"\gtCoarse_Segmentation\train\*\*.png"))[100], cv2.IMREAD_UNCHANGED)
print("a label image: ids", np.unique(m), "ground fraction %.2f" % (m == 1).mean(), "obstacle fraction %.4f" % (m >= 2).mean())
