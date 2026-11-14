#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yidun-embed-solver CLI 主入口（完整易盾验证链路）。

用法示例见 README.md。validate 为一次性 token，拿到后立即由业务方消费。
"""
import argparse
import os
import sys
import time

from modules.solver import solve_once

T0 = time.time()


def main():
    ap = argparse.ArgumentParser(
        prog="yidun-embed-solver",
        description="网易易盾 2.29+ 嵌入式混合滑块求解器（完整链路）")
    ap.add_argument("--captcha-id", required=True, help="易盾 captchaId（业务方分配）")
    ap.add_argument("--referer", required=True,
                    help="业务登录页 URL（域名白名单基准，含路径更稳）")
    ap.add_argument("--out", default="validate.txt", help="validate 输出文件")
    ap.add_argument("--tries", type=int, default=3, help="总尝试次数（每次换新题）")
    ap.add_argument("--port", type=int, default=8899, help="本地最小页端口")
    ap.add_argument("--width", type=int, default=320,
                    help="最小页滑块宽度 px（320=原图零缩放，其他宽度自动换算）")
    ap.add_argument("--chrome", default=os.environ.get("PLAYWRIGHT_CHROME", ""),
                    help="chrome 可执行路径（缺省用 playwright 自带 chromium）")
    ap.add_argument("--ua", default=os.environ.get("YIDUN_UA", "") or
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")
    args = ap.parse_args()

    def log(m):
        print(m, flush=True)

    if os.path.exists(args.out):
        os.unlink(args.out)
    for attempt in range(1, args.tries + 1):
        log("=== 第 %d/%d 次 ===" % (attempt, args.tries))
        try:
            v = solve_once(args.captcha_id, args.referer, args.port,
                           args.chrome or None, args.ua, args.width, on_log=log)
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
    sys.exit(main())
