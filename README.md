# yidun-embed-solver

网易易盾（NetEase Yidun）**2.29+ 滑块验证码的完整嵌入式混合求解链路**：从官方 SDK 加载、referer 白名单处理、缺口识别、人类轨迹合成到拿到一次性 `validate`，全流程单文件实现。

> 仅限对目标站点**拥有授权**的安全测试与学习研究使用。请遵守目标站点条款与当地法律，使用者自负责任。

## 为什么需要这个（2.29 之后的坑）

2026-11 实测：易盾 SDK 升级到 **2.29.14** 后，公开生态里的两类老方案先后失效：

| 旧路线 | 2.29 后的表现 |
|---|---|
| **纯协议直打**（逆向加密链，自己构造 `cb/data/轨迹`，如 tiny-jiu / CodeEmpower / U-Illll 路线） | `api/v2/check` 仍可返回 `result:true`，**但签发的 validate 会被业务方服务端二次校验（verify）拒绝** —— validate 里编码了签发代际与指纹质量。表现为 check 全过、业务接口报「验证码校验失败」 |
| **业务 SPA 页内拖拽**（Playwright/CDP 注入） | 事件风控拒绝合成事件流（拼图到位但 onVerify 不回调） |

2.29 的 `api/v2/get` 已不再直接返回题目，而是返回 `dt / ac(acToken) / ir(ir-sdk 启用) / resources` 配置块，题目由 SDK 二次拉取并渲染进 DOM；validate 改为 **`CN31_` 前缀的新代际格式**（约 531 字符）。

## 本方案：让真实 SDK 自己签发

**不逆向任何加密链** —— 把易盾官方 SDK（`cstaticdun.126.net/load.min.js`）放进一个本地最小页，让它在真实浏览器环境里完整运行：指纹/acToken/加密/check 全部由 SDK 自己完成，我们只补齐它绕不过去的两件事：

```
┌─ 本地最小页（http.server :8899）────────────────────────┐
│  load.min.js → initNECaptcha({captchaId, mode:'embed'})  │
└──────────────┬──────────────────────────────────────────┘
┌─ route 层 ────▼──────────────────────────────────────────┐
│ playwright route 拦截 c.dun.163.com / cstaticdun.126.net  │
│   → HTTP Referer 头 + URL query 的 referer 参数 双改写     │
│     （易盾按 captchaId 校验域名白名单时两处都看）           │
└──────────────┬──────────────────────────────────────────┘
┌─ 求解层 ──────▼──────────────────────────────────────────┐
│ DOM 取 .yidun_bg-img / .yidun_jigsaw（2.29 get 无图 URL）  │
│ → OpenCV Canny+matchTemplate 算缺口                       │
│ → 显示缩放比换算拖拽距离（width=320px 时 scale=1）         │
│ → CDP page.mouse 人类轨迹（sin^0.7 速度剖面+开头犹豫+      │
│   末尾微调+2~5px 过冲回拉+纵向抖动，isTrusted=true）       │
│ → SDK 页面内加密 check → onVerify 回调 validate           │
└──────────────┬──────────────────────────────────────────┘
               ▼ 一次性 validate（立即消费，落 --out 文件）
```

实测：单次求解约 8~10 秒，成功率 10/10（每次新题 1 次过）；SDK 后续升级时只需跟进 DOM 选择器，**加密链零维护**。

## 用法

```bash
pip install playwright opencv-python numpy requests
playwright install chromium

python yidun_embed_solver.py \
    --captcha-id <业务方分配的captchaId> \
    --referer https://<业务登录页>/login \
    --out validate.txt
```

拿到 `validate.txt` 后由业务调用方**立即消费**（易盾 validate 为一次性 token，时效极短）。

主要参数：

| 参数 | 说明 |
|---|---|
| `--captcha-id` | 业务方在易盾申请的 captchaId |
| `--referer` | 业务登录页 URL（域名白名单基准，含路径更稳） |
| `--out` | validate 输出文件路径 |
| `--tries` | 总尝试次数（默认 3，每次换新题） |
| `--port` | 本地最小页端口（默认 8899） |
| `--chrome` | chrome 可执行路径（缺省用 playwright 自带 chromium） |

## 已知预警点（SDK 再升级时先查这些）

1. `load.min.js` 的 `version` 串（当前 2.29.14）
2. `v2/get` 响应结构（ac/ir 块是否还在演进）
3. DOM 选择器：`.yidun_bg-img` / `.yidun_jigsaw` / `.yidun_slider`
4. validate 格式（`CN31_` 前缀 + 长度）
5. referer 白名单的双处校验行为

## 与其他开源方案的对比

| 项目 | 路线 | license | 2.29 后 |
|---|---|---|---|
| 本仓 | 嵌入式混合（真实 SDK 自签发） | GPL-3.0-or-later | ✅ 可用 |
| tiny-jiu/Yidun-Slider-Analysis | 纯协议直打（自复刻加密链） | 无 | ❌ verify 拒 |
| CodeEmpower/yidun-silder | v2.28.5 协议逆向 | 见其仓库 | ❌ 同上 |
| U-Illll/halfprotocol-regfarm | 0 拖动协议直打 | 见其仓库 | ❌ 同上 |
| CXRunfree/Autovisor | 业务 SPA 页内拖拽（智慧树专用） | MIT | ⚠️ 视页面环境 |

## 许可

本项目代码以 **GPL-3.0-or-later** 授权，详见 [LICENSE](LICENSE)。

易盾 SDK 本体不在本仓库内、亦不再分发 —— 运行时由页面从易盾官方 CDN（`cstaticdun.126.net`）自行加载，其版权归网易易盾所有。本仓库不含任何第三方源码或素材。
