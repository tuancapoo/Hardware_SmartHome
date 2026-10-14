"""Yolo:Bit giả: chân, màn hình LED. In ra console và báo cho GUI."""
import random
import hw


class FakePin:
    def __init__(self, name):
        self.name = name
        self._v = random.randint(1500, 3000)

    def write_analog(self, v):
        pct = round(v * 100 / 1023)
        print("    [%s] write_analog(%d)  ~ %d%%" % (self.name, v, pct))
        hw.emit("pin", self.name, "pwm", pct)

    def write_digital(self, v):
        print("    [%s] write_digital(%d)" % (self.name, v))
        hw.emit("pin", self.name, "pwm", 100 if v else 0)

    def servo_write(self, angle):
        print("    [%s] servo_write(%d°)" % (self.name, angle))
        hw.emit("pin", self.name, "servo", angle)

    def read_analog(self):
        if hw.gui:                                   # lấy từ slider trên GUI
            return round(hw.analog.get(self.name, 50) * 4095 / 100)
        self._v = max(0, min(4095, self._v + random.randint(-150, 150)))
        return self._v


for _i in range(17):
    globals()["pin%d" % _i] = FakePin("P%d" % _i)


class _Button:
    def __init__(self, name):
        self.name = name

    def is_pressed(self):
        return hw.buttons[self.name]


button_a, button_b = _Button("a"), _Button("b")


class Image:
    YES = "[ OK ]"
    NO = "[ XX ]"
    ARROW_E = "[ -> ]"


class _Display:
    def scroll(self, text):
        print("  LED> chạy chữ:", text)
        hw.emit("display", str(text))

    def show(self, img):
        print("  LED> hiện:", img)
        hw.emit("display", str(img))


display = _Display()
