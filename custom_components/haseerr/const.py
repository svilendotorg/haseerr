"""Constants for the haseerr integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "haseerr"
PLATFORMS: Final = ["sensor"]

# Config entry data keys
CONF_URL: Final = "url"
CONF_API_KEY: Final = "api_key"

# Options keys
OPT_USER_MAPPING: Final = "user_mapping"  # {ha_user_id: seerr_user_id}
OPT_AUTO_RESOLVE_BY_NAME: Final = "auto_resolve_by_name"  # bool fallback
OPT_WEB_URL: Final = "web_url"  # public Seerr URL for browser links; falls back to CONF_URL

# Service names
SVC_SEARCH: Final = "search"
SVC_REQUEST: Final = "request"
SVC_APPROVE_REQUEST: Final = "approve_request"
SVC_DECLINE_REQUEST: Final = "decline_request"
SVC_USER_QUOTA: Final = "user_quota"

# Event names
EVT_REQUEST_SUBMITTED: Final = "haseerr_request_submitted"
EVT_REQUEST_STATUS_CHANGED: Final = "haseerr_request_status_changed"

# Webhook
CONF_WEBHOOK_ID: Final = "webhook_id"

# Sensor states
STATE_CONNECTED: Final = "connected"
STATE_ERROR: Final = "error"
STATE_UNMAPPED_USER: Final = "unmapped_user"

# Defaults
DEFAULT_SEARCH_LIMIT: Final = 5
SEARCH_RESULT_TYPES: Final = ("movie", "tv", "music")  # filter out 'person'
NAME_FUZZY_THRESHOLD: Final = 0.85

# TMDB poster base
TMDB_POSTER_BASE: Final = "https://image.tmdb.org/t/p"

# Multi-turn confirmation state.
# hass.data[DOMAIN][PENDING_CONFIRM_KEY][user_id] = {tmdb_id, media_type, title, expires_at}
PENDING_CONFIRM_KEY: Final = "pending_confirm"
PENDING_CONFIRM_TTL_S: Final = 60

# Seerr permission bitmask values (from Overseerr's user.permissions field)
PERM_ADMIN: Final = 2
PERM_REQUEST_4K: Final = 4096
PERM_REQUEST_4K_MOVIE: Final = 8192
PERM_REQUEST_4K_TV: Final = 16384
