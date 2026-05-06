"""HaSeerr — Home Assistant integration for Seerr request submission."""

from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_WEBHOOK_ID, DOMAIN, PLATFORMS
from .services_impl import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)


def _haseerr_version() -> str:
    """Read version from manifest.json (used as a cache-buster on the card URL)."""
    try:
        manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
        return str(manifest.get("version", "0"))
    except Exception:
        return "0"


CARD_URL_PATH = "/haseerr_static/haseerr-card.js"
CARD_URL = f"{CARD_URL_PATH}?v={_haseerr_version()}"


async def _register_card(hass: HomeAssistant) -> None:
    """Serve the card JS and register it as a Lovelace resource (UI + YAML modes)."""
    from pathlib import Path

    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig
    except ImportError:
        _LOGGER.debug("frontend not available; skipping haseerr-card registration")
        return

    www_dir = Path(__file__).parent / "www"
    if not www_dir.is_dir():
        return

    # 1. Serve the JS at /haseerr_static/haseerr-card.js (idempotent)
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig("/haseerr_static", str(www_dir), True)]
        )
    except Exception as err:
        _LOGGER.debug("static path registration: %s", err)

    # 2. YAML-mode Lovelace: register via add_extra_js_url
    try:
        add_extra_js_url(hass, CARD_URL)
    except (RuntimeError, KeyError) as err:
        _LOGGER.warning("add_extra_js_url: %s", err)

    # 3. UI-mode (Storage) Lovelace: insert into the resource collection
    await _register_lovelace_resource(hass)


async def _register_lovelace_resource(hass: HomeAssistant) -> None:
    """Add the card to UI-mode Lovelace resources if not already present.

    Has no effect in YAML-mode Lovelace (resources collection is None there).
    """
    try:
        lovelace = hass.data.get("lovelace")
    except Exception:
        return
    if lovelace is None:
        _LOGGER.info(
            "Lovelace not loaded yet; if your dashboard is in UI mode and the "
            "haseerr-card doesn't appear, add %s manually under "
            "Settings → Dashboards → Resources (type: JavaScript Module)",
            CARD_URL,
        )
        return

    # `lovelace.resources` exists in UI/Storage mode; in YAML mode it's None.
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        return
    try:
        await resources.async_load()
        existing_id = None
        existing_url = None
        for item in resources.async_items():
            url = item.get("url", "")
            # Match by base path so old `?v=<prev>` entries get updated, not duplicated.
            if url.split("?", 1)[0] == CARD_URL_PATH:
                existing_id = item.get("id")
                existing_url = url
                break
        if existing_id is not None:
            if existing_url == CARD_URL:
                return  # already up-to-date
            await resources.async_update_item(
                existing_id, {"url": CARD_URL, "res_type": "module"}
            )
            _LOGGER.info(
                "Updated haseerr-card Lovelace resource: %s → %s", existing_url, CARD_URL
            )
        else:
            await resources.async_create_item({"url": CARD_URL, "res_type": "module"})
            _LOGGER.info("Registered haseerr-card as a Lovelace resource: %s", CARD_URL)
    except Exception as err:
        _LOGGER.warning(
            "Could not auto-register haseerr-card resource: %s. Add %s manually "
            "under Settings → Dashboards → Resources (type: JavaScript Module).",
            err,
            CARD_URL,
        )


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Back-fill webhook_id on entries created before v0.2 added the field."""
    if entry.data.get(CONF_WEBHOOK_ID):
        return True
    new_data = {**entry.data, CONF_WEBHOOK_ID: secrets.token_hex(32)}
    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.info(
        "Migrated entry %s — back-filled webhook_id for v0.2 webhook support", entry.entry_id
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # v0.1 entries were created without webhook_id; back-fill before continuing.
    if not entry.data.get(CONF_WEBHOOK_ID):
        await async_migrate_entry(hass, entry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    async_register_services(hass)
    # Intent handler is auto-registered by HA via async_setup_intents in intent.py
    await _register_card(hass)
    from .webhook import async_register_webhook

    await async_register_webhook(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change so sensor + caches refresh."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .webhook import async_unregister_webhook

    await async_unregister_webhook(hass, entry)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            async_unregister_services(hass)
    return unload_ok
