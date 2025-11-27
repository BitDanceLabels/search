# Hướng dẫn chạy dự án & demo API (Postman)
Cách làm (Windows):

Kích hoạt venv dự án (đang ở thư mục search):
PowerShell: .venv\Scripts\Activate.ps1
CMD: .venv\Scripts\activate.bat
Chạy ingest: python main.py
Chạy API: uvicorn ui:app --reload
# Nếu không kích hoạt venv, bạn phải gọi đúng python trong .venv:
uv run python main.py: chạy script Python thuần để deploy Vespa + ingest dữ liệu. Không mở HTTP API của FastAPI. Main.py không dùng Uvicorn; nó chỉ nói chuyện với Docker và Vespa để tạo schema và feed dữ liệu (có thể chỉnh .take(1000) trong file để feed ít).

uv run uvicorn ui:app --reload: chạy server FastAPI (Uvicorn) phục vụ /search. Lệnh này không deploy hay feed dữ liệu; nó giả định Vespa đã chạy sẵn (từ bước main.py).
## 1) Chuẩn bị môi trường
- Yêu cầu: Python 3.10+; Docker/Podman (để chạy Vespa); internet để tải image Vespa và dữ liệu FineWeb.
- Khuyến nghị cài [uv](https://docs.astral.sh/uv/) làm trình quản lý gói: `pip install --upgrade uv`.
- Nếu không dùng uv, có thể `pip install datasets pandas pyvespa fastapi uvicorn tqdm`.

## 2) Tạo file cấu hình `.env` (tùy chọn)
Tạo `.env` tại thư mục gốc với các biến sau (giá trị mặc định đã hợp lý, chỉ cần đổi nếu cần):
```
VESPA_URL=http://localhost
VESPA_PORT=8080
VESPA_RESULT_LIMIT=10
VESPA_MAX_RESULT_LIMIT=100
```

## 3) Cài đặt dependency
- Với uv:
  ```
  uv sync
  ```
- Hoặc với pip:
  ```
  pip install -r requirements.txt  # nếu đã sinh ra
  # Hoặc: pip install datasets pandas pyvespa fastapi uvicorn tqdm
  ```

.venv\Scripts\Activate.ps1


## 4) Khởi động Vespa + ingest dữ liệu
- Lệnh (từ thư mục gốc):
  ```
  python3 main.py
  ```
- Việc này sẽ:
  - Tạo package Vespa (schema BM25) và pull image Vespa qua Docker/Podman.
  - Tải dataset FineWeb (split CC-MAIN-2025-26) và feed vào Vespa.
- Chờ tiến trình feed hoàn tất; log sẽ hiển thị tiến độ và số bản ghi thành công/lỗi.

Chạy lại ingest (deploy Vespa + feed dữ liệu):

Đảm bảo Docker Desktop đang chạy và có mạng.
Tại thư mục dự án, dùng uv (đã cài deps):
uv run python main.py
Nếu muốn feed ít cho nhanh, chỉnh tạm trong main.py sau khi load dataset, ví dụ:
dataset = load_dataset(..., streaming=True).take(1000)
Sau khi tiến trình báo success/feed xong (Vespa container vẫn chạy), mở terminal khác:

uv run uvicorn ui:app --reload
Rồi thử lại Postman.
## 5) Chạy FastAPI UI/API
- Mở terminal khác sau khi Vespa đã sẵn sàng:
  ```
  uvicorn ui:app --reload
  ```
- Truy cập UI web: `http://localhost:8000`.

## 6) Demo API bằng Postman (hoặc curl)
- Endpoint: `POST http://localhost:8000/search`
- Body (JSON):
  ```json
  { "query": "python programming", "limit": 10 }
  ```
- Postman:
  - Method: POST
  - URL: `http://localhost:8000/search`
  - Body: raw → JSON → dán JSON trên
  - Send và xem `hits` (relevance, url, snippet…).
- curl tương đương:
  ```bash
  curl -X POST http://localhost:8000/search \
    -H "Content-Type: application/json" \
    -d '{"query":"python programming","limit":10}'
  ```

## 7) Lưu ý khi demo
- Cần Docker/Podman đang chạy và internet cho bước pull image + tải dữ liệu.
- Nếu muốn giới hạn dữ liệu để feed nhanh hơn, có thể sửa `main.py` để lấy ít mẫu (ví dụ dùng `.take(1000)` trên dataset stream).
- Nếu thay đổi port Vespa/UVicorn, cập nhật `.env` và đảm bảo Postman/curl gọi đúng cổng.

# Nếu muốn feed ít cho nhanh, chỉnh tạm trong main.py sau khi load dataset, ví dụ:
# dataset = load_dataset(..., streaming=True).take(1000)

dataset = load_dataset("HuggingFaceFW/fineweb", "CC-MAIN-2025-26", split="train", streaming=True).take(1000)
vespa_feed = dataset.map(lambda x: {
    "id": x["id"],
    "fields": {
        "text": x["text"],
        "url": x["url"],
        "id": x["id"],
    }
})

# cập nhật data telegram và mapping vào =>> 
dataset = load_dataset("HuggingFaceFW/fineweb", "CC-MAIN-2025-26", split="train", streaming=True)
vespa_feed = dataset.map(lambda x: {
    "id": x["id"],
    "fields": {
        "text": x["text"],
        "url": x["url"],
        "id": x["id"],
    }
})
https://huggingface.co/datasets/HuggingFaceFW/fineweb

# BỔ SUNG : cấu hình bọc wss và fastapi main 
=> để trỏ vô gateway và swaggers 