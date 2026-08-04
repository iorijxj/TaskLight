"""红绿灯图像合成。纯 PIL 运算，不依赖 tkinter，可脱离 GUI 测试。

底图用 A2（三灯全灭），需要点亮某盏时把 A1（三灯全亮）对应区域合成上去。
遮罩取两图的差异强度而非硬圆形，这样发光溢出到面板上的光晕能自然过渡。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

IMAGE_DIR = Path(__file__).resolve().parent.parent / "IMAGE"
LIT_FILE = "A1.png"
DARK_FILE = "A2.png"

# 面板加光晕的有效区域，由 A2 的非黑像素范围算得
CROP = (66, 238, 1978, 880)
# 裁剪后坐标系下，三盏灯之间的 x 分界（取相邻发光区间的中点）
LAMP_SPLITS = (691, 1212)
# 预合成的基准宽度：显示尺寸不会超过它，缩放时只做缩小
BASE_WIDTH = 960
GLOW_GAIN = 2.2

LAMP_NAMES = ("red", "orange", "green")
DARK_FRAME = "none"


def _load_pair() -> tuple[Image.Image, Image.Image]:
    lit = Image.open(IMAGE_DIR / LIT_FILE).convert("RGB").crop(CROP)
    dark = Image.open(IMAGE_DIR / DARK_FILE).convert("RGB").crop(CROP)
    scale = BASE_WIDTH / lit.width
    size = (BASE_WIDTH, round(lit.height * scale))
    return lit.resize(size, Image.LANCZOS), dark.resize(size, Image.LANCZOS)


def _glow_mask(lit: Image.Image, dark: Image.Image) -> Image.Image:
    diff = ImageChops.difference(lit, dark).convert("L")
    return diff.point(lambda v: min(255, int(v * GLOW_GAIN)))


def _lamp_mask(full_mask: Image.Image, index: int) -> Image.Image:
    """把整体遮罩按 x 切出单盏灯的部分，其余置黑。"""
    width, height = full_mask.size
    scale = width / (CROP[2] - CROP[0])
    splits = [0, *(round(s * scale) for s in LAMP_SPLITS), width]
    mask = Image.new("L", (width, height), 0)
    box = (splits[index], 0, splits[index + 1], height)
    mask.paste(full_mask.crop(box), box)
    return mask


def build_frames() -> dict[str, Image.Image]:
    """返回四张预合成图：三盏灯各自点亮，加一张全灭。"""
    lit, dark = _load_pair()
    full_mask = _glow_mask(lit, dark)
    frames = {DARK_FRAME: dark}
    for index, name in enumerate(LAMP_NAMES):
        frames[name] = Image.composite(lit, dark, _lamp_mask(full_mask, index))
    return frames


def aspect_ratio() -> float:
    return (CROP[2] - CROP[0]) / (CROP[3] - CROP[1])
