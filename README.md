# yidun-embed-solver

网易易盾（NetEase Yidun）**2.29+ 滑块验证码的完整嵌入式混合求解链路**。
不逆向加密链 —— 让官方 SDK 在真实浏览器环境里自己签发，只补齐它绕不过去的
两件事（referer 白名单、缺口拖拽），SDK 升级自动跟随，加密零维护。

> ⚠️ **免责声明**：本项目仅供对目标站点**拥有授权**的安全测试与学习研究使用。
> 请遵守目标站点条款与当地法律，使用者自负一切责任。作者不对任何滥用行为负责。

---

## 一、程序介绍

易盾 SDK 升级到 **2.29.14** 后，两类老方案先后失效（详见 [docs/ANALYSIS.md](docs/ANALYSIS.md)）：

| 旧路线 | 2.29 后的表现 |
|---|---|
| **纯协议直打**（逆向加密链自己构造 cb/data，如 tiny-jiu / CodeEmpower / U-Illll 路线） | `api/v2/check` 仍返回 `result:true`，**但 validate 被业务方服务端二次校验（verify）拒绝** —— validate 编码了签发代际与指纹质量 |
| **业务 SPA 页内拖拽**（Playwright/CDP 注入） | 事件风控拒绝合成事件流（拼图到位但 onVerify 不回调） |

本仓的混合路线：把官方 SDK（`cstaticdun.126.net/load.min.js`）放进本地最小页，
让它在真实浏览器环境完整运行（指纹/acToken/加密/check 全由 SDK 自己完成），
我们只做三件事：

1. **referer 白名单双改写** —— HTTP Referer 头 + URL query 的 `referer=` 参数
   两处同时改写（实测易盾两处都查，只改一处仍拒）；
2. **缺口识别与拖拽** —— DOM 取题图 → OpenCV 多法融合找缺口 → CDP 合成人类轨迹；
3. **validate 获取** —— SDK 页面内 onVerify 回调（`CN31_` 前缀新代际，~531 字符），
   落盘供业务方立即消费。

实测：单次求解 8~10 秒；成功率 **10/10**（每次新题一次过）；SDK 升级只需跟进
DOM 选择器，**加密链零维护**。

## 二、安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 三、用法

```bash
python yidun_embed_solver.py \
    --captcha-id <业务方分配的captchaId> \
    --referer https://<业务登录页>/login \
    --out validate.txt
```

validate 是**一次性 token**，拿到后立即由业务方消费（示例见
[examples/consume_validate.py](examples/consume_validate.py)）。

### 全部参数

| 参数 | 说明 |
|---|---|
| `--captcha-id` | 业务方在易盾申请的 captchaId |
| `--referer` | 业务登录页 URL（域名白名单基准，含路径更稳） |
| `--out` | validate 输出文件（默认 `validate.txt`） |
| `--tries` | 总尝试次数（默认 3，每次换新题） |
| `--port` | 本地最小页端口（默认 8899） |
| `--width` | 最小页滑块宽度 px（默认 320 = 原图零缩放） |
| `--chrome` | chrome 可执行路径（缺省用 playwright 自带 chromium） |
| `--ua` | User-Agent（默认 Chrome 138） |

## 四、项目结构

```
yidun_embed_solver.py    CLI 主入口
modules/
  captcha_page.py        本地最小页 + http.server（SDK 运行环境）
  referer_route.py       route 层：referer 双改写
  gap_detector.py        缺口识别：多法融合（Canny/带掩码模板/Sobel）+ 中位数一致
  human_drag.py          CDP 合成人类轨迹（isTrusted=true）
  solver.py              单次求解组装
docs/
  ANALYSIS.md            2.29 协演变实测分析（get/check/validate/referer/事件风控）
examples/
  consume_validate.py    validate 消费示例（通用模式）
```

各模块可单独调试（`python -c "from modules.gap_detector import find_gap"` …）。

## 五、原理与实测数据

完整实测分析（含 get 响应结构对比、check 参数表、validate 代际、IP 对照实验、
事件风控的页面环境依赖）见 **[docs/ANALYSIS.md](docs/ANALYSIS.md)**。

## 六、已知问题与升级预警点

SDK 再升级时按顺序查（都在 `modules/solver.py`）：

1. `load.min.js` 的 version 串（当前 2.29.14）
2. `v2/get` 响应结构（ac/ir 配置块是否演进）
3. DOM 选择器：`.yidun_bg-img` / `.yidun_jigsaw` / `.yidun_slider`
4. validate 格式（`CN31_` 前缀 + ~531 字符）
5. referer 白名单双处校验行为
6. `+5px` 拖拽校正系数（SDK 渲染偏移）

## 七、常见问题

**Q：为什么不逆向加密链自己发 check？**
逆向路线在 2.29 已被业务方 verify 拒（validate 编码了签发代际），且每次 SDK
升级都要重新逆向。嵌入式路线让 SDK 自己算，升级自动跟随 —— 长期维护成本低
一个量级。

**Q：validate 拿到后怎么用？**
它是易盾体系里的一次性通行证：你的业务请求带上 validate → 业务方服务端调
易盾 verify API 校验。参考 `examples/consume_validate.py`。

**Q：headless 被检测吗？**
本路线在 headless chromium + 最小页下实测稳定。若你的业务环境有额外指纹
校验，可尝试 `--chrome` 指定完整版 Chrome 并在 launch 参数里加你们的
stealth 配置。

**Q：与协议直打路线怎么选？**
研究加密细节看协议直打项目（tiny-jiu 等）；要**在生产里稳定消费 validate**
，选本仓 —— 关键差异是「谁签发」：协议直打自己签发（2.29 后被拒），本仓
SDK 签发（被接受）。

## 八、相关项目

| 项目 | 路线 | license |
|---|---|---|
| [tiny-jiu/Yidun-Slider-Analysis](https://github.com/tiny-jiu/Yidun-Slider-Analysis) | 纯协议直打 + 加密链分析 | 无 |
| [CodeEmpower/yidun-silder](https://github.com/CodeEmpower/yidun-silder) | v2.28.5 协议逆向 | 见其仓库 |
| [U-Illll/halfprotocol-regfarm](https://github.com/U-Illll/halfprotocol-regfarm) | 0 拖动协议直打 | 见其仓库 |
| [CXRunfree/Autovisor](https://github.com/CXRunfree/Autovisor) | 业务 SPA 页内拖拽（智慧树专用） | MIT |

## 许可

本项目代码以 **GPL-3.0-or-later** 授权，详见 [LICENSE](LICENSE)。

易盾 SDK 本体不在本仓库内、亦不再分发 —— 运行时由页面从易盾官方 CDN
（`cstaticdun.126.net`）自行加载，其版权归网易易盾所有。本仓库不含任何
第三方源码或素材。
