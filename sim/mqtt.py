"""mqtt giả của OhStem – bản mới chỉ còn dùng cho WiFi (MQTT đi qua umqtt.simple)."""
import hw


class _Mqtt:
    def connect_wifi(self, ssid, password):
        print("  WIFI> nối", ssid, "OK (giả lập – máy tính đã có mạng)")
        hw.emit("log", "info", "WiFi OK (giả lập)")


mqtt = _Mqtt()
