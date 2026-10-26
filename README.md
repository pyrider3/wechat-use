# wechat-use

让 Codex / Pi 在独立 Linux 桌面里操作官方微信：后台执行、按需查看、分区读状态，异常时返回完整截图。

这是组合现有开源工具的配置和 MCP 扩展，不是微信协议接口或腾讯官方产品。原仓库名为 `linux-background-wechat`；本机 MCP 仍叫 `wbox-wechat`，目录仍沿用 `wbox-mcp`，无需因此迁移账号数据。

## 这一版的变化

- **提速**：中文粘贴和截图合并为 `paste_and_capture`；核对后用 `send_prepared`，减少模型往返。
- **分区识别**：首次完整截图校准，之后只截取标题、输入框、最新消息等小区域。本地 OCR 后返回文字，区域图像相同时复用识别结果。
- **异常回图**：窗口尺寸/位置变化、额外窗口、菜单或稳定界面标记变化时，停止发送并返回新完整截图，由模型检查和重新校准。
- **专用快路径**：已打开的文件传输助手支持短文字自动核对与一次调用发送。草稿回读、发送记录和防重发保留。
- **查看器不暂停 AI**：可以边看边执行。即使查看器打开，AI 仍会继续；手动切换聊天或编辑草稿可能使检查失败，程序会重新观察，不盲目发送。
- **独立静音**：后台微信使用专用静音输出，其他应用的音量不变。

查看器只显示独立桌面，关闭窗口不退出微信。两个 AI 进程的单次动作仍互斥，但不提供整个任务的控制租约；不要让 Pi 与 Codex 同时操作同一个聊天。

## 安装

已验证环境：Arch Linux、Niri 26.04、官方微信 Linux 4.1.13、wbox-mcp 0.12.0。其他发行版和窗口缩放需要实测。

先安装系统依赖，Arch 示例：

```bash
sudo pacman -S git uv labwc grim xorg-server-xwayland xdotool \
  xorg-xprop xorg-setxkbmap wlr-randr xclip wl-clipboard wayvnc \
  tigervnc bubblewrap dbus libnotify tesseract libpulse
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
4. 短文字发给已打开的文件传输助手，可用 `send_partitioned_to_file_helper`；其他联系人和复杂格式保留两阶段流程。
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
- 快路径仅支持当前已打开的文件传输助手、80 字内单行文字，不会自动定位任意联系人。
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
