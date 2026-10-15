# Hardware – Yolo:Bit Nhà thông minh

Code chạy trên bo **Yolo:Bit** (MicroPython) và bộ **giả lập** để thử logic mà không cần bo thật.

Thay các biến ở secrets.jon vào yolobit-main.py
## Bí mật (WiFi, AIO key)

Repo này **công khai**, nên `yolobit-main.py` trên git chỉ chứa giá trị mẫu (`TEN_WIFI`, `aio_xxxxxxxx`).
Giá trị thật nằm trong `secrets.json` (đã `.gitignore`, **không bao giờ commit**):

```bash
cp secrets.example.json secrets.json     # rồi điền WiFi, UP_KEY, DOWN_KEY thật
```

## Nạp vào Yolo:Bit

1. Chọn bo trong `yolobit-main.py`: `DEVICE = "fan"` (`fan` | `light` | `curtain` | `env`).
2. `python build.py` → tạo `dist/yolobit-main.py` (đã có WiFi, key thật).
3. Mở file đó, copy toàn bộ vào tab Python của app.ohstem.vn, bấm **Nạp vào bo**.

## Chạy giả lập

```bash
cd sim
python gui_sim.py                 # cửa sổ hình ảnh, dùng DEVICE khai báo trong yolobit-main.py
python gui_sim.py light           # chọn bo khác (không sửa file)
python gui_sim.py --local         # broker giả, không cần mạng
python run_sim.py                 # chạy trong terminal, gõ lệnh: fan-dc 60, A, B
```

Giả lập tự đọc `secrets.json`. Chế độ mặc định nối Adafruit IO thật (cần `pip install paho-mqtt`).

## Định dạng MQTT (Adafruit IO, hai tài khoản)

| Hướng | Topic | Payload |
|---|---|---|
| Upstream, số đo và giá trị hiện tại | `<UP_USER>/feeds/data.<model>` | `{"deviceId","componentmodelId","val"}` |
| Upstream, khi có lệnh hoặc bấm nút | `<UP_USER>/feeds/control.<model>` | `{"deviceId","componentmodelId","mode","val","source"}` |
| Downstream, lệnh xuống bo | `<DOWN_USER>/feeds/<deviceId>` | `{"componentmodelId","mode","val"}` |

Dùng khóa **`val`**, không dùng `value`: Adafruit IO thấy khóa `value` sẽ chỉ giữ lại con số.
Mỗi bo gửi `data` mỗi `SEND_INTERVAL_MS` (30 s); không còn nhịp tim riêng, mọi tin upstream đều là tín hiệu còn sống.
