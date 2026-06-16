"""
DLNA HTTP 服务器 - 处理 UPnP 设备描述、SOAP 控制请求和媒体流
"""
import http.server
import socketserver
import threading
import logging
import re
from typing import Optional
from xml.etree import ElementTree as ET

from .ssdp import SSDPServer
from .dlna_service import DLNAServiceHandler

logger = logging.getLogger("Lumicast.HTTP")


class DLNARequestHandler(http.server.BaseHTTPRequestHandler):
    """处理所有 DLNA/UPnP HTTP 请求"""

    # 类属性，由外部设置
    ssdp_server: Optional[SSDPServer] = None
    dlna_service: Optional[DLNAServiceHandler] = None

    def log_message(self, format, *args):
        logger.debug(f"{self.client_address[0]} - {format % args}")

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/description.xml":
            self._serve_description()
        elif path.endswith(".xml"):
            self._serve_scpd(path)
        else:
            self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # 解析 SOAP Action
        soap_action = self.headers.get("SOAPACTION", "")
        soap_action = soap_action.strip('"')

        if "/control" in path:
            self._handle_control(path, soap_action, body)
        else:
            self.send_error(404)

    def do_SUBSCRIBE(self):
        """处理 UPnP 事件订阅"""
        self.send_response(200)
        self.send_header("SID", "uuid:lumicast-event-0")
        self.send_header("TIMEOUT", "Second-1800")
        self.end_headers()

    def do_UNSUBSCRIBE(self):
        self.send_response(200)
        self.end_headers()

    def _serve_description(self):
        """返回设备描述 XML"""
        if not self.ssdp_server:
            self.send_error(500)
            return

        xml = self.ssdp_server.get_device_xml()
        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(xml)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(xml.encode("utf-8"))

    def _serve_scpd(self, path: str):
        """返回 SCPD 服务描述 XML"""
        if not self.dlna_service:
            self.send_error(500)
            return

        # /AVTransport.xml -> AVTransport
        service_name = path.strip("/").replace(".xml", "")
        scpd = self.dlna_service.get_scpd(service_name)

        if not scpd:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(scpd)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(scpd.encode("utf-8"))

    def _handle_control(self, path: str, soap_action: str, body: bytes):
        """处理 SOAP 控制请求"""
        if not self.dlna_service:
            self.send_error(500)
            return

        # 解析 service type 和 action
        service_type = ""
        if "AVTransport" in soap_action:
            service_type = "urn:schemas-upnp-org:service:AVTransport:1"
        elif "RenderingControl" in soap_action:
            service_type = "urn:schemas-upnp-org:service:RenderingControl:1"
        elif "ConnectionManager" in soap_action:
            service_type = "urn:schemas-upnp-org:service:ConnectionManager:1"

        action = soap_action.split("#")[-1] if "#" in soap_action else soap_action

        # 解析 SOAP 请求体中的参数
        args = {}
        if body:
            try:
                # 提取命名空间前缀
                ns_match = re.search(r'xmlns:(\w+)="urn:schemas-upnp-org:service:', body.decode("utf-8", errors="ignore"))
                ns_prefix = ns_match.group(1) if ns_match else "u"

                root = ET.fromstring(body)
                # 找到 action body
                for elem in root.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if tag == action:
                        for child in elem:
                            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                            args[child_tag] = child.text or ""
                        break
            except ET.ParseError as e:
                logger.warning(f"SOAP parse error: {e}")
                self.send_error(400)
                return

        response = self.dlna_service.handle_action(service_type, action, args)

        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("EXT", "")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response.encode("utf-8"))

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, SUBSCRIBE, UNSUBSCRIBE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, SOAPACTION")
        self.end_headers()


class DLNAHTTPServer:
    """DLNA HTTP 服务器封装"""

    def __init__(
        self,
        ssdp_server: SSDPServer,
        dlna_service: DLNAServiceHandler,
        port: int = 8008,
    ):
        self.ssdp_server = ssdp_server
        self.dlna_service = dlna_service
        self.port = port
        self._httpd: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        DLNARequestHandler.ssdp_server = self.ssdp_server
        DLNARequestHandler.dlna_service = self.dlna_service

        self._httpd = socketserver.ThreadingTCPServer(
            ("0.0.0.0", self.port),
            DLNARequestHandler,
            bind_and_activate=False,
        )
        self._httpd.allow_reuse_address = True
        self._httpd.server_bind()
        self._httpd.server_activate()

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="DLNA-HTTP")
        self._thread.start()

        logger.info(f"DLNA HTTP server started on port {self.port}")

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        logger.info("DLNA HTTP server stopped")