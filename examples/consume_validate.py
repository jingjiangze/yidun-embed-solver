#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""示例：拿到 validate 后由业务方消费的通用模式。

易盾 validate 的一次性消费流程（各业务方接口形状不同，但模式一致）：
  1. 业务方前端在滑块 onVerify 里拿到 validate，随业务请求提交；
  2. 业务方服务端拿 validate + captchaId + 自己的 secretId/secretKey
     调易盾「二次校验」API（verify）；
  3. verify 通过 → 业务请求放行。

本示例演示第 1 步的通用形态：把 validate 作为业务请求的一个字段提交。
请把 BASE/PATH/FIELDS 换成你自己的业务接口 —— 本文件不含任何真实业务。
"""
import argparse
import json
import sys

import requests


def consume(validate: str, api_url: str, extra: dict, timeout: int = 15):
    """把 validate 放进业务请求体提交（示例形状：JSON POST）。"""
    payload = {"validate": validate, **extra}
    r = requests.post(api_url, json=payload, timeout=timeout)
    print("HTTP %s -> %s" % (r.status_code, r.text[:200]))
    return r


def main():
    ap = argparse.ArgumentParser(description="validate 消费示例")
    ap.add_argument("--file", default="validate.txt", help="validate 文件（solver 的 --out）")
    ap.add_argument("--api-url", required=True, help="你的业务接口（校验 validate 的那个）")
    ap.add_argument("--extra", default="{}", help="额外业务字段 JSON，如 '{\"user\":\"x\"}'")
    args = ap.parse_args()

    validate = open(args.file, encoding="utf-8").read().strip()
    if not validate:
        print("validate 文件为空")
        return 1
    consume(validate, args.api_url, json.loads(args.extra))
    return 0


if __name__ == "__main__":
    sys.exit(main())
