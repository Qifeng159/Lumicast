"""
DLNA SOAP 服务层 - 处理 AVTransport、RenderingControl、ConnectionManager
这是手机投屏软件与虚拟渲染器之间的控制协议
"""
import time
import threading
import logging
from typing import Dict, Any, Optional, Callable
from xml.etree import ElementTree as ET

logger = logging.getLogger("Lumicast.DLNAService")

# SCPD 描述 XML
AVTRANSPORT_SCPD = """<?xml version="1.0" encoding="UTF-8"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <actionList>
    <action><name>SetAVTransportURI</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>CurrentURI</name><direction>in</direction><relatedStateVariable>AVTransportURI</relatedStateVariable></argument>
        <argument><name>CurrentURIMetaData</name><direction>in</direction><relatedStateVariable>AVTransportURIMetaData</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>Play</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>Speed</name><direction>in</direction><relatedStateVariable>TransportPlaySpeed</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>Pause</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>Stop</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>Seek</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>Unit</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_SeekMode</relatedStateVariable></argument>
        <argument><name>Target</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_SeekTarget</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>GetPositionInfo</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>Track</name><direction>out</direction><relatedStateVariable>CurrentTrack</relatedStateVariable></argument>
        <argument><name>TrackDuration</name><direction>out</direction><relatedStateVariable>CurrentTrackDuration</relatedStateVariable></argument>
        <argument><name>TrackMetaData</name><direction>out</direction><relatedStateVariable>CurrentTrackMetaData</relatedStateVariable></argument>
        <argument><name>TrackURI</name><direction>out</direction><relatedStateVariable>CurrentTrackURI</relatedStateVariable></argument>
        <argument><name>RelTime</name><direction>out</direction><relatedStateVariable>RelativeTimePosition</relatedStateVariable></argument>
        <argument><name>AbsTime</name><direction>out</direction><relatedStateVariable>AbsoluteTimePosition</relatedStateVariable></argument>
        <argument><name>RelCount</name><direction>out</direction><relatedStateVariable>RelativeCounterPosition</relatedStateVariable></argument>
        <argument><name>AbsCount</name><direction>out</direction><relatedStateVariable>AbsoluteCounterPosition</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>GetTransportInfo</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>CurrentTransportState</name><direction>out</direction><relatedStateVariable>TransportState</relatedStateVariable></argument>
        <argument><name>CurrentTransportStatus</name><direction>out</direction><relatedStateVariable>TransportStatus</relatedStateVariable></argument>
        <argument><name>CurrentSpeed</name><direction>out</direction><relatedStateVariable>TransportPlaySpeed</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>GetMediaInfo</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>NrTracks</name><direction>out</direction><relatedStateVariable>NumberOfTracks</relatedStateVariable></argument>
        <argument><name>MediaDuration</name><direction>out</direction><relatedStateVariable>CurrentMediaDuration</relatedStateVariable></argument>
        <argument><name>CurrentURI</name><direction>out</direction><relatedStateVariable>AVTransportURI</relatedStateVariable></argument>
        <argument><name>CurrentURIMetaData</name><direction>out</direction><relatedStateVariable>AVTransportURIMetaData</relatedStateVariable></argument>
        <argument><name>NextURI</name><direction>out</direction><relatedStateVariable>NextAVTransportURI</relatedStateVariable></argument>
        <argument><name>NextURIMetaData</name><direction>out</direction><relatedStateVariable>NextAVTransportURIMetaData</relatedStateVariable></argument>
        <argument><name>PlayMedium</name><direction>out</direction><relatedStateVariable>PlaybackStorageMedium</relatedStateVariable></argument>
        <argument><name>RecordMedium</name><direction>out</direction><relatedStateVariable>RecordStorageMedium</relatedStateVariable></argument>
        <argument><name>WriteStatus</name><direction>out</direction><relatedStateVariable>RecordMediumWriteStatus</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>Next</name></action>
    <action><name>Previous</name></action>
    <action><name>SetNextAVTransportURI</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>NextURI</name><direction>in</direction><relatedStateVariable>NextAVTransportURI</relatedStateVariable></argument>
        <argument><name>NextURIMetaData</name><direction>in</direction><relatedStateVariable>NextAVTransportURIMetaData</relatedStateVariable></argument>
      </argumentList>
    </action>
  </actionList>
  <serviceStateTable>
    <stateVariable><name>TransportState</name><dataType>string</dataType><allowedValueList><allowedValue>STOPPED</allowedValue><allowedValue>PLAYING</allowedValue><allowedValue>PAUSED_PLAYBACK</allowedValue><allowedValue>TRANSITIONING</allowedValue></allowedValueList></stateVariable>
    <stateVariable><name>TransportStatus</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>TransportPlaySpeed</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>AVTransportURI</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>AVTransportURIMetaData</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>CurrentTrack</name><dataType>ui4</dataType></stateVariable>
    <stateVariable><name>CurrentTrackDuration</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>CurrentTrackMetaData</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>CurrentTrackURI</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_InstanceID</name><dataType>ui4</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_SeekMode</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_SeekTarget</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>RelativeTimePosition</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>AbsoluteTimePosition</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>RelativeCounterPosition</name><dataType>ui4</dataType></stateVariable>
    <stateVariable><name>AbsoluteCounterPosition</name><dataType>ui4</dataType></stateVariable>
    <stateVariable><name>NextAVTransportURI</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>NextAVTransportURIMetaData</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>NumberOfTracks</name><dataType>ui4</dataType></stateVariable>
    <stateVariable><name>CurrentMediaDuration</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>PlaybackStorageMedium</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>RecordStorageMedium</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>RecordMediumWriteStatus</name><dataType>string</dataType></stateVariable>
  </serviceStateTable>
</scpd>"""

RENDERING_CONTROL_SCPD = """<?xml version="1.0" encoding="UTF-8"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <actionList>
    <action><name>SetVolume</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>Channel</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Channel</relatedStateVariable></argument>
        <argument><name>DesiredVolume</name><direction>in</direction><relatedStateVariable>Volume</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>GetVolume</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>Channel</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Channel</relatedStateVariable></argument>
        <argument><name>CurrentVolume</name><direction>out</direction><relatedStateVariable>Volume</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>SetMute</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>Channel</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Channel</relatedStateVariable></argument>
        <argument><name>DesiredMute</name><direction>in</direction><relatedStateVariable>Mute</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>GetMute</name>
      <argumentList>
        <argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
        <argument><name>Channel</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Channel</relatedStateVariable></argument>
        <argument><name>CurrentMute</name><direction>out</direction><relatedStateVariable>Mute</relatedStateVariable></argument>
      </argumentList>
    </action>
  </actionList>
  <serviceStateTable>
    <stateVariable><name>Volume</name><dataType>ui2</dataType><allowedValueRange><minimum>0</minimum><maximum>100</maximum></allowedValueRange></stateVariable>
    <stateVariable><name>Mute</name><dataType>boolean</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_InstanceID</name><dataType>ui4</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_Channel</name><dataType>string</dataType></stateVariable>
  </serviceStateTable>
</scpd>"""

CONNECTION_MANAGER_SCPD = """<?xml version="1.0" encoding="UTF-8"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <actionList>
    <action><name>GetProtocolInfo</name>
      <argumentList>
        <argument><name>Source</name><direction>out</direction><relatedStateVariable>SourceProtocolInfo</relatedStateVariable></argument>
        <argument><name>Sink</name><direction>out</direction><relatedStateVariable>SinkProtocolInfo</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>GetCurrentConnectionIDs</name>
      <argumentList>
        <argument><name>ConnectionIDs</name><direction>out</direction><relatedStateVariable>CurrentConnectionIDs</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action><name>GetCurrentConnectionInfo</name>
      <argumentList>
        <argument><name>ConnectionID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_ConnectionID</relatedStateVariable></argument>
        <argument><name>RcsID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_RcsID</relatedStateVariable></argument>
        <argument><name>AVTransportID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_AVTransportID</relatedStateVariable></argument>
        <argument><name>ProtocolInfo</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_ProtocolInfo</relatedStateVariable></argument>
        <argument><name>PeerConnectionManager</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_ConnectionManager</relatedStateVariable></argument>
        <argument><name>PeerConnectionID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_ConnectionID</relatedStateVariable></argument>
        <argument><name>Direction</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Direction</relatedStateVariable></argument>
        <argument><name>Status</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_ConnectionStatus</relatedStateVariable></argument>
      </argumentList>
    </action>
  </actionList>
  <serviceStateTable>
    <stateVariable><name>SourceProtocolInfo</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>SinkProtocolInfo</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>CurrentConnectionIDs</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_ConnectionStatus</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_ConnectionManager</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_Direction</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_ProtocolInfo</name><dataType>string</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_ConnectionID</name><dataType>i4</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_AVTransportID</name><dataType>i4</dataType></stateVariable>
    <stateVariable><name>A_ARG_TYPE_RcsID</name><dataType>i4</dataType></stateVariable>
  </serviceStateTable>
</scpd>"""

SOAP_ENVELOPE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    '<s:Body>'
    '<u:{action}Response xmlns:u="{service_type}">'
    "{response_xml}"
    "</u:{action}Response>"
    "</s:Body>"
    "</s:Envelope>"
)

SOAP_ERROR = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    '<s:Body>'
    '<s:Fault>'
    "<faultcode>s:Client</faultcode>"
    "<faultstring>UPnPError</faultstring>"
    "<detail>"
    "<UPnPError xmlns=\"urn:schemas-upnp-org:control-1-0\">"
    "<errorCode>{error_code}</errorCode>"
    "<errorDescription>{error_desc}</errorDescription>"
    "</UPnPError>"
    "</detail>"
    "</s:Fault>"
    "</s:Body>"
    "</s:Envelope>"
)


class AVTransportState:
    """AVTransport 状态管理"""

    def __init__(self):
        self.transport_state = "STOPPED"
        self.transport_status = "OK"
        self.play_speed = "1"
        self.current_uri: str = ""
        self.current_uri_metadata = ""
        self.current_track = 0
        self.current_track_duration = "00:00:00"
        self.relative_time_position = "00:00:00"
        self.absolute_time_position = "00:00:00"
        self.next_uri: str = ""
        self.next_uri_metadata: str = ""
        self.volume: int = 50
        self.mute: bool = False
        self._start_time: float = 0
        self._pause_position: float = 0

    def _format_time(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def get_current_position(self) -> str:
        if self.transport_state == "STOPPED":
            return self._format_time(self._pause_position)
        if self.transport_state == "PAUSED_PLAYBACK":
            return self._format_time(self._pause_position)
        elapsed = time.time() - self._start_time + self._pause_position
        return self._format_time(elapsed)

    def reset(self):
        self.transport_state = "STOPPED"
        self.current_uri = ""
        self._start_time = 0
        self._pause_position = 0


class DLNAServiceHandler:
    """DLNA SOAP Action 处理引擎"""

    def __init__(self):
        self.state = AVTransportState()
        self._lock = threading.Lock()

        # 回调钩子
        self.on_set_uri: Optional[Callable[[str, str], None]] = None
        self.on_play: Optional[Callable[[], None]] = None
        self.on_pause: Optional[Callable[[], None]] = None
        self.on_stop: Optional[Callable[[], None]] = None
        self.on_seek: Optional[Callable[[str, str], None]] = None
        self.on_volume_change: Optional[Callable[[int], None]] = None
        self.on_mute_change: Optional[Callable[[bool], None]] = None
        self.on_next: Optional[Callable[[], None]] = None

    def get_scpd(self, service: str) -> str:
        scpds = {
            "AVTransport": AVTRANSPORT_SCPD,
            "RenderingControl": RENDERING_CONTROL_SCPD,
            "ConnectionManager": CONNECTION_MANAGER_SCPD,
        }
        return scpds.get(service, "")

    def handle_action(self, service_type: str, action: str, args: Dict[str, str]) -> str:
        """处理 SOAP Action 请求，返回响应 XML"""
        ns_map = {
            "urn:schemas-upnp-org:service:AVTransport:1": self._handle_avtransport,
            "urn:schemas-upnp-org:service:RenderingControl:1": self._handle_rendering_control,
            "urn:schemas-upnp-org:service:ConnectionManager:1": self._handle_connection_manager,
        }
        handler = ns_map.get(service_type)
        if handler is None:
            return SOAP_ERROR.format(error_code="401", error_desc="Invalid Action")
        return handler(action, args)

    def _handle_avtransport(self, action: str, args: Dict[str, str]) -> str:
        with self._lock:
            if action == "SetAVTransportURI":
                self.state.current_uri = args.get("CurrentURI", "")
                self.state.current_uri_metadata = args.get("CurrentURIMetaData", "")
                self.state.transport_state = "STOPPED"
                self.state._pause_position = 0
                logger.info(f"SetAVTransportURI: {self.state.current_uri}")
                if self.on_set_uri:
                    self.on_set_uri(self.state.current_uri, self.state.current_uri_metadata)
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", "")

            elif action == "Play":
                self.state.transport_state = "PLAYING"
                self.state._start_time = time.time()
                logger.info("Play")
                if self.on_play:
                    self.on_play()
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", "")

            elif action == "Pause":
                self.state.transport_state = "PAUSED_PLAYBACK"
                self.state._pause_position += time.time() - self.state._start_time
                logger.info("Pause")
                if self.on_pause:
                    self.on_pause()
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", "")

            elif action == "Stop":
                self.state.reset()
                logger.info("Stop")
                if self.on_stop:
                    self.on_stop()
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", "")

            elif action == "Seek":
                unit = args.get("Unit", "REL_TIME")
                target = args.get("Target", "00:00:00")
                logger.info(f"Seek: {unit}={target}")
                if self.on_seek:
                    self.on_seek(unit, target)
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", "")

            elif action == "GetPositionInfo":
                pos = self.state.get_current_position()
                resp = (
                    f"<Track>{self.state.current_track}</Track>"
                    f"<TrackDuration>{self.state.current_track_duration}</TrackDuration>"
                    f"<TrackMetaData></TrackMetaData>"
                    f"<TrackURI>{self.state.current_uri}</TrackURI>"
                    f"<RelTime>{pos}</RelTime>"
                    f"<AbsTime>{pos}</AbsTime>"
                    f"<RelCount>0</RelCount>"
                    f"<AbsCount>0</AbsCount>"
                )
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", resp)

            elif action == "GetTransportInfo":
                resp = (
                    f"<CurrentTransportState>{self.state.transport_state}</CurrentTransportState>"
                    f"<CurrentTransportStatus>{self.state.transport_status}</CurrentTransportStatus>"
                    f"<CurrentSpeed>{self.state.play_speed}</CurrentSpeed>"
                )
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", resp)

            elif action == "GetMediaInfo":
                resp = (
                    f"<NrTracks>1</NrTracks>"
                    f"<MediaDuration>{self.state.current_track_duration}</MediaDuration>"
                    f"<CurrentURI>{self.state.current_uri}</CurrentURI>"
                    f"<CurrentURIMetaData>{self.state.current_uri_metadata}</CurrentURIMetaData>"
                    f"<NextURI>{self.state.next_uri}</NextURI>"
                    f"<NextURIMetaData>{self.state.next_uri_metadata}</NextURIMetaData>"
                    f"<PlayMedium>NETWORK</PlayMedium>"
                    f"<RecordMedium>NOT_IMPLEMENTED</RecordMedium>"
                    f"<WriteStatus>NOT_IMPLEMENTED</WriteStatus>"
                )
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", resp)

            elif action == "SetNextAVTransportURI":
                self.state.next_uri = args.get("NextURI", "")
                self.state.next_uri_metadata = args.get("NextURIMetaData", "")
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", "")

            elif action in ("Next", "Previous"):
                if self.on_next and action == "Next":
                    self.on_next()
                return self._soap_response(action, "urn:schemas-upnp-org:service:AVTransport:1", "")

            else:
                return SOAP_ERROR.format(error_code="401", error_desc="Invalid Action")

    def _handle_rendering_control(self, action: str, args: Dict[str, str]) -> str:
        with self._lock:
            if action == "SetVolume":
                vol = int(args.get("DesiredVolume", "50"))
                self.state.volume = max(0, min(100, vol))
                logger.info(f"SetVolume: {self.state.volume}")
                if self.on_volume_change:
                    self.on_volume_change(self.state.volume)
                return self._soap_response(action, "urn:schemas-upnp-org:service:RenderingControl:1", "")

            elif action == "GetVolume":
                resp = f"<CurrentVolume>{self.state.volume}</CurrentVolume>"
                return self._soap_response(action, "urn:schemas-upnp-org:service:RenderingControl:1", resp)

            elif action == "SetMute":
                mute = args.get("DesiredMute", "0")
                self.state.mute = mute == "1"
                logger.info(f"SetMute: {self.state.mute}")
                if self.on_mute_change:
                    self.on_mute_change(self.state.mute)
                return self._soap_response(action, "urn:schemas-upnp-org:service:RenderingControl:1", "")

            elif action == "GetMute":
                resp = f"<CurrentMute>{'1' if self.state.mute else '0'}</CurrentMute>"
                return self._soap_response(action, "urn:schemas-upnp-org:service:RenderingControl:1", resp)

            else:
                return SOAP_ERROR.format(error_code="401", error_desc="Invalid Action")

    def _handle_connection_manager(self, action: str, args: Dict[str, str]) -> str:
        if action == "GetProtocolInfo":
            # 支持的协议和格式
            source = ""
            sink = (
                "http-get:*:video/mp4:*,"
                "http-get:*:video/x-matroska:*,"
                "http-get:*:video/x-msvideo:*,"
                "http-get:*:video/webm:*,"
                "http-get:*:video/mpeg:*,"
                "http-get:*:audio/mpeg:*,"
                "http-get:*:audio/mp4:*,"
                "http-get:*:audio/x-wav:*,"
                "http-get:*:audio/flac:*,"
                "http-get:*:image/jpeg:*,"
                "http-get:*:image/png:*,"
                "http-get:*:image/gif:*"
            )
            resp = f"<Source>{source}</Source><Sink>{sink}</Sink>"
            return self._soap_response(action, "urn:schemas-upnp-org:service:ConnectionManager:1", resp)

        elif action == "GetCurrentConnectionIDs":
            resp = "<ConnectionIDs>0</ConnectionIDs>"
            return self._soap_response(action, "urn:schemas-upnp-org:service:ConnectionManager:1", resp)

        elif action == "GetCurrentConnectionInfo":
            resp = (
                "<RcsID>-1</RcsID>"
                "<AVTransportID>-1</AVTransportID>"
                "<ProtocolInfo></ProtocolInfo>"
                "<PeerConnectionManager></PeerConnectionManager>"
                "<PeerConnectionID>-1</PeerConnectionID>"
                "<Direction>Input</Direction>"
                "<Status>OK</Status>"
            )
            return self._soap_response(action, "urn:schemas-upnp-org:service:ConnectionManager:1", resp)

        return SOAP_ERROR.format(error_code="401", error_desc="Invalid Action")

    def _soap_response(self, action: str, service_type: str, response_xml: str) -> str:
        return SOAP_ENVELOPE.format(action=action, service_type=service_type, response_xml=response_xml)