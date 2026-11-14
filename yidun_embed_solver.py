#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yidun-embed-solver — 网易易盾 2.29+ 嵌入式混合滑块求解器。

原理（2026-11 实测）：
  易盾 SDK 升级到 2.29 后，`/api/v2/get` 返回 dt / ac(acToken) / ir(ir-sdk 启用)
  / resources 配置块而非题目本身；纯协议直打（自己构造 cb/data/轨迹加密）虽然
  /api/v2/check 仍可返回 result:true，但其签发的 validate 会被业务方服务端二次
  校验（verify）拒绝 —— validate 里编码了签发代际与指纹质量。

  本求解器不逆向加密链，而是让**当前真实 SDK 在真实浏览器环境**里完整运行：
    1. 本地最小页 + 官方 load.min.js → initNECaptcha（embed 模式）；
    2. playwright route 同时改写 HTTP Referer 头与 URL query 里的 referer 参数
       （易盾按 captchaId 校验域名白名单时两处都看）；
    3. 从 DOM 取背景图/拼图（2.29 的 get 已不含图片 URL），OpenCV Canny +
       matchTemplate 算缺口，按显示缩放比换算拖拽距离；
    4. CDP page.mouse 合成人类轨迹（速度剖面 + 过冲回拉 + 纵向抖动，
       isTrusted=true），SDK 页面内自行加密提交 check；
    5. onVerify 回调拿到 validate（新代际格式），写入输出文件供业务方消费。

  validate 是一次性 token，请拿到后立即使用。

用法：
    python yidun_embed_solver.py --captcha-id <ID> --referer <https://业务登录页> \
        [--out validate.txt] [--tries 3] [--port 8899] [--chrome <chrome路径>]

依赖：playwright（chromium）、opencv-python、numpy、requests
免责：仅限对目标站点拥有授权的安全测试与学习研究使用；请遵守目标站点条款与当地法律。
"""
import argparse
import json
import math
import os
import random
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from playwright.sync_api import sync_playwright

T0 = time.time()


def log(m):
    print("[%6.1fs] %s" % (time.time() - T0, m), flush=True)


def make_cap_html(captcha_id: str, width: int = 320) -> str:
    return """<!DOCTYPE html><html><head>
<script src="https://cstaticdun.126.net/load.min.js"></script>
</head><body style="background:#fff">
<div id="cap" style="width:%dpx"></div>
<script>
window.__VALIDATE = null;
initNECaptcha({
  captchaId: '%s',
  element: '#cap',
  mode: 'embed',
  width: '%dpx',
  onVerify: function(err, data) {
    if (!err && data && data.validate) {
      window.__VALIDATE = data.validate;
      console.log('VALIDATE_OK:' + data.validate);
    } else {
      console.log('VERIFY_ERR:' + JSON.stringify(err || {}));
    }
  }
});
</script>
</body></html>""" % (width, captcha_id, width)


class _Handler(BaseHTTPRequestHandler):
    html = ""

    def do_GET(self):
        body = self.html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def rewrite_url(u: str, referer: str) -> str:
    """把 URL query 里的 referer 参数改写为业务页（保持其余参数不动）。"""
    if "referer=" not in u:
        return u
    return re.sub(
        r"referer=[^&]*",
        "referer=" + referer.replace(":", "%3A").replace("/", "%2F"),
        u)


def human_drag(page, x0, y0, distance):
    """CDP 合成人类拖拽（isTrusted=true）：sin^0.7 速度剖面 + 开头犹豫 +
    末尾微调 + 2~5px 过冲回拉 + 纵向抖动。"""
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
    page.mouse.move(x0 + target - over, y0)
    time.sleep(random.uniform(0.08, 0.18))
    page.mouse.move(x0 + distance, y0)
    time.sleep(random.uniform(0.1, 0.25))
    page.mouse.up()


def find_gap(piece_png: bytes, bg_png: bytes) -> int:
    """OpenCV 缺口偏移：Canny 边缘 + matchTemplate（上游 SlideCrack.discern 思路的
    公开通用实现，此处为原创整理版）。"""
    import cv2
    import numpy as np

    def clear_white(img):
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

    img1 = cv2.cvtColor(clear_white(cv2.imdecode(np.frombuffer(piece_png, np.uint8), 1)),
                        cv2.COLOR_RGB2GRAY)
    slide = cv2.Canny(img1, 100, 200)
    back = cv2.Canny(cv2.imdecode(np.frombuffer(bg_png, np.uint8), 0), 100, 200)
    res = cv2.matchTemplate(cv2.cvtColor(slide, cv2.COLOR_GRAY2RGB),
                            cv2.cvtColor(back, cv2.COLOR_GRAY2RGB),
                            cv2.TM_CCOEFF_NORMED)
    _mn, _mx, _ml, max_loc = cv2.minMaxLoc(res)
    return max_loc[0]


def solve_once(captcha_id, referer, port, chrome_path, ua):
    """单次求解：起最小页 + playwright + 拖拽 + onVerify。返回 validate 或 ''。"""
    handler = type("H", (_Handler,), {"html": make_cap_html(captcha_id)})
    srv = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(
                executable_path=chrome_path or None, headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            ctx = b.new_context(user_agent=ua, viewport={"width": 1280, "height": 800})
            page = ctx.new_page()

            def on_console(m):
                if "VERIFY_ERR" in m.text:
                    log("[page] " + m.text[:150])

            page.on("console", on_console)

            def route_dun(route):
                req = route.request
                u = rewrite_url(req.url, referer)
                hdrs = dict(req.headers)
                hdrs["referer"] = referer
                if u != req.url:
                    route.continue_(url=u, headers=hdrs)
                else:
                    route.continue_(headers=hdrs)

            page.route("**://c.dun.163.com/**", route_dun)
            page.route("**://cstaticdun.126.net/**", route_dun)
            page.route("**://*.dun.163yun.com/**", route_dun)

            page.goto("http://127.0.0.1:%d/" % port, wait_until="domcontentloaded",
                      timeout=30000)
            page.wait_for_selector(".yidun_slider, .yidun--jigsaw, .yidun_panel",
                                   timeout=20000)
            time.sleep(1.5)

            bgel = page.wait_for_selector(".yidun_bg-img", timeout=15000)
            bgsrc = bgel.get_attribute("src")
            bgbox = bgel.bounding_box()
            jigel = page.query_selector(".yidun_jigsaw")
            jigsrc = jigel.get_attribute("src") if jigel else None
            if not (bgsrc and jigsrc):
                log("bg/jigsaw 图没找到（SDK DOM 结构可能升级）")
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
            b.close()
            return validate
    finally:
        srv.shutdown()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--captcha-id", required=True, help="易盾 captchaId（业务方分配）")
    ap.add_argument("--referer", required=True,
                    help="业务登录页 URL（域名白名单用，如 https://example.com/login）")
    ap.add_argument("--out", default="validate.txt", help="validate 输出文件")
    ap.add_argument("--tries", type=int, default=3, help="总尝试次数")
    ap.add_argument("--port", type=int, default=8899, help="本地最小页端口")
    ap.add_argument("--chrome", default=os.environ.get("PLAYWRIGHT_CHROME", ""),
                    help="chrome 可执行文件路径（缺省用 playwright 自带）")
    ap.add_argument("--ua", default=os.environ.get("YIDUN_UA", "") or
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")
    args = ap.parse_args()

    if os.path.exists(args.out):
        os.unlink(args.out)
    for attempt in range(1, args.tries + 1):
        log("=== 第 %d/%d 次 ===" % (attempt, args.tries))
        try:
            v = solve_once(args.captcha_id, args.referer, args.port, args.chrome, args.ua)
        except Exception as e:
            log("异常: %s: %s" % (type(e).__name__, str(e)[:150]))
            v = ""
        if v:
            with open(args.out, "w") as f:
                f.write(v)
            log("★ validate 取得（%d 字符）→ %s" % (len(v), args.out))
            print("VALIDATE_OK")
            return 0
        time.sleep(2)
    print("VALIDATE_FAIL")
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
