"""Cấu hình tập trung cho toàn bộ bộ demo.

Mọi hằng số dùng chung nằm ở đây để 3 giao thức chạy trên CÙNG điều kiện.
Sửa 1 chỗ, cả 3 demo cùng đổi -> so sánh mới công bằng.
"""
from __future__ import annotations

# ---------------------------------------------------------------- kịch bản
SEED = 42               # cố định -> chạy lại cho ra đúng dãy số cũ
CYCLES = 15             # số chu kỳ đo mỗi lần chạy
CYCLE_INTERVAL = 0.5    # giây giữa 2 chu kỳ (demo nhanh; thực tế 3-60s)

# ------------------------------------------------------------ luật tưới
SOIL_DRY = 40.0         # dưới ngưỡng này -> bật bơm
SOIL_WET = 70.0         # trên ngưỡng này -> tắt bơm

# --------------------------------------------------------------- an ninh
# Cứ mỗi N chu kỳ thì giả lập PIR phát hiện chuyển động.
SECURITY_EVERY = 5

# ----------------------------------------------------------------- MQTT
MQTT_LOCAL_HOST = "127.0.0.1"
MQTT_LOCAL_PORT = 1884          # tránh đụng 1883 nếu máy đã có mosquitto
MQTT_PUBLIC_HOST = "broker.emqx.io"
MQTT_PUBLIC_PORT = 1883

TOPIC_TELEMETRY = "smartgarden/v1/telemetry"
TOPIC_SECURITY = "smartgarden/v1/security"
TOPIC_COMMAND = "smartgarden/v1/command"

# ----------------------------------------------------------------- HTTP
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 5001                # 5000 hay bị AirPlay trên macOS chiếm
HTTP_TELEMETRY_PATH = "/api/garden/telemetry"
HTTP_SECURITY_PATH = "/api/security/intrusion-alert"

# ----------------------------------------------------------------- CoAP
COAP_HOST = "127.0.0.1"
COAP_PORT = 5683
COAP_TELEMETRY_PATH = "garden/telemetry"
COAP_SECURITY_PATH = "security/intrusion"

# ------------------------------------------------------------- thiết bị
DEVICE_ID = "esp32_garden_01"
ZONE = "Khu vuc vuon sau"

# ------------------------------------------------- đo độ trễ đẩy lệnh
# Mỗi giao thức đo độ trễ đẩy lệnh bao nhiêu lần. Đây là sự kiện cỡ
# mili-giây nên một mẫu duy nhất rất dễ bị nhiễu (máy bận -> mẫu vọt lên
# vài chục ms). Nhiễu chỉ làm phép đo CHẬM ĐI, không làm nhanh lên thêm,
# nên các demo lấy mẫu NHỎ NHẤT trong số này và lưu lại mọi mẫu để đối chiếu.
PUSH_SAMPLES = 3

# ------------------------------------------------------------- kết quả
RESULTS_DIR = "results"
