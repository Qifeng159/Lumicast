# Lumicast — 虚拟投屏设备

将 Windows PC 模拟为 DLNA 投屏目标，手机投屏软件可直接发现并投屏到本机播放。

## 功能

- DLNA MediaRenderer 完整协议（SSDP 发现 + SOAP 控制）
- VLC 内嵌播放器，支持视频进度条拖拽
- 一键全屏，Esc 退出
- 桌面 GUI 控制面板（播放/暂停/停止/音量/投屏 URL）
- REST API 外部控制接口

## 项目结构

```
Lumicast/
├── main.py              # 主入口 + GUI
├── icon.ico             # 应用图标
├── core/
│   ├── ssdp.py          # SSDP 设备发现广播
│   ├── dlna_service.py  # DLNA SOAP 协议（AVTransport / RenderingControl）
│   └── http_server.py   # HTTP 服务（设备描述 + SOAP 端点）
├── renderer/
│   └── player.py        # VLC 内嵌播放器 + 浏览器降级
└── api/
    └── rest_api.py      # RESTful API + Web 控制面板
```

## 启动方式

### 方式一：Python 启动（推荐）

依赖更可控，方便调试和自定义参数。

**前提条件：**

- Python 3.10+
- VLC 播放器（[videolan.org](https://www.videolan.org/)）

**步骤：**

```bash
# 1. 安装依赖
pip install python-vlc pillow

# 2. 启动（默认设备名取电脑名）
python main.py

# 3. 自定义名称
python main.py --name "客厅大屏"

# 4. 调试模式（查看完整日志）
python main.py --debug
```

**为什么推荐 Python 启动：**

- 启动速度快，无解压开销
- 命令行参数灵活（`--name` / `--http-port` / `--api-port` / `--debug`）
- 控制台可见实时日志，方便排查网络问题
- 修改代码后即时生效，无需重新打包

### 方式二：EXE 启动

适合分发或无需 Python 环境的场景，双击运行即可。

```bash
# 直接双击
dist/Lumicast.exe

# 或命令行带参数
dist/Lumicast.exe --name "卧室电视" --debug
```

> EXE 由 PyInstaller 打包，首次启动需解压临时文件，约 2-3 秒冷启动。

## 使用方式

### 手机投屏

1. 手机和电脑在同一局域网
2. 启动 Lumicast（GUI 窗口会显示本机 IP）
3. 在手机投屏 App 中搜索设备：
   - **B站**：播放视频 → 右上角 TV 图标 → 选择 Lumicast
   - **腾讯视频**：播放 → 投屏按钮 → 选择 Lumicast
   - **nPlayer**：播放 → 投屏 → 选择 Lumicast
   - **VLC Mobile**：播放 → 渲染器 → 选择 Lumicast

### 手动投屏

在 GUI 底部的投屏 URL 输入框中粘贴视频链接，点击"投屏"或按回车。

### REST API

```bash
# 查看状态
curl http://localhost:9555/api/status

# 投屏
curl -X POST http://localhost:9555/api/cast \
  -H "Content-Type: application/json" \
  -d '{"uri": "http://example.com/video.mp4", "title": "测试视频"}'

# 暂停 / 恢复 / 停止
curl -X POST http://localhost:9555/api/pause
curl -X POST http://localhost:9555/api/play -d '{"uri": "..."}'
curl -X POST http://localhost:9555/api/stop

# 设置音量
curl -X POST http://localhost:9555/api/volume -d '{"volume": 80}'
```

## 协议栈

| 层级 | 协议 | 端口 | 用途 |
|------|------|------|------|
| 设备发现 | SSDP (UPnP) | 1900 UDP | 多播广播 |
| 设备描述 | HTTP/XML | 8008 | DLNA DMR 描述 |
| 控制层 | SOAP/UPnP | 8008 | AVTransport / RenderingControl / ConnectionManager |
| API 层 | REST/JSON | 9555 | 外部应用扩展 |

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--name` | 电脑名 | 投屏设备名称 |
| `--http-port` | 8008 | DLNA HTTP 端口 |
| `--api-port` | 9555 | REST API 端口 |
| `--debug` | 关闭 | 开启 DEBUG 日志 |