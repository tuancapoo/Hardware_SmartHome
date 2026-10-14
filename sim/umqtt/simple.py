"""umqtt.simple giả (cùng API MicroPython): mỗi MQTTClient là một phiên MQTT riêng.
- Mặc định: nối broker THẬT (Adafruit IO) bằng paho-mqtt (pip install paho-mqtt).
- SIM_BROKER=local: broker giả trong tiến trình, không cần mạng.
"""
import os
import queue
import threading

import hw

_LOCAL = os.environ.get("SIM_BROKER") == "local"
_hub = {}                                   # (chế độ local) topic -> [client]
_live = {}                                  # client_id -> MQTTClient đang nối (để đóng bản cũ khi nối lại)


def _s(x):
    return x.decode() if isinstance(x, (bytes, bytearray)) else str(x)


class MQTTClient:
    def __init__(self, client_id, server, port=0, user=None, password=None, keepalive=0, ssl=False, ssl_params=None):
        self.client_id, self.server, self.port = _s(client_id), server, port or 1883
        self.user, self.password = user, password
        self.cb = None
        self.q = queue.Queue()
        self.paho = None
        self.subs = []
        self._closing = False

    def set_callback(self, f):
        self.cb = f

    def connect(self, clean_session=True):
        self._net()
        if _LOCAL:
            hw.emit("log", "info", "[%s] nối broker GIẢ (local)" % self.user)
            return 0
        import paho.mqtt.client as paho
        old = _live.get(self.client_id)
        if old is not None and old is not self:
            old.disconnect()                    # cùng client_id: Adafruit chỉ cho một kết nối, không đóng thì hai bên đá nhau
        c = paho.Client(paho.CallbackAPIVersion.VERSION1, client_id=self.client_id) \
            if hasattr(paho, "CallbackAPIVersion") else paho.Client(client_id=self.client_id)
        c.username_pw_set(self.user, self.password)
        done, result = threading.Event(), {}

        def on_connect(cl, u, flags, rc):
            result["rc"] = rc
            done.set()

        c.on_connect = on_connect
        c.on_message = lambda cl, u, m: self.q.put((m.topic.encode(), m.payload))
        c.on_disconnect = lambda cl, u, rc: (None if self._closing else hw.emit("log", "err", "[%s] mất kết nối (rc=%s)" % (self.user, rc)))
        c.connect(self.server, self.port, 60)       # lỗi mạng -> ném ngoại lệ, main.py tự thử lại
        c.loop_start()
        if not done.wait(8) or result.get("rc") != 0:
            c.loop_stop()
            raise OSError("MQTT từ chối/không phản hồi (user %s, rc=%s)" % (self.user, result.get("rc")))
        self.paho = c
        _live[self.client_id] = self
        print("  MQTT> [%s] đã nối broker THẬT %s" % (self.user, self.server))
        hw.emit("log", "info", "[%s] đã nối broker THẬT %s" % (self.user, self.server))
        return 0

    def subscribe(self, topic, qos=0):
        topic = _s(topic)
        self.subs.append(topic)
        if _LOCAL:
            _hub.setdefault(topic, []).append(self)
        elif self.paho:
            self.paho.subscribe(topic)
        hw.emit("log", "info", "[%s] nghe %s" % (self.user, topic))

    def publish(self, topic, msg, retain=False, qos=0):
        self._net()
        topic, text = _s(topic), _s(msg)
        print("  MQTT> gửi  %s = %s" % (topic, text))
        hw.emit("publish", topic, text)
        if _LOCAL:
            for c in _hub.get(topic, []):
                c.q.put((topic.encode(), text.encode()))
        elif self.paho:
            self.paho.publish(topic, text)

    def check_msg(self):
        self._net()
        while True:
            try:
                topic, payload = self.q.get_nowait()
            except queue.Empty:
                return
            print("  MQTT> nhận %s = %s" % (_s(topic), _s(payload)))
            hw.emit("recv", _s(topic), _s(payload))
            if self.cb:
                self.cb(topic, payload)

    def ping(self):
        self._net()

    @staticmethod
    def _net():
        if hw.offline:
            raise OSError("Mạng đứt (giả lập)")

    def disconnect(self):
        self._closing = True
        if self.paho:
            self.paho.loop_stop()
            self.paho.disconnect()
