"""Giả lập AIOT kit bằng cửa sổ hình ảnh – chạy NGUYÊN file yolobit-main.py.

    python gui_sim.py [device] [--interval N] [--local]     (bỏ device = dùng DEVICE, bỏ --interval = dùng SEND_INTERVAL_MS trong yolobit-main.py)

- Cột trái : kéo thanh trượt để đổi số đo của cảm biến (như cắm cảm biến thật).
- Giữa     : linh kiện chấp hành phản ứng theo lệnh (quạt quay, đèn sáng, rèm mở).
- Cột phải : bảng gửi lệnh như server (downstream, đi qua Adafruit THẬT; --local = broker giả trong máy).
- Dưới     : màn LED 5x5 của Yolo:Bit và nhật ký MQTT.
"""
import argparse
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback

import simcore

simcore.setup()
import hw          # noqa: E402  (phải import sau simcore.setup để dùng đúng sys.path)

hw.gui = True

BG = "#f4f5f7"


def classify(c):
    """Phân loại component theo driver -> (nhóm, nhãn, min, max, bước)."""
    d, model = c["driver"], c["model"]
    if d == "dht20_temp":
        return "sensor", "temp", "Nhiệt độ (°C)", 0, 60, 0.5
    if d == "dht20_hum":
        return "sensor", "hum", "Độ ẩm (%)", 0, 100, 1
    if d == "analog_percent":
        return "sensor", "light", "Ánh sáng (%)", 0, 100, 1
    if d == "pwm_percent":
        return ("fan" if model == "fan-dc" else "led"), None, model, 0, 100, 1
    if d == "rgb_led_red":                                  # đèn LED RGB: bật = sáng đỏ
        return "led", None, model, 0, 100, 1
    if d == "servo_angle":
        return "curtain", None, model, 0, 180, 1
    return "other", None, model, 0, 100, 1


def mix(c1, c2, t):
    return "#%02x%02x%02x" % tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


class App:
    def __init__(self, root, device, cfg, code):
        self.root, self.cfg, self.code = root, cfg, code
        comps = cfg["components"]
        self.pin_state = {}          # tên chân -> giá trị hiện tại
        self.rgb_state = {}          # tên chân -> màu (r, g, b) của đèn RGB
        self.fan_angle = 0
        self.counts = {"data": 0, "control": 0, "hb": 0, "recv": 0, "cmd": 0}
        self.last_seen = None        # thời điểm nhận tin upstream gần nhất (server giả dùng để tính online)
        self.state = None            # ONLINE / OFFLINE
        self.transitions = []
        self.actuators = []          # {"pin","kind","cv","model","min_start"}
        root.title("Giả lập AIOT kit – device '%s'  id %s" % (device, cfg["device_id"]))
        root.configure(bg=BG)

        top = tk.Frame(root, bg=BG)
        top.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        left = tk.LabelFrame(top, text=" Cảm biến – kéo để đổi số đo ", bg=BG, padx=8, pady=6)
        mid = tk.LabelFrame(top, text=" Linh kiện chấp hành ", bg=BG, padx=8, pady=6)
        right = tk.LabelFrame(top, text=" Gửi lệnh như server (downstream) ", bg=BG, padx=8, pady=6)
        left.pack(side="left", fill="y", padx=4)
        mid.pack(side="left", fill="both", expand=True, padx=4)
        right.pack(side="left", fill="y", padx=4)

        for c in comps:
            kind, key, label, lo, hi, step = classify(c)
            if kind == "sensor":
                self.add_sensor(left, c, key, label, lo, hi, step)
            elif kind in ("fan", "led", "curtain"):
                self.add_actuator(mid, right, c, kind, label, lo, hi)
        if not self.actuators:
            tk.Label(mid, text="(thiết bị này không có linh kiện chấp hành)", bg=BG, fg="#777").pack(pady=40)
            tk.Label(right, text="(không có gì để điều khiển)", bg=BG, fg="#777").pack(pady=40)

        bt = tk.LabelFrame(root, text=" Nút bấm trên Yolo:Bit  →  điều khiển: %s " % (cfg["buttons"] or "(không gán)"), bg=BG,
                           padx=8, pady=4)
        bt.pack(fill="x", padx=14, pady=(0, 6))
        tk.Button(bt, text="Nút A:  +10  (quá max → 0)", width=26, command=lambda: hw.press("a")).pack(side="left", padx=4)
        tk.Button(bt, text="Nút B:  khác 0 → 0", width=22, command=lambda: hw.press("b")).pack(side="left", padx=4)

        st = tk.LabelFrame(root, text=" Server giả: device còn online không? ", bg=BG, padx=8, pady=4)
        st.pack(fill="x", padx=14, pady=(0, 6))
        self.status_lbl = tk.Label(st, text="chưa nhận tin nào", font=("Segoe UI", 11, "bold"), bg=BG, fg="#777")
        self.status_lbl.pack(side="left")
        self.net_off = tk.BooleanVar(value=False)
        tk.Checkbutton(st, text="Giả lập MẤT MẠNG (bo ngừng gửi)", variable=self.net_off, bg=BG,
                       command=lambda: setattr(hw, "offline", self.net_off.get())).pack(side="right")

        bottom = tk.Frame(root, bg=BG)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self.matrix = tk.StringVar(value="…")
        tk.Label(bottom, text="Màn LED Yolo:Bit:", bg=BG).pack(anchor="w")
        tk.Label(bottom, textvariable=self.matrix, font=("Consolas", 16, "bold"), fg="#ff4d4d", bg="#111",
                 anchor="w", padx=10, pady=4).pack(fill="x", pady=(0, 6))
        tk.Label(bottom, text="Nhật ký MQTT   (→ data · ▣ control · ⇒ server gửi lệnh · ← bo nhận lệnh)",
                 bg=BG).pack(anchor="w")
        self.log_box = tk.Text(bottom, height=7, bg="#111", fg="#ddd", font=("Consolas", 9), state="disabled")
        self.log_box.pack(fill="x")
        for tag, col in (("data", "#7dd3fc"), ("control", "#c4b5fd"), ("hb", "#94a3b8"), ("cmd", "#fde68a"), ("recv", "#86efac"), ("err", "#fca5a5"),
                         ("info", "#d1d5db")):
            self.log_box.tag_config(tag, foreground=col)

        threading.Thread(target=self.worker, daemon=True).start()
        self.poll()
        self.animate()
        self.check_online()

    # ---------- dựng giao diện ----------
    def add_sensor(self, parent, c, key, label, lo, hi, step):
        tk.Label(parent, text="%s\nupstream: %s/feeds/data.%s" % (label, self.cfg["up_user"], c["model"]), bg=BG,
                 justify="left").pack(anchor="w")
        if key in ("temp", "hum"):
            init = hw.sensors[key]
            cb = lambda v, k=key: hw.sensors.__setitem__(k, float(v))
        else:
            init = 50
            hw.analog[c["pin"]] = init
            cb = lambda v, p=c["pin"]: hw.analog.__setitem__(p, float(v))
        s = tk.Scale(parent, from_=lo, to=hi, resolution=step, orient="horizontal", length=250, command=cb, bg=BG,
                     highlightthickness=0)
        s.set(init)
        s.pack(pady=(0, 10))

    def add_actuator(self, mid, right, c, kind, model, lo, hi):
        pin = c["pin"]
        title = {"fan": "Quạt", "led": "Đèn LED RGB", "curtain": "Rèm (servo)"}[kind]
        box = tk.Frame(mid, bg=BG)
        box.pack(side="left", padx=6)
        tk.Label(box, text="%s – chân %s" % (title, pin), bg=BG).pack()
        cv = tk.Canvas(box, width=200, height=215, bg="white", highlightthickness=1, highlightbackground="#bbb")
        cv.pack()
        self.actuators.append({"pin": pin, "kind": kind, "cv": cv, "model": model, "min_start": c.get("min_start", 0)})
        self.pin_state[pin] = 0

        tk.Label(right, text="%s  (model: %s)\nbáo lại: control.%s" % (title, model, model), bg=BG, justify="left").pack(anchor="w")
        s = tk.Scale(right, from_=lo, to=hi, orient="horizontal", length=230, bg=BG, highlightthickness=0)
        s.set(60 if hi == 100 else 90)
        s.pack()
        row = tk.Frame(right, bg=BG)
        row.pack(pady=(0, 12))
        send = lambda v, m=model: self.send(m, v)
        tk.Button(row, text="Gửi", width=8, command=lambda: send(s.get())).pack(side="left", padx=3)
        tk.Button(row, text="Tắt (0)", width=8, command=lambda: send(0)).pack(side="left", padx=3)
        if hi == 100:
            tk.Button(row, text="Bật 100", width=8, command=lambda: send(100)).pack(side="left", padx=3)

    # ---------- chạy chương trình Yolo:Bit trong luồng riêng ----------
    def worker(self):
        try:
            simcore.run(self.code)
        except Exception as e:                       # lỗi của chương trình Yolo:Bit
            traceback.print_exc()
            hw.emit("log", "err", "Chương trình Yolo:Bit dừng vì lỗi: %r" % (e,))

    def send(self, model, value):
        """Gửi lệnh downstream tới bo (chạy luồng riêng để không treo cửa sổ khi nối mạng)."""
        import simserver

        def job():
            try:
                simserver.send_command(self.cfg, model, value)
            except Exception as e:
                hw.emit("log", "err", "Gửi lệnh lỗi: %r" % (e,))
        threading.Thread(target=job, daemon=True).start()

    # ---------- nhận sự kiện từ chương trình -> cập nhật giao diện ----------
    def poll(self):
        try:
            while True:
                self.handle(hw.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(30, self.poll)

    def handle(self, ev):
        kind = ev[0]
        if kind == "pin":
            self.pin_state[ev[1]] = ev[3]
        elif kind == "rgb":
            self.rgb_state[ev[1]] = ev[2]
        elif kind == "display":
            self.matrix.set(ev[1])
        elif kind == "publish":
            if ev[1].startswith(self.cfg["down_user"] + "/"):          # server gửi lệnh xuống
                self.counts["cmd"] += 1
                self.log("⇒ lệnh %s = %s" % (ev[1].split("/")[-1][-8:], ev[2]), "cmd")
            else:                                                       # bo gửi lên upstream
                tail = ev[1].split("/feeds/")[-1]
                group = tail.split(".")[0]
                self.last_seen = time.time()                            # tin nào cũng chứng tỏ bo còn sống
                if group == "status":
                    self.counts["hb"] += 1
                    self.log("♥ %-22s = %s" % (tail, ev[2]), "hb")
                elif group == "control":
                    self.counts["control"] += 1
                    self.log("▣ %-22s = %s" % (tail, ev[2]), "control")
                else:
                    self.counts["data"] += 1
                    self.log("→ %-22s = %s" % (tail, ev[2]), "data")
        elif kind == "recv":
            self.counts["recv"] += 1
            self.log("← nhận lệnh %s" % ev[2], "recv")
        elif kind == "log":
            self.log(ev[2], ev[1])

    def check_online(self):
        """Cách server tính: quá 3 chu kỳ gửi không có tin nào thì coi là offline."""
        timeout = 3 * self.cfg["heartbeat_ms"] / 1000.0
        if self.last_seen is not None:
            age = time.time() - self.last_seen
            now = "ONLINE" if age <= timeout else "OFFLINE"
            self.status_lbl.configure(
                text="%s   (tin cuối cách đây %ds · quá %ds không có tin ⇒ offline)" % (now, age, timeout),
                fg="#15803d" if now == "ONLINE" else "#b91c1c")
            if now != self.state:
                if self.state is not None:
                    self.log("★ server: device chuyển sang %s" % now, "info" if now == "ONLINE" else "err")
                self.state = now
                self.transitions.append(now)
        self.root.after(300, self.check_online)

    def log(self, text, tag):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n", tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ---------- vẽ hoạt ảnh ----------
    def animate(self):
        for a in self.actuators:
            v = self.pin_state.get(a["pin"], 0)
            cv = a["cv"]
            cv.delete("all")
            if a["kind"] == "fan":
                self.fan_angle = (self.fan_angle + v * 0.5) % 360
                self.draw_fan(cv, v, a["min_start"])
            elif a["kind"] == "led":
                self.draw_led(cv, v, self.rgb_state.get(a["pin"]))
            else:
                self.draw_curtain(cv, v)
        self.root.after(40, self.animate)

    def draw_fan(self, cv, v, min_start):
        cv.create_oval(15, 15, 185, 185, outline="#888", width=4)
        for k in range(3):
            cv.create_arc(25, 25, 175, 175, start=self.fan_angle + k * 120, extent=55, fill="#3b82f6", outline="#1d4ed8")
        cv.create_oval(88, 88, 112, 112, fill="#444", outline="")
        note = "  (dưới %d%% có thể không quay)" % min_start if 0 < v < min_start else ""
        cv.create_text(100, 200, text="%d%%%s" % (v, note), font=("Segoe UI", 9, "bold"))

    def draw_led(self, cv, v, rgb=None):
        if rgb is not None:                                 # đèn RGB: vẽ đúng màu bo đang bật (tắt = xám)
            on = any(rgb)
            if on:
                cv.create_oval(20, 5, 180, 165, fill=mix((255, 255, 255), rgb, 0.55), outline="", stipple="gray25")
            cv.create_oval(55, 35, 145, 125, fill=mix((120, 120, 120), rgb, 1.0) if on else "#787878", outline="#555", width=2)
            cv.create_rectangle(80, 125, 120, 160, fill="#777", outline="#444")
            label = "SÁNG ĐỎ" if tuple(rgb) == (255, 0, 0) else ("SÁNG" if on else "tắt")
            cv.create_text(100, 200, text="%d%%  %s" % (v, label), font=("Segoe UI", 9, "bold"))
            return
        t = v / 100.0
        if v > 0:
            cv.create_oval(20, 5, 180, 165, fill=mix((255, 255, 255), (255, 226, 74), t), outline="", stipple="gray25")
        cv.create_oval(55, 35, 145, 125, fill=mix((120, 120, 120), (255, 226, 74), t), outline="#555", width=2)
        cv.create_rectangle(80, 125, 120, 160, fill="#777", outline="#444")
        cv.create_text(100, 200, text="%d%%  %s" % (v, "SÁNG" if v else "tắt"), font=("Segoe UI", 9, "bold"))

    def draw_curtain(self, cv, angle):
        cv.create_rectangle(25, 25, 175, 175, fill="#bfe3ff", outline="#555", width=4)
        w = (1 - angle / 180.0) * 75                   # 0° = khép kín, 180° = mở hết
        cv.create_rectangle(25, 25, 25 + w, 175, fill="#d97706", outline="#92400e")
        cv.create_rectangle(175 - w, 25, 175, 175, fill="#d97706", outline="#92400e")
        cv.create_line(20, 25, 180, 25, width=4, fill="#444")
        state = "ĐÓNG" if angle <= 5 else ("MỞ HẾT" if angle >= 175 else "mở một phần")
        cv.create_text(100, 200, text="%d°  %s" % (angle, state), font=("Segoe UI", 9, "bold"))

    # ---------- tự kiểm tra (không cần người dùng) ----------
    def selftest(self, hold):
        def step(ms, fn):
            self.root.after(ms, fn)

        t = 1500
        for a in self.actuators:                       # mỗi actuator: bật mạnh rồi (quạt) giảm xuống 20
            step(t, lambda a=a: self.send(a["model"], 180 if a["kind"] == "curtain" else 80))
            t += 400
        for a in self.actuators:
            if a["kind"] == "fan":
                step(t, lambda a=a: self.send(a["model"], 20))
        timeout_ms = int(3 * self.cfg["heartbeat_ms"])
        snap = {}
        first = next((x for x in self.actuators if x["model"] == self.cfg["buttons"]), None)
        if first:                                          # thử nút A rồi nút B
            pin = first["pin"]
            step(t + 300, lambda: hw.press("a"))
            step(t + 900, lambda: snap.__setitem__("sau_nut_A", self.pin_state.get(pin)))
            step(t + 1000, lambda: hw.press("b"))
            step(t + 1600, lambda: snap.__setitem__("sau_nut_B", self.pin_state.get(pin)))
            t += 1700

        def go_offline():
            self.net_off.set(True)
            hw.offline = True
        t_off = t + 1500
        step(t_off, go_offline)
        step(t_off + timeout_ms + 3000, lambda: snap.__setitem__("khi_mat_mang", self.state))

        def go_online():
            self.net_off.set(False)
            hw.offline = False
        t_on = t_off + timeout_ms + 3200
        step(t_on, go_online)
        t_end = t_on + 9000                            # bo thử nối lại mỗi 5 giây
        step(t_end - 500, lambda: snap.__setitem__("sau_khi_co_mang", self.state))

        def report():
            print("SELFTEST", {"pins": self.pin_state, "counts": self.counts, "online": snap,
                               "transitions": self.transitions})
            if not hold:
                self.root.destroy()
        step(int(hold * 1000) if hold else t_end, report)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("device", nargs="?", default=None, help="mặc định: DEVICE khai báo trong yolobit-main.py")
    ap.add_argument("--interval", type=float, default=None, help="chu kỳ gửi cảm biến (giây); bỏ trống = dùng SEND_INTERVAL_MS trong yolobit-main.py")
    ap.add_argument("--heartbeat", type=float, default=None, help="thời gian cơ sở tính offline (mặc định = chu kỳ gửi); quá 3 lần không có tin thì coi là offline")
    ap.add_argument("--local", action="store_true", help="dùng broker GIẢ (không cần mạng)")
    ap.add_argument("--selftest", action="store_true", help="tự gửi vài lệnh, in kết quả rồi thoát")
    ap.add_argument("--hold", type=float, default=0, help="(selftest) giữ cửa sổ N giây rồi mới thoát")
    a = ap.parse_args()
    if a.local:
        os.environ["SIM_BROKER"] = "local"

    code, cfg = simcore.load(a.device, a.interval, a.heartbeat)
    root = tk.Tk()
    root.geometry("940x620+20+10")
    app = App(root, cfg["device"], cfg, code)
    if a.selftest:
        root.attributes("-topmost", True)
        app.selftest(a.hold)
    root.mainloop()


if __name__ == "__main__":
    main()
