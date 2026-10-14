"""Trạng thái phần cứng dùng chung giữa Yolo:Bit giả và giao diện (GUI)."""
import queue
import threading

events = queue.Queue()          # (loại, ...)  worker -> GUI
offline = False               # True: giả lập mất mạng (mọi thao tác MQTT báo lỗi)
buttons = {"a": False, "b": False}   # trạng thái nút A, B của Yolo:Bit
gui = False                     # True khi chạy với cửa sổ: cảm biến lấy giá trị từ slider
sensors = {"temp": 29.0, "hum": 65.0}
analog = {}                     # tên chân -> 0..100 (%)


def press(name, ms=250):
    """Nhấn nút A/B rồi nhả sau ms mili giây (chương trình quét nút mỗi 50 ms)."""
    buttons[name] = True
    threading.Timer(ms / 1000.0, lambda: buttons.__setitem__(name, False)).start()


def emit(kind, *data):
    events.put((kind,) + data)
