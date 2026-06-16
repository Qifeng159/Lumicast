"""
Lumicast — 虚拟投屏设备
模拟标准 DLNA 协议设备，内嵌 VLC 播放器
"""
import sys
import os
import time
import socket
import json
import threading
import logging
import tkinter as tk
from tkinter import ttk
import webbrowser
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import SSDPServer, DLNAServiceHandler, DLNAHTTPServer
from renderer import MediaPlayer
from api import RESTServer, api_state
from api.rest_api import on_api_play, on_api_pause, on_api_stop, on_api_set_volume, on_api_set_mute

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("Lumicast")

# ── 设计系统 ────────────────────────────────────────────
BG         = "#0b0e14"
SURFACE    = "#141820"
SURFACE2   = "#1c212a"
BORDER     = "#2a3040"
ACCENT     = "#6366f1"
ACCENT2    = "#818cf8"
SUCCESS    = "#22c55e"
WARNING    = "#f59e0b"
DANGER     = "#ef4444"
INFO       = "#3b82f6"
TEXT       = "#e2e8f0"
TEXT2      = "#94a3b8"
TEXT3      = "#64748b"

FONT       = ("Segoe UI", 10)
FONT_SM    = ("Segoe UI", 9)
FONT_BOLD  = ("Segoe UI", 11, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")
FONT_MONO  = ("Consolas", 9)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lumicast_config.json")


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    return cfg


def save_config(name):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"device_name": name}, f)
    except Exception:
        pass


# ── 按钮工厂 ────────────────────────────────────────────
def _btn(parent, text, bg, fg="#fff", font=FONT_BOLD, padx=14, pady=8, command=None):
    """Label 伪按钮：hover 高亮 + 点击触发"""
    b = tk.Label(parent, text=text, bg=bg, fg=fg, font=font, padx=padx, pady=pady,
                 cursor="hand2")
    default = bg

    def enter(e):
        if str(b["state"]) != "disabled":
            r, g, bl = int(default[1:3], 16), int(default[3:5], 16), int(default[5:7], 16)
            r, g, bl = min(255, r + 30), min(255, g + 30), min(255, bl + 30)
            b.configure(bg=f"#{r:02x}{g:02x}{bl:02x}")

    def leave(e):
        b.configure(bg=default)

    b.bind("<Enter>", enter)
    b.bind("<Leave>", leave)
    if command:
        b.bind("<Button-1>", lambda e: command())
    return b


# ═══════════════════════════════════════════════════════════
#  核心服务
# ═══════════════════════════════════════════════════════════
class Lumicast:
    def __init__(self, device_name="Windows", http_port=8008, api_port=9555):
        self.device_name = device_name
        self.http_port = http_port
        self.api_port = api_port
        self._running = True
        self._current_uri = ""
        self._playback_state = "STOPPED"
        self._volume = 50
        self._muted = False

        self.ssdp = SSDPServer(friendly_name=device_name, http_port=http_port, api_port=api_port)
        self.dlna_service = DLNAServiceHandler()
        self.http_server = DLNAHTTPServer(self.ssdp, self.dlna_service, http_port)
        self.media_player = MediaPlayer()
        self.rest_api = RESTServer(api_port)

        self._bind_dlna_events()
        self._bind_api_events()
        api_state["device_name"] = device_name

    def _bind_dlna_events(self):
        self.dlna_service.on_set_uri = lambda uri, meta: self._on_uri(uri)
        self.dlna_service.on_play = self._on_play
        self.dlna_service.on_pause = self._on_pause
        self.dlna_service.on_stop = self._on_stop
        self.dlna_service.on_volume_change = self._on_vol
        self.dlna_service.on_mute_change = self._on_mute

    def _bind_api_events(self):
        import api.rest_api as mod
        mod.on_api_play = lambda uri: self._on_play(uri)
        mod.on_api_pause = self._on_pause
        mod.on_api_stop = self._on_stop
        mod.on_api_set_volume = self._on_vol
        mod.on_api_set_mute = self._on_mute

    def _on_uri(self, uri):
        self._current_uri = uri
        api_state["current_media"] = uri

    def _on_play(self, uri=None):
        if uri:
            self._current_uri = uri
            api_state["current_media"] = uri
        self._playback_state = "PLAYING"
        api_state["playback_state"] = "PLAYING"
        if self._current_uri:
            self.media_player.play(self._current_uri)

    def _on_pause(self):
        self._playback_state = "PAUSED_PLAYBACK"
        api_state["playback_state"] = "PAUSED_PLAYBACK"
        self.media_player.pause()

    def _on_stop(self):
        self._playback_state = "STOPPED"
        self._current_uri = ""
        api_state["playback_state"] = "STOPPED"
        api_state["current_media"] = None
        self.media_player.stop()

    def _on_vol(self, vol):
        self._volume = max(0, min(100, int(vol)))
        api_state["volume"] = self._volume
        self.media_player.set_volume(self._volume)

    def _on_mute(self, mute):
        self._muted = bool(mute)
        api_state["mute"] = self._muted
        self.media_player.set_mute(self._muted)

    def set_name(self, name):
        self.device_name = name
        self.ssdp.friendly_name = name
        api_state["device_name"] = name
        save_config(name)

    def start_services(self):
        self.http_server.start()
        time.sleep(0.3)
        self.ssdp.start()
        time.sleep(0.3)
        self.rest_api.start()

    def stop_services(self):
        self._running = False
        self.media_player.cleanup()
        self.rest_api.stop()
        self.ssdp.stop()
        self.http_server.stop()


# ═══════════════════════════════════════════════════════════
#  UI
# ═══════════════════════════════════════════════════════════
class LumicastUI:
    def __init__(self, vc: Lumicast):
        self.vc = vc
        self.root = tk.Tk()
        self.root.title("Lumicast")
        self.root.geometry("960x640")
        self.root.minsize(640, 400)
        self.root.configure(bg="#000")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._is_fullscreen = False
        self._seeking = False
        self._vlc_ready = False

        self._build()
        self.root.after(600, self._init_vlc)
        self._start_loops()

    # ── 构建 ──────────────────────────────────────────

    def _build(self):
        # ── 视频区：填满整个窗口 ──
        self.video_frame = tk.Frame(self.root, bg="#000")
        self.video_frame.pack(fill="both", expand=True)

        # 占位提示
        self.video_placeholder = tk.Label(
            self.video_frame,
            text="Lumicast\n等待投屏...",
            font=("Segoe UI", 18), fg="#333", bg="#000", justify="center")
        self.video_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # ── 顶部信息条（浮动） ──
        self._top_overlay = tk.Frame(self.video_frame, bg="#0a0a0a")
        self._top_overlay.place(x=0, y=0, relwidth=1.0, height=36)

        self._name_var = tk.StringVar(value=self.vc.device_name)
        self._name_entry = tk.Entry(self._top_overlay, textvariable=self._name_var,
                                    font=("Segoe UI", 10), width=16,
                                    bg="#0a0a0a", fg=TEXT, insertbackground=TEXT,
                                    relief="flat", bd=0, highlightthickness=0)
        self._name_entry.pack(side="left", padx=(12, 6), pady=6)
        self._name_entry.bind("<Return>", lambda e: self._apply_name())

        _btn(self._top_overlay, "↻", ACCENT, font=("Segoe UI", 10, "bold"),
             padx=8, pady=4, command=self._apply_name).pack(side="left", pady=6)

        tk.Label(self._top_overlay, text=f"  {self.vc.ssdp.local_ip}",
                 font=FONT_SM, fg=TEXT3, bg="#0a0a0a").pack(side="right", padx=(0, 12), pady=6)

        # ── 投屏 URL 浮条 ──
        self._cast_overlay = tk.Frame(self.video_frame, bg="#0a0a0a")
        self._cast_var = tk.StringVar()
        self._cast_entry = tk.Entry(self._cast_overlay, textvariable=self._cast_var,
                                    font=("Segoe UI", 10), bg="#0a0a0a", fg=TEXT2,
                                    insertbackground=TEXT, relief="flat", bd=0,
                                    highlightthickness=0)
        self._cast_entry.pack(side="left", fill="x", expand=True, padx=(12, 8), pady=8)
        self._cast_entry.bind("<Return>", lambda e: self._do_cast())
        self._cast_entry.bind("<FocusIn>", lambda e: self._cast_entry.configure(fg=TEXT))
        self._cast_entry.bind("<FocusOut>",
            lambda e: self._cast_entry.configure(fg=TEXT2 if not self._cast_var.get() else TEXT))

        _btn(self._cast_overlay, "投屏", ACCENT, font=FONT_SM, padx=12, pady=5,
             command=self._do_cast).pack(side="right", padx=(0, 12), pady=8)

        # ── 底部控制条 ──
        self._ctrl_bar = tk.Frame(self.video_frame, bg="#0d1117")
        self._ctrl_bar.pack(side="bottom", fill="x")

        # 进度条行
        prog_row = tk.Frame(self._ctrl_bar, bg="#0d1117")
        prog_row.pack(fill="x", padx=16, pady=(10, 0))

        self._time_cur = tk.Label(prog_row, text="00:00", font=FONT_MONO,
                                  fg=TEXT3, bg="#0d1117", width=5, anchor="w")
        self._time_cur.pack(side="left")

        self._progress = tk.Scale(prog_row, from_=0, to=1000, orient="horizontal",
                                  bg="#0d1117", fg=ACCENT2, troughcolor="#1c212a",
                                  highlightthickness=0, relief="flat", bd=0,
                                  showvalue=False, sliderlength=14, sliderrelief="flat")
        self._progress.set(0)
        self._progress.pack(side="left", fill="x", expand=True, padx=8)
        self._progress.bind("<ButtonPress-1>", lambda e: setattr(self, '_seeking', True))
        self._progress.bind("<ButtonRelease-1>", lambda e: self._seek_from_bar())

        self._time_end = tk.Label(prog_row, text="00:00", font=FONT_MONO,
                                  fg=TEXT3, bg="#0d1117", width=5, anchor="e")
        self._time_end.pack(side="right")

        # 按钮行
        btn_row = tk.Frame(self._ctrl_bar, bg="#0d1117")
        btn_row.pack(fill="x", padx=16, pady=(6, 10))

        left_btns = tk.Frame(btn_row, bg="#0d1117")
        left_btns.pack(side="left")

        self._btn_play = _btn(left_btns, "▶ 播放", SUCCESS, padx=14, command=self._do_play)
        self._btn_play.pack(side="left", padx=2)
        self._btn_pause = _btn(left_btns, "⏸ 暂停", WARNING, padx=14, command=self._do_pause)
        self._btn_pause.pack(side="left", padx=2)
        self._btn_stop = _btn(left_btns, "⏹ 停止", DANGER, padx=14, command=self._do_stop)
        self._btn_stop.pack(side="left", padx=2)

        # 分隔
        tk.Frame(left_btns, bg=BORDER, width=1).pack(side="left", fill="y", padx=8, pady=3)

        # 音量
        self._vol_label = tk.Label(left_btns, text="50", font=FONT_MONO, fg=TEXT2,
                                   bg="#0d1117", width=3, anchor="e")
        self._vol_label.pack(side="left", padx=(0, 4))

        self._vol_slider = tk.Scale(left_btns, from_=0, to=100, orient="horizontal",
                                    bg="#0d1117", fg=ACCENT2, troughcolor="#1c212a",
                                    highlightthickness=0, relief="flat", bd=0,
                                    showvalue=False, sliderlength=10, length=96,
                                    command=lambda v: self._set_volume(int(float(v))))
        self._vol_slider.set(50)
        self._vol_slider.pack(side="left")

        self._mute_btn = _btn(left_btns, "静音", SURFACE2, font=FONT_SM, padx=8, pady=5,
                              command=self._toggle_mute)
        self._mute_btn.pack(side="left", padx=(6, 0))

        right_btns = tk.Frame(btn_row, bg="#0d1117")
        right_btns.pack(side="right")

        self._btn_fs = _btn(right_btns, "⛶ 全屏", INFO, padx=14, command=self._toggle_fullscreen)
        self._btn_fs.pack(side="right")

    # ── VLC 绑定 ─────────────────────────────────────

    def _init_vlc(self):
        try:
            self.video_frame.update_idletasks()
            self.vc.media_player.set_video_widget(self.video_frame)
            if self.vc.media_player.vlc_available:
                self._vlc_ready = True
                self.video_placeholder.configure(text="VLC 就绪\n等待投屏...", fg="#333")
                logger.info("VLC bound to video frame")
            else:
                self.video_placeholder.configure(text="VLC 不可用\n将使用浏览器", fg="#c62828")
        except Exception as e:
            logger.error(f"VLC init failed: {e}")

    # ── 操作 ─────────────────────────────────────────

    def _apply_name(self):
        name = self._name_var.get().strip()
        if name and name != self.vc.device_name:
            self.vc.set_name(name)

    def _do_play(self):
        uri = self.vc._current_uri or self._cast_var.get().strip()
        if uri:
            self.vc._on_play(uri)
            self._hide_placeholder()

    def _do_pause(self):
        self.vc._on_pause()

    def _do_stop(self):
        self.vc._on_stop()

    def _set_volume(self, vol):
        self.vc._on_vol(vol)

    def _toggle_mute(self):
        self.vc._on_mute(not self.vc._muted)

    def _do_cast(self):
        uri = self._cast_var.get().strip()
        if uri:
            self.vc._on_play(uri)
            self._hide_placeholder()

    def _hide_placeholder(self):
        if self.video_placeholder.winfo_ismapped():
            self.video_placeholder.place_forget()

    def _show_placeholder(self):
        if not self.video_placeholder.winfo_ismapped():
            self.video_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ── 进度条跳转 ───────────────────────────────────

    def _seek_from_bar(self):
        pos = self._progress.get() / 1000.0
        self.vc.media_player.seek(pos)
        self._seeking = False

    @staticmethod
    def _fmt(ms):
        if ms < 0:
            return "--:--"
        s = ms // 1000
        return f"{s // 60:02d}:{s % 60:02d}"

    # ── 全屏 ─────────────────────────────────────────

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        self._is_fullscreen = True
        self._top_overlay.place_forget()
        self._cast_overlay.place_forget()
        self.root.attributes('-fullscreen', True)
        self.root.bind("<Escape>", lambda e: self._exit_fullscreen())
        self._btn_fs.configure(text="⛶ 退出全屏")

    def _exit_fullscreen(self, event=None):
        if not self._is_fullscreen:
            return
        self._is_fullscreen = False
        self.root.attributes('-fullscreen', False)
        self.root.unbind("<Escape>")
        self._top_overlay.place(x=0, y=0, relwidth=1.0, height=36)
        self._btn_fs.configure(text="⛶ 全屏")

    # ── 轮询 ─────────────────────────────────────────

    def _start_loops(self):
        def poll_state():
            if not self.vc._running:
                return
            try:
                s = self.vc._playback_state
                # 按钮高亮
                if s == "PLAYING":
                    self._btn_play.configure(bg="#16a34a")
                    self._btn_pause.configure(bg=WARNING)
                    self._btn_stop.configure(bg=DANGER)
                elif s == "PAUSED_PLAYBACK":
                    self._btn_play.configure(bg=SUCCESS)
                    self._btn_pause.configure(bg="#d97706")
                    self._btn_stop.configure(bg=DANGER)
                else:
                    self._btn_play.configure(bg=SUCCESS)
                    self._btn_pause.configure(bg=WARNING)
                    self._btn_stop.configure(bg=DANGER)
                    self._show_placeholder()

                # 音量
                self._vol_slider.set(self.vc._volume)
                self._vol_label.configure(text=str(self.vc._volume))
                muted = self.vc._muted
                self._mute_btn.configure(
                    text="取消静音" if muted else "静音",
                    bg=DANGER if muted else SURFACE2)
            except Exception:
                pass
            self.root.after(1000, poll_state)

        def poll_progress():
            if not self.vc._running:
                return
            try:
                if not self._seeking and self.vc._playback_state in ("PLAYING", "PAUSED_PLAYBACK"):
                    length = self.vc.media_player.get_length()
                    current = self.vc.media_player.get_time()
                    if length > 0:
                        pos = min(1000, max(0, int(current / length * 1000)))
                        self._progress.set(pos)
                        self._time_cur.configure(text=self._fmt(current))
                        self._time_end.configure(text=self._fmt(length))
            except Exception:
                pass
            self.root.after(500, poll_progress)

        poll_state()
        poll_progress()

    def _on_close(self):
        self.vc.stop_services()
        self.root.destroy()

    def run(self):
        self.vc.start_services()
        self.root.mainloop()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Lumicast")
    parser.add_argument("--name", default=None, help="设备名称")
    parser.add_argument("--http-port", type=int, default=8008)
    parser.add_argument("--api-port", type=int, default=9555)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    cfg = load_config()
    device_name = args.name or cfg.get("device_name") or socket.gethostname()

    vc = Lumicast(device_name=device_name, http_port=args.http_port, api_port=args.api_port)

    if not args.name and not cfg.get("device_name"):
        save_config(device_name)

    ui = LumicastUI(vc)
    ui.run()


if __name__ == "__main__":
    main()