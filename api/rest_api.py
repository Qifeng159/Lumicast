"""
REST API 模块 - 提供可扩展的 HTTP API 接口
使其他设备/应用能够通过 RESTful API 控制 Lumicast
"""
import json
import threading
import logging
import time
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger("Lumicast.API")

# 全局状态存储
api_state: Dict[str, Any] = {
    "version": "1.0.0",
    "device_name": "Lumicast",
    "protocol": "DLNA",
    "status": "running",
    "uptime": 0,
    "current_media": None,
    "playback_state": "STOPPED",
    "volume": 50,
    "mute": False,
    "connections": 0,
}

api_state_lock = threading.Lock()

# 外部回调
on_api_play: Optional[Callable[[str], None]] = None
on_api_pause: Optional[Callable[[], None]] = None
on_api_stop: Optional[Callable[[], None]] = None
on_api_set_volume: Optional[Callable[[int], None]] = None
on_api_set_mute: Optional[Callable[[bool], None]] = None


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Lumicast</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:20px}
.header{text-align:center;margin:20px 0 30px}
.header h1{font-size:28px;font-weight:700;color:#58a6ff;letter-spacing:-0.5px}
.header .ver{font-size:13px;color:#484f58;margin-top:4px}
.status-badge{display:inline-flex;align-items:center;gap:6px;background:#161b22;border:1px solid #30363d;border-radius:20px;padding:6px 16px;font-size:13px;margin-top:8px}
.status-badge .dot{width:8px;height:8px;border-radius:50%;background:#3fb950}
.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;width:100%;max-width:420px;margin-bottom:16px}
.card h2{font-size:16px;font-weight:600;color:#e6edf3;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.card h2 .icon{font-size:18px}
.media-state{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.media-state .kv{font-size:13px}
.media-state .kv .label{color:#8b949e;margin-bottom:2px}
.media-state .kv .val{color:#e6edf3;font-weight:500;word-break:break-all}
.volume-row{display:flex;align-items:center;gap:12px}
.volume-row input[type=range]{flex:1;height:6px;-webkit-appearance:none;appearance:none;background:#30363d;border-radius:3px;outline:none}
.volume-row input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;border-radius:50%;background:#58a6ff;cursor:pointer;border:2px solid #0d1117}
.volume-row .vol-num{font-size:18px;font-weight:700;color:#58a6ff;min-width:36px;text-align:right}
.btn-row{display:flex;gap:10px;margin-top:16px}
.btn{flex:1;padding:12px 0;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:all 0.15s;color:#fff}
.btn:active{transform:scale(0.96)}
.btn-play{background:#238636}
.btn-play:hover{background:#2ea043}
.btn-pause{background:#d29922}
.btn-pause:hover{background:#e2a826}
.btn-stop{background:#da3633}
.btn-stop:hover{background:#f85149}
.btn-mute{background:#30363d;color:#c9d1d9;flex:0.4}
.btn-mute:hover{background:#484f58}
.btn-mute.muted{background:#da3633}
.cast-form{display:flex;flex-direction:column;gap:10px}
.cast-form input{width:100%;padding:10px 14px;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e6edf3;font-size:14px;outline:none}
.cast-form input:focus{border-color:#58a6ff}
.cast-form .btn-cast{width:100%;padding:12px;background:#1f6feb;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer}
.cast-form .btn-cast:hover{background:#388bfd}
.api-link{font-size:12px;color:#484f58;text-align:center;margin-top:4px}
.api-link a{color:#58a6ff;text-decoration:none}
.toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#238636;color:#fff;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:500;z-index:999;opacity:0;transition:opacity 0.3s;pointer-events:none}
.toast.show{opacity:1}
.toast.err{background:#da3633}
</style>
</head>
<body>
<div class="toast" id="toast"></div>

<div class="header">
  <h1>Lumicast</h1>
  <div class="ver">v{{version}}</div>
  <div class="status-badge"><span class="dot"></span>{{status}}</div>
</div>

<div class="card" id="media-card">
  <h2><span class="icon">&#9654;</span>播放状态</h2>
  <div class="media-state">
    <div class="kv"><div class="label">状态</div><div class="val" id="playback">STOPPED</div></div>
    <div class="kv"><div class="label">音量</div><div class="val" id="vol-display">50%</div></div>
    <div class="kv" style="grid-column:1/-1"><div class="label">当前媒体</div><div class="val" id="current-media">无</div></div>
  </div>
  <div class="btn-row">
    <button class="btn btn-play" onclick="apiPost('/api/play',{uri:prompt('输入视频URL:')||''})">&#9654; 播放</button>
    <button class="btn btn-pause" onclick="apiPost('/api/pause')">&#10074;&#10074; 暂停</button>
    <button class="btn btn-stop" onclick="apiPost('/api/stop')">&#9632; 停止</button>
  </div>
</div>

<div class="card">
  <h2><span class="icon">&#9834;</span>音量控制</h2>
  <div class="volume-row">
    <input type="range" id="vol-slider" min="0" max="100" value="50" oninput="setVolume(this.value)">
    <span class="vol-num" id="vol-num">50</span>
  </div>
  <div class="btn-row">
    <button class="btn btn-mute" id="mute-btn" onclick="toggleMute()">&#128263;</button>
  </div>
</div>

<div class="card">
  <h2><span class="icon">&#127909;</span>手动投屏</h2>
  <div class="cast-form">
    <input type="text" id="cast-uri" placeholder="输入视频/音频 URL ...">
    <button class="btn-cast" onclick="doCast()">投屏播放</button>
  </div>
</div>

<div class="api-link"><a href="/api">API 文档</a></div>

<script>
let isMuted=false;
function apiPost(path,body={}){
  fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(r=>r.json()).then(d=>{if(d.error){toast(d.message,'err')}else{refresh();toast('OK')}})
  .catch(e=>toast(e.message,'err'));
}
function setVolume(v){
  apiPost('/api/volume',{volume:parseInt(v)});
  document.getElementById('vol-num').textContent=v;
  document.getElementById('vol-slider').value=v;
  document.getElementById('vol-display').textContent=v+'%';
}
function toggleMute(){
  isMuted=!isMuted;
  apiPost('/api/mute',{mute:isMuted});
  var b=document.getElementById('mute-btn');
  b.textContent=isMuted?'🔇':'🔉';
  b.className='btn btn-mute'+(isMuted?' muted':'');
}
function doCast(){
  var uri=document.getElementById('cast-uri').value.trim();
  if(!uri){toast('请输入URL','err');return}
  apiPost('/api/cast',{uri:uri});
}
function refresh(){
  fetch('/api/media').then(r=>r.json()).then(d=>{
    document.getElementById('playback').textContent=d.playback_state||'STOPPED';
    document.getElementById('vol-display').textContent=(d.volume||0)+'%';
    document.getElementById('current-media').textContent=d.current_media||'无';
    document.getElementById('vol-slider').value=d.volume||50;
    document.getElementById('vol-num').textContent=d.volume||50;
    isMuted=d.mute||false;
    var b=document.getElementById('mute-btn');
    b.textContent=isMuted?'🔇':'🔉';
    b.className='btn btn-mute'+(isMuted?' muted':'');
  });
}
function toast(msg,t){
  var el=document.getElementById('toast');
  el.textContent=msg;el.className='toast show'+(t==='err'?' err':'');
  setTimeout(function(){el.className='toast'},2000);
}
refresh();setInterval(refresh,3000);
</script>
</body>
</html>"""


class APIRequestHandler(BaseHTTPRequestHandler):
    """REST API 请求处理器"""

    def log_message(self, format, *args):
        logger.debug(f"API {self.client_address[0]} - {format % args}")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, val in CORS_HEADERS.items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error_json(self, message: str, status: int = 400):
        self._send_json({"error": True, "message": message}, status)

    def _read_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        for key, val in CORS_HEADERS.items():
            self.send_header(key, val)
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/" or path == "/dashboard":
            self._handle_dashboard()
        elif path == "/api":
            self._handle_root()
        elif path == "/api/status":
            self._handle_status()
        elif path == "/api/device":
            self._handle_device_info()
        elif path == "/api/media":
            self._handle_media_info()
        elif path == "/api/protocols":
            self._handle_protocols()
        elif path == "/api/health":
            self._send_json({"status": "ok", "timestamp": time.time()})
        elif path.startswith("/api/config/"):
            self._handle_get_config(path)
        else:
            self._send_error_json("Not Found", 404)

    def do_POST(self):
        body = self._read_body()
        path = self.path.split("?")[0]

        if path == "/api/play":
            self._handle_play(body)
        elif path == "/api/pause":
            self._handle_pause()
        elif path == "/api/stop":
            self._handle_stop()
        elif path == "/api/volume":
            self._handle_set_volume(body)
        elif path == "/api/mute":
            self._handle_set_mute(body)
        elif path == "/api/cast":
            self._handle_cast(body)
        elif path.startswith("/api/config/"):
            self._handle_set_config(path, body)
        else:
            self._send_error_json("Not Found", 404)

    # ── GET handlers ──
    def _handle_root(self):
        self._send_json({
            "name": "Lumicast API",
            "version": "1.0.0",
            "description": "Virtual Display Cast Device API",
            "endpoints": {
                "status": "GET  /api/status",
                "device": "GET  /api/device",
                "media":  "GET  /api/media",
                "protocols": "GET  /api/protocols",
                "play":   "POST /api/play",
                "pause":  "POST /api/pause",
                "stop":   "POST /api/stop",
                "volume": "POST /api/volume",
                "mute":   "POST /api/mute",
                "cast":   "POST /api/cast",
                "health": "GET  /api/health",
            },
        })

    def _handle_dashboard(self):
        html = DASHBOARD_HTML
        html = html.replace("{{device_name}}", api_state.get("device_name", "Lumicast"))
        html = html.replace("{{version}}", api_state.get("version", "1.0.0"))
        html = html.replace("{{status}}", api_state.get("status", "running"))
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_status(self):
        with api_state_lock:
            self._send_json(dict(api_state))

    def _handle_device_info(self):
        self._send_json({
            "device_name": api_state["device_name"],
            "protocol": api_state["protocol"],
            "version": api_state["version"],
            "capabilities": {
                "video": ["mp4", "mkv", "avi", "webm", "mov"],
                "audio": ["mp3", "aac", "flac", "wav", "ogg"],
                "image": ["jpg", "png", "gif", "bmp", "webp"],
                "max_resolution": "3840x2160",
                "hdr": False,
            },
        })

    def _handle_media_info(self):
        self._send_json({
            "current_media": api_state.get("current_media"),
            "playback_state": api_state.get("playback_state"),
            "volume": api_state.get("volume"),
            "mute": api_state.get("mute"),
        })

    def _handle_protocols(self):
        self._send_json({
            "supported": [
                {
                    "name": "DLNA/UPnP",
                    "version": "1.0",
                    "role": "MediaRenderer",
                    "status": "active",
                    "description": "Standard DLNA Digital Media Renderer",
                },
                {
                    "name": "Miracast",
                    "version": "1.0",
                    "role": "Sink",
                    "status": "planned",
                    "description": "Wi-Fi Display Sink (requires Wi-Fi hardware)",
                },
            ],
            "api": {
                "name": "Lumicast REST API",
                "version": "1.0",
                "protocol": "HTTP/JSON",
                "status": "active",
            },
        })

    def _handle_get_config(self, path: str):
        config_key = path.replace("/api/config/", "")
        # 可扩展的配置读取
        self._send_json({"key": config_key, "value": None})

    # ── POST handlers ──
    def _handle_play(self, body: dict):
        uri = body.get("uri", body.get("url", ""))
        if not uri:
            self._send_error_json("Missing 'uri' or 'url' parameter")
            return

        with api_state_lock:
            api_state["current_media"] = uri
            api_state["playback_state"] = "PLAYING"

        if on_api_play:
            on_api_play(uri)

        self._send_json({"success": True, "action": "play", "uri": uri})

    def _handle_pause(self):
        with api_state_lock:
            api_state["playback_state"] = "PAUSED_PLAYBACK"

        if on_api_pause:
            on_api_pause()

        self._send_json({"success": True, "action": "pause"})

    def _handle_stop(self):
        with api_state_lock:
            api_state["playback_state"] = "STOPPED"
            api_state["current_media"] = None

        if on_api_stop:
            on_api_stop()

        self._send_json({"success": True, "action": "stop"})

    def _handle_set_volume(self, body: dict):
        volume = body.get("volume", 50)
        volume = max(0, min(100, int(volume)))

        with api_state_lock:
            api_state["volume"] = volume

        if on_api_set_volume:
            on_api_set_volume(volume)

        self._send_json({"success": True, "action": "volume", "value": volume})

    def _handle_set_mute(self, body: dict):
        mute = body.get("mute", False)
        mute = bool(mute)

        with api_state_lock:
            api_state["mute"] = mute

        if on_api_set_mute:
            on_api_set_mute(mute)

        self._send_json({"success": True, "action": "mute", "value": mute})

    def _handle_cast(self, body: dict):
        """统一的投屏接口 - 外部应用可以直接通过此接口投屏"""
        uri = body.get("uri", body.get("url", ""))
        title = body.get("title", "")
        media_type = body.get("type", "video")

        if not uri:
            self._send_error_json("Missing 'uri' or 'url' parameter")
            return

        with api_state_lock:
            api_state["current_media"] = uri
            api_state["playback_state"] = "PLAYING"

        if on_api_play:
            on_api_play(uri)

        self._send_json({
            "success": True,
            "action": "cast",
            "uri": uri,
            "title": title,
            "type": media_type,
        })

    def _handle_set_config(self, path: str, body: dict):
        config_key = path.replace("/api/config/", "")
        value = body.get("value", body.get(config_key))
        # 可扩展的配置写入
        self._send_json({"success": True, "key": config_key, "value": value})


class RESTServer:
    """REST API 服务器"""

    def __init__(self, port: int = 9555):
        self.port = port
        self._httpd: Optional[ThreadingTCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def update_uptime(self, start_time: float):
        with api_state_lock:
            api_state["uptime"] = int(time.time() - start_time)

    def start(self):
        self._httpd = ThreadingTCPServer(("0.0.0.0", self.port), APIRequestHandler)
        self._httpd.allow_reuse_address = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="REST-API")
        self._thread.start()
        logger.info(f"REST API server started on port {self.port}")
        logger.info(f"Dashboard: http://localhost:{self.port}/")

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        logger.info("REST API server stopped")