"""Camera tilt from an ArUco marker on a vertical wall (sentry/perception/camera_pose.py), from the live robot stream or from saved photos.

  python -m tools.estimate_camera_tilt --marker-m 0.15 --bottom-h 0.12                  # live: 40 frames, prints the median tilt
  python -m tools.estimate_camera_tilt --marker-m 0.15 --bottom-h 0.12 --image a.jpg b.jpg
--bottom-h is the height of the marker's LOWER edge above the floor; --camera-h is the lens height (tape, default 0.100 m).
The marker must be on a vertical surface (book held upright, wall) and within about 2 m. Compare the result with tools/measure_camera_pose.py (strips).
"""
import argparse
import json

import cv2
import numpy as np

from sentry.perception.camera_pose import TiltFilter


def undistorter(cam):
    K, D = np.array(cam["K"]), np.array(cam["D"])
    m1, m2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), K, (640, 480), cv2.CV_16SC2)
    return K, lambda im: cv2.remap(im, m1, m2, cv2.INTER_LINEAR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marker-m", type=float, required=True, help="printed marker side (m), the black square only")
    ap.add_argument("--bottom-h", type=float, required=True, help="height of the marker's lower edge above the floor (m)")
    ap.add_argument("--camera-h", type=float, default=0.100)
    ap.add_argument("--id", type=int, default=None)
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--image", nargs="*")
    ap.add_argument("--camera", default="calib/camera.json")
    a = ap.parse_args()
    K, und = undistorter(json.load(open(a.camera)))
    tilt, shown = TiltFilter(max_distance_m=3.0), 0

    def feed(img):
        nonlocal shown
        e = tilt.update_frame(und(img), K, a.marker_m, a.bottom_h, a.id, a.camera_h)
        if e:
            shown += 1
            print("marker at %.2f m: pitch %+.2f deg (position), %+.1f deg (orientation, noisy), roll %+.1f deg, reproj %.2f px" %
                  (e["distance_m"], e["pitch_deg"], e["pitch_ori_deg"], e["roll_deg"], e["reproj_px"]))

    if a.image:
        for p in a.image:
            feed(cv2.imread(p))
    else:
        from sentry.net.zmq_rx import ZMQReceiver
        with ZMQReceiver() as rx:
            n = 0
            while n < a.frames:
                f = rx.read(timeout=5)
                if f is None:
                    break
                n += 1
                feed(f.frame_bgr)
    if not tilt.hist:
        print("no usable marker found (marker visible, vertical, within ~2.5 m, right id/dictionary 4x4_50?)")
    else:
        print("\nMEDIAN of %d frames: pitch %+.2f deg (positive = looking down), roll %+.2f deg, %d outliers rejected" % (len(tilt.hist), tilt.pitch_deg, tilt.roll_deg, tilt.rejected))


if __name__ == "__main__":
    main()
