# Lipay Python SDK

Official Python client for [Lipay](https://message.lipay.store) — the developer platform for WhatsApp messaging, routing, and Customer Service Window (CSW) management across Africa.

Use this library in your application (BrandFlow, Teacher, custom backends) to check whether the Meta **24-hour customer service window** is open before sending free-text WhatsApp messages.

---

## Installation

**From Git (tagged release):**

```bash
pip install "lipay-sdk[fastapi] @ git+https://github.com/Evans-musamia/lipay-python-sdk.git@v1.0.0"
```

**Core only (no FastAPI extra):**

```bash
pip install git+https://github.com/Evans-musamia/lipay-python-sdk.git@v1.0.0
```

**Editable (local development):**

```bash
git clone https://github.com/Evans-musamia/lipay-python-sdk.git
cd lipay-python-sdk
pip install -e ".[dev]"
```

---

## Quick start

```python
import asyncio

from lipay_sdk import LipayCswSessionGuard


async def main() -> None:
    guard = LipayCswSessionGuard("https://message.lipay.store")

    active = await guard.is_window_active(
        customer_phone="+254700000000",
        business_phone="+254711111111",
    )

    if active:
        print("CSW open — safe to send free-text via Lipay /v1/whatsapp/send")
    else:
        print("CSW closed — send an approved template first")

    await guard.close()


if __name__ == "__main__":
    asyncio.run(main())
```

### Configuration object (Pydantic)

For explicit control over timeouts, cache TTL, and API paths:

```python
from lipay_sdk.csw_session_guard import LipayCswSessionGuard, LipaySdkConfig

config = LipaySdkConfig(
    gateway_url="https://message.lipay.store",
    local_active_ttl_seconds=180,
    http_timeout_seconds=10.0,
)
guard = LipayCswSessionGuard(config)
```

### Full status payload

```python
status = await guard.get_session_status(
    customer_phone="254700000000",
    business_phone="254711111111",
)
print(status.is_communication_window_active, status.window_expires_at)
```

---

## Caching behavior

The SDK implements an **in-process memory guard** in front of Lipay's Redis-backed `GET /api/v1/switchboard/session-status` endpoint.

| Event | Behavior |
|--------|----------|
| Lipay returns `active=true` | Response cached in your app process RAM for **180 seconds** (configurable via `LipaySdkConfig.local_active_ttl_seconds`) |
| Repeat lookup within TTL | Served from local memory — **no HTTP call** to Lipay |
| Lipay returns `active=false` | **Never cached** — every lookup hits Lipay |
| Local TTL expires | Cache entry dropped; next lookup syncs from Lipay |

This mirrors how Twilio-style SDKs reduce read amplification: your container avoids redundant session-status traffic while the gateway remains the source of truth on Redis.

---

## FastAPI integration

Install the optional extra:

```bash
pip install "lipay-sdk[fastapi] @ git+https://github.com/Evans-musamia/lipay-python-sdk.git@v1.0.0"
```

Wire the guard on application startup:

```python
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request

from lipay_sdk import LipayCswSessionGuard
from lipay_sdk.csw_session_guard import LipaySdkConfig


@asynccontextmanager
async def lifespan(app: FastAPI):
    http = httpx.AsyncClient(timeout=10.0)
    config = LipaySdkConfig(gateway_url="https://message.lipay.store")
    app.state.lipay_guard = LipayCswSessionGuard(config, http_client=http)
    yield
    await app.state.lipay_guard.close()


app = FastAPI(lifespan=lifespan)


def get_guard(request: Request) -> LipayCswSessionGuard:
    return request.app.state.lipay_guard


@app.get("/check-window")
async def check_window(
    customer_phone: str,
    business_phone: str,
    guard: LipayCswSessionGuard = Depends(get_guard),
):
    return await guard.get_session_status(
        customer_phone=customer_phone,
        business_phone=business_phone,
    )
```

---

## API reference

### `LipayCswSessionGuard`

| Method | Description |
|--------|-------------|
| `is_window_active(customer_phone, business_phone)` | `bool` — CSW open for pair |
| `get_session_status(...)` | `SessionStatus` — full gateway payload |
| `fetch_from_lipay(...)` | Always calls Lipay (bypasses local cache) |
| `close()` | Close owned `httpx` client |

### `LipaySdkConfig` (Pydantic)

| Field | Default | Description |
|-------|---------|-------------|
| `gateway_url` | required | Lipay gateway base URL |
| `local_active_ttl_seconds` | `180` | Local RAM cache TTL |
| `http_timeout_seconds` | `5.0` | HTTP client timeout |
| `session_status_path` | `/api/v1/switchboard/session-status` | Status endpoint path |

---

## License

MIT — see [LICENSE](LICENSE).
