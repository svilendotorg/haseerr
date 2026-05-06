# Changelog

All notable changes to HaSeerr.

## v0.4.1 — 2026-05-06

### Added — voice-intent STT robustness

Real-world testing against the BG fine-tuned Whisper model (`svilendotorg/whisper-medium-bg-ct2`, derived from `shripadbhat/whisper-medium-bg`) surfaced a number of speech-to-text mistranscriptions that didn't match the v0.4.0 patterns. This release expands `intents/{en,bg}.yaml` to absorb them.

**Bulgarian `RequestMedia`:**
- Added STT-quirk verb variants: `истегли`, `изтеглий`, `изтъгли`, `изтегляй`, `свалий`, `набери`
- Added English-loanword variants Whisper-bg produces when hearing "download": `донлоад`, `донлоуд`, `даунлоад`, `даунлоуд`, `донвоадът`, `донлоадът`, `даумо`
- Added optional `[от]` and `[и]` filler particles between verb and title (absorbs "изтегли **и** Терминатор" filler)
- Added `ми` ("for me") indirect-object form for all verbs

**Bulgarian `ConfirmRequest`:**
- Added `да.`, `— да.`, `— да` (literal punctuation/em-dash variants in case hassil's normalizer doesn't strip them for BG)
- Added natural confirmations: `добре`, `разбрано`, `окей`, `ок`, `точно така` (with punctuation/em-dash variants for each)

**Bulgarian `CancelRequest`:**
- Added `стига`, `недей`

**English `RequestMedia`:**
- Added verb alternatives to `request`: `download`, `find`, `search`, `get me`
- Added `downward` (Whisper STT mishear of "download")
- All polite (`please`/`can you`) and season-suffixed forms work for every verb

**English `ConfirmRequest`:**
- Added `yep`

### Fixed

- BG voice intents from v0.4.0 used a simplified slot schema (`slots: title: { wildcard: true }`) that silently fails on non-EN languages in HA's hassil matcher. Migrated to the full hassil schema with a top-level `lists:` block, which is what HA's `default_agent` actually loads from `<config>/custom_sentences/<lang>/<file>.yaml`. The integration's `intents/<lang>.yaml` files are reference; the user must still copy them into `<config>/custom_sentences/` per the integration's voice docs.

### No breaking changes

- All v0.4.0 patterns still match. v0.4.1 only adds variants.

## v0.4.0 — 2026-05-06

### Added

- **4K permission gating** — `haseerr.request` with `is_4k: true` checks the mapped Seerr user's permission bitmask via `/api/v1/user/<id>` and rejects with a localized error before any Seerr write. Recognizes `REQUEST_4K` (4096), `REQUEST_4K_MOVIE` (8192), `REQUEST_4K_TV` (16384), and bypasses for `ADMIN` (2). Music requests with `is_4k=true` are rejected outright (no 4K concept).
- **Localized service descriptions** — full EN+BG parity. `translations/en.json` gap-filled (`is_4k`, `title`, full `user_quota` service); `translations/bg.json` gained the entire `services` block. New `exceptions.not_authorized_4k.message` in both locales surfaces the 4K rejection in the user's HA frontend language.
- **Card 4K toggle** — global `4K` checkbox above the search box in `haseerr-card`. When on, every `Request` click submits with `is_4k: true`. Music results never submit 4K. Success toast shows `· 4K` suffix when applicable.
- **Translation parity tests** (`tests/test_translations.py`) — three structural tests catch drift: `services.yaml` ↔ `en.json`, `en.json` ↔ `bg.json`, and the `exceptions.not_authorized_4k.message` placeholder check across both locales.

### Changed

- **BG voice intents** — `RequestMedia` now uses the colloquial verbs `свали` ("download") and `намери` ("find"). The bookish `поискай` is removed across all sentence patterns. Resolves a grammar bug in the previous `(можеш ли да|моля) поискай` pattern (mixed `да`-form imperatives are invalid Bulgarian).

### No breaking changes

- 4K rejection on unauthorized requests was previously a generic `SeerrApiError` from Seerr; it is now a localized `HomeAssistantError`. Existing automations that catch `Exception` keep working; those parsing the error message will see different text (in the user's locale).

## v0.3.0 — 2026-05-04

### Added

- **Webhook migrator** — v0.1 config entries lacking `webhook_id` are auto-back-filled on next start (`async_migrate_entry`). Existing installs get the v0.2 webhook capability without re-adding the integration.
- **Card Overseerr links** — each search result row's title is now a clickable link that opens the Seerr detail page in a new tab. URL is built from the Seerr base in the search response.
- **Card UI polish** — title header empty by default (was "HaSeerr"); media types capitalized (`Movie` / `TV` / `Music`); "avail" → "Available".
- **Project icons** — `icon.png` (256×256) and `icon@2x.png` (512×512) for HACS / HA-brands; logo variants in `docs/screenshots/`.
- **Documentation reorg** — public-facing `docs/` folder with separate `design.md`, `development.md`, `voice.md`, `webhook.md`. README streamlined to a quick-start with links into the docs.

### Changed

- `haseerr.search` response now includes `seerr_url` (the configured base) so cards/automations can build per-result deep links.

## v0.2.0 — 2026-05-04

### Added

- **Multi-turn voice flow** — `RequestMedia` plants pending state; `ConfirmRequest` ("yes") submits, `CancelRequest` ("no") drops. 60 s confirmation window. Bulgarian + English.
- **Webhook receiver** — HA webhook endpoint accepts Seerr `notification_type` payloads; emits `haseerr_request_status_changed` events. No core `overseerr` integration required for status updates.
- **4K profile** — optional `is_4k` flag on `haseerr.request`. Honors Seerr's per-user 4K permission.
- **User quota** — `haseerr.user_quota` service returns Seerr's monthly quota. Card displays `🎬 X/N · 📺 X/N` in the header.
- **Music (Lidarr) requests** — search returns music when Lidarr is configured in Seerr; `haseerr.request` accepts `media_type: music`.
- **Card GUI editor** — visual form when adding `type: custom:haseerr-card` via dashboard "+ Add card".
- **Localized intent responses** — Bulgarian replies in `bg` pipelines, English elsewhere.
- **Integration tests** — full HTTP-stack tests via `aioresponses` (54 tests total).

### Changed

- Config-flow `unique_id` now uses `<url>|<commitTag-or-version>` instead of bare URL — survives URL renames.
- `haseerr_request_submitted` event payload now includes `title`.
- Removed redundant `aiohttp>=3.9` from manifest `requirements`.
- Removed the `haseerr.reload_user_mapping` stub (use the integration tile's **Configure** button).

### Fixed

- TV requests now default `seasons: "all"` (Seerr returned 500 when omitted).

## v0.1.0 — 2026-05-04

### Initial release

- HA integration domain `haseerr` (avoids clash with core `overseerr`).
- Services: `haseerr.search`, `haseerr.request`, `haseerr.approve_request`, `haseerr.decline_request`.
- Smart user-mapping wizard (email-exact → name-exact → fuzzy ≥ 0.85).
- Custom Lovelace card (Lit web component); auto-registers in YAML and UI-mode Lovelace.
- Voice intent `RequestMedia` (en + bg).
- `sensor.haseerr_status` diagnostic sensor.
- HACS-installable, hassfest + HACS validators in CI.

### Live-deployed fixes that landed before v0.2

- `async_setup_intents` (was `async_register_intents`) — HA's intent platform discovery name.
- Options changes now refresh the sensor via an update listener.
- Search query RFC 3986 percent-encoding (Seerr rejects form-style `+`).
- Lovelace card auto-registration for UI/Storage-mode dashboards (was YAML-only).
