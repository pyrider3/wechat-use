# wechat-use

让 Codex / Pi 在独立 Linux 桌面里操作官方微信：后台执行、按需查看、分区读状态，异常时返回完整截图。

这是组合现有开源工具的配置和 MCP 扩展，不是微信协议接口或腾讯官方产品。原仓库名为 `linux-background-wechat`；本机 MCP 仍叫 `wbox-wechat`，目录仍沿用 `wbox-mcp`，无需因此迁移账号数据。

## 这一版的变化

- **提速**：中文粘贴和截图合并为 `paste_and_capture`；核对后用 `send_prepared`，减少模型往返。
- **分区识别**：首次完整截图校准，之后只截取标题、输入框、最新消息等小区域。本地 OCR 后返回文字，区域图像相同时复用识别结果。
- **异常回图**：窗口尺寸/位置变化、额外窗口、菜单或稳定界面标记变化时，停止发送并返回新完整截图，由模型检查和重新校准。
- **消息 OCR 复核**：低置信气泡增加固定白底视图交叉检查，结果冲突仍返回截图；接收人核对与防重发保留。
- **专用快路径**：已打开的文件传输助手和普通联系人支持短文字自动核对与一次调用发送。草稿回读、发送记录和防重发保留。
- **查看器不暂停 AI**：可以边看边执行。即使查看器打开，AI 仍会继续；手动切换聊天或编辑草稿可能使检查失败，程序会重新观察，不盲目发送。
- **独立静音**：后台微信使用专用静音输出，其他应用的音量不变。

查看器只显示独立桌面，关闭窗口不退出微信。两个 AI 进程的单次动作仍互斥，但不提供整个任务的控制租约；不要让 Pi 与 Codex 同时操作同一个聊天。

## 安装

已验证环境：Arch Linux、Niri 26.04、官方微信 Linux 4.1.13、wbox-mcp 0.12.0。其他发行版和窗口缩放需要实测。

先安装系统依赖，Arch 示例：

```bash
sudo pacman -S git uv labwc grim xorg-server-xwayland xdotool \
  xorg-xprop xorg-setxkbmap wlr-randr xclip wl-clipboard wayvnc \
  tigervnc python-gobject gtk3 gtk-vnc bubblewrap dbus libnotify tesseract libpulse
```

需要用户级 systemd、可用的 PipeWire/PulseAudio、libX11，以及官方微信位于 `/opt/wechat/wechat`。安装器不安装系统包、不下载微信、不自动登录。

```bash
git clone https://github.com/pyrider3/wechat-use.git
cd wechat-use
python3 install.py --check
python3 install.py
```

安装器将：

1. 安装固定提交的 wbox-mcp 和 Pillow 到用户虚拟环境。
2. 下载固定版本的中文/英文 Tesseract 模型并校验 SHA-256，不把模型二进制打包进本仓库。
3. 安装查看器、静音服务、MCP 快捷工具及技能，生成本机 VNC 凭据。
4. 将 MCP 注册到检测到的 Codex / Pi；`--no-register` 可跳过。

默认安装目录 `~/.local/share/wbox-mcp`，可用 `--prefix` 指定空目录。首次安装遇到已有配置会停止。

主桌面控制另行安装 [niri-computer-use](https://github.com/ayagmar/niri-computer-use) 及其技能、停止键；检测到该命令时安装器会注册它。本项目不代替它的完整安装流程。

## 更新已有安装

```bash
git pull --ff-only
python3 install.py --check
python3 install.py --update
```

如果原来指定了目录，更新时传入相同的 `--prefix`。更新会备份并替换本项目管理的辅助脚本、技能和服务文件；**保留微信账号目录、现有 config.yaml、布局校准和查看器凭据**，不停止运行中的微信。

Pi 执行 `/reload`；Codex 重连 MCP 或重启，已运行的旧 MCP 进程不会自动换成新代码。无需为加载新工具退出微信。安装器流程已有隔离测试，全新机器的端到端部署仍待验证。

## 使用

1. 让代理读取 `background-wechat` 技能，调用 `wbox-wechat` 的 `launch` 和 `screenshot`，由你自行扫码。
2. 首次调用 `inspect_regions` 会要求校准并返回完整图。代理先检查正常窗口，再用图中的实际区域调用 `calibrate_regions`。安装器只提供 `auto-layout.example.json` 示例，**不把示例当成已验证布局**。
3. 正常时用 `inspect_regions` 读文字状态，只有区域像素变化才重新 OCR。低置信度文字为 `null`，不能当成可靠内容。
4. 短文字发给已打开的文件传输助手，可用 `send_partitioned_to_file_helper`；普通联系人核对并打开后可用 `send_partitioned_to_contact {recipient, text, operation_id}`；复杂格式保留两阶段流程。
5. 想看或手动操作时，在应用菜单搜索“后台微信”。关闭查看器，微信和 AI 继续运行。误最小化时在查看器内按 Alt+Tab。

例如：“用后台微信给文件传输助手发送：你好，这是后台中文测试。”

正常时仍会截取小区域，并不是永久复用任务开始时的旧截图。布局变化后先看新完整图，不能为了绕过异常反复校准。

## 新工具

| 工具 | 用途 |
|---|---|
| `paste_and_capture` | 点击已核对的输入框、粘贴中文，返回草稿截图和一次性 token；不发送 |
| `send_prepared` | 核对 token、聊天标题图像和草稿回读后，只发送一次并返回截图 |
| `calibrate_regions` | 从新完整图建立布局和固定标记；可提供基于该图推导的 layout |
| `inspect_regions` | 返回聊天标题、草稿 OCR、最新发出消息；异常时附完整图 |
| `send_to_file_helper` | 原始单调用 OCR 快路径，实验功能 |
| `forward_latest_two` | 两条短文字逐条转发，默认只准备并取消，带持久防重发 |
| `group_member_counts` | 搜索群名关键词、逐群核对成员人数，只读批量查询 |
| `send_elements_workflow` | 显式试验：文字元素清单选人，沿用原发送核对 |
| `inspect_ui_elements` | 可选只读试验：文字元素清单、坐标、置信度和画面编号 |
| `search_contacts_workflow` | 搜索精确备注、核对本地联系人、进入聊天并发送 |
| `search_open_contact` | 搜索并核对联系人，不发送消息 |
| `send_contacts_workflow` | 可见最近联系人的选人、等待切换、核对与发送合并批次 |
| `send_partitioned_to_contact` | 已打开普通联系人的分区快路径，必须提供精确 recipient |
| `send_to_contact` | 普通联系人自动核对，返回发送后完整截图 |
| `send_partitioned_to_file_helper` | 文件传输助手分区快路径，正常成功仅返回文字 |

参数、结果和不确定状态见 [工具说明](docs/tools.md)。

## 实测速度与准确性

| 场景 | 本机测量 |
|---|---:|
| 单独截图 | 47–53 ms |
| 原始分步准备与发送，包含模型往返 | 31.9 s |
| 两阶段发送，同段流程包含模型往返 | 8.7 s |
| 初次 OCR 单调用发送，仅工具执行 | 1.75 s |
| 分区发送，仅工具执行，两条短中文 | 1.31 / 1.37 s |
| 不变画面，命中区域缓存 | 0.10 s |
| 弹窗 / 几何变化，返回完整图 | 约 0.05 s |

这些不是同口径的完整 A/B 实验。两条分区测试均正确，不代表总体准确率；一条含标点文字的 OCR 曾认错字，程序返回 `SEND_UNCERTAIN`，没有重发。完整测量口径和覆盖范围见 [性能与验证](docs/performance.md)。

## 保留的检查与限制

- 发送前核对接收者、草稿和布局，发出后核对气泡、空输入框和失败标记。`ui_confirmed` 是界面证据，不是腾讯服务器投递回执。
- 快路径支持当前已核对并打开的普通联系人或文件传输助手、80 字内单行文字，不会自动定位任意联系人。普通联系人标题须与 recipient 大小写、空格完全一致；重名须先查看联系人信息消歧。
- 联系人列表 OCR 和部分中文标点仍可能不可靠；复杂窗口交回模型看图。
- 可检测 X11 可见弹窗和固定标记变化，**不能保证所有内嵌覆盖层都被检测到**。
- 查看器不暂停 AI。手动操作和 AI 共享独立桌面的鼠标键盘；布局、聊天或草稿改变时检查会拒绝继续。
- 独立桌面不是完整安全沙箱：网络、设备和图形运行目录仍有共享。微信登录需自行扫码，同账号的其他客户端可能被影响。
- 音频监听对当前进程的新流存在处理延迟；后续启动直接指定静音输出。未验证所有音频后端或真实来电，不能作为强制音频隔离。
- 查看器仅监听 `127.0.0.1:15927`，VncAuth 没有传输加密，不要直接开放到局域网或公网。查看器与主桌面的剪贴板同步关闭。
- Pi 的 `/wechat` 聊天桥接是另一套功能，不等于个人微信界面控制。

## 测试

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
```

测试使用临时目录和模拟后端，不连接你的微信或发送消息。覆盖图像缓存、弹窗/布局拒绝、草稿变化、一次性 token、持久化防重发、查看器不阻止 AI，以及更新时保留配置和账号数据。GitHub Actions 运行同一组测试。

## 目录与隐私

代码模板在 `templates/`，代理技能在 `skills/`。账号、凭据、截图、请求日志、计时日志、OCR 模型与本机校准文件不随仓库发布。

本机账号数据：`~/.local/share/wbox-mcp/wechat-profile/`；校准配置：`~/.config/wbox-mcp/wechat/`；备份：安装目录的 `backups/`。

## 依赖与许可

本项目脚本采用 MIT 许可。第三方项目各自适用其原许可，源码和二进制未打包：

- [wbox-mcp](https://github.com/quazardous/wbox-mcp)：独立桌面 MCP，安装固定提交。
- [niri-computer-use](https://github.com/ayagmar/niri-computer-use)：可选主桌面控制。
- [Labwc](https://labwc.github.io/)、[WayVNC](https://github.com/any1/wayvnc)、[TigerVNC](https://tigervnc.org/)：独立桌面与查看器。
- [Tesseract tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast)：OCR 模型，Apache-2.0。
- [Pillow](https://python-pillow.github.io/)：区域图像处理。

## 卸载

关闭查看器，通过微信 MCP `stop` 停止独立会话，然后执行：

```bash
systemctl --user disable --now wbox-wechat-silent.service
systemctl --user stop wbox-wechat-viewer.service
codex mcp remove wbox-wechat  # 如已注册
pi mcp remove wbox-wechat    # 如已注册
```

按安装器目标路径移除启动器、用户服务、快捷方式、技能和辅助代码，执行 `systemctl --user daemon-reload`。微信账号目录和校准数据是否删除由你决定。若需移除专用 null-sink，用 `pactl list short modules` 找到对应模块 ID 后卸载，不要卸载其他音频模块。

### 接收人看图兜底

普通联系人短文字发送在标题 OCR 失败时自动返回整屏、放大标题和一次性凭证，交给当前 Codex/Pi 模型看图。AI 确认身份后调用 `resume_visual_contact_send`，按原请求编号继续并处理批次剩余项；标题/窗口/布局变化则需重新看图。保留草稿核验和持久防重发，已提交但不确定的消息不会重发。看图不是后台另接视觉 API；需重连 MCP / Pi `/reload` 加载新工具和技能。当前不扩展转发选择器或发送后正文的视觉确认。

## 分辨率变化后恢复快速流程

屏幕尺寸或主窗口几何变化会返回 `layout_recalibration_required` 和新截图、actual_size。批次另外返回 `workflow_awaiting_calibration`、completed、pending_messages、resume_tool。当前 AI 按新图提交 `calibrate_regions {layout}`，再用 inspect_regions 验证，继续原批次与原请求编号；不调整用户分辨率，也不让整批长期退回逐步截图。新区域需按当前窗口推断，不能盲目缩放或携带未经核对的搜索/群/转发子布局。弹窗或未知遮挡仍需先解决；发送不确定仍禁止重发。恢复依赖宿主 AI 执行图像复核与后续调用，不是服务器内置视觉推断。

### 减少静态标记误报

新版去掉可能落入高窗口输入区的底部 H-72 标记，支持显式 `layout.anchor_regions`（2–6 条不重叠标题/消息/草稿的静态细分隔区域）。像素变化只读等待 120ms 复查一次，不修改基线、不降低阈值；持续变化返回 anchor_review_required、失败区域和差异。AI 先看图区分菜单遮挡与旧标记混入动态内容：前者处理遮挡，后者看图后更新静态标记。不会把所有变化都当成尺寸失效。旧校准须经过一次视觉复核，不能静默迁移。批次保留待处理条目和原编号。

## 自己打开后台微信

应用菜单搜索并点击“后台微信”，无需先找 AI：独立桌面已运行时直接打开查看器；未运行时按需启动 `wbox-wechat-session.service` 再显示。登录过期在查看器中自行扫码。关闭查看器只断开显示，不退出微信；再次打开仍是同一会话。重复点击不会启动多个查看器。此服务不设开机自动启动，不接管已经由其他 MCP 持有的会话；该类旧会话生命周期仍由原持有进程决定。

手动冷启动会话由用户服务保持，可在确需退出时自行执行 `systemctl --user stop wbox-wechat-session.service`，这会停止它所启动的独立桌面。正常查看不需要此命令。启动失败可查看 `journalctl --user -u wbox-wechat-session.service`。

## 查看器自动缩放

新版使用原生 Wayland GTK-VNC 查看器，画面等比例适应窗口，GTK 随所在显示器采用桌面缩放。查看器窗口变大、变小或移动到其他显示器，不会向后台发送改分辨率请求；WayVNC 同时启用 `--disable-resizing`。后台保持自己的固定分辨率和微信缩放，减少校准失效。主桌面/后台剪贴板仍不互通。运行时状态（是否连接、窗口大小、后端尺寸、GTK 缩放）保存在 `$XDG_RUNTIME_DIR/wbox-wechat-viewer-status.json`，不记录画面、密码或聊天。

依赖系统 Python 的 PyGObject、GTK 3 和 GTK-VNC 2.0（Arch 包：python-gobject、gtk3、gtk-vnc）。保留现有本地密码认证，不启用免密。此版本锁定与旧查看器一致的 VNC 密码认证，避开本机 neatvnc 的 ARD 握手崩溃。
