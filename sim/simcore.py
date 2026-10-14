"""Phần dùng chung: bù hàm MicroPython, nạp yolobit-main.py, đọc cấu hình."""
import ast
import io
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "..", "yolobit-main.py")


def setup():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    # MicroPython có các hàm này, CPython thì không
    time.ticks_ms = lambda: int(time.time() * 1000)
    time.ticks_diff = lambda a, b: a - b
    time.sleep_ms = lambda ms: time.sleep(ms / 1000.0)


def _consts(src):
    """Đọc các hằng số dạng chuỗi và bảng DEVICES từ yolobit-main.py (không chạy file)."""
    out = {}
    for node in ast.parse(src).body:
        if not isinstance(node, ast.Assign):
            continue
        tgt = node.targets[0]
        try:
            if isinstance(tgt, ast.Tuple):                      # A, B = "x", "y"
                vals = ast.literal_eval(node.value)
                for t, v in zip(tgt.elts, vals):
                    out[t.id] = v
            elif isinstance(tgt, ast.Name):
                out[tgt.id] = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            pass
    return out


def load(device, interval_s=None, heartbeat_s=None):
    """Trả về (code, cfg). code là yolobit-main.py, chỉ đổi DEVICE (và chu kỳ gửi nếu interval_s được truyền;
    interval_s=None thì giữ nguyên SEND_INTERVAL_MS khai báo trong file)."""
    src = open(MAIN, encoding="utf-8").read()            # WiFi/key đặt thẳng trong yolobit-main.py
    device = device or _consts(src)["DEVICE"]           # không chỉ định thì dùng DEVICE khai báo trong file
    src = re.sub(r'^DEVICE = "[^"]*"', 'DEVICE = "%s"' % device, src, flags=re.M)
    if interval_s is not None:
        src = re.sub(r"^SEND_INTERVAL_MS = \d+", "SEND_INTERVAL_MS = %d" % int(interval_s * 1000), src, flags=re.M)
    c = _consts(src)
    if interval_s is None:
        interval_s = c["SEND_INTERVAL_MS"] / 1000.0      # dùng đúng chu kỳ đã đặt trong yolobit-main.py
    dev = c["DEVICES"][device]
    models = {m["_id"]: m for m in c.get("MODELS", [])}
    for comp in dev["components"]:                       # min_start giờ nằm trong MODELS, không còn trong DEVICES
        comp.setdefault("min_start", (models.get(comp.get("modelId")) or {}).get("min_start"))
    acts = [x["model"] for x in dev["components"] if x["driver"] in ("pwm_percent", "servo_angle")]
    buttons = dev["buttons"] if "buttons" in dev else (acts[0] if acts else None)
    cfg = {"device": device, "up_user": c["UP_USER"], "down_user": c["DOWN_USER"], "down_key": c["DOWN_KEY"],
           "device_id": dev["id"], "components": dev["components"],
           "heartbeat_ms": int((heartbeat_s or interval_s) * 1000), "buttons": buttons}   # đơn vị thời gian để tính offline
    return compile(src, MAIN, "exec"), cfg


def run(code):
    exec(code, {"__name__": "__main__"})
