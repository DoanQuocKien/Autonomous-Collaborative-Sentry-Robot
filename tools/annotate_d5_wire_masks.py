"""Manually trace wire pixels for the D5 segmentation feasibility pilot.

Run from the project root:
    python -m tools.annotate_d5_wire_masks
    python -m tools.annotate_d5_wire_masks --summary

Dependencies: opencv-python, numpy (already used by the perception project).

This tool is a mask-labeling aid, NOT an automatic segmentation model.
Masks are 8-bit PNGs (0 background, 255 wire). YOLO-seg polygon
conversion and any model training are separate, later steps.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil

import cv2
import numpy as np

IMAGE_TYPES = {".jpg", ".jpeg", ".png"}
WIN = "D5 Wire Mask Pilot"


def list_images(source: Path) -> list[Path]:
    if not source.is_dir():
        raise FileNotFoundError(f"Image directory not found: {source}")
    imgs = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_TYPES)
    if not imgs:
        raise RuntimeError(f"No images found in {source}")
    return imgs


def read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Cannot read image: {path}")
    return image


def mask_path(out: Path, image: Path) -> Path:
    return out / "masks" / (image.stem + ".png")


def load_mask(out: Path, image: Path, shape: tuple[int, int]) -> tuple[np.ndarray, bool]:
    p = mask_path(out, image)
    if not p.exists():
        return np.zeros(shape, np.uint8), False
    data = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    if data is None or data.shape != shape:
        raise ValueError(f"Mask unreadable or dimension mismatch: {p}")
    return np.where(data >= 128, 255, 0).astype(np.uint8), True


def overlay(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    vis = image.copy()
    hit = mask > 0
    if np.any(hit):
        tint = np.array([255, 235, 0], np.float32)  # BGR cyan
        vis[hit] = np.clip(vis[hit].astype(np.float32) * 0.30 + tint * 0.70, 0, 255).astype(np.uint8)
    return vis


def contrast_view(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)


def summarize(imgs: list[Path], out: Path) -> None:
    complete = 0
    contact = []
    for file in imgs:
        image = read_image(file)
        mask, exists = load_mask(out, file, image.shape[:2])
        count = int(np.count_nonzero(mask))
        complete += int(exists and count > 0)
        state = f"{count} px" if exists else "NOT SAVED"
        print(f"{'OK' if exists and count else '--':2}  {file.name}: {state}")
        vis = overlay(image, mask)
        contact.append((file.name, vis, state))
    print(f"\nMasks completed: {complete}/{len(imgs)}")
    if not contact:
        return
    columns = 3
    tile_w, tile_h, header = 400, 300, 26
    rows = (len(contact) + columns - 1) // columns
    canvas = np.full((rows * (tile_h + header), columns * tile_w, 3), 30, np.uint8)
    for k, (name, vis, status) in enumerate(contact):
        row, col = divmod(k, columns)
        x, y = col * tile_w, row * (tile_h + header)
        canvas[y + header:y + header + tile_h, x:x + tile_w] = cv2.resize(
            vis, (tile_w, tile_h), interpolation=cv2.INTER_AREA
        )
        title = f"{name[:35]} | {status}"
        cv2.putText(canvas, title, (x + 3, y + 18), cv2.FONT_HERSHEY_SIMPLEX,
                    0.38, (235, 235, 235), 1, cv2.LINE_AA)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "review_contact_sheet.jpg"
    if not cv2.imwrite(str(target), canvas):
        raise RuntimeError(f"Could not write contact sheet {target}")
    print(f"Contact sheet: {target}")


class Annotator:
    def __init__(self, images: list[Path], out: Path, zoom: float, brush: int):
        self.images = images
        self.out = out
        self.zoom = zoom
        self.brush = brush
        self.index = 0
        self.image = None
        self.mask = None
        self.exists = False
        self.dirty = False
        self.history = []
        self.drawing = False
        self.erase = False
        self.prev = None
        self.cursor = None
        self.enhance = False
        self.message = ""
        self.load(0)

    def load(self, index: int) -> None:
        self.index = index
        self.image = read_image(self.images[index])
        self.mask, self.exists = load_mask(self.out, self.images[index], self.image.shape[:2])
        self.dirty = False
        self.history = []
        self.drawing = False
        self.prev = None
        self.message = "Click/drag LEFT = wire | RIGHT = erase. Trace cable, not tile seams."

    def coordinates(self, x: int, y: int):
        h, w = self.mask.shape
        # Mouse callback is in enlarged-view coordinates.
        xx, yy = int(x / self.zoom), int(y / self.zoom)
        if not (0 <= xx < w and 0 <= yy < h):
            return None
        return xx, yy

    def stroke(self, p: tuple[int, int]) -> None:
        color = 0 if self.erase else 255
        radius = max(0, self.brush // 2)
        if self.prev is None:
            cv2.circle(self.mask, p, radius, color, -1, cv2.LINE_8)
        else:
            cv2.line(self.mask, self.prev, p, color, self.brush, cv2.LINE_8)
        self.prev = p
        self.dirty = True

    def on_mouse(self, event, x, y, flags, userdata):
        pt = self.coordinates(x, y)
        self.cursor = (x, y) if pt is not None else None
        if event in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN):
            if pt is None:
                return
            self.history.append(self.mask.copy())
            self.history = self.history[-30:]
            self.drawing = True
            self.erase = (event == cv2.EVENT_RBUTTONDOWN)
            self.prev = None
            self.stroke(pt)
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            if pt is not None:
                self.stroke(pt)
        elif event in (cv2.EVENT_LBUTTONUP, cv2.EVENT_RBUTTONUP):
            if self.drawing and pt is not None:
                self.stroke(pt)
            self.drawing = False
            self.prev = None

    def render(self) -> np.ndarray:
        img = contrast_view(self.image) if self.enhance else self.image
        drawn = overlay(img, self.mask)
        h, w = drawn.shape[:2]
        W, H = round(w * self.zoom), round(h * self.zoom)
        disp = cv2.resize(drawn, (W, H), interpolation=cv2.INTER_NEAREST)
        if self.cursor:
            x, y = self.cursor
            radius = max(1, round((self.brush / 2) * self.zoom))
            cv2.circle(disp, (x, y), radius, (0, 255, 255), 1, cv2.LINE_AA)
        footer = np.full((115, W, 3), 28, dtype=np.uint8)
        name = self.images[self.index].name
        status = "UNSAVED" if self.dirty else ("SAVED" if self.exists else "NOT ANNOTATED")
        lines = [
            f"{self.index + 1}/{len(self.images)}  {name[:58]}  [{status}]",
            f"Wire pixels: {np.count_nonzero(self.mask)} | Brush: {self.brush}px | View: {'CLAHE' if self.enhance else 'original'}",
            "LEFT draw  RIGHT erase  [ ] brush  U undo  T contrast  S save  N next  P previous  Q quit",
            self.message[:max(45, W // 9)],
        ]
        for i, line in enumerate(lines):
            color = (90, 230, 255) if i == 3 else (230, 230, 230)
            cv2.putText(footer, line, (8, 23 + i * 27),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.46, color, 1, cv2.LINE_AA)
        return np.vstack((disp, footer))

    def save(self) -> None:
        if np.count_nonzero(self.mask) == 0:
            self.message = "Mask empty: draw visible WIRE pixels before saving."
            return
        path = mask_path(self.out, self.images[self.index])
        path.parent.mkdir(parents=True, exist_ok=True)
        preview = self.out / "previews" / (self.images[self.index].stem + ".jpg")
        preview.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and self.dirty:
            backup_dir = self.out / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            shutil.copy2(path, backup_dir / f"{path.stem}_{timestamp}.png")
        if not cv2.imwrite(str(path), self.mask):
            raise RuntimeError(f"Could not save mask to {path}")
        if not cv2.imwrite(str(preview), overlay(self.image, self.mask)):
            raise RuntimeError(f"Could not save preview to {preview}")
        self.exists = True
        self.dirty = False
        self.message = f"Saved {path.name} ({int(np.count_nonzero(self.mask))} wire pixels)"

    def navigate(self, direction: int) -> None:
        if self.dirty:
            self.message = "Unsaved edits! Press S to save, then N or P."
            return
        target = self.index + direction
        if 0 <= target < len(self.images):
            self.load(target)
        else:
            self.message = "Already at the first/last image."

    def run(self):
        cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(WIN, self.on_mouse)
        quit_confirm = False
        try:
            while True:
                cv2.imshow(WIN, self.render())
                key = cv2.waitKeyEx(35)
                if key == -1:
                    continue
                if key in (ord("q"), ord("Q"), 27):
                    if self.dirty and not quit_confirm:
                        self.message = "UNSAVED! Press Q again to discard edits and quit, or S to save."
                        quit_confirm = True
                        continue
                    break
                quit_confirm = False
                if key in (ord("s"), ord("S")):
                    self.save()
                elif key in (ord("n"), ord("N")):
                    self.navigate(1)
                elif key in (ord("p"), ord("P")):
                    self.navigate(-1)
                elif key in (ord("u"), ord("U")):
                    if self.history:
                        self.mask = self.history.pop()
                        self.dirty = True
                        self.message = "Undid last stroke."
                    else:
                        self.message = "Nothing to undo."
                elif key in (ord("t"), ord("T")):
                    self.enhance = not self.enhance
                    self.message = "Contrast affects DISPLAY only, not mask."
                elif key == ord("["):
                    self.brush = max(1, self.brush - 1)
                    self.message = f"Brush width now {self.brush} original-image pixels."
                elif key == ord("]"):
                    self.brush = min(32, self.brush + 1)
                    self.message = f"Brush width now {self.brush} original-image pixels."
        finally:
            cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=Path("data/D5_wire_seg_pilot"))
    ap.add_argument("--out", type=Path, default=Path("data/D5_wire_seg_masks_v1"))
    ap.add_argument("--zoom", type=float, default=1.5,
                    help="Screen scale (original mask resolution never changes).")
    ap.add_argument("--brush", type=int, default=3,
                    help="Initial brush width in ORIGINAL image pixels.")
    ap.add_argument("--summary", action="store_true", help="No GUI: inspect saved mask coverage.")
    args = ap.parse_args()
    if not (1 <= args.brush <= 32 and 0.75 <= args.zoom <= 3.0):
        ap.error("Expected --brush 1..32 and --zoom 0.75..3.0")
    imgs = list_images(args.source)
    print(f"Found {len(imgs)} pilot images in {args.source}")
    if len(imgs) != 12:
        print("NOTE: pilot expected 12 images; inspect folder if you intended 12.")
    if args.summary:
        summarize(imgs, args.out)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    print("Masks: blue/cyan strokes are WIRE pixels. Avoid tiles, shadows and reflections.")
    print("Left draw, right erase, [ ] brush width, T contrast, U undo, S save, N next, P previous, Q quit")
    Annotator(imgs, args.out, args.zoom, args.brush).run()
    print("Run summary: python -m tools.annotate_d5_wire_masks --summary")


if __name__ == "__main__":
    main()
