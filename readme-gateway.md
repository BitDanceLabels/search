# Gateway Registration Guide

This service can auto-register its routes into a gateway. Use the envs below and restart to re-register.
#
.\.venv\Scripts\python -m ensurepip
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install python-dotenv==1.0.1
uvicorn ui:app --host 0.0.0.0 --port 8044 --env-file .env

uvicorn ui:app --host 0.0.0.0 --port 8044

## Required env
- `SERVICE_NAME`: unique name (e.g. `simple-search`).
- `SERVICE_BASE_URL`: where the gateway calls this service (e.g. `http://127.0.0.1:8000`).
- `GATEWAY_URL`: gateway base URL (e.g. `http://127.0.0.1:30090`). If empty, registration is skipped.
- `GATEWAY_PREFIX`: optional path prefix to avoid collisions (e.g. `/ai-search`).
- `REGISTER_RETRIES` / `REGISTER_DELAY`: retry policy (default 5 / 1.0).

## How it works
- `ui.py` calls `register_with_gateway` (from `gateway_register.py`) on startup.
- It POSTs to `${GATEWAY_URL}/gateway/register` with the service metadata and routes:
  - `/search`
  - `/search/bm25`
  These get prefixed if `GATEWAY_PREFIX` is set.

## Run and verify
1) Export envs (example):
```bash
export SERVICE_NAME=simple-search
export SERVICE_BASE_URL=http://127.0.0.1:8000
export GATEWAY_URL=http://127.0.0.1:30090
export GATEWAY_PREFIX=/ai-search   # optional
```
2) Start the service:
```bash
uvicorn ui:app --host 0.0.0.0 --port 8044
```
3) Check logs for: `Gateway registered: service=simple-search ... routes=2`.
4) Open gateway Swagger to confirm the routes exist (with prefix if set).
5) When host/port/prefix changes, update envs and restart to re-register.

### One-liner run (example)
Chạy kèm env trong một lệnh (đổi giá trị nếu cần):
```bash
SERVICE_NAME=simple-search \
SERVICE_BASE_URL=http://127.0.0.1:8044 \
GATEWAY_URL=http://127.0.0.1:30090 \
GATEWAY_PREFIX=/ai-search \
uvicorn ui:app --host 0.0.0.0 --port 8044
```
Nếu gateway không reachable, log sẽ báo lỗi đăng ký nhưng app vẫn chạy; cần đảm bảo `GATEWAY_URL` đúng và gateway đang mở cổng.

## Common pitfalls
- Wrong base URLs: `SERVICE_BASE_URL` must be where this service is reachable; `GATEWAY_URL` must point to the gateway, not vice versa.
- Prefix mismatch: if you set `GATEWAY_PREFIX`, call the gateway using that prefix to avoid 404.
- Gateway unavailable: registration will retry; if all retries fail, the service still starts but routes will not be mapped until next restart with a reachable gateway.
