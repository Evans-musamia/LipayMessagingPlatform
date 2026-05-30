"""
Customer Service Window (CSW) session guard for Lipay tenant applications.

Queries Lipay's Redis-backed session-status API with an in-process TTL cache
so active-window lookups avoid redundant network round-trips.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field, field_validator


def _normalize_phone(phone: str) -> str:
    cleaned = phone.strip().replace(" ", "").replace("-", "")
    if not cleaned:
        return cleaned
    if not cleaned.startswith("+"):
        return f"+{cleaned.lstrip('+')}"
    return cleaned


class LipaySdkConfig(BaseModel):
    """Runtime configuration for the Lipay HTTP client and local cache."""

    gateway_url: str = Field(
        ...,
        description="Lipay gateway base URL, e.g. https://message.lipay.store",
        min_length=8,
    )
    local_active_ttl_seconds: int = Field(
        default=180,
        ge=0,
        description="In-process cache TTL after a successful active=true response",
    )
    http_timeout_seconds: float = Field(default=5.0, gt=0)
    session_status_path: str = Field(
        default="/api/v1/switchboard/session-status",
        description="Path appended to gateway_url for CSW lookups",
    )

    @field_validator("gateway_url", "session_status_path")
    @classmethod
    def strip_slashes(cls, value: str) -> str:
        return value.strip()


class SessionStatus(BaseModel):
    """Normalized response from Lipay session-status."""

    customer_phone_number: str
    business_phone_number: str
    is_communication_window_active: bool
    window_expires_at: str | None = None

    @classmethod
    def from_api_payload(cls, payload: dict[str, Any]) -> SessionStatus:
        return cls.model_validate(payload)


class LipayCswSessionGuard:
    """
    In-process TTL cache + Lipay ``GET /api/v1/switchboard/session-status`` client.

    Use before outbound free-text WhatsApp sends to confirm the 24-hour CSW is open.
    """

    def __init__(
        self,
        config: LipaySdkConfig | str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if isinstance(config, str):
            config = LipaySdkConfig(gateway_url=config)
        self._config = config
        self._base_url = config.gateway_url.rstrip("/")
        self._status_path = (
            config.session_status_path
            if config.session_status_path.startswith("/")
            else f"/{config.session_status_path}"
        )
        self._http = http_client
        self._owns_client = http_client is None
        self._local: dict[str, tuple[SessionStatus, float]] = {}

    @property
    def config(self) -> LipaySdkConfig:
        return self._config

    def _pair_key(self, business_phone: str, customer_phone: str) -> str:
        return f"{_normalize_phone(business_phone)}:{_normalize_phone(customer_phone)}"

    def _read_local(self, pair_key: str) -> SessionStatus | None:
        entry = self._local.get(pair_key)
        if not entry:
            return None
        payload, expires_at = entry
        if time.monotonic() >= expires_at:
            self._local.pop(pair_key, None)
            return None
        return payload

    def _write_local_active(self, pair_key: str, status: SessionStatus) -> None:
        ttl = self._config.local_active_ttl_seconds
        self._local[pair_key] = (status, time.monotonic() + ttl)

    def _clear_local(self, pair_key: str) -> None:
        self._local.pop(pair_key, None)

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._config.http_timeout_seconds)
        return self._http

    async def close(self) -> None:
        if self._owns_client and self._http is not None:
            await self._http.aclose()
            self._http = None

    async def fetch_from_lipay(
        self,
        *,
        customer_phone: str,
        business_phone: str,
    ) -> SessionStatus:
        params = urlencode(
            {
                "customer_phone": customer_phone.lstrip("+"),
                "business_phone": business_phone.lstrip("+"),
            }
        )
        url = f"{self._base_url}{self._status_path}?{params}"
        client = await self._client()
        response = await client.get(url)
        response.raise_for_status()
        return SessionStatus.from_api_payload(response.json())

    async def get_session_status(
        self,
        *,
        customer_phone: str,
        business_phone: str,
    ) -> SessionStatus:
        """Return CSW status — local memory first, then Lipay gateway."""
        pair_key = self._pair_key(business_phone, customer_phone)

        cached = self._read_local(pair_key)
        if cached is not None:
            return cached

        status = await self.fetch_from_lipay(
            customer_phone=customer_phone,
            business_phone=business_phone,
        )

        if status.is_communication_window_active:
            self._write_local_active(pair_key, status)
        else:
            self._clear_local(pair_key)

        return status

    async def is_window_active(
        self,
        *,
        customer_phone: str,
        business_phone: str,
    ) -> bool:
        """
        Convenience API: ``True`` when the Meta 24-hour CSW is open for this pair.

        Example::

            guard = LipayCswSessionGuard("https://message.lipay.store")
            if await guard.is_window_active(
                customer_phone="+254700000000",
                business_phone="+254711111111",
            ):
                ...
        """
        status = await self.get_session_status(
            customer_phone=customer_phone,
            business_phone=business_phone,
        )
        return status.is_communication_window_active

    def is_communication_window_active(self, status: SessionStatus | dict[str, Any]) -> bool:
        """Evaluate a status object returned by :meth:`get_session_status`."""
        if isinstance(status, SessionStatus):
            return status.is_communication_window_active
        return bool(status.get("is_communication_window_active"))
