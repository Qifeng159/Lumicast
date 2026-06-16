"""
渲染器模块 - VLC 内嵌播放 + 浏览器降级
"""
import subprocess
import threading
import logging
import os
import sys
import webbrowser
import json
import shutil
import urllib.request
from typing import Optional, Callable
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger("Lumicast.Renderer")


class MediaPlayer:
    """媒体播放器 — VLC 内嵌优先，降级到浏览器"""

    def __init__(self):
        self._vlc_instance = None
        self._vlc_player = None
        self._vlc_available = False
        self._video_widget = None
        self._playing = False
        self._current_uri: str = ""
        self._media_type: str = ""
        self._lock = threading.RLock()
        self._player_server: Optional["PlayerServer"] = None
        self._current_process: Optional[subprocess.Popen] = None
        self._volume = 50
        self._muted = False

        self.on_state_change: Optional[Callable[[str, str], None]] = None

        self._init_vlc()

    def _init_vlc(self):
        try:
            import vlc
            vlc_paths = [
                r"C:\Program Files\VideoLAN\VLC",
                r"C:\Program Files (x86)\VideoLAN\VLC",
            ]
            for p in vlc_paths:
                if os.path.isdir(p) and p not in os.environ.get("PATH", ""):
                    os.add_dll_directory(p)
            self._vlc_instance = vlc.Instance("--no-xlib --quiet")
            self._vlc_player = self._vlc_instance.media_player_new()
            self._vlc_available = True
            logger.info("VLC embedded player initialized")
        except Exception as e:
            logger.warning(f"VLC not available: {e}, will use browser fallback")
            self._vlc_available = False

    def set_video_widget(self, widget):
        """设置 tkinter 窗口句柄用于 VLC 内嵌渲染"""
        self._video_widget = widget
        if self._vlc_available and widget:
            try:
                hwnd = widget.winfo_id()
                self._vlc_player.set_hwnd(hwnd)
            except Exception as e:
                logger.error(f"Failed to set VLC hwnd: {e}")

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def current_uri(self) -> str:
        return self._current_uri

    @property
    def vlc_available(self) -> bool:
        return self._vlc_available

    def _ensure_player_server(self):
        if self._player_server is None:
            self._player_server = PlayerServer(self, port=9556)
            self._player_server.start()

    def play(self, uri: str):
        with self._lock:
            self.stop()
            self._current_uri = uri
            self._media_type = self._detect_media_type(uri)
            logger.info(f"Playing [{self._media_type}]: {uri}")

            if self._vlc_available and self._video_widget:
                # VLC 内嵌播放
                media = self._vlc_instance.media_new(uri)
                self._vlc_player.set_media(media)
                self._vlc_player.audio_set_volume(self._volume)
                self._vlc_player.audio_set_mute(self._muted)
                self._vlc_player.play()
                # Wait for playback to actually start
                def _wait_start():
                    import time
                    for _ in range(50):
                        time.sleep(0.1)
                        if self._vlc_player.is_playing():
                            break
                    with self._lock:
                        self._playing = self._vlc_player.is_playing()
                        if self.on_state_change:
                            self.on_state_change("PLAYING", uri)
                threading.Thread(target=_wait_start, daemon=True).start()
                return

            # 降级：浏览器
            self._open_browser_player(uri)
            self._playing = True
            if self.on_state_change:
                self.on_state_change("PLAYING", uri)

    def _open_browser_player(self, uri: str):
        self._ensure_player_server()
        player_url = f"http://127.0.0.1:9556/?uri={urllib.request.quote(uri, safe='')}"
        threading.Thread(
            target=lambda: webbrowser.open(player_url, new=1),
            daemon=True, name="Browser-Open"
        ).start()
        logger.info(f"Opening browser player for: {uri}")

    def _detect_media_type(self, uri: str) -> str:
        lower = uri.lower()
        video_exts = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts")
        audio_exts = (".mp3", ".aac", ".flac", ".wav", ".ogg", ".wma", ".m4a", ".opus")
        for ext in video_exts:
            if ext in lower:
                return "video"
        for ext in audio_exts:
            if ext in lower:
                return "audio"
        return "video"

    def pause(self):
        with self._lock:
            if self._vlc_available and self._vlc_player:
                self._vlc_player.pause()
            self._playing = False
            logger.info("Paused")
            if self.on_state_change:
                self.on_state_change("PAUSED_PLAYBACK", self._current_uri)

    def resume(self):
        with self._lock:
            if self._vlc_available and self._vlc_player:
                self._vlc_player.play()
            self._playing = True
            logger.info("Resumed")
            if self.on_state_change:
                self.on_state_change("PLAYING", self._current_uri)

    def stop(self):
        with self._lock:
            if self._vlc_available and self._vlc_player:
                self._vlc_player.stop()
            if self._current_process:
                try:
                    self._current_process.terminate()
                    self._current_process.wait(timeout=3)
                except Exception:
                    try:
                        self._current_process.kill()
                    except Exception:
                        pass
                self._current_process = None
            self._playing = False
            self._current_uri = ""
            self._media_type = ""
            logger.info("Stopped")
            if self.on_state_change:
                self.on_state_change("STOPPED", "")

    def set_volume(self, volume: int):
        self._volume = max(0, min(100, int(volume)))
        if self._vlc_available and self._vlc_player:
            self._vlc_player.audio_set_volume(self._volume)

    def set_mute(self, mute: bool):
        self._muted = bool(mute)
        if self._vlc_available and self._vlc_player:
            self._vlc_player.audio_set_mute(self._muted)

    def seek(self, position: float):
        """跳转到指定位置 (0.0 - 1.0)"""
        if self._vlc_available and self._vlc_player:
            self._vlc_player.set_position(position)

    def get_length(self) -> int:
        """获取媒体总时长（毫秒），-1 表示未知"""
        if self._vlc_available and self._vlc_player:
            return self._vlc_player.get_length()
        return -1

    def get_time(self) -> int:
        """获取当前播放时间（毫秒）"""
        if self._vlc_available and self._vlc_player:
            return self._vlc_player.get_time()
        return 0

    def get_position(self) -> float:
        """获取当前播放位置 (0.0 - 1.0)"""
        if self._vlc_available and self._vlc_player:
            return self._vlc_player.get_position()
        return 0.0

    def set_fullscreen(self, fullscreen: bool):
        """设置全屏模式"""
        if self._vlc_available and self._vlc_player:
            self._vlc_player.set_fullscreen(fullscreen)

    def get_fullscreen(self) -> bool:
        """获取全屏状态"""
        if self._vlc_available and self._vlc_player:
            return self._vlc_player.get_fullscreen()
        return False

    def cleanup(self):
        if self._vlc_player:
            self._vlc_player.stop()
            self._vlc_player.release()
        if self._vlc_instance:
            self._vlc_instance.release()
        if self._player_server:
            self._player_server.stop()


PLAYER_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lumicast Player</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #000; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
#player-container { flex: 1; display: flex; align-items: center; justify-content: center; }
video { max-width: 100%; max-height: 100%; outline: none; }
#status-bar {
  display: flex; align-items: center; justify-content: center; gap: 16px;
  padding: 8px 16px; background: #111; color: #aaa; font: 13px/1.5 system-ui, sans-serif;
}
#status { color: #4caf50; }
.ctrl-btn { background: #333; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.ctrl-btn:hover { background: #555; }
.hidden { display: none; }
#error-msg { color: #f44336; display: none; }
</style>
</head>
<body>
<div id="player-container">
  <video id="video" controls autoplay playsinline></video>
  <div id="error-msg"></div>
</div>
<div id="status-bar">
  <span id="status">等待投屏...</span>
  <button class="ctrl-btn" onclick="location.reload()">刷新</button>
</div>
<script>
let lastUri = '';
async function playUri(uri) {
  const v = document.getElementById('video'), s = document.getElementById('status'),
        e = document.getElementById('error-msg');
  if (!uri) { s.textContent = '等待投屏...'; e.style.display = 'none'; v.classList.add('hidden'); return; }
  if (uri === lastUri && !v.paused) return;
  lastUri = uri; s.textContent = '加载中...'; e.style.display = 'none'; v.classList.remove('hidden');
  try { v.src = uri; v.load(); await v.play(); s.textContent = '播放中'; s.style.color = '#4caf50'; }
  catch(err) { s.textContent = '播放失败'; s.style.color = '#f44336'; e.style.display = 'block'; e.textContent = '错误: ' + err.message; }
}
async function check() {
  try {
    const r = await fetch('/api/current_uri?_='+Date.now()), d = await r.json();
    if (d.uri && d.uri !== lastUri) playUri(d.uri);
    if (d.state === 'STOPPED' && lastUri) {
      const v = document.getElementById('video'); v.pause(); v.currentTime = 0;
      lastUri = ''; document.getElementById('status').textContent = '已停止'; document.getElementById('status').style.color = '#aaa';
    }
  } catch(e) {}
}
const p = new URLSearchParams(window.location.search), init = p.get('uri');
if (init) { playUri(decodeURIComponent(init)); setInterval(check, 3000); }
else setInterval(check, 2000);
check();
</script>
</body>
</html>"""


class PlayerAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/current_uri":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = json.dumps({
                "uri": self.server.media_player._current_uri or "",
                "state": "PLAYING" if self.server.media_player._playing else "STOPPED",
            })
            self.wfile.write(data.encode())
        elif self.path in ("/", "/index.html") or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PLAYER_HTML.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class PlayerServer:
    def __init__(self, media_player: "MediaPlayer", port: int = 9556):
        self.port = port
        self.media_player = media_player
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._httpd = HTTPServer(("127.0.0.1", self.port), PlayerAPIHandler)
        self._httpd.media_player = self.media_player
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="PlayerAPI")
        self._thread.start()
        logger.info(f"Player API started on http://127.0.0.1:{self.port}")

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None


class MediaFetcher:
    """HTTP 媒体流获取器"""
    def __init__(self, cache_dir: Optional[str] = None):
        import tempfile
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "lumicast_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch(self, uri: str, callback: Callable[[str], None]):
        def _fetch():
            try:
                req = urllib.request.Request(uri, headers={"User-Agent": "Lumicast/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    filename = "stream"
                    cd = resp.headers.get("Content-Disposition", "")
                    if "filename=" in cd:
                        filename = cd.split("filename=")[-1].strip('"')
                    ct = resp.headers.get("Content-Type", "")
                    ext_map = {"video/mp4": ".mp4", "video/webm": ".webm", "video/x-matroska": ".mkv",
                               "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "image/jpeg": ".jpg", "image/png": ".png"}
                    ext = next((e for c, e in ext_map.items() if c in ct), ".mp4")
                    cache_path = os.path.join(self.cache_dir, f"{filename}{ext}")
                    with open(cache_path, "wb") as f:
                        shutil.copyfileobj(resp, f)
                    logger.info(f"Media cached: {cache_path}")
                    callback(cache_path)
            except Exception as e:
                logger.error(f"Failed to fetch media: {e}")
                callback(uri)

        threading.Thread(target=_fetch, daemon=True, name="Media-Fetcher").start()