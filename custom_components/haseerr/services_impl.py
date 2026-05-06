"""Service handlers for haseerr."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_URL,
    DOMAIN,
    EVT_REQUEST_SUBMITTED,
    OPT_USER_MAPPING,
    OPT_WEB_URL,
    PERM_ADMIN,
    PERM_REQUEST_4K,
    PERM_REQUEST_4K_MOVIE,
    PERM_REQUEST_4K_TV,
    SVC_APPROVE_REQUEST,
    SVC_DECLINE_REQUEST,
    SVC_REQUEST,
    SVC_SEARCH,
    SVC_USER_QUOTA,
)
from .hub import SeerrClient, SeerrError, SeerrPermissionError

_LOGGER = logging.getLogger(__name__)


SEARCH_SCHEMA = vol.Schema(
    {
        vol.Required("query"): cv.string,
        vol.Optional("media_type", default="all"): vol.In(["all", "movie", "tv", "music"]),
        vol.Optional("limit", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
    }
)

REQUEST_SCHEMA = vol.Schema(
    {
        vol.Required("tmdb_id"): vol.Any(vol.Coerce(int), cv.string),
        vol.Required("media_type"): vol.In(["movie", "tv", "music"]),
        vol.Optional("seasons"): vol.Any("all", [int]),
        vol.Optional("user_override"): vol.Coerce(int),
        vol.Optional("title"): cv.string,
        vol.Optional("is_4k", default=False): cv.boolean,
    }
)

ID_SCHEMA = vol.Schema({vol.Required("request_id"): vol.Coerce(int)})
DECLINE_SCHEMA = ID_SCHEMA.extend({vol.Optional("reason"): cv.string})


async def _client_for(hass: HomeAssistant, entry: ConfigEntry) -> SeerrClient:
    session = async_get_clientsession(hass)
    return SeerrClient(session, entry.data[CONF_URL], entry.data[CONF_API_KEY])


def _entry(hass: HomeAssistant) -> ConfigEntry:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise RuntimeError("haseerr is not configured")
    return entries[0]


async def _resolve_user_id(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall) -> int:
    if (override := call.data.get("user_override")) is not None:
        if not call.context.user_id:
            raise RuntimeError("admin context required for user_override")
        user = await hass.auth.async_get_user(call.context.user_id)
        if user is None or not user.is_admin:
            raise RuntimeError("user_override requires admin")
        return int(override)

    mapping: dict[str, int] = entry.options.get(OPT_USER_MAPPING, {})
    ha_user_id = call.context.user_id
    if not ha_user_id or ha_user_id not in mapping:
        raise RuntimeError("user not mapped, complete options flow")
    return int(mapping[ha_user_id])


async def _search(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    entry = _entry(hass)
    client = await _client_for(hass, entry)
    results = await client.search(
        query=call.data["query"],
        media_type=call.data.get("media_type", "all"),
        limit=call.data.get("limit", 5),
    )
    # Include the Seerr base for card deep-links. Prefer configured web_url
    # (e.g. https://seerr.example.com) over the API URL (e.g. http://10.x:5055).
    web_url = (entry.options.get(OPT_WEB_URL) or "").strip().rstrip("/")
    base = web_url or entry.data[CONF_URL].rstrip("/")
    return {"results": results, "seerr_url": base}


def _sensor(hass: HomeAssistant, entry: ConfigEntry):
    """Return the status sensor if available, else None."""
    return hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("sensor")


async def _check_4k_permission(client: SeerrClient, user_id: int, media_type: str) -> None:
    """Raise SeerrPermissionError if user_id can't request 4K of media_type.

    Music has no 4K concept and is always rejected as a sanity guard.
    """
    if media_type == "music":
        raise SeerrPermissionError("music has no 4K")

    perms = await client.get_user_permissions(user_id)
    if perms & PERM_ADMIN:
        return
    if perms & PERM_REQUEST_4K:
        return
    if media_type == "movie" and perms & PERM_REQUEST_4K_MOVIE:
        return
    if media_type == "tv" and perms & PERM_REQUEST_4K_TV:
        return
    raise SeerrPermissionError(f"user {user_id} cannot request 4K {media_type}")


async def _request(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    entry = _entry(hass)
    user_id = await _resolve_user_id(hass, entry, call)
    client = await _client_for(hass, entry)
    sensor = _sensor(hass, entry)

    media_type = call.data["media_type"]
    if call.data.get("is_4k", False):
        try:
            await _check_4k_permission(client, user_id, media_type)
        except SeerrPermissionError as err:
            _LOGGER.debug("4K request denied: %s", err)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_authorized_4k",
                translation_placeholders={"media_type": media_type},
            ) from err

    try:
        result = await client.request(
            tmdb_id=call.data["tmdb_id"],
            media_type=media_type,
            user_id=user_id,
            seasons=call.data.get("seasons"),
            is_4k=call.data.get("is_4k", False),
        )
    except SeerrError as err:
        if sensor is not None:
            sensor.record_error(str(err))
        raise
    if sensor is not None:
        sensor.record_request(result["request_id"])
    hass.bus.async_fire(
        EVT_REQUEST_SUBMITTED,
        {
            "tmdb_id": call.data["tmdb_id"],
            "media_type": media_type,
            "title": call.data.get("title"),
            "request_id": result["request_id"],
            "ha_user_id": call.context.user_id,
            "seerr_user_id": user_id,
            "status": result["status"],
        },
    )
    return result


async def _approve(call: ServiceCall) -> ServiceResponse:
    client = await _client_for(call.hass, _entry(call.hass))
    return await client.approve_request(call.data["request_id"])


async def _decline(call: ServiceCall) -> ServiceResponse:
    client = await _client_for(call.hass, _entry(call.hass))
    return await client.decline_request(call.data["request_id"], call.data.get("reason"))


async def _user_quota(call: ServiceCall) -> ServiceResponse:
    """Return Seerr quota for the caller's mapped user (or for user_id if admin override)."""
    hass = call.hass
    entry = _entry(hass)
    user_id = await _resolve_user_id(hass, entry, call)
    client = await _client_for(hass, entry)
    return await client.get_user_quota(user_id)


def async_register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        SVC_SEARCH,
        _search,
        schema=SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SVC_REQUEST,
        _request,
        schema=REQUEST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SVC_APPROVE_REQUEST,
        _approve,
        schema=ID_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SVC_DECLINE_REQUEST,
        _decline,
        schema=DECLINE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SVC_USER_QUOTA,
        _user_quota,
        schema=vol.Schema({vol.Optional("user_override"): vol.Coerce(int)}),
        supports_response=SupportsResponse.ONLY,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    for svc in (
        SVC_SEARCH,
        SVC_REQUEST,
        SVC_APPROVE_REQUEST,
        SVC_DECLINE_REQUEST,
        SVC_USER_QUOTA,
    ):
        hass.services.async_remove(DOMAIN, svc)
