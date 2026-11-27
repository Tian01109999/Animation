"""Backend vẽ: GPU (OpenGL qua cửa sổ glfw ẩn) nếu có, ngược lại CPU raster.

Lý do: bản skia-python cho Windows dựng bằng MSVC nên "raster pipeline" của skia trên CPU rất chậm (vẽ ảnh xoay,
blend mode, màu bán trong suốt... chậm 50-100 lần). Trên GPU mọi thao tác này ~1 ms.
Đặt biến môi trường STORYTOON_CPU=1 để ép dùng CPU (chậm, chỉ để gỡ lỗi).
"""
from __future__ import annotations

import logging
import os
import threading

import numpy as np
import skia

log = logging.getLogger("storytoon.render")


class Backend:
    def __init__(self) -> None:
        self.ctx: skia.GrDirectContext | None = None
        self._win = None
        self._tex: dict[tuple[int, bool], skia.Image] = {}
        if os.environ.get("STORYTOON_CPU") == "1":
            log.info("Render bằng CPU (STORYTOON_CPU=1)")
            return
        try:
            import glfw  # type: ignore
            if not glfw.init():
                raise RuntimeError("glfw.init() thất bại")
            glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
            self._win = glfw.create_window(16, 16, "storytoon-render", None, None)
            if not self._win:
                raise RuntimeError("không tạo được OpenGL context")
            glfw.make_context_current(self._win)
            self.ctx = skia.GrDirectContext.MakeGL()
            if self.ctx is None:
                raise RuntimeError("skia không tạo được GrDirectContext GL")
            self.thread = threading.get_ident()
            log.info("Render bằng GPU (OpenGL)")
        except Exception as e:  # noqa: BLE001 — mọi lỗi GL -> CPU
            log.warning("Không dùng được GPU để render (%s) — chuyển sang CPU (chậm hơn nhiều)", e)
            self.ctx = None

    @property
    def gpu(self) -> bool:
        return self.ctx is not None

    def surface(self, w: int, h: int) -> skia.Surface:
        """Surface trung gian (RGBA premul)."""
        w, h = max(1, int(w)), max(1, int(h))
        if self.ctx is not None:
            info = skia.ImageInfo.Make(w, h, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType)
            s = skia.Surface.MakeRenderTarget(self.ctx, skia.Budgeted.kYes, info)
            if s is not None:
                return s
            log.warning("Không tạo được surface GPU %dx%d — dùng CPU", w, h)
        return skia.Surface(w, h)

    def texture(self, img: skia.Image, mipmaps: bool = False, cache: bool = False) -> skia.Image:
        """Đưa ảnh lên GPU (1 lần). `cache=True`: nhớ theo uniqueID (dùng cho ảnh nền lớn dùng lại nhiều shot)."""
        if self.ctx is None or img is None or img.isTextureBacked():
            return img
        key = (img.uniqueID(), mipmaps)
        if cache and key in self._tex:
            return self._tex[key]
        t = img.makeTextureImage(self.ctx, skia.GrMipmapped.kYes if mipmaps else skia.GrMipmapped.kNo)
        t = t if t is not None else img
        if cache:
            self._tex[key] = t
            while len(self._tex) > 12:
                self._tex.pop(next(iter(self._tex)))
        return t

    def snapshot(self, s: skia.Surface) -> skia.Image:
        return s.makeImageSnapshot()


class FrameTarget:
    """Surface khung đầu ra + bộ đệm numpy để đọc về và gửi sang ffmpeg."""

    def __init__(self, be: Backend, W: int, H: int) -> None:
        self.be, self.W, self.H = be, W, H
        self.buf = np.zeros((H, W, 4), np.uint8)
        if be.gpu:
            self.info = skia.ImageInfo.Make(W, H, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType)
            self.surface = be.surface(W, H)
            self.pix_fmt = "rgba"
            self._gpu = True  # đọc về bằng readPixels (kể cả khi surface rơi về CPU)
        else:
            # CPU: BGRA (N32) bọc thẳng numpy — RGBA trên CPU chậm hơn ~80 lần do phải đảo kênh
            self.surface = skia.Surface(self.buf, colorType=skia.kBGRA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
            self.pix_fmt = "bgra"
            self._gpu = False
        self.canvas = self.surface.getCanvas()

    def read(self) -> np.ndarray:
        if self._gpu:
            self.surface.readPixels(self.info, self.buf, self.W * 4)
        else:
            self.surface.flushAndSubmit()
        return self.buf

    def rgb(self) -> np.ndarray:
        """Bản sao RGB (để lưu PNG)."""
        b = self.buf
        return b[..., :3].copy() if self.pix_fmt == "rgba" else b[..., 2::-1].copy()


_BE: Backend | None = None
_LOCK = threading.Lock()


def get_backend() -> Backend:
    global _BE
    with _LOCK:
        if _BE is None:
            _BE = Backend()
        return _BE
