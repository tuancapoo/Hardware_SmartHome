"""Tạo dist/yolobit-main.py (đã điền WiFi và key thật) để dán / nạp vào Yolo:Bit bằng OhStem.

    python build.py

File trong dist/ chứa bí mật nên đã nằm trong .gitignore, không bao giờ commit.
"""
import os
import sys

from inject_secrets import PLACEHOLDERS, SECRETS, HERE, inject

if hasattr(sys.stdout, "reconfigure"):             # console Windows mặc định không in được tiếng Việt
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = os.path.join(HERE, "yolobit-main.py")
OUT = os.path.join(HERE, "dist", "yolobit-main.py")


def main():
    if not os.path.exists(SECRETS):
        sys.exit("Chưa có secrets.json. Sao chép secrets.example.json thành secrets.json rồi điền WiFi và AIO key.")
    with open(SRC, encoding="utf-8") as f:
        out = inject(f.read())
    left = [k for k, v in PLACEHOLDERS.items() if '"%s"' % v in out]
    if left:
        print("Cảnh báo: vẫn còn giá trị mẫu cho:", ", ".join(left))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out)
    print("Đã tạo", OUT)
    print("Mở file này, copy toàn bộ vào tab Python của OhStem rồi nạp vào bo.")


if __name__ == "__main__":
    main()
