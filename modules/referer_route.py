#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""playwright route 层：referer 白名单的双改写。

实测（2026-11）：易盾按 captchaId 校验域名白名单时，**HTTP Referer 头**与
**URL query 里的 referer 参数**两处都会被检查 —— 只改一处时请求仍被拒。
本模块对易盾全部域名（c.dun.163.com / cstaticdun.126.net / *.dun.163yun.com）
的请求统一改写。
"""
import re

DUN_HOST_GLOBS = [
    "**://c.dun.163.com/**",
    "**://cstaticdun.126.net/**",
    "**://*.dun.163yun.com/**",
    "**://*.dun.163.com/**",
]


def rewrite_url(u: str, referer: str) -> str:
    """把 URL query 里的 referer 参数改写为业务页（保持其余参数不动）。"""
    if "referer=" not in u:
        return u
    return re.sub(
        r"referer=[^&]*",
        "referer=" + referer.replace(":", "%3A").replace("/", "%2F"),
        u)


def make_route_handler(referer: str):
    """返回 playwright 的 route handler（含 HTTP 头 + URL 参数双改写）。"""

    def handler(route):
        req = route.request
        u = rewrite_url(req.url, referer)
        hdrs = dict(req.headers)
        hdrs["referer"] = referer
        if u != req.url:
            route.continue_(url=u, headers=hdrs)
        else:
            route.continue_(headers=hdrs)

    return handler


def install_routes(page, referer: str):
    """把双改写 route 挂到 page 上（覆盖易盾全部域名）。"""
    handler = make_route_handler(referer)
    for glob in DUN_HOST_GLOBS:
        page.route(glob, handler)
