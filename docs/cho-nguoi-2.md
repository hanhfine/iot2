# Bàn giao cho người 2 — làm việc tiếp với bộ demo giao thức IoT

Tài liệu này viết cho người tiếp nhận repo: **chạy được demo trước lớp**, và nếu muốn thì
**phát triển tiếp code**. Phần code đã xong 7/7 bước; việc còn lại là của con người (chạy
demo, làm slide/báo cáo) và các hướng mở rộng ở mục 4.

Đọc kèm: `README.md` (tổng quan + số liệu) và `de_tai_mau.txt` (đề tài mẫu của thầy).

---

## 1. Chạy thử trong 5 phút

`results/` không nằm trong git (số liệu sinh ra khi chạy), nên lần đầu phải đo:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python compare.py                          # ~1 phút: loopback, 3 giao thức
python decide.py                           # chấm điểm, công bố giao thức chọn
python demo.py --fast                       # demo giao thức đã chọn
```

Máy bạn 2 cần: Python 3.11+, không cần Internet (broker/server đều chạy nội bộ trên
`127.0.0.1`).

## 2. Trạng thái hiện tại

| Bước | Nội dung | File | Commit |
|---|---|---|---|
| 1 | Khung chung (kịch bản, luật tưới, đếm byte) | `common/` | `059ad49` |
| — | **Tiêu chí + trọng số (đặt TRƯỚC khi đo)** | `common/criteria.py` | `29b9a2f` |
| 2 | HTTP demo | `protocols/http_*` | `70a5759` |
| 3 | MQTT demo + broker nội bộ | `protocols/mqtt_*` | `e3c8b2a` |
| 4 | CoAP demo + Observe | `protocols/coap_*` | `12e4ccb` |
| 5 | So sánh 3 giao thức × 6 môi trường + biểu đồ | `compare.py` | `086e615` |
| 6 | Ma trận quyết định, chọn giao thức, kiểm tra độ vững | `decide.py` | `0b5e505` |
| 7 | Demo tinh cho người thuyết trình | `demo.py` | `13fc5e0` |

**Kết luận đã chốt: chọn CoAP** — 9.44/10, so với MQTT 8.36 và HTTP 1.05. CoAP thắng ở cả
4 cách đánh trọng số khác nhau (xem phần "KIỂM TRA ĐỘ VỮNG" khi chạy `decide.py`).

| Chỉ số (loopback, 8 chu kỳ) | HTTP | MQTT | CoAP |
|---|---:|---:|---:|
| Byte mỗi chu kỳ | 557.6 B | 163.8 B | **112.4 B** |
| Overhead | 84.5% | 47.3% | **23.3%** |
| Gói mỗi chu kỳ | 3.33 | 8.67 | **1.00** |
| Độ trễ nhận lệnh (không hẹn trước) | 252.1 ms | **1.08 ms** | 1.67 ms |
| Cách đẩy lệnh | polling | subscribe | observe |

**Đánh đổi phải nói rõ khi bảo vệ:** CoAP chỉ 7/10 về tin cậy (MQTT 9/10 — có QoS 0/1/2,
Last Will, Retained message) và 5/10 về dễ triển khai (MQTT 6, HTTP 9). Nếu nhóm đổi ưu
tiên sang "không được mất cảnh báo" thì MQTT là lựa chọn hợp lý — đổi trọng số trong
`common/criteria.py` rồi chạy lại `decide.py`, đừng sửa kết luận bằng tay.

## 3. Việc tiếp theo — chọn theo thời gian bạn có

### A. Chỉ cần demo trước lớp (~30 phút)
1. Chạy `python demo.py` một lần trước ở nhà, xem dòng thời gian in ra có dễ đọc không.
2. Viết ra giấy 3 con số bạn muốn nhấn: **1.08 ms** (đẩy lệnh MQTT) / **252 ms** (HTTP phải
   chờ polling) / **112 B mỗi chu kỳ** (CoAP).
3. Trước giờ demo: tắt các tiến trình cũ (`pkill -f "http_server|coap_server|mqtt_"`), chạy
   lại `python demo.py` xem có lên không.

### B. Làm slide / báo cáo
Nguồn số liệu, không cần tự đo lại:

| Cần gì | Lấy ở đâu |
|---|---|
| Bảng so sánh 3 giao thức | màn hình `python compare.py`, hoặc `results/so_sanh.json` |
| 5 biểu đồ (byte, overhead, gói, RTT, độ trễ lệnh) | `results/*.png` — `python compare.py --all --chart` |
| Bảng điểm có trọng số + lý do | `results/quyet_dinh.json`, hoặc chạy `python decide.py` |
| Số liệu cho "việc 1" (chọn công nghệ không dây) | `python compare.py --all` — cột LoRa/NB-IoT/Zigbee |

Điểm đáng trích nhất cho việc 1:

```
LoRaWAN (payload toi da 51 B):
  HTTP  558 B/chu ky -> phai chia 10.9 goi
  MQTT  164 B/chu ky -> phai chia  3.2 goi
  CoAP  112 B/chu ky -> phai chia  2.2 goi
```

### C. Phát triển tiếp code
Xem mục 4 và 5.

## 4. Thêm một giao thức mới (ví dụ WebSocket)

1. Viết `protocols/websocket_demo.py` với hàm
   `run(link_profile="ideal", cycles=..., verbose=True, manage_server=True) -> ProtocolReport`
   (giống `protocols/http_demo.py`). Bắt buộc:
   - `ProtocolReport(protocol="WebSocket", transport="TCP", push_method=...)`,
     `l3_bytes_per_packet=40` cho TCP, `28` cho UDP;
   - đếm byte **thật ở tầng socket** bằng `common.wire.count_socket_bytes()` — đừng ước lượng;
   - server chạy bằng `common.server_proc.ServerProcess` (tiến trình riêng, nếu không byte
     của server sẽ bị cộng lẫn vào client);
   - đo độ trễ đẩy lệnh `config.PUSH_SAMPLES` lần, lấy **min**, lưu `report.push_samples_ms`.
2. Đăng ký ở **3 nơi**: `compare.py` (`PROTOCOLS` + nhánh trong `run_one`), `decide.py`
   (`PROTOCOLS`), `demo.py` (`PROTOCOLS`).
3. `common/criteria.py`: thêm điểm định tính `reliability` + `simplicity` và lý do trong
   `QUALITATIVE_RATIONALE` cho giao thức mới. **Bắt buộc** — `tests/test_decide.py` sẽ đỏ nếu
   thiếu, vì mọi giao thức đều phải có điểm định tính đã công bố.
4. `tests/test_compare.py::test_du_ba_giao_thuc` đang khoá cứng 3 giao thức — sửa có ý thức
   (đây là chỗ cố tình bắt bạn xác nhận việc thêm giao thức).
5. Viết `tests/test_<ten>.py` (theo mẫu `tests/test_http.py`). Lưu ý: `test_compare.py` kiểm
   tra **payload của mọi giao thức phải bằng nhau** — giao thức mới phải dùng
   `common/scenario.py` để sinh dữ liệu, không tự random.
6. Chạy `.venv/bin/python -m pytest tests/ -q`, rồi `python compare.py --all --chart` và
   `python decide.py` để xem giao thức mới có làm đổi người thắng không. Nếu đổi thì ghi rõ
   trong báo cáo — **không chỉnh tiêu chí cho khớp kết quả**.

## 5. Thêm một công nghệ không dây mới

`common/link.py`: thêm một `LinkProfile(...)` (băng thông, độ trễ, payload tối đa, năng
lượng/byte, tầm) rồi đưa vào tuple trong `PROFILES` và vào `PROFILE_ORDER`. Sau đó cập nhật
`tests/test_compare.py::test_du_sau_moi_truong` (đang đếm `len(PROFILE_ORDER) == 6`).

## 6. Quy ước bắt buộc — đừng phá

| Quy ước | Vì sao |
|---|---|
| Tiêu chí + trọng số đặt **trước** khi đo; muốn đổi thì commit việc đổi trước, rồi mới chạy | `git log` là bằng chứng không chọn tiêu chí cho khớp kết quả |
| Mỗi kết luận phải có test khoá lại | Sửa code làm sai kết luận thì test báo ngay |
| Số liệu in ra phải là **số đo thật**, không hard-code, không bịa | Đây là chỗ dễ mất điểm nhất khi bảo vệ |
| Độ trễ phải đo nhiều mẫu và lưu **cả** các mẫu | Một mẫu duy nhất đã từng cho MQTT 57 ms thay vì ~1 ms |
| Byte đếm ở tầng socket; server luôn chạy tiến trình riêng | Nếu không, byte hai phía bị cộng lẫn |
| Test và output in ra dùng ASCII (không dấu); tài liệu thì viết có dấu | Tránh vỡ hiển thị trên terminal khác nhau |

## 7. Sự cố thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `OSError: [Errno 48] Address already in use` | Cổng đang bị chiếm: HTTP 5001, CoAP 5683, MQTT 1884. `pkill -f "http_server\|coap_server\|mqtt_broker"` rồi chạy lại |
| Broker MQTT báo `can not match "max-connections"` | amqtt ≥ 0.12 đổi sang tên trường gạch dưới: `max_connections` (đã sửa trong `protocols/mqtt_broker.py`) |
| Đếm byte CoAP ra 0 | aiocoap không gọi `socket.send`; phải dùng `_count_datagrams()` trong `protocols/coap_demo.py` |
| Một test đỏ lẻ tẻ rồi lần sau lại xanh | Nghi phép đo nhiễu: chạy lại vài lần; nếu đúng thì tăng `PUSH_SAMPLES` trong `common/config.py` |
| Suite chạy lâu/chập chờn | Cả bộ test mất ~2 phút và có mở cổng, nên **đừng chạy 2 lần pytest song song** |

## 8. Đọc code theo thứ tự nào

1. `common/config.py` — mọi hằng số dùng chung.
2. `common/scenario.py` + `common/logic.py` — kịch bản và luật tưới (3 giao thức dùng chung).
3. `common/metrics.py` + `common/wire.py` — đếm byte thật và tổng hợp số liệu.
4. `protocols/http_demo.py` — mẫu dễ nhất để hình dung một giao thức được đo thế nào.
5. `compare.py` → `decide.py` → `demo.py`.

## 9. Ba câu dễ bị hỏi khi bảo vệ — và trả lời có số

- **"Sao chọn CoAP mà không phải MQTT?"** → CoAP 9.44 / MQTT 8.36 theo ma trận đã chốt
  trước khi đo. CoAP thắng ở cả 4 cách đánh trọng số. Nhưng nói rõ đánh đổi: CoAP 7/10 về
  tin cậy, MQTT 9/10.
- **"Sao không dùng HTTP cho đơn giản?"** → HTTP phải polling nên lệnh xuống thiết bị mất
  252 ms (MQTT/CoAP ~1 ms), overhead 84.5%, và trên LoRa phải chia 10.9 gói mỗi chu kỳ.
- **"Số liệu này đo thật hay chép?"** → ba bằng chứng: (1) `git log` cho thấy tiêu chí commit
  `29b9a2f` trước mọi số liệu; (2) byte đếm ở tầng socket bằng `ByteCounter`; (3) mỗi lần đo
  độ trễ đều lưu cả 3 mẫu trong `results/*.json` để kiểm chứng lại.

## 10. Liên hệ / còn thiếu gì

- Trong repo này **chưa có**: phần cứng thật (ESP32 + Wokwi) — nằm ở phần mô phỏng Wokwi của
  `de_tai_mau.txt`; slide; báo cáo viết tay.
- Điểm yếu đã biết: các môi trường không dây (Wi-Fi/BLE/Zigbee/LoRa/NB-IoT) được mô phỏng
  theo thông số chuẩn của chuẩn, không đo trên thiết bị thật (`common/link.py`).
