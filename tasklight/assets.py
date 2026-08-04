"""红绿灯图片资源。四张独立 PNG，各对应一种灯态，带 alpha 通道。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

IMAGE_DIR = Path(__file__).resolve().parent.parent / "IMAGE"
DARK_FRAME = "none"
FRAME_FILES = {
    "red": "L_Red.png",
    "orange": "L_Yellow.png",
    "green": "L_Green.png",
    DARK_FRAME: "L_Off.png",
}
# 显示尺寸不会超过它，缩放时只做缩小
BASE_WIDTH = 960


@lru_cache(maxsize=1)
def build_frames() -> dict[str, Image.Image]:
    frames = {}
    for name, filename in FRAME_FILES.items():
        image = Image.open(IMAGE_DIR / filename).convert("RGBA")
        scale = BASE_WIDTH / image.width
        frames[name] = image.resize(
            (BASE_WIDTH, round(image.height * scale)), Image.LANCZOS
        )
    return frames


def aspect_ratio() -> float:
    frame = build_frames()[DARK_FRAME]
    return frame.width / frame.height
