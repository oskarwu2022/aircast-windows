#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AirCast —— 局域网 AirPlay 投屏接收端（Windows）
iPhone / iPad 控制中心「屏幕镜像」即可发现并投屏到本机。

协议层由开源 UxPlay 负责，本程序是它的桌面外壳：
设备名、画质、全屏、PIN 码、音频、日志、二维码连接引导、防火墙一键配置。
"""

import ctypes
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tkinter import messagebox, ttk

APP_TITLE = "AirCast 局域网投屏"
GUIDE_PORT = 8787
UXPLAY_TCP_PORT = 7000  # 连接状态探测用

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
SETTINGS_PATH = os.path.join(APP_DIR, "aircast-settings.json")
DATA_DIR = os.path.join(APP_DIR, "data")

sys.path.insert(0, os.path.join(APP_DIR, "vendor"))
try:
    import qrcode
except Exception:  # pragma: no cover
    qrcode = None


# ----------------------------------------------------------------------------- 基础工具
def find_runtime():
    """返回 (bin_dir, gst_plugins_dir)；优先用打包自带的 runtime。"""
    candidates = [
        os.path.join(APP_DIR, "runtime"),
        os.path.join(os.path.dirname(APP_DIR), "runtime"),
    ]
    for base in candidates:
        exe = os.path.join(base, "uxplay.exe")
        if os.path.isfile(exe):
            plugins = os.path.join(base, "gstreamer-1.0")
            if not os.path.isdir(plugins):
                plugins = os.path.join(base, "lib", "gstreamer-1.0")
            return base, plugins
    # 开发模式回退到构建目录
    dev = r"C:\Users\oskarwu\AirCast\msys64\ucrt64"
    if os.path.isfile(os.path.join(dev, "bin", "uxplay.exe")):
        return os.path.join(dev, "bin"), os.path.join(dev, "lib", "gstreamer-1.0")
    if os.path.isfile(os.path.join(dev, "bin", "gst-launch-1.0.exe")):
        return os.path.join(dev, "bin"), os.path.join(dev, "lib", "gstreamer-1.0")
    return None, None


def local_ipv4():
    """挑选最像局域网的那块网卡 IP。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        cands = []
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            score = 0
            if ip.startswith("192.168.") or ip.startswith("10."):
                score += 2
            if ip.startswith("172."):
                score += 1
            cands.append((score, ip))
        if cands:
            cands.sort(reverse=True)
            return cands[0][1]
    except Exception:
        pass
    return "127.0.0.1"


def port_in_use(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def smart_decode(data):
    """中文 Windows 上子进程输出常是 GBK，Python 默认按 UTF-8 解码会报错。"""
    if isinstance(data, str):
        return data
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def established_on_port(port):
    """用 netstat 探测是否有客户端连上 UxPlay（不依赖日志缓冲）。"""
    try:
        r = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, timeout=5,
            creationflags=0x08000000,
        )
        out = smart_decode(r.stdout or b"")
    except Exception:
        return False
    needle = ":%d" % port
    for line in out.splitlines():
        if needle in line and ("ESTABLISHED" in line.upper()):
            return True
    return False


GUIDE_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>投屏到 {name}</title>
<style>
body{{margin:0;font-family:-apple-system,"PingFang SC",sans-serif;background:#0d1117;color:#e6edf3;
display:flex;min-height:100vh;align-items:center;justify-content:center}}
.card{{max-width:520px;padding:28px 24px;background:#161b22;border:1px solid #30363d;border-radius:18px}}
h1{{font-size:20px;margin:0 0 4px}}p.sub{{color:#8b949e;margin:0 0 22px;font-size:13px}}
ol{{padding-left:20px;line-height:2;font-size:15px}}
code{{background:#21262d;padding:2px 6px;border-radius:6px;font-size:13px}}
.badge{{display:inline-block;margin-top:18px;padding:8px 14px;border-radius:10px;background:#1f6feb22;
border:1px solid #1f6feb55;color:#58a6ff;font-size:13px}}
</style></head><body><div class="card">
<h1>投屏到 {name}</h1>
<p class="sub">已连上接收端 · 局域网内可用</p>
<ol>
<li>打开 <b>控制中心</b>（右上角下滑）</li>
<li>点 <b>屏幕镜像</b>（两个方框图标）</li>
<li>选择 <code>{name}</code></li>
</ol>
<div class="badge">设备地址 {ip}</div>
</div></body></html>
"""


class GuideServer:
    """给别人扫码看的小引导页。"""

    def __init__(self, port=GUIDE_PORT):
        self.port = port
        self.httpd = None
        self.thread = None

    def start(self, name, ip):
        html = GUIDE_HTML.format(name=name, ip=ip).encode("utf-8")

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)

            def log_message(self, *a):
                pass

        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), H)
        except OSError:
            return False
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None


# ----------------------------------------------------------------------------- 主界面
class AirCastApp:
    PRESETS = {
        "流畅 720p30": ("1280x720", 30),
        "高清 1080p30": ("1920x1080", 30),
        "高清 1080p60": ("1920x1080", 60),
        "超清 2K30": ("2560x1440", 30),
        "超清 4K30": ("3840x2160", 30),
    }

    def __init__(self, root):
        self.root = root
        self.proc = None
        self.log_queue = queue.Queue()
        self.guide = GuideServer()
        self.runtime_bin, self.gst_plugins = find_runtime()
        self.ip = local_ipv4()
        self.settings = self.load_settings()
        self.pin_current = None
        self.last_state = "idle"

        self.build_ui()
        self.apply_settings()
        self.root.after(120, self.pump_log)
        self.root.after(1500, self.poll_state)

    # ---------------------------------------------------------------- 配置
    def load_settings(self):
        defaults = {
            "name": "AirCast 客厅",
            "preset": "高清 1080p30",
            "fullscreen": False,
            "audio": True,
            "pin": False,
            "nohold": False,
            "lowlatency": False,
            "record": False,
        }
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
        return defaults

    def save_settings(self):
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def apply_settings(self):
        s = self.settings
        self.var_name.set(s.get("name", "AirCast"))
        self.var_preset.set(s.get("preset", "高清 1080p30"))
        self.var_full.set(bool(s.get("fullscreen")))
        self.var_audio.set(bool(s.get("audio", True)))
        self.var_pin.set(bool(s.get("pin")))
        self.var_nohold.set(bool(s.get("nohold")))
        self.var_lowlat.set(bool(s.get("lowlatency")))
        self.var_record.set(bool(s.get("record")))

    # ---------------------------------------------------------------- UI
    def build_ui(self):
        self.root.title(APP_TITLE)
        self.root.geometry("880x640")
        self.root.minsize(820, 600)
        self.root.configure(bg="#0d1117")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background="#0d1117", foreground="#e6edf3",
                        fieldbackground="#161b22", font=("Microsoft YaHei UI", 10))
        style.configure("TFrame", background="#0d1117")
        style.configure("Card.TFrame", background="#161b22")
        style.configure("TLabel", background="#0d1117", foreground="#e6edf3")
        style.configure("Card.TLabel", background="#161b22", foreground="#e6edf3")
        style.configure("Dim.TLabel", background="#161b22", foreground="#8b949e",
                        font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background="#0d1117", foreground="#ffffff",
                        font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("TCheckbutton", background="#161b22", foreground="#e6edf3")
        style.map("TCheckbutton", background=[("active", "#161b22")])
        style.configure("TButton", font=("Microsoft YaHei UI", 10))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("TCombobox", fieldbackground="#21262d", background="#21262d")

        # 头部
        head = ttk.Frame(self.root, padding=(18, 14, 18, 6))
        head.pack(fill="x")
        ttk.Label(head, text="AirCast  ·  局域网投屏接收端", style="Title.TLabel").pack(side="left")
        self.lbl_status = tk.Label(head, text="● 未启动", fg="#8b949e", bg="#0d1117",
                                   font=("Microsoft YaHei UI", 10, "bold"))
        self.lbl_status.pack(side="right")

        body = ttk.Frame(self.root, padding=(14, 6, 14, 6))
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, style="Card.TFrame", padding=14)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        def row(parent, label, widget_factory, pady=6):
            f = ttk.Frame(parent, style="Card.TFrame")
            f.pack(fill="x", pady=pady)
            ttk.Label(f, text=label, style="Dim.TLabel", width=12, anchor="w").pack(side="left")
            w = widget_factory(f)
            w.pack(side="left", fill="x", expand=True)
            return w

        self.var_name = tk.StringVar()
        row(left, "设备名称", lambda p: ttk.Entry(p, textvariable=self.var_name,
                                                 font=("Microsoft YaHei UI", 10)))

        self.var_preset = tk.StringVar()
        row(left, "画质", lambda p: ttk.Combobox(p, textvariable=self.var_preset, state="readonly",
                                               values=list(self.PRESETS.keys())))

        opts = ttk.Frame(left, style="Card.TFrame")
        opts.pack(fill="x", pady=(10, 2))
        self.var_full = tk.BooleanVar()
        self.var_audio = tk.BooleanVar()
        self.var_pin = tk.BooleanVar()
        self.var_nohold = tk.BooleanVar()
        self.var_lowlat = tk.BooleanVar()
        self.var_record = tk.BooleanVar()
        for text, var in (("全屏显示", self.var_full), ("传输声音", self.var_audio),
                          ("需要 PIN 码确认", self.var_pin), ("允许新设备抢占", self.var_nohold),
                          ("低延迟优先（弱化音画同步）", self.var_lowlat),
                          ("录制到 mp4", self.var_record)):
            ttk.Checkbutton(opts, text=text, variable=var).pack(anchor="w", pady=2)

        btns = ttk.Frame(left, style="Card.TFrame")
        btns.pack(fill="x", pady=(14, 0))
        self.btn_start = ttk.Button(btns, text="▶  启动接收端", style="Accent.TButton",
                                    command=self.start_server)
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_stop = ttk.Button(btns, text="■  停止", command=self.stop_server, state="disabled")
        self.btn_stop.pack(side="left")

        fw = ttk.Frame(left, style="Card.TFrame")
        fw.pack(fill="x", pady=(8, 0))
        ttk.Label(fw, text="首次使用需放行防火墙（会弹 UAC）",
                  style="Dim.TLabel").pack(side="left")
        ttk.Button(fw, text="配置防火墙", command=self.setup_firewall).pack(side="right")

        # 右侧：二维码 + 地址
        right = ttk.Frame(body, style="Card.TFrame", padding=14)
        right.pack(side="left", fill="both")
        ttk.Label(right, text="手机扫码看连接方法", style="Card.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        self.qr_canvas = tk.Canvas(right, width=210, height=210, bg="#ffffff",
                                   highlightthickness=0)
        self.qr_canvas.pack(pady=(10, 10))
        self.lbl_url = tk.Label(right, text="", fg="#58a6ff", bg="#161b22",
                                font=("Consolas", 10), wraplength=210)
        self.lbl_url.pack()
        ttk.Button(right, text="打开引导页", command=self.open_guide).pack(pady=(8, 0), fill="x")
        self.lbl_pin = tk.Label(right, text="", fg="#f0883e", bg="#161b22",
                                font=("Consolas", 13, "bold"))
        self.lbl_pin.pack(pady=(10, 0))

        # 日志
        logf = ttk.Frame(self.root, padding=(14, 0, 14, 12))
        logf.pack(fill="both", expand=False)
        self.log = tk.Text(logf, height=11, bg="#010409", fg="#c9d1d9", insertbackground="#c9d1d9",
                           font=("Consolas", 9), borderwidth=0, wrap="none")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set, state="disabled")

        self.render_qr(f"http://{self.ip}:{GUIDE_PORT}/")
        self.lbl_url.configure(text=f"http://{self.ip}:{GUIDE_PORT}/")
        self.append_log(f"本机局域网地址：{self.ip}")
        if not self.runtime_bin or not os.path.isfile(os.path.join(self.runtime_bin, "uxplay.exe")):
            self.append_log("[!] 未找到 uxplay.exe —— 请确认 runtime 目录完整。")

    def render_qr(self, data):
        c = self.qr_canvas
        c.delete("all")
        if qrcode is None:
            c.create_text(105, 105, text="(缺少 qrcode 模块)", fill="#333")
            return
        qr = qrcode.QRCode(border=2, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(data)
        qr.make(fit=True)
        m = qr.get_matrix()
        n = len(m)
        px = max(2, int(200 / n))
        off = (210 - n * px) // 2
        for y, rowv in enumerate(m):
            for x, v in enumerate(rowv):
                if v:
                    c.create_rectangle(off + x * px, off + y * px,
                                       off + x * px + px, off + y * px + px,
                                       fill="#000000", outline="")

    # ---------------------------------------------------------------- 日志
    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        # 控制行数
        if int(self.log.index("end-1c").split(".")[0]) > 1200:
            self.log.delete("1.0", "300.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def pump_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.append_log(line)
                self.scan_line(line)
        except queue.Empty:
            pass
        self.root.after(120, self.pump_log)

    def scan_line(self, line):
        m = re.search(r"PIN[^0-9]*([0-9]{4})", line, re.I)
        if m and "pin" in line.lower():
            self.pin_current = m.group(1)
            self.lbl_pin.configure(text="PIN: " + m.group(1))
        if re.search(r"connection request|accepted connection|starting mirroring", line, re.I):
            self.set_state("connected")
        if re.search(r"stop mirroring|connection closed|client .*disconnect|reset", line, re.I):
            self.set_state("idle")

    # ---------------------------------------------------------------- 状态
    def set_state(self, state):
        if state == self.last_state:
            return
        self.last_state = state
        if state == "running":
            self.lbl_status.configure(text="● 等待连接", fg="#58a6ff")
        elif state == "connected":
            self.lbl_status.configure(text="● 投屏中", fg="#3fb950")
        else:
            self.lbl_status.configure(text="● 未启动", fg="#8b949e")

    def poll_state(self):
        if self.proc is None:
            self.set_state("idle")
        else:
            if self.proc.poll() is not None:
                self.append_log(f"[i] uxplay 已退出（代码 {self.proc.returncode}）")
                self.proc = None
                self.set_state("idle")
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled")
            else:
                if established_on_port(UXPLAY_TCP_PORT):
                    self.set_state("connected")
                elif self.last_state != "idle":
                    self.set_state("running")
        self.root.after(2000, self.poll_state)

    # ---------------------------------------------------------------- 启动 / 停止
    def build_rc_lines(self):
        """UxPlay 在 Windows 上无法从命令行接收中文/UTF-8 参数，
        因此把选项写进 UTF-8 的启动配置文件，通过 $UXPLAYRC 传给 uxplay。"""
        res, fps = self.PRESETS.get(self.var_preset.get(), ("1920x1080", 30))
        name = (self.var_name.get().strip() or "AirCast").replace('"', "'")
        lines = [
            'n "%s"' % name,
            "s %s@%d" % (res, fps),
            'vs "d3d12videosink"',
            'as "wasapisink"',
            "p",  # 固定端口（便于防火墙/排错）
        ]
        if self.var_full.get():
            lines.append("fs")
        if not self.var_audio.get():
            lines.append("a")
        if self.var_pin.get():
            lines.append("pin")
        if self.var_nohold.get():
            lines.append("nohold")
        if self.var_lowlat.get():
            lines.append("vsync no")
        if self.var_record.get():
            os.makedirs(DATA_DIR, exist_ok=True)
            path = os.path.join(DATA_DIR, "record-%s.mp4" % time.strftime("%Y%m%d-%H%M%S"))
            lines.append('mp4 "%s"' % path)
        return lines

    def write_rc(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, "uxplayrc.txt")
        text = "\n".join(self.build_rc_lines()) + "\n"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path, text


    def child_env(self, rc_path=None):
        env = os.environ.copy()
        env["PATH"] = self.runtime_bin + os.pathsep + env.get("PATH", "")
        if self.gst_plugins and os.path.isdir(self.gst_plugins):
            env["GST_PLUGIN_PATH_1_0"] = self.gst_plugins
            env["GST_PLUGIN_SYSTEM_PATH_1_0"] = ""
        os.makedirs(DATA_DIR, exist_ok=True)
        env["GST_REGISTRY"] = os.path.join(DATA_DIR, "gst-registry.bin")
        scanner = os.path.join(self.runtime_bin, "gst-plugin-scanner.exe")
        if os.path.isfile(scanner):
            env["GST_PLUGIN_SCANNER"] = scanner
        if rc_path:
            env["UXPLAYRC"] = rc_path
        return env

    def start_server(self):
        if self.proc is not None:
            return
        if not self.runtime_bin or not os.path.isfile(os.path.join(self.runtime_bin, "uxplay.exe")):
            messagebox.showerror(APP_TITLE, "找不到 uxplay.exe，runtime 目录可能不完整。")
            return
        self.settings.update({
            "name": self.var_name.get().strip(),
            "preset": self.var_preset.get(),
            "fullscreen": self.var_full.get(),
            "audio": self.var_audio.get(),
            "pin": self.var_pin.get(),
            "nohold": self.var_nohold.get(),
            "lowlatency": self.var_lowlat.get(),
            "record": self.var_record.get(),
        })
        self.save_settings()

        self.ip = local_ipv4()
        self.guide.stop()
        if self.guide.start(self.var_name.get().strip() or "AirCast", self.ip):
            url = f"http://{self.ip}:{GUIDE_PORT}/"
            self.lbl_url.configure(text=url)
            self.render_qr(url)
        else:
            url = f"http://{self.ip}:{GUIDE_PORT}/ (端口被占用)"
            self.lbl_url.configure(text=url)
        self.pin_current = None
        self.lbl_pin.configure(text="")

        args = [os.path.join(self.runtime_bin, "uxplay.exe")]
        try:
            rc_path, rc_text = self.write_rc()
        except Exception as e:
            messagebox.showerror(APP_TITLE, "写入配置失败：%s" % e)
            return
        self.append_log("[i] 启动参数（UXPLAYRC）：")
        for ln in rc_text.strip().splitlines():
            self.append_log("    " + ln)
        try:
            self.proc = subprocess.Popen(
                args, cwd=self.runtime_bin, env=self.child_env(rc_path),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        except Exception as e:
            self.proc = None
            messagebox.showerror(APP_TITLE, "启动失败：%s" % e)
            return

        threading.Thread(target=self.reader, args=(self.proc,), daemon=True).start()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.set_state("running")
        self.append_log(f"[i] 已启动「{self.var_name.get()}」，iPhone/iPad 打开控制中心 → 屏幕镜像 → 选择该名称。")

    def reader(self, proc):
        """按字节读，逐行用 utf-8/gbk 智能解码（中文 Windows 上两种都会出现）。"""
        pending = b""
        try:
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    self.log_queue.put(smart_decode(line.rstrip(b"\r")))
            if pending:
                self.log_queue.put(smart_decode(pending))
        except Exception:
            pass
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass

    def stop_server(self):
        if self.proc is None:
            return
        try:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=0x08000000)
        except Exception:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None
        self.guide.stop()
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.set_state("idle")
        self.lbl_pin.configure(text="")
        self.append_log("[i] 已停止。")

    # ---------------------------------------------------------------- 附加动作
    def setup_firewall(self):
        candidates = [
            os.path.join(APP_DIR, "scripts", "allow-firewall.ps1"),
            os.path.join(APP_DIR, "allow-firewall.ps1"),
            os.path.join(os.path.dirname(APP_DIR), "scripts", "allow-firewall.ps1"),
        ]
        script = next((p for p in candidates if os.path.isfile(p)), None)
        if not script:
            messagebox.showwarning(APP_TITLE, "找不到 allow-firewall.ps1")
            return
        exe = os.path.join(self.runtime_bin, "uxplay.exe") if self.runtime_bin else ""
        params = '-NoProfile -ExecutionPolicy Bypass -File "%s"' % script
        if exe:
            params += ' -Exe "%s"' % exe
        try:
            # ShellExecuteW + "runas" 直接触发 UAC，避免多层引号转义出错
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "powershell.exe", params, os.path.dirname(script), 1)
            if rc > 32:
                self.append_log("[i] 已请求管理员权限，请在 UAC 弹窗中点「是」。")
            else:
                self.append_log("[!] 提权被取消或失败（代码 %s）。" % rc)
                messagebox.showwarning(APP_TITLE,
                                       "没能启动管理员脚本（代码 %s）。\n"
                                       "可以手动右键 scripts\\allow-firewall.ps1 → 使用 PowerShell 运行。" % rc)
        except Exception as e:
            messagebox.showerror(APP_TITLE, "无法提权：%s" % e)

    def open_guide(self):
        webbrowser.open(f"http://127.0.0.1:{GUIDE_PORT}/")

    def on_close(self):
        if self.proc is not None:
            if not messagebox.askokcancel(APP_TITLE, "接收端还在运行，确定退出？"):
                return
            self.stop_server()
        self.guide.stop()
        self.save_settings()
        self.root.destroy()


def selftest():
    """自检：不起界面，验证运行环境、启动/停止接收端。用于打包后排查问题。"""
    lines = []

    def out(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        lines.append(s)

    out("APP_DIR      =", APP_DIR)
    rt, plugins = find_runtime()
    out("runtime_bin  =", rt)
    out("gst_plugins  =", plugins)
    out("local ip     =", local_ipv4())
    if not rt:
        out("FAIL: 未找到 uxplay.exe")
        _write_selftest(lines)
        return 1
    root = tk.Tk()
    root.withdraw()
    app = AirCastApp(root)
    out("rc lines     =", app.build_rc_lines())
    app.start_server()
    for _ in range(60):
        root.update()
        time.sleep(0.1)
    alive = app.proc is not None and app.proc.poll() is None
    out("uxplay alive =", alive)
    out("--- log ---")
    out(app.log.get("1.0", "end").strip())
    app.stop_server()
    root.update()
    root.destroy()
    out("SELFTEST", "OK" if alive else "FAILED")
    _write_selftest(lines)
    return 0 if alive else 1


def _write_selftest(lines):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "selftest.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    root = tk.Tk()
    icon = os.path.join(APP_DIR, "aircast.ico")
    if os.path.isfile(icon):
        try:
            root.iconbitmap(icon)
        except Exception:
            pass
    app = AirCastApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    # airplay 参数：AirCast.exe --autostart 启动后自动开始接收
    if "--autostart" in sys.argv or "-autostart" in sys.argv:
        root.after(600, app.start_server)
    root.mainloop()


if __name__ == "__main__":
    main()
