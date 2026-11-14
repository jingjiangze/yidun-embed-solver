#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单次求解组装：最小页 → route → SDK 渲染 → DOM 取图 → 缺口 → 拖拽 → onVerify。"""
import time

from .captcha_page import CaptchaPageServer
from .gap_detector import find_gap
from .human_drag import human_drag
from .referer_route import install_routes


def solve_once(captcha_id, referer, port=8899, chrome_path=None, ua=None,
               width=320, on_log=print):
    """单次求解。返回 validate 字符串或 ''。

    on_log: 日志回调（默认 print；调用方可换成自己的 logger）。
    """
    T0 = time.time()

    def log(m):
        on_log("[%6.1fs] %s" % (time.time() - T0, m))

    ua = ua or ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")

    with CaptchaPageServer(captcha_id, port, width) as page_srv:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(
                executable_path=chrome_path or None, headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            try:
                ctx = b.new_context(user_agent=ua, viewport={"width": 1280, "height": 800})
                page = ctx.new_page()

                def on_console(m):
                    if "VERIFY_ERR" in m.text:
                        log("[page] " + m.text[:150])

                page.on("console", on_console)
                install_routes(page, referer)

                page.goto(page_srv.url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector(".yidun_slider, .yidun--jigsaw, .yidun_panel",
                                       timeout=20000)
                time.sleep(1.5)

                bgel = page.wait_for_selector(".yidun_bg-img", timeout=15000)
                bgsrc = bgel.get_attribute("src")
                bgbox = bgel.bounding_box()
                jigel = page.query_selector(".yidun_jigsaw")
                jigsrc = jigel.get_attribute("src") if jigel else None
                if not (bgsrc and jigsrc):
                    log("bg/jigsaw 图没找到（SDK DOM 结构可能升级，见 README 预警点）")
                    return ""
                log("bg 显示宽=%.0f" % bgbox["width"])

                def fetch_img(u):
                    resp = ctx.request.get(u, headers={"Referer": referer,
                                                       "User-Agent": ua}, timeout=15000)
                    return resp.body()

                bg = fetch_img("https:" + bgsrc if bgsrc.startswith("//") else bgsrc)
                front = fetch_img("https:" + jigsrc if jigsrc.startswith("//") else jigsrc)

                gap = find_gap(front, bg)
                import cv2
                import numpy as np
                bg_w = cv2.imdecode(np.frombuffer(bg, np.uint8), 0).shape[1]
                scale = bgbox["width"] / float(bg_w)
                drag = int(round((gap + 5) * scale))
                log("缺口 %dpx scale=%.3f → 拖拽 %dpx" % (gap, scale, drag))

                handle = (page.query_selector(".yidun_slider")
                          or page.query_selector(".yidun--jigsaw .yidun_slider"))
                if not handle:
                    log("没找到把手 .yidun_slider")
                    return ""
                box = handle.bounding_box()
                x0 = box["x"] + box["width"] / 2
                y0 = box["y"] + box["height"] / 2

                human_drag(page, x0, y0, drag)
                log("拖拽完成，等 onVerify…")

                validate = ""
                for _ in range(40):
                    v = page.evaluate("window.__VALIDATE")
                    if v:
                        validate = v
                        break
                    time.sleep(0.5)
                return validate
            finally:
                b.close()
