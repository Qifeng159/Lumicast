"""
SSDP (Simple Service Discovery Protocol) 实现
负责在局域网内广播设备存在，让手机投屏软件发现本机
"""
import socket
import threading
import time
import uuid
import logging
from typing import Optional, Callable

logger = logging.getLogger("Lumicast.SSDP")

SSDP_MULTICAST_ADDR = "239.255.255.250"
SSDP_PORT = 1900

# DLNA 设备模板
DLNA_DEVICE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion>
    <major>1</major>
    <minor>0</minor>
  </specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
    <friendlyName>{friendly_name}</friendlyName>
    <manufacturer>Lumicast</manufacturer>
    <manufacturerURL>https://github.com/lumicast</manufacturerURL>
    <modelName>Lumicast DMR</modelName>
    <modelNumber>1.0</modelNumber>
    <modelURL>https://github.com/lumicast</modelURL>
    <serialNumber>{uuid}</serialNumber>
    <UDN>uuid:{uuid}</UDN>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
        <SCPDURL>/AVTransport.xml</SCPDURL>
        <controlURL>/AVTransport/control</controlURL>
        <eventSubURL>/AVTransport/event</eventSubURL>
      </service>
      <service>
        <serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:RenderingControl</serviceId>
        <SCPDURL>/RenderingControl.xml</SCPDURL>
        <controlURL>/RenderingControl/control</controlURL>
        <eventSubURL>/RenderingControl/event</eventSubURL>
      </service>
      <service>
        <serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:ConnectionManager</serviceId>
        <SCPDURL>/ConnectionManager.xml</SCPDURL>
        <controlURL>/ConnectionManager/control</controlURL>
        <eventSubURL>/ConnectionManager/event</eventSubURL>
      </service>
    </serviceList>
    <presentationURL>http://{host}:{api_port}/</presentationURL>
  </device>
</root>"""

NOTIFY_TEMPLATE = (
    "NOTIFY * HTTP/1.1\r\n"
    "HOST: {host}:{port}\r\n"
    "CACHE-CONTROL: max-age={max_age}\r\n"
    "LOCATION: http://{local_ip}:{http_port}/description.xml\r\n"
    "NT: {nt}\r\n"
    "NTS: {nts}\r\n"
    "SERVER: {server}\r\n"
    "USN: {usn}\r\n"
    "BOOTID.UPNP.ORG: {boot_id}\r\n"
    "CONFIGID.UPNP.ORG: 1\r\n"
    "\r\n"
)

SEARCH_RESPONSE_TEMPLATE = (
    "HTTP/1.1 200 OK\r\n"
    "CACHE-CONTROL: max-age={max_age}\r\n"
    "DATE: {date}\r\n"
    "EXT:\r\n"
    "LOCATION: http://{local_ip}:{http_port}/description.xml\r\n"
    "SERVER: {server}\r\n"
    "ST: {st}\r\n"
    "USN: {usn}\r\n"
    "BOOTID.UPNP.ORG: {boot_id}\r\n"
    "CONFIGID.UPNP.ORG: 1\r\n"
    "Content-Length: 0\r\n"
    "\r\n"
)


class SSDPServer:
    """SSDP 广播服务器 - 让手机能发现本机作为 DLNA 渲染器"""

    def __init__(
        self,
        friendly_name: str = "Lumicast",
        http_port: int = 8008,
        api_port: int = 9555,
        server_name: str = "Lumicast/1.0 UPnP/1.0",
        max_age: int = 1800,
    ):
        self.friendly_name = friendly_name
        self.http_port = http_port
        self.api_port = api_port
        self.server_name = server_name
        self.max_age = max_age
        self.device_uuid = str(uuid.uuid4())
        self.boot_id = str(int(time.time()))
        self._running = False
        self._local_ip: Optional[str] = None
        self._sock: Optional[socket.socket] = None
        self._notify_thread: Optional[threading.Thread] = None
        self._listen_thread: Optional[threading.Thread] = None
        self.on_discovery_request: Optional[Callable] = None

    @property
    def local_ip(self) -> str:
        if not self._local_ip:
            self._local_ip = self._get_local_ip()
        return self._local_ip

    def _get_local_ip(self) -> str:
        """获取本机局域网 IP"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_device_xml(self) -> str:
        """生成 DLNA 设备描述 XML"""
        return DLNA_DEVICE_TEMPLATE.format(
            friendly_name=self.friendly_name,
            uuid=self.device_uuid,
            host=self.local_ip,
            api_port=self.api_port,
            http_port=self.http_port,
        )

    def _build_notify(self, nts: str, nt: str, usn: str) -> bytes:
        msg = NOTIFY_TEMPLATE.format(
            host=SSDP_MULTICAST_ADDR,
            port=SSDP_PORT,
            max_age=self.max_age,
            local_ip=self.local_ip,
            http_port=self.http_port,
            nt=nt,
            nts=nts,
            server=self.server_name,
            usn=usn,
            boot_id=self.boot_id,
        )
        return msg.encode("utf-8")

    def _send_alive(self):
        """发送 ssdp:alive 广播"""
        root_udn = f"uuid:{self.device_uuid}"
        device_usn = f"{root_udn}::urn:schemas-upnp-org:device:MediaRenderer:1"

        messages = [
            self._build_notify("ssdp:alive", "upnp:rootdevice", root_udn),
            self._build_notify("ssdp:alive", root_udn, root_udn),
            self._build_notify("ssdp:alive", "urn:schemas-upnp-org:device:MediaRenderer:1", device_usn),
            self._build_notify("ssdp:alive", "urn:schemas-upnp-org:service:AVTransport:1", root_udn),
            self._build_notify("ssdp:alive", "urn:schemas-upnp-org:service:RenderingControl:1", root_udn),
            self._build_notify("ssdp:alive", "urn:schemas-upnp-org:service:ConnectionManager:1", root_udn),
        ]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        # 绑定到本机 LAN IP 以确保从正确的网卡发出
        sock.bind((self.local_ip, 0))
        for msg in messages:
            try:
                sock.sendto(msg, (SSDP_MULTICAST_ADDR, SSDP_PORT))
            except Exception as e:
                logger.warning(f"SSDP alive send failed: {e}")
        sock.close()
        logger.info(f"SSDP alive sent via {self.local_ip}")

    def _send_byebye(self):
        """发送 ssdp:byebye 广播 - 告知设备下线"""
        root_udn = f"uuid:{self.device_uuid}"
        messages = [
            self._build_notify("ssdp:byebye", "upnp:rootdevice", root_udn),
            self._build_notify("ssdp:byebye", root_udn, root_udn),
        ]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        for msg in messages:
            try:
                sock.sendto(msg, (SSDP_MULTICAST_ADDR, SSDP_PORT))
            except Exception:
                pass
        sock.close()

    def _notify_loop(self):
        """定期发送 ssdp:alive 的循环线程"""
        self._send_alive()
        while self._running:
            time.sleep(self.max_age // 2)
            if self._running:
                self._send_alive()

    def _listen_loop(self):
        """监听 SSDP M-SEARCH 请求"""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 绑定到本机局域网 IP，确保多播组加入正确的网卡
        local_ip = self.local_ip
        mreq = socket.inet_aton(SSDP_MULTICAST_ADDR) + socket.inet_aton(local_ip)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        self._sock.bind((local_ip, SSDP_PORT))
        self._sock.settimeout(2.0)

        logger.info(f"SSDP listener started on {local_ip}:{SSDP_PORT} (multicast: {SSDP_MULTICAST_ADDR})")

        root_udn = f"uuid:{self.device_uuid}"
        device_usn = f"{root_udn}::urn:schemas-upnp-org:device:MediaRenderer:1"

        while self._running:
            try:
                data, addr = self._sock.recvfrom(4096)
                msg = data.decode("utf-8", errors="ignore")

                if "M-SEARCH" not in msg:
                    continue

                # 提取 ST (Search Target)
                st = "ssdp:all"
                for line in msg.split("\r\n"):
                    if line.lower().startswith("st:"):
                        st = line.split(":", 1)[1].strip()
                        break

                # 匹配并响应
                search_targets = {
                    "ssdp:all": "upnp:rootdevice",
                    "upnp:rootdevice": "upnp:rootdevice",
                    root_udn: root_udn,
                    "urn:schemas-upnp-org:device:MediaRenderer:1": "urn:schemas-upnp-org:device:MediaRenderer:1",
                }

                matched_st = None
                matched_usn = root_udn

                for key, val in search_targets.items():
                    if st == key:
                        matched_st = val
                        if st == "urn:schemas-upnp-org:device:MediaRenderer:1":
                            matched_usn = device_usn
                        break

                if matched_st is None:
                    continue

                from email.utils import formatdate

                response = SEARCH_RESPONSE_TEMPLATE.format(
                    max_age=self.max_age,
                    date=formatdate(timeval=None, localtime=False, usegmt=True),
                    local_ip=self.local_ip,
                    http_port=self.http_port,
                    server=self.server_name,
                    st=matched_st,
                    usn=matched_usn,
                    boot_id=self.boot_id,
                )

                resp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                resp_sock.bind((self.local_ip, 0))
                resp_sock.sendto(response.encode("utf-8"), addr)
                resp_sock.close()

                if self.on_discovery_request:
                    self.on_discovery_request(addr, st)

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"SSDP listen error: {e}")

    def start(self):
        """启动 SSDP 服务"""
        if self._running:
            return
        self._running = True

        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True, name="SSDP-Listener")
        self._listen_thread.start()

        self._notify_thread = threading.Thread(target=self._notify_loop, daemon=True, name="SSDP-Notify")
        self._notify_thread.start()

        logger.info(f"SSDP server started. Device: {self.friendly_name} @ {self.local_ip}")

    def stop(self):
        """停止 SSDP 服务"""
        if not self._running:
            return
        self._running = False
        self._send_byebye()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        logger.info("SSDP server stopped")