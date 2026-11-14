#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CDP 合成人类拖拽轨迹（isTrusted=true）。

实测观察：同样的合成事件，在业务 SPA 页内会被易盾事件风控拒绝（拼图到位但
onVerify 不回调），在干净最小页 + 本轨迹下稳定通过。差异点推测在页面环境
复杂度与事件流属性，故本模块只保证轨迹质量（速度剖面/过冲/抖动），环境侧
由 solver 的最小页方案保证。
"""
import math
import random
import time


def human_drag(page, x0, y0, distance):
    """从 (x0,y0) 拖动 distance 像素。

    轨迹设计：
      * 速度剖面 v(t)=sin(pi*t^0.7)：先加速后减速（人类手部肌肉特征）
      * 开头 8% 犹豫（减速）、结尾 10% 微调（减速）
      * 60% 概率 2~5px 过冲再回拉（越位校正）
      * 中段纵向 ±2px 抖动、两端 ±1px（避免点成直线）
      * 每步 dt 在基准 ±40% 抖动（采样不均匀）
    """
    n = random.randint(35, 50)
    total_ms = random.uniform(420, 750)
    pts = []
    for i in range(n):
        t = i / n
        v = math.sin(math.pi * (t ** 0.7)) + random.uniform(-0.08, 0.08)
        if t < 0.08:
            v *= 0.3
        if t > 0.9:
            v *= 0.5
        pts.append(max(v, 0.01))
    sv = sum(pts)
    over = random.uniform(2, 5)
    target = distance + over

    page.mouse.move(x0, y0)
    time.sleep(random.uniform(0.1, 0.2))
    page.mouse.down()
    time.sleep(random.uniform(0.08, 0.15))

    acc = 0.0
    for i, v in enumerate(pts):
        acc += v / sv * target
        nx = x0 + acc
        ny = y0 + (random.uniform(-2, 2) if 0.2 < i / n < 0.9 else random.uniform(-1, 1))
        page.mouse.move(nx, ny)
        dt = total_ms / n * random.uniform(0.7, 1.4) / 1000
        time.sleep(max(dt, 0.004))

    time.sleep(random.uniform(0.05, 0.12))
    page.mouse.move(x0 + target - over, y0)   # 回拉
    time.sleep(random.uniform(0.08, 0.18))
    page.mouse.move(x0 + distance, y0)
    time.sleep(random.uniform(0.1, 0.25))
    page.mouse.up()
