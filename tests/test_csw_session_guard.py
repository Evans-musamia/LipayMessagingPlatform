"""Unit tests for lipay_sdk.csw_session_guard."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from lipay_sdk import LipayCswSessionGuard
from lipay_sdk.csw_session_guard import LipaySdkConfig, SessionStatus


ACTIVE = SessionStatus(
    customer_phone_number="+254700000000",
    business_phone_number="+254711111111",
    is_communication_window_active=True,
    window_expires_at="2026-06-01T15:30:22Z",
)

INACTIVE = SessionStatus(
    customer_phone_number="+254700000000",
    business_phone_number="+254711111111",
    is_communication_window_active=False,
    window_expires_at=None,
)


def test_config_from_string_gateway_url():
    guard = LipayCswSessionGuard("https://message.lipay.store")
    assert guard.config.gateway_url == "https://message.lipay.store"


def test_config_pydantic_overrides():
    config = LipaySdkConfig(
        gateway_url="https://message.lipay.store",
        local_active_ttl_seconds=60,
        session_status_path="/api/v1/switchboard/session-status",
    )
    guard = LipayCswSessionGuard(config)
    assert guard.config.local_active_ttl_seconds == 60


@pytest.mark.asyncio
async def test_is_window_active_true():
    guard = LipayCswSessionGuard("https://message.lipay.store")
    with patch.object(
        guard, "fetch_from_lipay", new_callable=AsyncMock, return_value=ACTIVE
    ):
        assert await guard.is_window_active(
            customer_phone="254700000000",
            business_phone="254711111111",
        )


@pytest.mark.asyncio
async def test_local_cache_skips_second_fetch():
    guard = LipayCswSessionGuard("https://message.lipay.store")
    with patch.object(
        guard, "fetch_from_lipay", new_callable=AsyncMock, return_value=ACTIVE
    ) as mock_fetch:
        await guard.get_session_status(
            customer_phone="254700000000",
            business_phone="254711111111",
        )
        await guard.get_session_status(
            customer_phone="254700000000",
            business_phone="254711111111",
        )
    mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_inactive_never_cached():
    guard = LipayCswSessionGuard("https://message.lipay.store")
    with patch.object(
        guard, "fetch_from_lipay", new_callable=AsyncMock, return_value=INACTIVE
    ) as mock_fetch:
        await guard.get_session_status(
            customer_phone="254700000000",
            business_phone="254711111111",
        )
        await guard.get_session_status(
            customer_phone="254700000000",
            business_phone="254711111111",
        )
    assert mock_fetch.await_count == 2


@pytest.mark.asyncio
async def test_expired_local_cache_refetches():
    config = LipaySdkConfig(
        gateway_url="https://message.lipay.store",
        local_active_ttl_seconds=1,
    )
    guard = LipayCswSessionGuard(config)
    pair_key = guard._pair_key("254711111111", "254700000000")
    guard._local[pair_key] = (ACTIVE, time.monotonic() - 1)

    with patch.object(
        guard, "fetch_from_lipay", new_callable=AsyncMock, return_value=ACTIVE
    ) as mock_fetch:
        await guard.get_session_status(
            customer_phone="254700000000",
            business_phone="254711111111",
        )
    mock_fetch.assert_awaited_once()
