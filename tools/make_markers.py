"""Print-ready A4 PDFs: ArUco markers (10 cm) and the fisheye calibration checkerboard.

Run:  python tools/make_markers.py          -> assets/print/*.pdf
Print at 100 % / "actual size" (NOT "fit to page"), on flat rigid paper, then MEASURE the
100 mm scale bar and a marker/square with a ruler and put the real sizes in config.toml.
1 mm = 10 px (254 dpi), so sizes are exact.
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

DPI = 254


def px(mm):
    return int(round(mm * 10))


def page(landscape=False):
    w, h = px(210), px(297)
    return np.full((w, h) if landscape else (h, w), 255, np.uint8)


def text(img, s, x, y, scale=1.6):
    cv2.putText(img, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, 0, 3, cv2.LINE_AA)


def scale_bar(img, x, y):
    cv2.line(img, (x, y), (x + px(100), y), 0, 4)
    for i in range(11):
        cv2.line(img, (x + px(10) * i, y - px(3)), (x + px(10) * i, y + px(3)), 0, 4)
    text(img, "this bar must measure 100 mm; if not, printer is scaling", x, y + px(9), 1.1)


def marker(dict_name, marker_id, size_mm=100):
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
    return cv2.aruco.generateImageMarker(d, marker_id, px(size_mm))


def marker_pages(ids, dict_name="DICT_4X4_50", size_mm=100):
    per_page = 2 if size_mm <= 100 else 1  # two 10 cm markers fit an A4 page; bigger ones get a page each
    pages = []
    for i in range(0, len(ids), per_page):
        pg = page()
        for slot, mid in enumerate(ids[i:i + per_page]):
            x, y = (px(210) - px(size_mm)) // 2, px(15) + slot * px(125)
            pg[y:y + px(size_mm), x:x + px(size_mm)] = marker(dict_name, mid, size_mm)
            text(pg, "%s id %d  (%d mm)" % (dict_name, mid, size_mm), x, y + px(size_mm) + px(8))
        scale_bar(pg, px(55), px(282))
        pages.append(pg)
    return pages


def checkerboard(cols=10, rows=7, sq_mm=25):
    """cols x rows squares -> (cols-1) x (rows-1) inner corners. Top-left square is black."""
    s = px(sq_mm)
    board = np.full((rows * s, cols * s), 255, np.uint8)
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                board[r * s:(r + 1) * s, c * s:(c + 1) * s] = 0
    return board


def checkerboard_page(cols=10, rows=7, sq_mm=25):
    pg = page(landscape=True)
    b = checkerboard(cols, rows, sq_mm)
    x, y = (pg.shape[1] - b.shape[1]) // 2, px(8)
    pg[y:y + b.shape[0], x:x + b.shape[1]] = b
    text(pg, "checkerboard %dx%d inner corners, square %d mm" % (cols - 1, rows - 1, sq_mm), x, y + b.shape[0] + px(7))
    scale_bar(pg, x, y + b.shape[0] + px(15))
    return pg


def save_pdf(pages, path):
    imgs = [Image.fromarray(p) for p in pages]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], resolution=DPI)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "assets" / "print"
    out.mkdir(parents=True, exist_ok=True)
    save_pdf(marker_pages(list(range(6))), out / "aruco_4x4_50_ids0-5_100mm.pdf")
    save_pdf(marker_pages(list(range(6)), size_mm=150), out / "aruco_4x4_50_ids0-5_150mm.pdf")
    save_pdf([checkerboard_page()], out / "checkerboard_9x6_25mm.pdf")
    print("wrote", *sorted(p.name for p in out.glob("*.pdf")))
