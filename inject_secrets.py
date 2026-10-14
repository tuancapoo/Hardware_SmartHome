"""Chèn bí mật (WiFi, AIO key) từ secrets.json vào mã Yolo:Bit.

File yolobit-main.py trên git chỉ chứa giá trị mẫu; giá trị thật nằm trong secrets.json (không commit).
Dùng bởi build.py (tạo file để nạp vào bo) và bởi bộ giả lập.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.join(HERE, "secrets.json")

# Giá trị mẫu: khóa trong secrets.json -> giá trị placeholder trong file trên git
PLACEHOLDERS = {"WIFI_SSID": "TEN_WIFI", "WIFI_PASS": "MAT_KHAU", "UP_KEY": "aio_xxxxxxxx", "DOWN_KEY": "aio_xxxxxxxx"}


def _q(value):
    return json.dumps(value, ensure_ascii=False)


def inject(src, secrets=None):
    """Thay giá trị mẫu trong mã nguồn bằng giá trị thật. Không có secrets.json thì giữ nguyên."""
    if secrets is None:
        if not os.path.exists(SECRETS):
            return src
        with open(SECRETS, encoding="utf-8") as f:
            secrets = json.load(f)
    s = dict(PLACEHOLDERS, **secrets)
    src = re.sub(r'^WIFI_SSID, WIFI_PASS = "[^"]*", "[^"]*"',
                 lambda m: "WIFI_SSID, WIFI_PASS = %s, %s" % (_q(s["WIFI_SSID"]), _q(s["WIFI_PASS"])), src, flags=re.M)
    src = re.sub(r'^(UP_USER, UP_KEY = "[^"]*", )"[^"]*"', lambda m: m.group(1) + _q(s["UP_KEY"]), src, flags=re.M)
    src = re.sub(r'^(DOWN_USER, DOWN_KEY = "[^"]*", )"[^"]*"', lambda m: m.group(1) + _q(s["DOWN_KEY"]), src, flags=re.M)
    return src


def extract(src):
    """Đọc giá trị bí mật hiện có trong mã nguồn (dùng một lần khi tách bí mật ra khỏi file)."""
    m1 = re.search(r'^WIFI_SSID, WIFI_PASS = "([^"]*)", "([^"]*)"', src, flags=re.M)
    m2 = re.search(r'^UP_USER, UP_KEY = "[^"]*", "([^"]*)"', src, flags=re.M)
    m3 = re.search(r'^DOWN_USER, DOWN_KEY = "[^"]*", "([^"]*)"', src, flags=re.M)
    return {"WIFI_SSID": m1.group(1), "WIFI_PASS": m1.group(2), "UP_KEY": m2.group(1), "DOWN_KEY": m3.group(1)}


def sanitize(src):
    """Đưa các giá trị bí mật về giá trị mẫu (để commit lên git)."""
    return inject(src, dict(PLACEHOLDERS))
