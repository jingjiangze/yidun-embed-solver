#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网易易盾滑块求解器模块包（2.29+ 嵌入式混合路线）。

模块划分（各步骤可单独调试）：
  captcha_page   本地最小页 + http.server（官方 SDK 运行环境）
  referer_route  playwright route：HTTP Referer 头 + URL query referer 双改写
  gap_detector   缺口识别：多法融合（带掩码模板 / Canny / Sobel 相关）+ 中位数一致
  human_drag     CDP 合成人类轨迹（isTrusted=true）
  solver         单次求解组装（get→gap→drag→onVerify→validate）
"""
