# Linux 后台微信工作台

让 Codex / Pi 在独立 Linux 桌面里操作官方微信，同时保留可随时打开的查看器，不占用日常桌面的键鼠焦点。

这是把现有开源工具组合起来的**配置与安装脚本**，不是微信协议接口，也不是腾讯官方产品。

## 功能

- **后台微信**：wbox-mcp + Labwc headless + Xwayland，独立用户目录和 D-Bus 会话。
- **按需查看**：应用菜单中的“后台微信”使用 TigerVNC 连接现有会话；关闭查看器不会退出微信。
- **手动接管**：查看器打开时，后续自动写操作返回 `manual_control_active`，仍允许截图和列出窗口。
- **中文发送**：独立剪贴板写入中文，再 Ctrl+V；发送前核对聊天对象和内容，发送后核对消息气泡。
- **独立静音**：关闭微信消息和通话铃声；专用静音音频输出与监听服务只识别隔离用户目录里的进程。
- **主桌面控制**：可另外注册 niri-computer-use，按其技能使用共享控制租约与停止键。

## 已验证与限制

本机验证环境为 Arch Linux、Niri 26.04、微信 Linux 4.1.13、wbox-mcp 0.12.0。已验证后台截图、中文粘贴、文件传输助手发送、查看器连接、手动接管保护，以及静音输出和其他应用音量保持不变。

安装器的跨机器部署尚未验证；不承诺其他发行版和微信版本直接可用。微信需要你自行扫码，原客户端的同账号登录状态可能受影响。

独立桌面不是完整安全沙箱：图形运行目录、网络和设备仍有共享。手动接管保护在请求入口检查，不会撤销已开始的动作；wbox 没有跨 Codex/Pi 的自动操作租约，避免两个代理同时操作。

当前会话的音频通过事件监听静音并转移，存在处理延迟；下一次微信启动时直接指定静音输出。未验证真实来电、所有音频后端或音频设备重启后的无缝切换，因此不能当作强制音频隔离。

## 安装

先安装系统依赖。Arch 示例（自行核对软件源）：

```bash
sudo pacman -S git uv labwc grim xdotool xorg-xprop xorg-setxkbmap \
  wlr-randr xclip wl-clipboard wayvnc tigervnc bubblewrap dbus libnotify
```

还需要可用的用户 systemd、PipeWire/PulseAudio（`pactl`），以及官方 Linux 微信位于 `/opt/wechat/wechat`。安装器不修改系统软件包，不下载微信，不复制在线账号数据，不自动登录。

```bash
python3 install.py --check
python3 install.py
```

默认安装在 `~/.local/share/wbox-mcp`。安装器检测到已有安装或相关配置时会停止，避免覆盖正在使用的环境。可通过 `--prefix` 指定空目录；`--no-register` 跳过代理配置。

安装时生成本机凭据，仓库中不包含密码、登录态、聊天记录、二维码或聊天截图。

主桌面控制另行安装 [niri-computer-use](https://github.com/ayagmar/niri-computer-use) 及其技能，配置停止键。安装器检测到该命令时会注册到已安装的 Codex/Pi，不代替其完整安装流程。

## 使用

1. 在 Codex 重连 MCP / 重启；Pi 执行 `/reload`，用 `/mcp` 检查。
2. 让代理读取 `background-wechat` 技能，调用 `wbox-wechat` 的 `launch`、`screenshot`，由你扫码。
3. 要查看或手动操作，应用菜单搜索“后台微信”。查看器目前要求后台会话已运行，不自动新建微信会话。
4. 关闭查看器后可恢复自动操作。若误最小化微信，在查看器中按 Alt+Tab。

例如：“用后台微信给文件传输助手发送：你好，这是后台中文测试。”

查看器关闭了与主桌面的剪贴板同步。手动中文输入尚未完整验证，自动中文粘贴已经验证。Pi 的 `/wechat` 聊天桥接是另一套功能，不等于个人微信界面控制。

## 查看器连接

仅监听 `127.0.0.1:15927`，使用 VncAuth，凭据文件权限为 0600。它没有传输加密，不能直接改成公网或局域网监听。原 remote-viewer 在本机触发认证崩溃，改用显式指定 VncAuth 的 TigerVNC。

## 依赖与许可

本仓库脚本采用 MIT 许可。第三方项目各自适用其原许可，没有将第三方源码或二进制打包到本仓库：

- [wbox-mcp](https://github.com/quazardous/wbox-mcp)：独立桌面 MCP，安装器固定一个已检查的提交。
- [niri-computer-use](https://github.com/ayagmar/niri-computer-use)：主桌面控制（可选）。
- [Labwc](https://labwc.github.io/)、[WayVNC](https://github.com/any1/wayvnc)、[TigerVNC](https://tigervnc.org/)：独立桌面与查看器。

## 卸载

先关闭查看器，并通过微信 MCP `stop` 停止独立会话。执行：

```bash
systemctl --user disable --now wbox-wechat-silent.service
systemctl --user stop wbox-wechat-viewer.service
codex mcp remove wbox-wechat  # 如已注册
pi mcp remove wbox-wechat    # 如已注册
```

随后按安装器的目标路径移除启动器、用户服务、桌面快捷方式、技能和配置，执行 `systemctl --user daemon-reload`。独立微信账号数据在安装目录的 `wechat-profile/`，保留还是删除由你决定。可用 `pactl list short modules` 找到专用 null-sink 模块并按模块 ID 卸载，不要卸载其他音频模块。
