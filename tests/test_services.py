"""Tests for haseerr services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haseerr.const import (
    DOMAIN,
    OPT_USER_MAPPING,
    PERM_ADMIN,
    PERM_REQUEST_4K,
    PERM_REQUEST_4K_MOVIE,
    PERM_REQUEST_4K_TV,
    SVC_REQUEST,
    SVC_SEARCH,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def configured(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": "http://test.local:5055", "api_key": "abc"},
        options={OPT_USER_MAPPING: {"ha-1": 4}},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry


async def test_search_service_returns_results(hass: HomeAssistant, configured):
    sample = [{"tmdb_id": 1, "title": "X", "media_type": "movie"}]
    with patch("custom_components.haseerr.hub.SeerrClient.search", return_value=sample):
        out = await hass.services.async_call(
            DOMAIN,
            SVC_SEARCH,
            {"query": "X"},
            blocking=True,
            return_response=True,
        )
    assert out["results"] == sample
    assert out["seerr_url"] == "http://test.local:5055"


async def test_search_service_uses_web_url_when_configured(hass: HomeAssistant):
    """When web_url is set in options, search response prefers it over the API URL."""
    from custom_components.haseerr.const import OPT_USER_MAPPING, OPT_WEB_URL

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": "http://test.local:5055", "api_key": "abc"},
        options={
            OPT_USER_MAPPING: {"ha-1": 4},
            OPT_WEB_URL: "https://seerr.public.example.com",
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sample = [{"tmdb_id": 1, "title": "X", "media_type": "movie"}]
    with patch("custom_components.haseerr.hub.SeerrClient.search", return_value=sample):
        out = await hass.services.async_call(
            DOMAIN,
            SVC_SEARCH,
            {"query": "X"},
            blocking=True,
            return_response=True,
        )
    assert out["seerr_url"] == "https://seerr.public.example.com"


async def test_request_resolves_mapped_user(hass: HomeAssistant, configured):
    fake_user = SimpleNamespace(id="ha-1", is_admin=False)
    from homeassistant.core import Context

    ctx = Context(user_id="ha-1")
    with (
        patch.object(hass.auth, "async_get_user", return_value=fake_user),
        patch(
            "custom_components.haseerr.hub.SeerrClient.request",
            return_value={
                "request_id": 1247,
                "status": "pending",
                "seerr_user_id": 4,
                "seerr_user_display": "Bob",
            },
        ) as m_req,
    ):
        out = await hass.services.async_call(
            DOMAIN,
            SVC_REQUEST,
            {"tmdb_id": 693134, "media_type": "movie"},
            blocking=True,
            return_response=True,
            context=ctx,
        )
    m_req.assert_called_once()
    kwargs = m_req.call_args.kwargs
    assert kwargs["user_id"] == 4
    assert out["status"] == "pending"


async def test_request_event_includes_title(hass: HomeAssistant, configured):
    fake_user = SimpleNamespace(id="ha-1", is_admin=False)
    from homeassistant.core import Context

    ctx = Context(user_id="ha-1")
    events = []
    hass.bus.async_listen("haseerr_request_submitted", lambda e: events.append(e))
    with (
        patch.object(hass.auth, "async_get_user", return_value=fake_user),
        patch(
            "custom_components.haseerr.hub.SeerrClient.request",
            return_value={
                "request_id": 1247,
                "status": "pending",
                "seerr_user_id": 4,
                "seerr_user_display": "Bob",
            },
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            SVC_REQUEST,
            {"tmdb_id": 693134, "media_type": "movie", "title": "Dune: Part Two"},
            blocking=True,
            return_response=True,
            context=ctx,
        )
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["title"] == "Dune: Part Two"


async def test_request_rejects_unmapped_user(hass: HomeAssistant, configured):
    from homeassistant.core import Context

    ctx = Context(user_id="ha-other")
    with patch("custom_components.haseerr.hub.SeerrClient.request"):
        with pytest.raises(Exception, match="not mapped"):
            await hass.services.async_call(
                DOMAIN,
                SVC_REQUEST,
                {"tmdb_id": 1, "media_type": "movie"},
                blocking=True,
                context=ctx,
                return_response=True,
            )


async def _call_4k_request(hass, media_type, perms, *, expect_error=False):
    """Helper: invoke haseerr.request with is_4k=True under given perms."""
    from homeassistant.core import Context

    request_called = []

    async def fake_request(self, **kwargs):
        request_called.append(kwargs)
        return {
            "request_id": 99,
            "status": "pending",
            "seerr_user_id": 4,
            "seerr_user_display": "Alice",
        }

    with (
        patch(
            "custom_components.haseerr.hub.SeerrClient.get_user_permissions",
            return_value=perms,
        ),
        patch(
            "custom_components.haseerr.hub.SeerrClient.request",
            new=fake_request,
        ),
    ):
        try:
            await hass.services.async_call(
                DOMAIN,
                SVC_REQUEST,
                {"tmdb_id": 27205, "media_type": media_type, "is_4k": True},
                blocking=True,
                return_response=True,
                context=Context(user_id="ha-1"),
            )
        except HomeAssistantError as err:
            if not expect_error:
                raise
            return err, request_called
    if expect_error:
        pytest.fail("expected HomeAssistantError but request succeeded")
    return None, request_called


async def test_request_4k_movie_unauthorized_raises(hass: HomeAssistant, configured):
    """User with REQUEST only (no 4K bits) → HomeAssistantError, no Seerr write."""
    err, calls = await _call_4k_request(hass, "movie", perms=32, expect_error=True)
    assert err.translation_key == "not_authorized_4k"
    assert err.translation_placeholders == {"media_type": "movie"}
    assert calls == []  # no POST happened


async def test_request_4k_movie_authorized_global(hass: HomeAssistant, configured):
    """REQUEST_4K (4096) bit alone allows movie 4K."""
    _, calls = await _call_4k_request(hass, "movie", perms=PERM_REQUEST_4K | 32)
    assert calls and calls[0]["is_4k"] is True


async def test_request_4k_movie_authorized_per_type(hass: HomeAssistant, configured):
    """REQUEST_4K_MOVIE (8192) bit alone allows movie 4K."""
    _, calls = await _call_4k_request(hass, "movie", perms=PERM_REQUEST_4K_MOVIE | 32)
    assert calls and calls[0]["is_4k"] is True


async def test_request_4k_tv_authorized_per_type(hass: HomeAssistant, configured):
    """REQUEST_4K_TV (16384) bit alone allows TV 4K."""
    _, calls = await _call_4k_request(hass, "tv", perms=PERM_REQUEST_4K_TV | 32)
    assert calls and calls[0]["is_4k"] is True


async def test_request_4k_movie_admin_bypass(hass: HomeAssistant, configured):
    """ADMIN (2) bit alone bypasses 4K-specific checks."""
    _, calls = await _call_4k_request(hass, "movie", perms=PERM_ADMIN)
    assert calls and calls[0]["is_4k"] is True


async def test_request_4k_music_rejected_no_lookup(hass: HomeAssistant, configured):
    """is_4k=true with media_type=music → reject without permission lookup or Seerr write."""
    from homeassistant.core import Context

    perm_calls = []

    async def fake_perms(self, user_id):
        perm_calls.append(user_id)
        return PERM_ADMIN

    request_calls = []

    async def fake_request(self, **kwargs):
        request_calls.append(kwargs)
        return {"request_id": 99, "status": "pending"}

    with (
        patch(
            "custom_components.haseerr.hub.SeerrClient.get_user_permissions",
            new=fake_perms,
        ),
        patch(
            "custom_components.haseerr.hub.SeerrClient.request",
            new=fake_request,
        ),
    ):
        with pytest.raises(HomeAssistantError) as ei:
            await hass.services.async_call(
                DOMAIN,
                SVC_REQUEST,
                {"tmdb_id": 1, "media_type": "music", "is_4k": True},
                blocking=True,
                return_response=True,
                context=Context(user_id="ha-1"),
            )
        assert ei.value.translation_key == "not_authorized_4k"
    assert perm_calls == []  # short-circuit: never fetched perms
    assert request_calls == []


async def test_request_non_4k_skips_permission_check(hass: HomeAssistant, configured):
    """is_4k=False → zero calls to get_user_permissions (no overhead on common path)."""
    from homeassistant.core import Context

    perm_calls = []

    async def fake_perms(self, user_id):
        perm_calls.append(user_id)
        return PERM_ADMIN

    async def fake_request(self, **kwargs):
        return {"request_id": 1, "status": "pending"}

    with (
        patch(
            "custom_components.haseerr.hub.SeerrClient.get_user_permissions",
            new=fake_perms,
        ),
        patch(
            "custom_components.haseerr.hub.SeerrClient.request",
            new=fake_request,
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            SVC_REQUEST,
            {"tmdb_id": 1, "media_type": "movie"},  # no is_4k
            blocking=True,
            return_response=True,
            context=Context(user_id="ha-1"),
        )
    assert perm_calls == []
