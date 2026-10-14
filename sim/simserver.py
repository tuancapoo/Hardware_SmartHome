"""'Server giả': gửi lệnh downstream tới bo, giống server/Dashboard thật.
    topic   <DOWN_USER>/feeds/<deviceId>
    payload {"model": "...", "mode": "on|off", "val": n}
"""
import json
import threading

from umqtt.simple import MQTTClient

_client = None
_lock = threading.Lock()


def send_command(cfg, model, value):
    """cfg: dict từ simcore.load. value = 0 nghĩa là tắt."""
    global _client
    mode = "off" if float(value) == 0 else "on"
    payload = {"model": model, "mode": mode, "val": value}
    with _lock:
        if _client is None:
            _client = MQTTClient("sim-server", "io.adafruit.com", 1883, cfg["down_user"], cfg["down_key"], keepalive=60)
            _client.connect()
        _client.publish("%s/feeds/%s" % (cfg["down_user"], cfg["device_id"]), json.dumps(payload))
