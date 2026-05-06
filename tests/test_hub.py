"""Tests for SeerrClient (hub.py)."""

from __future__ import annotations

import pytest
from aiohttp import ClientConnectionError, ClientSession
from aioresponses import aioresponses

from custom_components.haseerr.hub import SeerrAuthError, SeerrClient, SeerrConnectionError


@pytest.mark.asyncio
async def test_status_ok(fixture, seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                f"{seerr_url}/api/v1/status",
                payload=fixture("status"),
                status=200,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            result = await client.status()
            assert result["version"] == "2.0.2"


@pytest.mark.asyncio
async def test_status_unauthorized_raises(seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(f"{seerr_url}/api/v1/status", status=401)
            client = SeerrClient(session, seerr_url, seerr_api_key)
            with pytest.raises(SeerrAuthError):
                await client.status()


@pytest.mark.asyncio
async def test_status_connection_error_raises(seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(f"{seerr_url}/api/v1/status", exception=ClientConnectionError("boom"))
            client = SeerrClient(session, seerr_url, seerr_api_key)
            with pytest.raises(SeerrConnectionError):
                await client.status()


@pytest.mark.asyncio
async def test_search_filters_persons_and_normalizes(fixture, seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                f"{seerr_url}/api/v1/search?query=Dune",
                payload=fixture("search"),
                status=200,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            results = await client.search("Dune", limit=5)

    # 4 raw → 3 after filtering out person
    assert len(results) == 3
    types = {r["media_type"] for r in results}
    assert types == {"movie", "tv"}
    # First movie maps title + year
    first = next(r for r in results if r["tmdb_id"] == 693134)
    assert first["title"] == "Dune: Part Two"
    assert first["year"] == 2024
    assert first["status"] == "not_requested"
    # Available movie
    avail = next(r for r in results if r["tmdb_id"] == 438631)
    assert avail["status"] == "available"
    # TV uses name + firstAirDate
    tv = next(r for r in results if r["media_type"] == "tv")
    assert tv["title"] == "Dune: Prophecy"
    assert tv["year"] == 2024


@pytest.mark.asyncio
async def test_search_respects_limit(fixture, seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                f"{seerr_url}/api/v1/search?query=Dune",
                payload=fixture("search"),
                status=200,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            results = await client.search("Dune", limit=2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_request_movie_body_shape(fixture, seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(
                f"{seerr_url}/api/v1/request",
                payload=fixture("request_movie"),
                status=201,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            result = await client.request(tmdb_id=693134, media_type="movie", user_id=4)

            # Inspect what we sent
            req = next(iter(m.requests.values()))[0]
            assert req.kwargs["json"] == {
                "mediaId": 693134,
                "mediaType": "movie",
                "userId": 4,
            }
    assert result["request_id"] == 1247
    assert result["status"] == "pending"
    assert result["seerr_user_display"] == "Bob"


@pytest.mark.asyncio
async def test_request_tv_defaults_seasons_to_all(fixture, seerr_url, seerr_api_key):
    """Regression: Seerr returns 500 when TV request omits seasons."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(f"{seerr_url}/api/v1/request", payload=fixture("request_tv"), status=201)
            client = SeerrClient(session, seerr_url, seerr_api_key)
            await client.request(tmdb_id=71912, media_type="tv", user_id=4)
            req = next(iter(m.requests.values()))[0]
            assert req.kwargs["json"] == {
                "mediaId": 71912,
                "mediaType": "tv",
                "userId": 4,
                "seasons": "all",
            }


@pytest.mark.asyncio
async def test_search_music_results(fixture, seerr_url, seerr_api_key):
    """Music results normalize artist + album into title; use foreignAlbumId/mbId as identifier."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                f"{seerr_url}/api/v1/search?query=Radiohead",
                payload=fixture("search_music"),
                status=200,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            results = await client.search("Radiohead", limit=5)
    assert len(results) == 2
    assert all(r["media_type"] == "music" for r in results)
    ok = next(r for r in results if r["title"].endswith("OK Computer"))
    assert ok["title"] == "Radiohead — OK Computer"
    assert ok["year"] == 1997
    assert ok["status"] == "not_requested"
    assert ok["tmdb_id"] == "ddf0c693-7d28-4dad-839c-fb0d3e6c5d78"
    kid_a = next(r for r in results if r["title"].endswith("Kid A"))
    assert kid_a["status"] == "available"
    assert kid_a["tmdb_id"] == "abc123"


@pytest.mark.asyncio
async def test_get_user_quota(fixture, seerr_url, seerr_api_key):
    """get_user_quota fetches /api/v1/user/{id}/quota."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                f"{seerr_url}/api/v1/user/4/quota",
                payload=fixture("quota"),
                status=200,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            q = await client.get_user_quota(4)
    assert q["movie"]["used"] == 4
    assert q["tv"]["limit"] == 5


@pytest.mark.asyncio
async def test_request_movie_4k(fixture, seerr_url, seerr_api_key):
    """is_4k=True adds 'is4k': True to the request body."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(f"{seerr_url}/api/v1/request", payload=fixture("request_movie"), status=201)
            client = SeerrClient(session, seerr_url, seerr_api_key)
            await client.request(tmdb_id=693134, media_type="movie", user_id=4, is_4k=True)
            req = next(iter(m.requests.values()))[0]
            assert req.kwargs["json"] == {
                "mediaId": 693134,
                "mediaType": "movie",
                "userId": 4,
                "is4k": True,
            }


@pytest.mark.asyncio
async def test_request_tv_all_seasons(fixture, seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(f"{seerr_url}/api/v1/request", payload=fixture("request_tv"), status=201)
            client = SeerrClient(session, seerr_url, seerr_api_key)
            await client.request(tmdb_id=71912, media_type="tv", user_id=4, seasons="all")
            req = next(iter(m.requests.values()))[0]
            assert req.kwargs["json"] == {
                "mediaId": 71912,
                "mediaType": "tv",
                "userId": 4,
                "seasons": "all",
            }


@pytest.mark.asyncio
async def test_request_tv_specific_seasons(fixture, seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(f"{seerr_url}/api/v1/request", payload=fixture("request_tv"), status=201)
            client = SeerrClient(session, seerr_url, seerr_api_key)
            await client.request(tmdb_id=71912, media_type="tv", user_id=4, seasons=[1, 2])
            req = next(iter(m.requests.values()))[0]
            assert req.kwargs["json"]["seasons"] == [1, 2]


@pytest.mark.asyncio
async def test_approve_request(seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(
                f"{seerr_url}/api/v1/request/1247/approve",
                payload={"id": 1247, "status": 2},
                status=200,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            result = await client.approve_request(1247)
    assert result == {"ok": True, "status": "approved"}


@pytest.mark.asyncio
async def test_decline_request_with_reason(seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(
                f"{seerr_url}/api/v1/request/1247/decline",
                payload={"id": 1247, "status": 3},
                status=200,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            result = await client.decline_request(1247, reason="too violent for kids")
            req = next(iter(m.requests.values()))[0]
            assert req.kwargs["json"] == {"reason": "too violent for kids"}
    assert result == {"ok": True, "status": "declined"}


@pytest.mark.asyncio
async def test_approve_request_204_no_content(seerr_url, seerr_api_key):
    """Seerr sometimes returns 204 No Content on approve; must not crash."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(
                f"{seerr_url}/api/v1/request/1247/approve",
                status=204,
                body=b"",
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            result = await client.approve_request(1247)
    assert result["ok"] is True
    assert result["status"] == "approved"


@pytest.mark.asyncio
async def test_decline_request_204_no_content(seerr_url, seerr_api_key):
    """Seerr sometimes returns 204 No Content on decline; must not crash."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(
                f"{seerr_url}/api/v1/request/1247/decline",
                status=204,
                body=b"",
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            result = await client.decline_request(1247)
    assert result["ok"] is True
    assert result["status"] == "declined"


@pytest.mark.asyncio
async def test_list_users(fixture, seerr_url, seerr_api_key):
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                f"{seerr_url}/api/v1/user?take=200&sort=created",
                payload=fixture("users"),
                status=200,
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            users = await client.list_users()
    assert len(users) == 3
    assert {u["display_name"] for u in users} == {"Alice", "Bob", "Carol"}
    assert users[0] == {
        "id": 1,
        "display_name": "Alice",
        "email": "alice@example.com",
    }


@pytest.mark.asyncio
async def test_get_user_permissions(seerr_url, seerr_api_key):
    """Returns the permissions bitmask field from /api/v1/user/<id>."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                f"{seerr_url}/api/v1/user/4",
                payload={"id": 4, "displayName": "Alice", "permissions": 4096},
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            perms = await client.get_user_permissions(4)
            assert perms == 4096


@pytest.mark.asyncio
async def test_get_user_permissions_defaults_to_zero(seerr_url, seerr_api_key):
    """Missing permissions field is treated as 0 (no perms)."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                f"{seerr_url}/api/v1/user/4",
                payload={"id": 4, "displayName": "Alice"},
            )
            client = SeerrClient(session, seerr_url, seerr_api_key)
            perms = await client.get_user_permissions(4)
            assert perms == 0
