"""Structural parity tests for translations/*.json.

These guard against drift: anyone adding a new service field or changing
services.yaml without updating translations gets a CI failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
COMPONENT = ROOT / "custom_components" / "haseerr"
TRANSLATIONS = COMPONENT / "translations"
SERVICES_YAML = COMPONENT / "services.yaml"


def _load_json(name: str) -> dict:
    return json.loads((TRANSLATIONS / f"{name}.json").read_text(encoding="utf-8"))


def _load_services_yaml() -> dict:
    return yaml.safe_load(SERVICES_YAML.read_text(encoding="utf-8"))


def test_en_translations_cover_all_services():
    """Every service+field in services.yaml has a matching entry in en.json."""
    services = _load_services_yaml()
    en = _load_json("en")
    en_services = en.get("services", {})
    missing: list[str] = []
    for svc_name, svc_def in services.items():
        if svc_name not in en_services:
            missing.append(f"services.{svc_name}")
            continue
        en_svc = en_services[svc_name]
        if "name" not in en_svc:
            missing.append(f"services.{svc_name}.name")
        if "description" not in en_svc:
            missing.append(f"services.{svc_name}.description")
        en_fields = en_svc.get("fields", {})
        for field_name in svc_def.get("fields") or {}:
            if field_name not in en_fields:
                missing.append(f"services.{svc_name}.fields.{field_name}")
    assert not missing, f"Missing en.json entries: {missing}"


def test_bg_structurally_matches_en():
    """Every key path under services in en.json exists at the same path in bg.json."""
    en = _load_json("en")
    bg = _load_json("bg")
    en_services = en.get("services", {})
    bg_services = bg.get("services", {})
    missing: list[str] = []
    for svc_name, en_svc in en_services.items():
        if svc_name not in bg_services:
            missing.append(f"services.{svc_name}")
            continue
        bg_svc = bg_services[svc_name]
        for k in ("name", "description"):
            if k in en_svc and k not in bg_svc:
                missing.append(f"services.{svc_name}.{k}")
        en_fields = en_svc.get("fields", {})
        bg_fields = bg_svc.get("fields", {})
        for field_name in en_fields:
            if field_name not in bg_fields:
                missing.append(f"services.{svc_name}.fields.{field_name}")
    assert not missing, f"Missing bg.json entries: {missing}"


def test_exceptions_block_present_in_both_locales():
    """exceptions.not_authorized_4k.message exists in en + bg with {media_type} placeholder."""
    for locale in ("en", "bg"):
        data = _load_json(locale)
        msg = data.get("exceptions", {}).get("not_authorized_4k", {}).get("message")
        assert msg, f"{locale}.json: exceptions.not_authorized_4k.message missing"
        assert (
            "{media_type}" in msg
        ), f"{locale}.json: message must contain {{media_type}} placeholder, got: {msg!r}"
