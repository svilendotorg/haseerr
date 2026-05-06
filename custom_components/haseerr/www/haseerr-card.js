// haseerr-card.js — Lovelace custom card for HaSeerr
import { LitElement, html, css } from "https://unpkg.com/lit@3.1.0/index.js?module";

class HaSeerrCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _query: { state: true },
    _results: { state: true },
    _loading: { state: true },
    _toast: { state: true },
    _quota: { state: true },
    _is4k: { state: true },
  };

  static styles = css`
    :host { display: block; }
    ha-card { padding: 16px; }
    .row {
      display: grid;
      grid-template-columns: 60px 1fr auto;
      gap: 12px;
      align-items: center;
      padding: 8px 0;
      border-top: 1px solid var(--divider-color);
    }
    .row img { width: 60px; border-radius: 4px; }
    .toast {
      background: var(--success-color, #4caf50);
      color: white; padding: 8px 12px; border-radius: 4px;
      margin-top: 8px;
    }
    .input-row { display: flex; gap: 8px; align-items: stretch; }
    .input-row input { flex: 1; padding: 8px; }
    .quality-chip {
      background: transparent;
      border: 1.5px solid var(--divider-color);
      color: var(--secondary-text-color);
      padding: 0 14px;
      border-radius: 16px;
      font-size: 0.78em;
      font-weight: 700;
      letter-spacing: 0.5px;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s, color 0.15s;
      user-select: none;
      display: inline-flex;
      align-items: center;
    }
    .quality-chip:hover {
      border-color: var(--primary-color);
      color: var(--primary-color);
    }
    .quality-chip.active {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, white);
    }
    .quality-chip.active:hover {
      filter: brightness(1.1);
    }
    .quota-row {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .quota-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 4px 10px;
      border-radius: 14px;
      font-size: 0.78em;
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
      color: var(--primary-text-color);
    }
    .quota-icon { font-size: 0.95em; line-height: 1; }
    .quota-count {
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.2px;
    }
    .quota-bar {
      width: 36px;
      height: 4px;
      background: var(--divider-color);
      border-radius: 2px;
      overflow: hidden;
      flex-shrink: 0;
    }
    .quota-fill {
      display: block;
      height: 100%;
      background: var(--success-color, #4caf50);
      transition: width 0.3s ease, background 0.2s;
    }
    .quota-pill.mid .quota-fill {
      background: var(--warning-color, #ff9800);
    }
    .quota-pill.warn .quota-fill {
      background: #ff7043;
    }
    .quota-pill.full .quota-fill {
      background: var(--error-color, #f44336);
    }
    .quota-pill.full {
      color: var(--error-color, #f44336);
    }
    .quota-pill.unlimited {
      opacity: 0.7;
    }
  `;

  setConfig(config) {
    this._config = {
      title: "",
      limit: 5,
      poster_size: "w200",
      hide_unavailable: false,
      allow_season_picker: true,
      show_quota: true,
      ...config,
    };
    this._query = "";
    this._results = [];
    this._seerrUrl = "";
    this._loading = false;
    this._toast = "";
    this._quota = null;
    this._is4k = false;
  }

  connectedCallback() {
    super.connectedCallback();
    if (this._config?.show_quota && this.hass) this._refreshQuota();
  }

  async _refreshQuota() {
    try {
      const r = await this.hass.callService(
        "haseerr", "user_quota", {}, undefined, false, true
      );
      this._quota = r.response;
    } catch (e) {
      this._quota = null;
    }
  }

  static getConfigElement() {
    return document.createElement("haseerr-card-editor");
  }

  static getStubConfig() {
    return { title: "HaSeerr", limit: 5 };
  }

  async _onSearch() {
    if (!this._query.trim()) return;
    this._loading = true;
    this._toast = "";
    try {
      const resp = await this.hass.callService(
        "haseerr", "search",
        { query: this._query, limit: this._config.limit },
        undefined, false, true /* return_response */
      );
      this._seerrUrl = resp.response.seerr_url || "";
      this._results = (resp.response.results || []).filter(
        r => !this._config.hide_unavailable || r.status !== "available"
      );
    } catch (e) {
      this._toast = `Search failed: ${e.message || e}`;
    } finally {
      this._loading = false;
    }
  }

  async _onPick(result, seasons) {
    try {
      const data = {
        tmdb_id: result.tmdb_id,
        media_type: result.media_type,
        title: result.title,
      };
      if (result.media_type === "tv" && seasons) data.seasons = seasons;
      if (this._is4k && result.media_type !== "music") data.is_4k = true;
      const resp = await this.hass.callService(
        "haseerr", "request", data, undefined, false, true
      );
      const r = resp.response;
      const suffix = data.is_4k ? " · 4K" : "";
      this._toast = `Requested ${result.title} for ${r.seerr_user_display} — ${r.status}${suffix}`;
      this._query = "";
      this._results = [];
      // Refresh quota since the count went up
      if (this._config.show_quota) this._refreshQuota();
    } catch (e) {
      this._toast = `Request failed: ${e.message || e}`;
    }
  }

  _renderQuota() {
    if (!this._config.show_quota || !this._quota) return "";
    const m = this._quota.movie || {};
    const t = this._quota.tv || {};
    const pct = (q) => (q.limit ? Math.min(100, Math.round(((q.used ?? 0) / q.limit) * 100)) : 0);
    const fmt = (q) => (q.limit ? `${q.used ?? 0}/${q.limit}` : "∞");
    const stateClass = (q) => {
      if (!q.limit) return "unlimited";
      const p = pct(q);
      if (p >= 100) return "full";
      if (p >= 80) return "warn";
      if (p >= 50) return "mid";
      return "ok";
    };
    const pill = (icon, q, label) => html`
      <span class="quota-pill ${stateClass(q)}" title=${`${label}: ${fmt(q)}`}>
        <span class="quota-icon">${icon}</span>
        <span class="quota-count">${fmt(q)}</span>
        ${q.limit
          ? html`<span class="quota-bar"><span class="quota-fill" style="width:${pct(q)}%"></span></span>`
          : ""}
      </span>
    `;
    return html`
      <div class="quota-row">
        ${pill("🎬", m, "Movies")}
        ${pill("📺", t, "TV")}
      </div>
    `;
  }

  _seerrLink(r) {
    if (!this._seerrUrl) return null;
    const path = r.media_type === "music"
      ? `/music/${encodeURIComponent(r.tmdb_id)}`
      : `/${r.media_type}/${r.tmdb_id}`;
    return `${this._seerrUrl}${path}`;
  }

  _mediaTypeLabel(t) {
    if (t === "movie") return "Movie";
    if (t === "tv") return "TV";
    if (t === "music") return "Music";
    return t;
  }

  render() {
    return html`
      <ha-card .header=${this._config.title || ""}>
        ${this._renderQuota()}
        <div class="input-row">
          <input
            type="text"
            placeholder="Search movies & TV…"
            .value=${this._query}
            @input=${(e) => (this._query = e.target.value)}
            @keydown=${(e) => e.key === "Enter" && this._onSearch()}
          />
          <button
            type="button"
            class="quality-chip ${this._is4k ? "active" : ""}"
            @click=${() => (this._is4k = !this._is4k)}
            title=${this._is4k ? "4K request enabled" : "Toggle 4K request"}
            aria-pressed=${this._is4k}
          >4K</button>
          <button @click=${this._onSearch}>🔍</button>
        </div>
        ${this._loading ? html`<div>Searching…</div>` : ""}
        ${this._results.map((r) => {
          const link = this._seerrLink(r);
          const titleNode = link
            ? html`<a href=${link} target="_blank" rel="noopener noreferrer">${r.title}</a>`
            : html`${r.title}`;
          return html`
            <div class="row">
              ${r.poster_url
                ? html`<img src=${r.poster_url} alt="poster"/>`
                : html`<div></div>`}
              <div>
                <strong>${titleNode}</strong> (${r.year || "—"}) · ${this._mediaTypeLabel(r.media_type)}
                <div style="font-size: 0.85em; color: var(--secondary-text-color)">
                  ${(r.overview || "").slice(0, 120)}…
                </div>
              </div>
              ${r.status === "available"
                ? html`<span>✓ Available</span>`
                : html`<button @click=${() => this._onPick(r, "all")}>Request</button>`}
            </div>
          `;
        })}
        ${this._toast ? html`<div class="toast">${this._toast}</div>` : ""}
      </ha-card>
    `;
  }
}

customElements.define("haseerr-card", HaSeerrCard);


class HaSeerrCardEditor extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
  };

  static styles = css`
    :host { display: block; padding: 16px; }
    .field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
    .field label { font-weight: 500; }
    .field-inline { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    input[type="text"], input[type="number"], select {
      padding: 6px 8px;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
    }
  `;

  setConfig(config) {
    this._config = {
      title: "HaSeerr",
      limit: 5,
      poster_size: "w200",
      hide_unavailable: false,
      allow_season_picker: true,
      ...config,
    };
  }

  _emit(field, value) {
    const next = { ...this._config, [field]: value };
    this._config = next;
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: next }, bubbles: true, composed: true,
    }));
  }

  render() {
    if (!this._config) return html``;
    return html`
      <div class="field">
        <label>Title</label>
        <input type="text" .value=${this._config.title || ""}
          @input=${(e) => this._emit("title", e.target.value)} />
      </div>
      <div class="field">
        <label>Search result limit (1-20)</label>
        <input type="number" min="1" max="20" .value=${this._config.limit || 5}
          @input=${(e) => this._emit("limit", parseInt(e.target.value, 10) || 5)} />
      </div>
      <div class="field">
        <label>Poster size</label>
        <select @change=${(e) => this._emit("poster_size", e.target.value)}>
          ${["w92", "w154", "w185", "w200", "w300", "w500"].map(s => html`
            <option value=${s} ?selected=${(this._config.poster_size || "w200") === s}>${s}</option>
          `)}
        </select>
      </div>
      <div class="field-inline">
        <input type="checkbox" id="hu" .checked=${this._config.hide_unavailable ?? false}
          @change=${(e) => this._emit("hide_unavailable", e.target.checked)} />
        <label for="hu">Hide already-available results</label>
      </div>
      <div class="field-inline">
        <input type="checkbox" id="asp" .checked=${this._config.allow_season_picker ?? true}
          @change=${(e) => this._emit("allow_season_picker", e.target.checked)} />
        <label for="asp">Allow TV season picker</label>
      </div>
    `;
  }
}
customElements.define("haseerr-card-editor", HaSeerrCardEditor);


// Register card in HA's picker UI
window.customCards = window.customCards || [];
window.customCards.push({
  type: "haseerr-card",
  name: "HaSeerr",
  description: "Request movies & TV via Seerr",
  preview: true,
  documentationURL: "https://github.com/svilendotorg/haseerr",
});
