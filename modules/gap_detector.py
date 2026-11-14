#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缺口识别：多法融合 + 中位数一致性。

方法池（均针对易盾滑块的前景拼图/背景底图）：
  1. 带白边清除的 Canny + matchTemplate（主判，TM_CCOEFF_NORMED）
  2. 带掩码模板匹配（拼图非白色区域做 mask，TM_CCORR_NORMED）
  3. Sobel 梯度图相关（对光照变化更稳）
多法结果先取中位数、剔除与中位数偏差超过容差的离群值后再平均 —— 单法在
低对比度/重复纹理背景上会系统性跑偏，融合后实测稳定。
"""
import statistics

import cv2
import numpy as np

_CANNY_LO, _CANNY_HI = 100, 200
_OUTLIER_TOL = 12  # 像素；与中位数偏差超过该值的方法结果视为离群


def _decode(img: bytes, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.frombuffer(img, dtype=np.uint8), flags)


def _clear_white(img):
    """裁掉拼图四周的纯白边（易盾拼图外围是白色透明垫）。"""
    rows, cols, _c = img.shape
    min_x, min_y, max_x, max_y = 255, 255, 0, 0
    for x in range(1, rows):
        for y in range(1, cols):
            if len(set(img[x, y])) >= 2:
                if x <= min_x:
                    min_x = x
                elif x >= max_x:
                    max_x = x
                if y <= min_y:
                    min_y = y
                elif y >= max_y:
                    max_y = y
    return img[min_x:max_x, min_y:max_y]


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img


def _canny_template(piece_gray, back_gray):
    slide = cv2.Canny(piece_gray, _CANNY_LO, _CANNY_HI)
    back = cv2.Canny(back_gray, _CANNY_LO, _CANNY_HI)
    res = cv2.matchTemplate(cv2.cvtColor(slide, cv2.COLOR_GRAY2RGB),
                            cv2.cvtColor(back, cv2.COLOR_GRAY2RGB),
                            cv2.TM_CCOEFF_NORMED)
    _mn, _mx, _ml, max_loc = cv2.minMaxLoc(res)
    return max_loc[0]


def _masked_template(piece_rgb, back_rgb):
    """带掩码模板匹配：mask = 非白色区域（拼图本体）。"""
    piece_gray = _gray(piece_rgb)
    lower, upper = 1, 254
    mask = cv2.inRange(piece_gray, lower, upper)
    slide = cv2.Canny(piece_gray, _CANNY_LO, _CANNY_HI)
    back = cv2.Canny(_gray(back_rgb), _CANNY_LO, _CANNY_HI)
    res = cv2.matchTemplate(cv2.cvtColor(slide, cv2.COLOR_GRAY2RGB),
                            cv2.cvtColor(back, cv2.COLOR_GRAY2RGB),
                            cv2.TM_CCORR_NORMED, mask=mask)
    _mn, _mx, _ml, max_loc = cv2.minMaxLoc(res)
    return max_loc[0]


def _sobel_template(piece_gray, back_gray):
    sx = cv2.Sobel(piece_gray, cv2.CV_32F, 1, 0, ksize=3)
    bx = cv2.Sobel(back_gray, cv2.CV_32F, 1, 0, ksize=3)
    res = cv2.matchTemplate(np.abs(sx).astype(np.uint8),
                            np.abs(bx).astype(np.uint8),
                            cv2.TM_CCOEFF_NORMED)
    _mn, _mx, _ml, max_loc = cv2.minMaxLoc(res)
    return max_loc[0]


def find_gap(piece_png: bytes, bg_png: bytes) -> int:
    """返回缺口在背景图坐标系中的 x 偏移（px）。多法融合 + 中位数一致。"""
    piece = _decode(piece_png)
    back = _decode(bg_png, 0)
    piece_rgb = cv2.cvtColor(_clear_white(piece), cv2.COLOR_RGB2GRAY)  # 先裁白边
    piece_rgb = cv2.cvtColor(piece_rgb, cv2.COLOR_GRAY2RGB)
    back_rgb = cv2.cvtColor(back, cv2.COLOR_GRAY2RGB)

    pg = _gray(piece_rgb)
    bg = _gray(back_rgb)

    results = []
    for fn in (_canny_template, _masked_template, _sobel_template):
        try:
            results.append(fn(pg, bg))
        except cv2.error:
            pass  # 掩码形状等边界情况；两法可用即足够
    if not results:
        raise RuntimeError("全部缺口识别方法失败")
    med = statistics.median(results)
    kept = [r for r in results if abs(r - med) <= _OUTLIER_TOL]
    return int(round(statistics.median(kept or results)))
