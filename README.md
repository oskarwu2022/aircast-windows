# AirCast · 把 Windows 变成 AirPlay 接收端

一个开箱即用的局域网投屏接收端：**iPhone / iPad / Mac 在控制中心「屏幕镜像」里点一下，画面和声音就投到 Windows 电脑上**。
全局域网直连，不经过任何服务器，不需要联网账号。

界面外壳是本仓库的 Python 代码（MIT）；AirPlay 协议内核用开源项目 [UxPlay](https://github.com/FDH2/UxPlay)，
由本仓库的脚本从源码编译，并打包成免安装的便携目录。

```
iPhone ──AirPlay(局域网)──> AirCast.exe (GUI) ──> uxplay.exe ──> GStreamer ──> 画面/声音
```

## 特性

- 🖥️ **免装即用**：Release 里下载 zip 解压，双击 `AirCast.exe` 就能用（不需要装 Python、Bonjour、GStreamer）
- 🔊 **画面 + 声音**：D3D12 硬解 H.264，WASAPI 输出音频
- 🀄 **中文设备名**：绕过了 Windows 命令行 UTF-8 的坑（走 `UXPLAYRC` 配置文件传参）
- 🎛️ **常用开关都在界面上**：设备名、720p~4K、全屏、静音、PIN 码确认、允许新设备抢占、低延迟模式、录制 mp4、实时日志、连接状态灯
- 📱 **二维码引导**：界面右侧二维码指向本机小网页，别人扫码即可看到连接步骤（适合会议室/教室）
- 🛡️ **一键防火墙**：界面里点一下，UAC 提权后自动放行程序与端口、把网络切到「专用」
- 🧰 **自带自检**：`AirCast.exe --selftest` 输出环境与启动结果到 `data\selftest.log`

## 快速开始

1. 到 [Releases](../../releases) 下载 `AirCast-Windows-x64.zip`，解压到任意目录（**不要**只解压出 exe，`_internal\` 和 `runtime\` 都要在）
2. 双击 `AirCast.exe`；想启动即开始接收就用 `AirCast.exe --autostart`
3. 点 **▶ 启动接收端**（设备名可改成"客厅大屏"之类）
4. iPhone：控制中心 → **屏幕镜像** → 选中你的设备名
5. 停止：界面点 **■ 停止**，或在手机上点「停止镜像」

> 手机和电脑要在**同一个 Wi-Fi/局域网**；电脑网线 + 手机 Wi-Fi 连同一台路由器也完全可以。

## 界面选项

| 选项 | 对应 UxPlay 参数 | 说明 |
|---|---|---|
| 设备名称 | `-n` | 手机上显示的名字，支持中文/emoji |
| 画质 | `-s WxH@fps` | 720p30 / 1080p30 / 1080p60 / 2K30 / 4K30，只是"请求"，最终以手机为准 |
| 全屏显示 | `-fs` | 投屏窗口铺满屏；窗口内也可 `Alt+Enter` 切换 |
| 传输声音 | `-a`（关闭时） | 关掉则只投画面 |
| 需要 PIN 码确认 | `-pin` | 每次连接需在电脑上确认一次性 PIN |
| 允许新设备抢占 | `-nohold` | 默认当前设备独占 |
| 低延迟优先 | `-vsync no` | 牺牲音画同步换更低延迟 |
| 录制到 mp4 | `-mp4` | 存到 `data\record-*.mp4` |

固定端口（`-p`）：TCP 7000/7001/7100、UDP 6000/6001/7011，mDNS 走 UDP 5353。

## 从源码构建

需要 **Windows 10/11 x64**、[MSYS2](https://www.msys2.org/)（默认装在 `C:\msys64`）、Python 3.10+。

```powershell
git clone https://github.com/<you>/<repo>.git
cd <repo>
```

**① 装 MSYS2 依赖**（打开 "MSYS2 UCRT64" 终端）：

```bash
pacman -S --needed git \
  mingw-w64-ucrt-x86_64-{cmake,gcc,ninja,pkgconf,libplist,openssl} \
  mingw-w64-ucrt-x86_64-{gstreamer,gst-plugins-base,gst-libav,gst-plugins-good,gst-plugins-bad}
```

**② 编译 UxPlay 并收集运行环境**（同一个 UCRT64 终端，仓库目录下执行）：

```bash
bash build/build-uxplay.sh     # 拉取并编译 UxPlay 1.74 → .work/UxPlay/build/uxplay.exe
bash build/make-runtime.sh     # 把 exe + DLL 依赖 + GStreamer 插件收集成 runtime/
```

**③ 打包界面**（普通 PowerShell，仓库根目录）：

```powershell
powershell -ExecutionPolicy Bypass -File build\build-exe.ps1
# 产物：dist\AirCast\（可直接运行）  以及  AirCast-Windows-x64.zip
```

**④ 自检**

```powershell
& .\dist\AirCast\AirCast.exe --selftest
Get-Content .\dist\AirCast\data\selftest.log
```

也可以只跑界面（不打包，用系统 Python）：

```powershell
python app\aircast.py
```

## 目录结构

```
AirCast.exe            主程序（PyInstaller onedir；exe 与 _internal\、runtime\ 必须在一起）
_internal\             ← 打包生成
runtime\               ← 构建生成：uxplay.exe + GStreamer 全套（约 230 MB）
app\
  aircast.py           全部界面与进程管理逻辑（单文件，约 700 行）
  aircast.ico          图标
  vendor\qrcode\       纯 Python 二维码库（BSD）
scripts\
  allow-firewall.ps1   防火墙一键放行（自带提权）
build\
  build-uxplay.sh      编译 UxPlay
  make-runtime.sh      收集可移植运行环境
  build-exe.ps1        打包 + 组装 + 压缩
.github\workflows\build.yml    CI：自动编译、打包、发布
```

运行时数据：`data\uxplayrc.txt`（实际传给 uxplay 的参数）、`data\gst-registry.bin`（GStreamer 缓存）、
`data\record-*.mp4`（录像）、`aircast-settings.json`（界面设置）。

## 排错

**手机里看不到设备名**

1. 界面点 **配置防火墙**（或手动 `powershell -ExecutionPolicy Bypass -File scripts\allow-firewall.ps1`）
2. 网络必须是「专用」：设置 → 网络和 Internet → Wi-Fi → 属性 → 网络配置文件 → 专用
3. 关闭路由器的 **AP 隔离 / 客户端隔离**；手机别开 VPN、别连访客 Wi-Fi
4. 本机自检：`AirCast.exe --selftest`，看 `data\selftest.log`
5. 确认服务确实在广播（任意装了 Python 的机器）：
   ```powershell
   python -c "from zeroconf import Zeroconf,ServiceBrowser; import time;\
   z=Zeroconf(); ServiceBrowser(z,'_airplay._tcp.local.'); time.sleep(5); z.close()"
   ```

**能看到设备名但投上去黑屏/卡顿**

- 换视频输出：把 `data\uxplayrc.txt` 里的 `vs "d3d12videosink"` 改成 `vs "d3d11videosink"`
- 降低画质（1080p30），或勾选"低延迟优先"
- 关掉独显的"节能/混合模式"，确保核显或独显驱动正常（D3D12 硬解依赖它）
- 日志区会显示 GStreamer 的告警，可直接复制反馈

**提示找不到 uxplay.exe**

解压不完整：`runtime\uxplay.exe` 必须与 `AirCast.exe` 同级目录存在。

## 已知限制

- **DRM 内容**：Apple TV App 里带 FairPlay 保护的影片投不了（只有声音），这是所有开源接收端的共同限制
- **不支持 AirPlay 2 多房间音频**；单纯听 Apple Music（音频模式）可以
- **HLS 视频流**（YouTube App 类）默认未启用（UxPlay 的 `-hls` 选项未开启）
- **macOS 客户端**可以镜像，但体验不如 iOS；建议直接用内建「AirPlay 到 Mac」
- 电脑休眠会中断投屏，长时间演示请临时关掉睡眠

## 实现要点（给想改代码的人）

- **服务发现**：UxPlay 1.74 内置 mDNS 广播 `_airplay._tcp` / `_raop._tcp`（声明 `model=AppleTV3,2`），
  因此 Windows 上不需要安装 Bonjour。实测与系统里的 mDNSResponder 共存无冲突。
- **中文设备名**：Windows 下 CRT 会用 ANSI 代码页转换 argv，UTF-8 中文会变成乱码并被 UxPlay 拒绝。
  解决方式是把参数写进 UTF-8 的启动配置文件，通过环境变量 `UXPLAYRC` 传入（见 `write_rc()`）。
- **日志解码**：中文 Windows 上 `netstat`、GStreamer 的错误信息是 GBK，Python 3.11+ 默认按 UTF-8 解码会抛
  `UnicodeDecodeError`，因此子进程输出按字节读取，逐行 utf-8 → gbk 回退解码（见 `smart_decode()`）。
- **连接状态**：每 2 秒轮询 `netstat` 判断 7000 端口是否有 ESTABLISHED，并结合日志关键字切换"等待连接/投屏中"。

## 许可证

- 本仓库自有代码：**MIT**（见 [LICENSE](LICENSE)）
- 发行包内含的第三方二进制（UxPlay **GPLv3**、GStreamer **LGPL**、FFmpeg 等）：见 [THIRD-PARTY.md](THIRD-PARTY.md)

若要分发含二进制的 zip，请保留 THIRD-PARTY 声明并标注上游源码链接。
