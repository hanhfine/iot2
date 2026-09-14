# Bộ demo giao thức IoT — hệ thống tưới cây thông minh + giám sát an ninh (ESP32)

So sánh **MQTT / HTTP / CoAP** trên cùng một kịch bản, đo bằng số thật ở tầng socket,
rồi **chọn ra một giao thức** có căn cứ (ma trận tiêu chí + trọng số) để đem đi demo.

Sản phẩm gồm 3 lệnh, chạy theo thứ tự:

```bash
python compare.py --all --chart    # 18 tổ hợp (3 giao thức × 6 môi trường) — vài phút
python decide.py                   # chấm điểm theo tiêu chí đã chốt -> công bố giao thức chọn
python demo.py                     # bản demo tinh của giao thức vừa chọn (cho người thuyết trình)
```

> **Người tiếp nhận repo** (người 2): đọc [`docs/cho-nguoi-2.md`](docs/cho-nguoi-2.md) —
> bàn giao trạng thái, việc cần làm tiếp, cách thêm giao thức/công nghệ mới, quy ước bắt buộc
> và các lỗi thường gặp.

---

## 1. Cài đặt

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Không cần Internet: broker MQTT, server HTTP và server CoAP đều chạy nội bộ trên
`127.0.0.1`. Chỉ khi muốn thử broker công khai mới cần mạng (`--public`).

## 2. Chạy nhanh để xem kết quả

```bash
python compare.py --all --chart    # 18 tổ hợp (3 giao thức × 6 môi trường) — vài phút
python decide.py                   # đo lại trên loopback rồi chấm điểm
python demo.py                     # demo giao thức thắng, in ra từng chu kỳ
```

Muốn nhanh hơn khi đang phát triển:

```bash
python compare.py                          # chỉ loopback, 8 chu kỳ
python compare.py --links wifi,lora        # chọn môi trường cụ thể
python decide.py --from-results            # dùng lại results/so_sanh.json, không đo lại
python demo.py --fast --cycles 5           # demo ngắn, không nghỉ giữa các sự kiện
```

## 3. Vì sao bộ số liệu này đáng tin

| Nguyên tắc | Nơi thực hiện |
|---|---|
| Tiêu chí + trọng số được **commit TRƯỚC khi đo** | `common/criteria.py` (commit `29b9a2f`, trước mọi số liệu) |
| Cả 3 giao thức chạy **cùng kịch bản, cùng seed** | `common/scenario.py`, `common/logic.py` |
| **Byte đếm thật** ở tầng socket, không ước lượng | `common/wire.py`, `common/metrics.py` |
| Server chạy **tiến trình riêng** nên không lẫn byte client | `common/server_proc.py` |
| Độ trễ đẩy lệnh đo **nhiều mẫu, lấy mẫu nhỏ nhất** | `common/config.py` (`PUSH_SAMPLES`), `protocols/*_demo.py` |
| Kiểm thử tự động chặn hồi quy | `tests/` — 165 test |

Chi tiết đáng lưu ý ở phép đo độ trễ: đây là sự kiện cỡ mili-giây, một mẫu duy nhất
chỉ cần máy bận một nhịp là nhảy lên vài chục ms (đã gặp thật: một mẫu 57 ms trong khi
các mẫu khác ~1 ms). Nhiễu **chỉ làm phép đo chậm đi**, không bao giờ làm nhanh lên
thêm, nên mỗi giao thức đo 3 mẫu và lấy mẫu nhỏ nhất; **cả 3 mẫu đều được lưu** trong
`results/*.json` (`push_samples_ms`) để ai nghi ngờ thì kiểm chứng lại được.

## 4. Kết quả lần chạy gần nhất (loopback, 8 chu kỳ)

| Chỉ số | HTTP | MQTT | CoAP |
|---|---:|---:|---:|
| Byte mỗi chu kỳ | 557.6 B | 163.8 B | **112.4 B** |
| Overhead (header / tổng) | 84.5% | 47.3% | **23.3%** |
| Gói mỗi chu kỳ | 3.33 | 8.67 | **1.00** |
| Byte bắt tay ban đầu | 333 B | 66 B | **37 B** |
| Độ trễ nhận lệnh (không hẹn trước) | 252.1 ms | **1.08 ms** | 1.67 ms |
| Cách đẩy lệnh | polling | subscribe | observe |

Số của lần chạy gần nhất — chạy lại sẽ lệch chút (vài phần nghìn giây), nhưng thứ hạng
giữa 3 giao thức thì không đổi.

**Trên môi trường hẹp (LoRaWAN, tối đa 51 B/gói)** — cả 3 đều phải chia nhỏ gói, nhưng
mức độ chênh nhau rõ rệt:

```
HTTP  558 B/chu ky  ->  phai chia 10.9 goi
MQTT  164 B/chu ky  ->  phai chia  3.2 goi
CoAP  112 B/chu ky  ->  phai chia  2.2 goi
```

Kết luận dùng được cho báo cáo: muốn lên LoRa thì phải bỏ JSON, chuyển sang mã hoá nhị
phân (CBOR/protobuf), và CoAP là điểm xuất phát gần đích nhất.

## 5. Chấm điểm và chọn giao thức

Tiêu chí (đã commit trước khi đo — xem `git log`):

| Tiêu chí | Trọng số | Nguồn điểm |
|---|---:|---|
| Độ trễ cảnh báo an ninh | 25% | đo |
| Server chủ động đẩy lệnh bơm | 25% | đo |
| Byte tiêu thụ mỗi chu kỳ | 20% | đo |
| Chạy nổi trên mạng hẹp (LoRa/NB-IoT) | 15% | đo |
| Tin cậy khi mạng chập chờn | 10% | đặc tính |
| Dễ triển khai & bảo trì | 5% | đặc tính |

Kết quả lần chạy gần nhất: **CoAP 9.44 / MQTT 8.36 / HTTP 1.05** (thang 10).
`decide.py` còn tự kiểm tra **độ vững**: đổi trọng số theo 4 kiểu ưu tiên khác nhau
(tiết kiệm pin, tin cậy, dễ làm, trọng số gốc) — CoAP vẫn thắng cả 4. Nếu hai giao thức
sát điểm (< 0.30/10), script in cảnh báo **HOÀ KỸ THUẬT** thay vì trình bày như thắng dứt khoát.

## 6. Bản demo cho người thuyết trình

```bash
python demo.py                 # tự lấy giao thức đã chọn trong results/quyet_dinh.json
python demo.py --proto MQTT    # muốn demo giao thức khác
```

`demo.py` in ra: kịch bản → dòng thời gian từng chu kỳ (độ ẩm đất, lệnh bơm, relay đổi
trạng thái, cảnh báo PIR) → bảng kết quả so với 2 giao thức còn lại → vì sao chọn giao
thức này → vài câu thoại gợi ý. Mọi số in ra đều là **số đo thật của lần chạy đó** hoặc
lấy nguyên văn từ `results/`.

## 7. Cấu trúc thư mục

| Đường dẫn | Vai trò |
|---|---|
| `compare.py` | Chạy 3 giao thức × 6 môi trường, in bảng so sánh, xuất 5 biểu đồ |
| `decide.py` | Chấm điểm theo ma trận tiêu chí, công bố giao thức chọn, kiểm tra độ vững |
| `demo.py` | Demo tinh giao thức đã chọn — dành cho người 2 chạy trước lớp |
| `common/config.py` | Mọi hằng số dùng chung (seed, chu kỳ, ngưỡng tưới, cổng) |
| `common/scenario.py` | Sinh dữ liệu cảm biến (đất khô dần, bơm thì ẩm lại) — seed cố định |
| `common/logic.py` | Luật điều khiển bơm, dùng chung cho cả 3 giao thức |
| `common/metrics.py` | `ByteCounter` đếm byte thật ở socket + `ProtocolReport` tổng hợp |
| `common/link.py` | Đặc tính 6 công nghệ không dây (Wi-Fi, BLE, Zigbee, LoRa, NB-IoT) |
| `common/criteria.py` | Tiêu chí + trọng số + điểm định tính (đặt trước khi đo) |
| `common/server_proc.py` | Quản lý tiến trình server con |
| `protocols/*_demo.py` | Client thiết bị giả lập + phép đo cho từng giao thức |
| `protocols/*_server.py` | Server trung tâm cho từng giao thức |
| `protocols/mqtt_broker.py` | Broker MQTT nội bộ (chạy offline) |
| `tests/` | 165 test, chạy `.venv/bin/python -m pytest tests/ -q` |
| `results/` | Số liệu + biểu đồ sinh ra khi chạy (không commit — xem `.gitignore`) |

## 8. Kiểm thử

```bash
.venv/bin/python -m pytest tests/ -q      # 165 test, khoảng 2 phút
```

Test được viết theo kiểu "khoá lại kết luận": cùng payload cho cả 3 giao thức, CoAP phải
nhẹ nhất, HTTP phải chậm nhất khi đẩy lệnh, byte UDP đếm được thật, tiêu chí đo được phải
chiếm ≥ 80% trọng số... Nếu ai sửa code làm sai một kết luận, test báo ngay.

## 9. Giới hạn đã biết

- Số liệu là **mô phỏng trên loopback + đặc tính môi trường không dây**, không phải đo
  trên phần cứng ESP32 thật. Phần cứng (Wokwi + ESP32) là demo song song, xem đề tài mẫu.
- Độ trễ trên Wi-Fi/BLE/Zigbee/LoRa/NB-IoT được tính thêm từ thông số chuẩn của từng công
  nghệ (`common/link.py`), không đo bằng thiết bị thật.
- Điểm 2 tiêu chí định tính (tin cậy, dễ triển khai) dựa trên đặc tính giao thức, có ghi
  lý do trong `common/criteria.py` — chiếm 15% tổng điểm, không phải số đo.
