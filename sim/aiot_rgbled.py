"""RGBLed giả (thư viện aiot_rgbled của OhStem): in màu ra console và báo cho GUI vẽ đèn."""
import hw


class RGBLed:
    def __init__(self, pin, count=4):
        self.pin, self.count = pin, count
        self.name = getattr(pin, "name", "?")
        self.colors = [(0, 0, 0)] * count

    def show(self, index, color):
        """index 0 = tất cả LED, 1..count = từng LED; color = (r, g, b)."""
        color = tuple(int(c) for c in color)
        for i in (range(self.count) if index == 0 else [index - 1]):
            self.colors[i] = color
        print("    [%s] RGB LED %s = (%d, %d, %d)" % (self.name, "tất cả" if index == 0 else index, *color))
        on = any(any(c) for c in self.colors)
        hw.emit("pin", self.name, "pwm", 100 if on else 0)      # trạng thái bật/tắt cho các phần dùng số
        hw.emit("rgb", self.name, self.colors[0])               # màu để GUI vẽ
