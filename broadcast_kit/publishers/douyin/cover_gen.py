from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageOps


logger = logging.getLogger(__name__)


class MediaError(RuntimeError):
    pass


def _center_crop_to_ratio(image: Image.Image, ratio_w: int, ratio_h: int) -> Image.Image:
    source_w, source_h = image.size
    target_ratio = ratio_w / ratio_h
    source_ratio = source_w / source_h
    if source_ratio > target_ratio:
        new_w = int(source_h * target_ratio)
        left = (source_w - new_w) // 2
        box = (left, 0, left + new_w, source_h)
    else:
        new_h = int(source_w / target_ratio)
        top = (source_h - new_h) // 2
        box = (0, top, source_w, top + new_h)
    return image.crop(box)


def _save_jpg(image: Image.Image, path: Path, size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = image.resize(size, Image.Resampling.LANCZOS).convert("RGB")
    rgb.save(path, format="JPEG", quality=92, optimize=True)
    logger.info("cover generated: %s", path)
    return path.resolve()


def _save_png(image: Image.Image, path: Path, size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba = image.resize(size, Image.Resampling.LANCZOS).convert("RGB")
    rgba.save(path, format="PNG", optimize=True)
    logger.info("cover generated: %s", path)
    return path.resolve()


def generate_covers_from_infographic(
    infographic_path: str | Path, out_dir: str | Path, stem: str | None = None
) -> tuple[Path, Path]:
    source = Path(infographic_path).expanduser().resolve()
    if not source.exists():
        raise MediaError(f"infographic not found: {source}")
    covers_dir = Path(out_dir).expanduser().resolve() / "covers"
    prefix = f"{stem}_" if stem else ""
    horizontal_path = covers_dir / f"{prefix}cover_4_3_1200x900.jpg"
    vertical_path = covers_dir / f"{prefix}cover_3_4_900x1200.jpg"
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened)
            horizontal = _center_crop_to_ratio(image, 4, 3)
            vertical = _center_crop_to_ratio(image, 3, 4)
            return (
                _save_jpg(horizontal, horizontal_path, (1200, 900)),
                _save_jpg(vertical, vertical_path, (900, 1200)),
            )
    except OSError as exc:
        raise MediaError(f"cannot read infographic: {source}") from exc


def _ffmpeg_extract_frame(video: Path, out_path: Path, at_seconds: float) -> Path:
    if shutil.which("ffmpeg") is None:
        raise MediaError("ffmpeg not found on PATH; install via brew install ffmpeg or apt install ffmpeg")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{at_seconds:.2f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise MediaError(f"ffmpeg frame extraction failed: {result.stderr.strip()[:400]}")
    if not out_path.exists():
        raise MediaError(f"ffmpeg succeeded but frame missing: {out_path}")
    return out_path.resolve()


def generate_covers_from_video(
    video_path: str | Path, out_dir: str | Path, at_seconds: float = 6.0
) -> tuple[Path, Path]:
    video = Path(video_path).expanduser().resolve()
    if not video.exists():
        raise MediaError(f"video not found: {video}")
    covers_dir = Path(out_dir).expanduser().resolve() / "covers"
    frame_path = covers_dir / "frame.png"
    horizontal_path = covers_dir / "cover_4_3_1200x900.png"
    vertical_path = covers_dir / "cover_3_4_900x1200.png"
    _ffmpeg_extract_frame(video, frame_path, at_seconds)
    try:
        with Image.open(frame_path) as opened:
            image = ImageOps.exif_transpose(opened)
            horizontal = _center_crop_to_ratio(image, 4, 3)
            vertical = _center_crop_to_ratio(image, 3, 4)
            return (
                _save_png(horizontal, horizontal_path, (1200, 900)),
                _save_png(vertical, vertical_path, (900, 1200)),
            )
    except OSError as exc:
        raise MediaError(f"cannot read extracted frame: {frame_path}") from exc
