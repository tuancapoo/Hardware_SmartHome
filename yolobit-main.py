# ============================================================
#  AIOT KIT – Yolo:Bit + MQTT (Adafruit IO)        (1 file duy nhất)
#  Khai báo theo mô hình DB: Device -> Component -> Model(driver)
#
#  UPSTREAM  (bo -> server)  tài khoản UP_USER, tách 3 group:
#     data.<model>      số đo cảm biến, VÀ giá trị hiện tại của thiết bị chấp hành (gửi định kỳ)
#                       {"deviceId","componentmodelId","val"}
#     control.<model>   trạng thái THẬT của thiết bị chấp hành sau khi chạy lệnh / bấm nút
#                       {"deviceId","componentmodelId","mode":"on|off","val","source":"command|button"}
#     componentmodelId = _id của loại linh kiện trong collection `models` (xem MODELS bên dưới)
#     topic đầy đủ: <UP_USER>/feeds/<group>.<feed>
#  DOWNSTREAM (server -> bo) tài khoản DOWN_USER:
#     topic   <DOWN_USER>/feeds/<deviceId>          (mỗi bo nghe đúng feed của mình)
#     payload {"model": "fan-dc", "mode": "on", "val": 60}
#  LƯU Ý: dùng khóa "val", KHÔNG dùng "value" – Adafruit IO thấy khóa "value" sẽ chỉ giữ lại con số đó
#  NÚT BẤM trên Yolo:Bit: gán cho một model trong DEVICES bằng khóa "buttons" (mục 2)
#     A: tăng value thêm 10, vượt max thì về 0        B: khác 0 thì về 0
# ============================================================
from yolobit import *
from mqtt import *                       # chỉ dùng mqtt.connect_wifi
from umqtt.simple import MQTTClient      # mỗi tài khoản Adafruit một phiên MQTT riêng
from aiot_dht20 import DHT20
from machine import Pin, SoftI2C
import json
import time

# ===================== 1. CẤU HÌNH – CHỈ SỬA PHẦN NÀY =====================
WIFI_SSID, WIFI_PASS = "TEN_WIFI", "MAT_KHAU"
UP_USER, UP_KEY = "tuanvip069", "aio_xxxxxxxx"      # KHÔNG đưa key lên git / gửi ảnh
DOWN_USER, DOWN_KEY = "tuanvip069_downstream", "aio_xxxxxxxx"   # key của tài khoản DOWNSTREAM
DEVICE = "fan"                    # fan | light | curtain | env  -> chọn bo rồi nạp
SEND_INTERVAL_MS = 30000          # chu kỳ gửi cảm biến (>= 10 s để khỏi bị Adafruit chặn)
PING_INTERVAL_MS = 30000          # giữ kết nối cho phiên downstream (không có tin nào gửi đi)

# ===================== 1b. DANH SÁCH COMPONENT MODEL (cùng định dạng collection `models` trong DB) =====================
# _id = componentmodelId gửi lên server · name = tên feed (duy nhất) · type: slider | switch | None (cảm biến)
# range = dải hợp lệ (quạt, đèn, servo bị kẹp trong dải này) · min_start = mức tối thiểu để thiết bị chạy
MODELS = [
    {"_id": "00000000-0000-4000-8000-000000000201", "name": "dht20-temp", "label": "DHT20 - Nhiệt độ", "kind": "sensor", "type": None,
     "metric": "temperature", "unit": "°C", "range": {"min": -40, "max": 80}, "min_start": None},
    {"_id": "00000000-0000-4000-8000-000000000202", "name": "dht20-hum", "label": "DHT20 - Độ ẩm", "kind": "sensor", "type": None,
     "metric": "humidity", "unit": "%", "range": {"min": 0, "max": 100}, "min_start": None},
    {"_id": "00000000-0000-4000-8000-000000000203", "name": "light", "label": "Cảm biến ánh sáng", "kind": "sensor", "type": None,
     "metric": "light", "unit": "%", "range": {"min": 0, "max": 100}, "min_start": None},
    {"_id": "00000000-0000-4000-8000-000000000204", "name": "fan-dc", "label": "Động cơ quạt mini DC", "kind": "actuator", "type": "slider",
     "metric": "fan_speed", "unit": "%", "range": {"min": 0, "max": 100}, "min_start": 30},
    {"_id": "00000000-0000-4000-8000-000000000205", "name": "led", "label": "Đèn LED", "kind": "actuator", "type": "switch",
     "metric": "brightness", "unit": "%", "range": {"min": 0, "max": 100}, "min_start": None},
    {"_id": "00000000-0000-4000-8000-000000000206", "name": "servo-sg90", "label": "Động cơ Servo SG90", "kind": "actuator", "type": "slider",
     "metric": "servo_angle", "unit": "°", "range": {"min": 0, "max": 180}, "min_start": None},
]

# ===================== 2. KHAI BÁO DEVICE / COMPONENT =====================
# id     = devices._id                 model  = models.name (tên feed upstream)   modelId = models._id (componentmodelId)
# driver = loại driver bên dưới        pin    = chân cắm trên Yolo:Bit
# Một device KHÔNG có 2 component cùng model (DB có index unique device_id + model_id).
# buttons = model (thiết bị chấp hành) mà nút A/B điều khiển. Bỏ khóa này = actuator đầu tiên; None = tắt nút.
DEVICES = {
    "fan": {"id": "00000000-0000-4000-8000-000000000401", "buttons": "led", "components": [
        {"model": "dht20-temp", "modelId": "00000000-0000-4000-8000-000000000201", "driver": "dht20_temp"},
        {"model": "dht20-hum", "modelId": "00000000-0000-4000-8000-000000000202", "driver": "dht20_hum"},
        {"model": "led", "modelId": "00000000-0000-4000-8000-000000000205", "driver": "pwm_percent", "pin": "P0"},
        {"model": "fan-dc", "modelId": "00000000-0000-4000-8000-000000000204", "driver": "pwm_percent", "pin": "P10"},
    ]},
    "light": {"id": "00000000-0000-4000-8000-000000000402", "buttons": "led", "components": [
        {"model": "light", "modelId": "00000000-0000-4000-8000-000000000203", "driver": "analog_percent", "pin": "P1"},
        {"model": "led", "modelId": "00000000-0000-4000-8000-000000000205", "driver": "pwm_percent", "pin": "P0"},
    ]},
    "curtain": {"id": "00000000-0000-4000-8000-000000000403", "buttons": "servo-sg90", "components": [
        {"model": "light", "modelId": "00000000-0000-4000-8000-000000000203", "driver": "analog_percent", "pin": "P1"},
        {"model": "servo-sg90", "modelId": "00000000-0000-4000-8000-000000000206", "driver": "servo_angle", "pin": "P2"},
    ]},
    "env": {"id": "00000000-0000-4000-8000-000000000404", "components": [
        {"model": "dht20-temp", "modelId": "00000000-0000-4000-8000-000000000201", "driver": "dht20_temp"},
        {"model": "dht20-hum", "modelId": "00000000-0000-4000-8000-000000000202", "driver": "dht20_hum"},
    ]},
}

PINS = {"P0": pin0, "P1": pin1, "P2": pin2, "P3": pin3, "P4": pin4,
        "P10": pin10, "P13": pin13, "P14": pin14, "P15": pin15, "P16": pin16}

# ===================== 3. DRIVER – MỖI LOẠI LINH KIỆN MỘT CLASS =====================
# Cảm biến: read() -> số.   Chấp hành: apply(v) -> giá trị thực tế đã chạy.
_dht = None
def get_dht():
    global _dht
    if _dht is None:
        _dht = DHT20(SoftI2C(scl=Pin(22), sda=Pin(21)))
    _dht.read_dht20()
    return _dht

class Dht20Temp:                      # model "dht20-temp"
    def __init__(self, cfg): pass
    def read(self): return get_dht().dht20_temperature()

class Dht20Hum:                       # model "dht20-hum"
    def __init__(self, cfg): pass
    def read(self): return get_dht().dht20_humidity()

class AnalogPercent:                  # model "light" (analog 0-4095 -> 0-100 %)
    def __init__(self, cfg): self.pin = PINS[cfg["pin"]]
    def read(self): return round(self.pin.read_analog() * 100 / 4095)

class PwmPercent:                     # model "fan-dc", "led" (0 = tắt)
    def __init__(self, cfg):
        self.pin = PINS[cfg["pin"]]
        self.min_start = cfg.get("min_start") or 0          # lấy từ model
        self.max, self.value = cfg["range"]["max"], 0       # dải lấy từ model; max/value để nút A,B biết tăng tới đâu
        self.apply(0)
    def apply(self, v):
        v = max(0, min(self.max, int(v)))
        self.value = v
        if 0 < v < self.min_start:    # quạt < 30 % có thể không quay (UC02-2 A1)
            print("Cảnh báo: dưới", self.min_start, "% thiết bị có thể không chạy")
        self.pin.write_analog(round(v * 1023 / 100))
        return v

class ServoAngle:                     # model "servo-sg90" (0-180 độ)
    def __init__(self, cfg):
        self.pin = PINS[cfg["pin"]]
        self.max, self.value = cfg["range"]["max"], 0
        self.apply(0)
    def apply(self, v):
        v = max(0, min(self.max, int(v)))
        self.value = v
        self.pin.servo_write(v)
        return v

# Đăng ký driver. Thêm loại linh kiện mới: viết class ở trên rồi thêm 1 dòng ở đây.
DRIVERS = {
    "dht20_temp": Dht20Temp, "dht20_hum": Dht20Hum, "analog_percent": AnalogPercent,
    "pwm_percent": PwmPercent, "servo_angle": ServoAngle,
}

# ===================== 4. KẾT NỐI & VÒNG LẶP (không cần sửa) =====================
DEVICE_ID = DEVICES[DEVICE]["id"]
sensors, actuators = [], {}           # sensors: danh sách; actuators: model -> item
up, down = None, None                 # 2 phiên MQTT: upstream (gửi) / downstream (nghe lệnh)
first_actuator = None                # actuator đầu tiên (mặc định của nút A/B nếu device không khai báo "buttons")
button_target = None                 # item mà nút A/B điều khiển

MODEL_BY_ID = {m["_id"]: m for m in MODELS}
for cfg in DEVICES[DEVICE]["components"]:
    m = MODEL_BY_ID.get(cfg["modelId"])
    if m is None or m["name"] != cfg["model"]:        # khai báo sai thì báo ngay lúc khởi động
        raise ValueError("modelId không khớp model '%s' trong MODELS: %s" % (cfg["model"], cfg["modelId"]))
    cfg = dict(cfg)
    cfg["range"], cfg["min_start"] = m["range"], m["min_start"]
    drv = DRIVERS[cfg["driver"]](cfg)
    item = {"model": m["name"], "modelId": m["_id"], "drv": drv}
    item["group"] = "control" if hasattr(drv, "apply") else "data"
    if hasattr(drv, "apply"):
        actuators[cfg["model"]] = item
        if first_actuator is None:
            first_actuator = item
    else:
        sensors.append(item)

if "buttons" in DEVICES[DEVICE]:          # khai báo rõ: tên model, hoặc None để tắt nút
    button_target = actuators.get(DEVICES[DEVICE]["buttons"])
    if DEVICES[DEVICE]["buttons"] is not None and button_target is None:
        print("Cảnh báo: buttons =", DEVICES[DEVICE]["buttons"], "không phải actuator của bo này -> nút A/B bị tắt")
else:
    button_target = first_actuator

def up_topic(group, feed):
    return UP_USER + "/feeds/" + group + "." + feed

def down_topic():
    return DOWN_USER + "/feeds/" + DEVICE_ID

def send_up(group, feed, payload):    # gửi một tin lên upstream
    up.publish(up_topic(group, feed), json.dumps(payload))

def safe_publish(item, value, source=None, group=None):   # group: "data" (định kỳ) hoặc "control" (khi đổi)
    group = group or item["group"]
    payload = {"deviceId": DEVICE_ID, "componentmodelId": item["modelId"], "val": value}      # data
    if group == "control":                                                                    # control
        payload["mode"] = "on" if value else "off"
    if source:
        payload["source"] = source        # control: "command" (lệnh từ xa) hay "button" (bấm nút tại bo)
    try:
        send_up(group, item["model"], payload)
    except Exception as e:
        print("Publish lỗi:", e)
        connect()

def on_command(topic, msg):           # callback của umqtt: nhận bytes
    try:
        d = json.loads(msg.decode() if hasattr(msg, "decode") else msg)
        item = None
        for a in actuators.values():                  # nhận lệnh theo componentmodelId (hoặc tên model)
            if d.get("componentmodelId") == a["modelId"] or d.get("model") == a["model"]:
                item = a
        if item is None:
            print("Lệnh cho model không có trên bo:", d.get("componentmodelId") or d.get("model"))
            return
        value = 0 if d.get("mode") == "off" else float(d.get("val", 100))
        safe_publish(item, item["drv"].apply(value), "command")   # chạy xong báo lại giá trị thật (control)
    except Exception as e:
        print("Lệnh lỗi:", msg, e)

def set_manual(item, v):              # đặt giá trị bằng tay rồi báo lên control để server cập nhật
    actual = item["drv"].apply(v)
    print("Nút bấm:", item["model"], "=", actual)
    safe_publish(item, actual, "button")

def press_a():                        # A: tăng thêm 10, vượt max thì về 0
    d = button_target["drv"]
    set_manual(button_target, d.value + 10 if d.value + 10 <= d.max else 0)

def press_b():                        # B: khác 0 thì về 0
    if button_target["drv"].value != 0:
        set_manual(button_target, 0)

def connect():
    global up, down
    for old in (up, down):                # đóng phiên cũ (nếu còn) trước khi nối lại, tránh hai kết nối cùng ID đá nhau
        try:
            old.disconnect()
        except Exception:
            pass
    while True:
        try:
            display.scroll("WF")
            mqtt.connect_wifi(WIFI_SSID, WIFI_PASS)
            up = MQTTClient("yb-up-" + DEVICE, "io.adafruit.com", 1883, UP_USER, UP_KEY, keepalive=60)
            up.connect()
            down = MQTTClient("yb-down-" + DEVICE, "io.adafruit.com", 1883, DOWN_USER, DOWN_KEY, keepalive=60)
            down.set_callback(on_command)
            down.connect()
            down.subscribe(down_topic())
            display.show(Image.YES)
            return
        except Exception as e:
            print("Lỗi kết nối:", e)
            display.show(Image.NO)
            time.sleep(5)

def send_sensors():
    for s in sensors:
        try:
            safe_publish(s, s["drv"].read())
        except Exception as e:
            print("Đọc", s["model"], "lỗi:", e)
    for a in actuators.values():          # thiết bị chấp hành cũng gửi giá trị hiện tại lên data như cảm biến
        safe_publish(a, a["drv"].value, None, "data")

connect()
last = time.ticks_ms() - SEND_INTERVAL_MS        # gửi ngay lần đầu
last_ping = time.ticks_ms()
prev_a, prev_b = False, False
while True:
    a_now, b_now = button_a.is_pressed(), button_b.is_pressed()
    if button_target is not None:         # chỉ phản ứng ở thời điểm vừa nhấn xuống (giữ nút không lặp)
        if a_now and not prev_a:
            press_a()
        if b_now and not prev_b:
            press_b()
    prev_a, prev_b = a_now, b_now
    try:
        down.check_msg()                          # nhận lệnh – phải gọi liên tục
        if time.ticks_diff(time.ticks_ms(), last_ping) >= PING_INTERVAL_MS:
            last_ping = time.ticks_ms()
            down.ping()
            up.ping()
    except Exception as e:
        print("Mất kết nối:", e)
        connect()
    if time.ticks_diff(time.ticks_ms(), last) >= SEND_INTERVAL_MS:
        last = time.ticks_ms()
        send_sensors()
    time.sleep_ms(50)
