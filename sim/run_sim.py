"""Chạy NGUYÊN file yolobit-main.py ở chế độ console.
Cách dùng:  python run_sim.py [device] [--interval N] [--local]   (bỏ device = dùng DEVICE, bỏ --interval = dùng SEND_INTERVAL_MS trong yolobit-main.py)
Gõ lệnh như server:  <model> <giá trị>   ví dụ   fan-dc 60    (0 = tắt)
Bấm nút Yolo:Bit:     A (tăng 10, quá max về 0)   hoặc   B (về 0)
Muốn có cửa sổ hình ảnh: python gui_sim.py <device>
"""
import argparse
import os
import sys
import threading

import simcore

simcore.setup()
ap = argparse.ArgumentParser()
ap.add_argument("device", nargs="?", default=None, help="mặc định: DEVICE khai báo trong yolobit-main.py")
ap.add_argument("--interval", type=float, default=None, help="chu kỳ gửi cảm biến (giây); bỏ trống = dùng SEND_INTERVAL_MS trong yolobit-main.py")
ap.add_argument("--heartbeat", type=float, default=None, help="thời gian cơ sở tính offline (mặc định = chu kỳ gửi); quá 3 lần không có tin thì coi là offline")
ap.add_argument("--local", action="store_true", help="dùng broker GIẢ (không cần mạng)")
a = ap.parse_args()
if a.local:
    os.environ["SIM_BROKER"] = "local"

code, cfg = simcore.load(a.device, a.interval, a.heartbeat)
import simserver  # noqa: E402


def reader():
    for line in sys.stdin:
        parts = line.strip().split(None, 1)
        if len(parts) == 1 and parts[0].lower() in ("a", "b"):         # nút bấm trên Yolo:Bit
            import hw
            hw.press(parts[0].lower())
        elif len(parts) == 2:
            try:
                simserver.send_command(cfg, parts[0], float(parts[1]))
            except Exception as e:
                print("  Gửi lệnh lỗi:", e)


threading.Thread(target=reader, daemon=True).start()
print("=== Yolo:Bit giả lập – device '%s' id %s (Ctrl+C để dừng) ===" % (cfg["device"], cfg["device_id"]))
try:
    simcore.run(code)
except KeyboardInterrupt:
    print("\nĐã dừng.")
