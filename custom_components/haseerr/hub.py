"""SeerrClient — async HTTP wrapper for the Seerr API."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientSession

from .const import SEARCH_RESULT_TYPES, TMDB_POSTER_BASE

_LOGGER = logging.getLogger(__name__)


SEERR_STATUS_MAP = {1: "pending", 2: "approved", 3: "declined"}


def _year_from_date(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        return int(date_str[:4])
    except (TypeError, ValueError):
        return None


def _normalize_status(media_info: dict | None) -> str:
    """Map Seerr's media-info status code to our 3-state string."""
    if media_info is None:
        return "not_requested"
    code = media_info.get("status")
    if code == 5:
        return "available"
    return "requested"


def _normalize_result(raw: dict, poster_size: str = "w300") -> dict:
    media_type = raw.get("mediaType")
    if media_type == "music":
        # Lidarr-via-Seerr music: {artist, title (album), releaseDate, mbId or foreignAlbumId}
        artist = raw.get("artist") or raw.get("artistName") or ""
        album = raw.get("title") or raw.get("name") or "(untitled)"
        title = f"{artist} — {album}" if artist else album
        date = raw.get("releaseDate")
        # Music ID is MusicBrainz; expose under tmdb_id for API symmetry.
        identifier = raw.get("foreignAlbumId") or raw.get("mbId") or raw.get("id")
    else:
        title = raw.get("title") or raw.get("name") or "(untitled)"
        date = raw.get("releaseDate") or raw.get("firstAirDate")
        identifier = raw["id"]
    poster = raw.get("posterPath")
    return {
        "tmdb_id": identifier,
        "media_type": media_type,
        "title": title,
        "year": _year_from_date(date),
        "poster_url": f"{TMDB_POSTER_BASE}/{poster_size}{poster}" if poster else None,
        "overview": raw.get("overview"),
        "status": _normalize_status(raw.get("mediaInfo")),
    }


class SeerrError(Exception):
    """Base error."""


class SeerrAuthError(SeerrError):
    """API key rejected."""


class SeerrConnectionError(SeerrError):
    """Cannot reach Seerr."""


class SeerrApiError(SeerrError):
    """Seerr returned a non-2xx response (other than 401)."""


class SeerrPermissionError(SeerrError):
    """User lacks permission for the requested operation."""


class SeerrClient:
    """Thin async wrapper around Seerr's REST API."""

    def __init__(self, session: ClientSession, url: str, api_key: str) -> None:
        self._session = session
        self._url = url.rstrip("/")
        self._headers = {"X-Api-Key": api_key, "Accept": "application/json"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with self._session.request(
                method, f"{self._url}{path}", headers=self._headers, **kwargs
            ) as resp:
                if resp.status == 401:
                    raise SeerrAuthError("API key rejected")
                if resp.status >= 400:
                    text = await resp.text()
                    raise SeerrApiError(f"{resp.status}: {text[:200]}")
                if resp.content_type == "application/json":
                    return await resp.json()
                return None
        except ClientError as err:
            raise SeerrConnectionError(str(err)) from err

    async def status(self) -> dict:
        """Return Seerr /api/v1/status payload."""
        return await self._request("GET", "/api/v1/status")

    async def search(self, query: str, limit: int = 5, media_type: str = "all") -> list[dict]:
        """Search Seerr, filter out persons, normalize, and apply limit."""
        # Seerr strict-checks for RFC 3986 percent-encoding on `query`.
        # aiohttp's default params= uses form-style (+ for space) which Seerr rejects.
        encoded = quote(query, safe="")
        data = await self._request("GET", f"/api/v1/search?query={encoded}")
        results = data.get("results", [])
        filtered = [r for r in results if r.get("mediaType") in SEARCH_RESULT_TYPES]
        if media_type in SEARCH_RESULT_TYPES:
            filtered = [r for r in filtered if r["mediaType"] == media_type]
        return [_normalize_result(r) for r in filtered[:limit]]

    async def request(
        self,
        *,
        tmdb_id: int,
        media_type: str,
        user_id: int,
        seasons: list[int] | str | None = None,
        is_4k: bool = False,
    ) -> dict:
        """Submit a media request to Seerr and return a normalized response."""
        body: dict = {"mediaId": tmdb_id, "mediaType": media_type, "userId": user_id}
        if media_type == "tv":
            # Seerr returns 500 if a TV request omits seasons. Default to all.
            body["seasons"] = seasons if seasons is not None else "all"
        if is_4k:
            body["is4k"] = True
        raw = await self._request("POST", "/api/v1/request", json=body)
        return {
            "request_id": raw["id"],
            "status": SEERR_STATUS_MAP.get(raw.get("status", 1), "pending"),
            "seerr_user_id": raw.get("requestedBy", {}).get("id"),
            "seerr_user_display": raw.get("requestedBy", {}).get("displayName"),
        }

    async def approve_request(self, request_id: int) -> dict:
        raw = await self._request("POST", f"/api/v1/request/{request_id}/approve") or {}
        status = SEERR_STATUS_MAP.get(raw.get("status"), "approved")
        return {"ok": True, "status": status}

    async def get_user_quota(self, user_id: int) -> dict:
        """Return Seerr's quota info for a user: {movie: {limit, used, restricted}, tv: {...}}."""
        return await self._request("GET", f"/api/v1/user/{user_id}/quota")

    async def get_user_permissions(self, user_id: int) -> int:
        """Return the user's permission bitmask from /api/v1/user/<id>."""
        data = await self._request("GET", f"/api/v1/user/{user_id}")
        return int(data.get("permissions", 0))

    async def list_users(self) -> list[dict]:
        """Return all Seerr users as normalized dicts."""
        data = await self._request("GET", "/api/v1/user", params={"take": 200, "sort": "created"})
        results = data.get("results", [])
        return [
            {
                "id": u["id"],
                "display_name": u["displayName"],
                "email": u.get("email"),
            }
            for u in results
        ]

    async def decline_request(self, request_id: int, reason: str | None = None) -> dict:
        body = {"reason": reason} if reason else None
        raw = await self._request("POST", f"/api/v1/request/{request_id}/decline", json=body) or {}
        status = SEERR_STATUS_MAP.get(raw.get("status"), "declined")
        return {"ok": True, "status": status}
