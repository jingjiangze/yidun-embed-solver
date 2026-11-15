# 2.29 协演变与嵌入式混合路线 —— 实测分析

> 本文全部为本仓作者的一手实测数据（2026-11，production captchaId 场景），
> 无转载内容。供研究参考。

## 1. SDK 2.24 → 2.29.14 的请求链变化

### v2/get 响应结构

**旧版（2.24.0 时代）**——get 直接返回题目：

```json
{"data": {"token": "<hex32>", "bg": ["https://...jpg"], "front": ["https://...jpg"], ...}}
```

**新版（2.29.14）**——get 只返回配置，题目由 SDK 二次拉取：

```json
{"data": {
  "dt": "<enc>",
  "ac": {"enable": 1, "bid": "<captchaId>", "pn": "YD…", "token": "9ca17ae2…"},
  "ir": {"enable": 1, "apiServer": ["ir-sdk.dun.163.com", ...], "pn": "YD…", "token": "…"},
  "imageServer": ["necaptcha.nosdn.127.net", ...],
  "resources": ["/2.28.5/core-optimi.m25b40.v2.28.5.min.js"],
  "apiServer": ["c.dun.163.com", ...],
  ...
}}
```

要点：
- `ac`（acToken）与 `ir`（ir-sdk 页面侧凭据）同时启用 —— 纯协议直打必须自己复刻这两条凭据链，且**逐字节一致**（白盒 AES 链/CRC32/私有 base64），版本一升级就要重新逆向。
- 题目图不再出现在 get 响应里，需要从渲染后的 DOM（`.yidun_bg-img` / `.yidun_jigsaw`）取。

### validate 代际

| 签发方式 | validate 形态 | 业务方 verify |
|---|---|---|
| 2.24 协议直打（v2/check result:true） | 172 字符，base64 形态 | ❌ **拒** |
| 2.29 页面内 SDK onVerify | **531 字符，`CN31_` 前缀** | ✅ 过 |

## 2. 「check 通过但 verify 拒」的失效机制（实测复现）

对照组实验（production captchaId，type=2 滑块）：

| 签发方式 | 签发 IP | 消费 IP | check | 业务 verify |
|---|---|---|---|---|
| 2.24 协议直打 | 机房 | 机房（同一出口） | result:true | **-4 拒** |
| 2.24 协议直打 | 家宽 | 机房 | result:true | **-4 拒** |
| 2.29 页面 SDK | 机房（headless Chrome） | 机房 | （SDK 内部） | ✅ 过 |

结论：**verify 拒的不是 IP，是 validate 编码的签发代际/指纹质量**。check 接口
的 result:true 只代表轨迹数据自洽，不代表签发物会被业务方接受。

另附带观察：家宽（长期跑协议实验的出口）check 连续 14 次 `result:false`，
机房 IP 反而干净 —— 协议类实验会累积出口风控，实验请用干净 IP。

### 附：v3 协议直打同样被拒（2026-11-15 实测）

社区项目 tiny-jiu/Yidun-Slider-Analysis 走的是 **v3 协议**（getconf → v3/get →
v3/check，带 irToken/dt 参数，data 五字段 d/m/p/f/ext 自实现加密），在易盾
官方 demo 页可过验（本仓作者复现成功）。改造其对 production captchaId 后：

| 步骤 | 结果 |
|---|---|
| v3/get | ✅ 正常出题（token + 480×240 图） |
| v3/check | ✅ `result:true`，validate 172 字符 |
| **业务消费判别**（validate + 密码提交） | ❌ **`-4 滑动验证码校验失败`** |

⇒ **verify 层对「非页面内 SDK 签发」一律拒，与协议代际（v2/v3）无关**。
tiny-jiu 在 demo 页「能用」是因为 demo 无严格业务 verify；生产 captchaId 场景
下协议直打全线失效，validate 必须由页面内真实 SDK 签发（本仓路线）。

## 3. referer 白名单是「双处校验」

易盾按 captchaId 校验来源域名时，**同时检查**：
1. HTTP 请求的 `Referer` 头
2. 请求 URL query 里的 `referer=` 参数（SDK 填的是 `location.href`）

只改一处（例如只改头）时请求仍被拒。本仓 `modules/referer_route.py` 的
`install_routes` 同时改写两处，实测 get/check/图片加载全部放行。

## 4. 合成事件的可接受性依赖页面环境

同样的 CDP 合成鼠标事件流（isTrusted=true）+ 同等质量人类轨迹：
- **在业务 SPA 页内**（页面复杂、埋点多、SDK 参数来自页面 JS 上下文）→ 事件风控拒绝，拼图到位但 onVerify 不回调（token 空）
- **在干净最小页**（只加载 SDK + 一个 div）→ 稳定通过（本仓实测 10/10）

推论：事件风控有页面环境维度的评分；把 SDK 摘出来放到最小页是关键一步。

## 5. v2/check 请求参数（2.29 SDK 实际发送）

```
id=<captchaId>&token=<题token>&acToken=undefined&data=<SDK加密的轨迹+环境包>
&width=320&type=2&version=2.24.0&cb=<SDK生成>&extraData=&bf=0&runEnv=10
&sdkVersion=undefined&referer=&callback=__JSONP_xxx
```

注意 `data` 由页面内 SDK 加密（不可复刻，也不需要复刻——本路线根本不自己发
check，SDK 自己发）。

## 6. 一次性消费约束

validate 拿到后必须由业务方**立即**提交（实测同 token 第二次提交必拒）。
跨进程/跨机器传递时，请在同一分钟内完成消费。

## 7. 复现清单（researchers）

1. 最小页 + load.min.js（embed, width 与原始题图一致 320px 免缩放）
2. route 双改 referer（HTTP 头 + URL 参数，覆盖 c.dun.163.com / cstaticdun.126.net / *.dun.163yun.com）
3. DOM 拿 `.yidun_bg-img`/`.yidun_jigsaw` 的 src 下载
4. 多法融合找缺口（Canny+模板 / 带掩码模板 / Sobel，中位数一致），+5px 校正
5. CDP 人类轨迹（速度剖面 + 过冲回拉 + 纵向抖动，35~50 步，420~750ms）
6. onVerify → window.__VALIDATE → 落盘 → 立即消费
