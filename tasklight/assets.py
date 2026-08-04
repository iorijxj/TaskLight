"""红绿灯图片资源。四张独立 PNG 各对应一盏灯，另合成一张红+橙同亮。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops

IMAGE_DIR = Path(__file__).resolve().parent.parent / "IMAGE"

FRAME_RED = "red"
FRAME_ORANGE = "orange"
FRAME_GREEN = "green"
FRAME_RED_ORANGE = "red_orange"
FRAME_DARK = "none"

SOURCE_FILES = {
    FRAME_RED: "L_Red.png",
    FRAME_ORANGE: "L_Yellow.png",
    FRAME_GREEN: "L_Green.png",
    FRAME_DARK: "L_Off.png",
}
# 显示尺寸不会超过它，缩放时只做缩小
BASE_WIDTH = 960


@lru_cache(maxsize=1)
def build_frames() -> dict[str, Image.Image]:
    frames = {}
    for name, filename in SOURCE_FILES.items():
        image = Image.open(IMAGE_DIR / filename).convert("RGBA")
        scale = BASE_WIDTH / image.width
        frames[name] = image.resize(
            (BASE_WIDTH, round(image.height * scale)), Image.LANCZOS
        )
    frames[FRAME_RED_ORANGE] = _combine(frames[FRAME_RED], frames[FRAME_ORANGE])
    return frames


def _combine(first: Image.Image, second: Image.Image) -> Image.Image:
    """逐像素取较亮者。

    每张源图只亮一盏灯、其余部分彼此相同，所以「取较亮」恰好等于把两盏灯
    各自的发光叠上去，面板本身不受影响，也不需要额外出图。
    """
    return ImageChops.lighter(first, second)


def aspect_ratio() -> float:
    frame = build_frames()[FRAME_DARK]
    return frame.width / frame.height
