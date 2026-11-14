#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地最小页 + http.server：易盾官方 SDK 的运行环境。

只负责把官方 load.min.js 加载进来并 initNECaptcha(embed 模式) 渲染滑块。
SDK 本体不在本仓库内 —— 由页面从易盾官方 CDN（cstaticdun.126.net）自行加载。
"""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def make_cap_html(captcha_id: str, width: int = 320) -> str:
    """生成最小验证页：width 与易盾原始题图（320）一致可省坐标缩放换算。"""
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


class CaptchaPageServer:
    """serve 最小页的本地 http.server（线程化，随 solve_once 生命周期启停）。"""

    def __init__(self, captcha_id: str, port: int = 8899, width: int = 320):
        handler = type("H", (BaseHTTPRequestHandler,),
                       {"html": make_cap_html(captcha_id, width)})
        self._srv = HTTPServer(("127.0.0.1", port), handler)
        self._port = port

    def start(self):
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def shutdown(self):
        self._srv.shutdown()

    @property
    def url(self):
        return "http://127.0.0.1:%d/" % self._port

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.shutdown()
