"""DHT20 giả: GUI thì lấy từ slider, console thì dao động ngẫu nhiên."""
import random
import hw


class DHT20:
    def __init__(self, i2c):
        pass

    def read_dht20(self):
        if not hw.gui:
            hw.sensors["temp"] = max(15.0, min(45.0, hw.sensors["temp"] + random.uniform(-0.6, 0.6)))
            hw.sensors["hum"] = max(20.0, min(95.0, hw.sensors["hum"] + random.uniform(-1.5, 1.5)))

    def dht20_temperature(self):
        return round(hw.sensors["temp"], 1)

    def dht20_humidity(self):
        return round(hw.sensors["hum"], 1)
