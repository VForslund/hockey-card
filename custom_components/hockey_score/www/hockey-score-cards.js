/**
 * Hockey Score — the two dashboard cards bundled with the hockey_score
 * integration. Served by the integration itself (add_extra_js_url with a
 * ?v=<manifest version> cache-busted URL): dashboards need no Lovelace
 * resource entries and card updates arrive with integration updates.
 *
 *   custom:hockey-score-card            the scoreboard — last match,
 *                                       the live/upcoming game, next match
 *   custom:hockey-score-standings-card   the league table, tracked row
 *                                       highlighted
 *
 * Data contract: the FLAT sensor attributes produced by the integration's
 * flatten.py. Every slot reads its own prefix — last_* / current_* /
 * next_* — with no data branching: idle → current_* is the upcoming game,
 * live → it is this game, and is_live switches cosmetics only (LIVE pill +
 * big scores vs VS + date · time). The one cosmetic exception: the venue
 * line reads current_game.venue from the passed-through API object
 * (venue is not part of the flat contract). Standings rows carry an
 * optional row.badge — the team's self-hosted logo URL; the proven
 * initials placeholder shows whenever any badge URL is empty.
 */

const TEAM_ENTITY = "sensor.hockey_team";
const BADGES_ENTITY = "sensor.hockey_team_badges";
const STANDINGS_ENTITY = "sensor.hockey_team_standings";

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>'"]/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
      })[c]
  );

// A badge image, or a same-sized initials placeholder when the URL is
// missing (the data source has no logo for every team, e.g. Visby/Roma HK).
function renderBadge(url, alt, cls) {
  if (url) {
    return `<img class="${cls}" src="${esc(url)}" alt="${esc(alt || "")}" />`;
  }
  const initial = alt && alt.length ? esc(alt.charAt(0).toUpperCase()) : "?";
  return `<div class="${cls} badge-placeholder">${initial}</div>`;
}

const BASE_CSS = `
  ha-card {
    padding: 20px;
    border-radius: 18px;
    background: var(--card-background-color);
    box-shadow: var(--ha-card-box-shadow, 0 4px 12px rgba(0, 0, 0, 0.18));
    color: var(--primary-text-color);
  }
  .hockey-card-container {
    display: flex;
    flex-direction: column;
    gap: 16px;
    font-family: var(--paper-font-body1_-_font-family, sans-serif);
  }
  .header-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .sub-title-tag {
    font-weight: 800;
    color: var(--secondary-text-color);
    text-transform: uppercase;
    font-size: 0.65rem;
    letter-spacing: 0.8px;
  }
  .sub-date-tag {
    font-size: 0.7rem;
    color: var(--secondary-text-color);
    font-weight: 500;
    opacity: 0.85;
  }
  img.mini-badge {
    width: 22px;
    height: 22px;
    object-fit: contain;
    filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.4));
  }
  .badge-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    color: var(--secondary-text-color);
    font-weight: 800;
    font-size: 0.9rem;
    box-sizing: border-box;
  }
  .mini-badge.badge-placeholder {
    font-size: 0.6rem;
  }
  .no-match-note {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--secondary-text-color);
    opacity: 0.7;
  }
  .missing {
    padding: 8px 2px;
    font-size: 0.85rem;
    color: var(--secondary-text-color);
  }
`;

// The scoreboard, ported 1:1 from the button-card template that ran on
// the overview dashboard (same art, same guards).
const SCOREBOARD_CSS = `
  @keyframes blink {
    from { opacity: 1; }
    to { opacity: 0.2; }
  }
  .team-title {
    font-weight: 800;
    font-size: 1.25rem;
    letter-spacing: 0.3px;
  }
  .scoreboard {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(150px, auto) minmax(0, 1fr);
    align-items: center;
    gap: 10px;
    background: var(--secondary-background-color, rgba(255,255,255,0.035));
    padding: 20px 14px 18px;
    border-radius: 16px;
    text-align: center;
    border: 1px solid rgba(255,255,255,0.055);
  }
  .team-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }
  .team-badge {
    width: 64px;
    height: 64px;
    object-fit: contain;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
  }
  .team-name {
    font-size: 0.86rem;
    font-weight: 750;
    max-width: 105px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .center-score {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .score-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 7px;
  }
  .score-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  .score-number {
    min-width: 58px;
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 14px;
    line-height: 1;
    font-size: 2.15rem;
    font-weight: 900;
    color: var(--primary-text-color, #ffffff);
    background: rgba(255,255,255,0.055);
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.035);
  }
  .score-number.live {
    background: linear-gradient(180deg, rgba(255,59,48,0.14), rgba(255,255,255,0.06));
    border-color: rgba(255,59,48,0.30);
    color: #fff;
    box-shadow:
      0 0 18px rgba(255,59,48,0.35),
      inset 0 1px 0 rgba(255,255,255,0.08);
    animation: hk-score-pulse 2s infinite ease-in-out;
  }
  @keyframes hk-score-pulse {
    0%, 100% { box-shadow: 0 0 14px rgba(255,59,48,0.25), inset 0 1px 0 rgba(255,255,255,0.08); }
    50%      { box-shadow: 0 0 24px rgba(255,59,48,0.45), inset 0 1px 0 rgba(255,255,255,0.08); }
  }
  .score-separator {
    color: var(--secondary-text-color);
    font-size: 1.2rem;
    font-weight: 800;
    line-height: 1;
    opacity: 0.7;
  }
  .score-vs {
    min-width: 72px;
    height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    background: rgba(255,255,255,0.055);
    color: var(--secondary-text-color);
    font-size: 1rem;
    font-weight: 800;
    letter-spacing: 1.5px;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .venue-text {
    font-size: 0.68rem;
    font-weight: 600;
    color: var(--secondary-text-color);
    opacity: 0.72;
    max-width: 160px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sub-games-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .sub-game-box {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.07);
    padding: 12px 14px;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  }
  .sub-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .sub-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    /* Both boxes share this row height in every state, so LAST and NEXT
       always align — a wrapped or short one-sided row cannot skew them. */
    min-height: 24px;
    /* Below the fit threshold the chip drops to its own line instead of
       overlapping the badges (ponytail review, narrow-phone guard). */
    flex-wrap: wrap;
  }
  .mini-badges-wrapper {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 800;
    font-size: 0.95rem;
  }
  .mini-score {
    white-space: nowrap;
  }
  .vs-span {
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--secondary-text-color);
    padding: 0 2px;
  }
  .result-badge {
    position: relative;
    padding: 3px 8px;
    border-radius: 6px;
    font-weight: 800;
    font-size: 0.65rem;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    white-space: nowrap;
  }
  .result-badge.win {
    background: rgba(34, 197, 94, 0.18);
    color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.3);
  }
  .result-badge.loss {
    background: rgba(239, 68, 68, 0.18);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
  }
  .result-badge.draw {
    background: rgba(234, 179, 8, 0.18);
    color: #facc15;
    border: 1px solid rgba(234, 179, 8, 0.3);
  }
  /* OT / SO decision tag — a solid mini-pill of the chip's own color family,
     hovering over the chip's bottom-right corner (half outside its edge). */
  .result-badge .decision-tag {
    position: absolute;
    right: -7px;
    bottom: -6px;
    padding: 1px 4px;
    border-radius: 5px;
    font-size: 0.5rem;
    line-height: 1;
    letter-spacing: 0.4px;
    font-weight: 800;
    border: 1px solid rgba(255, 255, 255, 0.28);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
  }
  .result-badge.win .decision-tag {
    background: #16a34a;
    color: #04240e;
  }
  .result-badge.loss .decision-tag {
    background: #dc2626;
    color: #fff1f2;
  }
  .result-badge.draw .decision-tag {
    background: #eab308;
    color: #1f1804;
  }
  .time-badge {
    background: rgba(255, 255, 255, 0.08);
    color: var(--primary-text-color);
    font-size: 0.75rem;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.1);
  }
`;

const COMPACT_CSS = `
  ha-card { padding: 12px; }
  .hockey-card-container { gap: 10px; }
  .scoreboard { padding: 10px 8px 10px; gap: 6px; }
  .team-badge { width: 44px; height: 44px; }
  .score-number { min-width: 44px; height: 46px; font-size: 1.6rem; border-radius: 10px; }
  .sub-game-box { padding: 8px 10px; gap: 6px; }
  .team-title { font-size: 1.05rem; }
`;

const STANDINGS_CSS = `
  .standings-table {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }
  .standings-table th {
    font-weight: 800;
    color: var(--secondary-text-color);
    text-transform: uppercase;
    font-size: 0.62rem;
    letter-spacing: 0.8px;
    padding: 4px 6px 8px;
    text-align: right;
    border-bottom: 1px solid rgba(255, 255, 255, 0.09);
  }
  .standings-table th.pos-col,
  .standings-table th.team-col {
    text-align: left;
  }
  .standings-table td {
    padding: 5px 6px;
    font-size: 0.82rem;
    text-align: right;
    border-bottom: 1px solid rgba(255, 255, 255, 0.045);
  }
  .standings-table td.pos,
  .standings-table td.team-col {
    text-align: left;
  }
  .standings-table td.pos {
    width: 30px;
    font-weight: 700;
    color: var(--secondary-text-color);
  }
  .standings-table td.team-col {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 160px;
  }
  .standings-table td.tp {
    font-weight: 800;
  }
  img.row-badge {
    width: 18px;
    height: 18px;
    object-fit: contain;
    vertical-align: middle;
    margin-right: 7px;
  }
  .row-badge.badge-placeholder {
    display: inline-flex;
    vertical-align: middle;
    width: 16px;
    height: 16px;
    font-size: 0.55rem;
    border-radius: 4px;
    margin-right: 9px;
  }
  .row-team {
    vertical-align: middle;
  }
  /* Tracked-row highlight: Leksands IF blue #26358C (PMS 286 C) — the
     team this install follows. Alphas lifted vs the old red to keep the
     same perceived tint (navy is a much darker base than that red). */
  .standings-table tbody tr.tracked td {
    background: rgba(38, 53, 140, 0.16);
    border-bottom: 1px solid rgba(38, 53, 140, 0.30);
    font-weight: 800;
  }
  .standings-table tbody tr.tracked td:first-child {
    box-shadow: inset 3px 0 0 rgba(38, 53, 140, 0.85);
  }
`;

const COMPACT_TABLE_CSS = `
  ha-card { padding: 12px; }
  .hockey-card-container { gap: 10px; }
  .standings-table td { padding: 3px 4px; font-size: 0.74rem; }
  .standings-table th { padding: 2px 4px 6px; font-size: 0.56rem; }
`;

// Everything the two cards share: shadow DOM root, hass subscription,
// render-only-on-change, full-width sections layout, the wait placeholder.
class HockeyBaseCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._sig = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getGridOptions() {
    return { columns: 12 };
  }

  // The entities this card listens to; the order fixes the _html arguments.
  _listenEntities() {
    return [];
  }

  _waitHtml(missing) {
    return `${BASE_CSS}<ha-card><div class="missing">
      Waiting for Hockey Score sensors (${esc(missing.join(", "))}) &hellip;
    </div></ha-card>`;
  }

  _render() {
    if (!this._hass || !this._config) {
      return;
    }
    const ids = this._listenEntities();
    const states = ids.map((id) => this._hass.states[id]);
    const sig = JSON.stringify(
      states.map((state) => state && [state.state, state.attributes])
    );
    if (sig === this._sig) {
      return;
    }
    this._sig = sig;
    const missing = ids.filter((id) => !this._hass.states[id]);
    if (missing.length) {
      this.shadowRoot.innerHTML = this._waitHtml(missing);
      return;
    }
    this.shadowRoot.innerHTML = this._html(
      ...states.map((state) => (state && state.attributes) || {})
    );
  }
}

class HockeyScoreCard extends HockeyBaseCard {
  static getStubConfig() {
    return {
      type: "hockey-score-card",
      entity: TEAM_ENTITY,
      badges_entity: BADGES_ENTITY,
    };
  }

  setConfig(config) {
    if (config.entity && typeof config.entity !== "string") {
      throw new Error("entity must be an entity id");
    }
    this._config = {
      entity: config.entity || TEAM_ENTITY,
      badges_entity: config.badges_entity || BADGES_ENTITY,
      name: config.name || "",
      compact: !!config.compact,
    };
    this._sig = null;
    this._render();
  }

  getCardSize() {
    return 6;
  }

  _listenEntities() {
    return [this._config.entity, this._config.badges_entity];
  }

  _html(a, b) {
    const compact = this._config.compact;
    const isLive = !!a.is_live;

    // current_* — the live game while live, the upcoming game while idle.
    const homeTeam = a.current_home_team || "";
    const awayTeam = a.current_away_team || "";
    const homeScore = a.current_home_score;
    const awayScore = a.current_away_score;
    // The one cosmetic object exception (see header comment).
    const venue = (a.current_game && a.current_game.venue) || "";

    const hasScore =
      homeScore != null &&
      awayScore != null &&
      (homeScore > 0 || awayScore > 0 || isLive);

    const livePeriod = String(a.current_period || "").toUpperCase();
    const liveLabel = livePeriod ? `LIVE &bull; ${livePeriod}` : "LIVE";

    const statusBadge = isLive
      ? `<div style="display: inline-flex; align-items: center; gap: 6px; background: rgba(255, 59, 48, 0.14); color: #ff6b63; padding: 4px 10px; border-radius: 999px; font-weight: 800; font-size: 0.72rem; letter-spacing: 0.6px; border: 1px solid rgba(255,59,48,0.18);">
          <span style="width: 6px; height: 6px; background: #ff3b30; border-radius: 50%; animation: blink 1s infinite alternate linear;"></span>
          ${liveLabel}
        </div>`
      : `<div style="color: var(--secondary-text-color); font-size: 0.85rem; font-weight: 600;">
          ${esc(a.current_game_date || "")} &bull; ${esc(a.current_game_time || "")}
        </div>`;

    const scoreDisplay = isLive
      ? `<div class="score-wrap"><div class="score-row">
          <div class="score-number live">${esc(homeScore ?? 0)}</div>
          <div class="score-separator">:</div>
          <div class="score-number live">${esc(awayScore ?? 0)}</div>
        </div></div>`
      : hasScore
        ? `<div class="score-wrap"><div class="score-row">
            <div class="score-number">${esc(homeScore)}</div>
            <div class="score-separator">:</div>
            <div class="score-number">${esc(awayScore)}</div>
          </div></div>`
        : `<div class="score-vs">VS</div>`;

    // last_* — the last finished match. Off-season blanking: no date
    // means "No previous match", never "null - null" with an empty chip.
    const hasLastGame = !!a.last_game_date;
    const lastHasScore =
      hasLastGame && a.last_home_score != null && a.last_away_score != null;
    const lastScoreText = lastHasScore
      ? `${esc(a.last_home_score)} - ${esc(a.last_away_score)}`
      : `–`;
    const lastResult = a.last_result || "";
    // OT / SO rides as a corner tag hovering at the chip's bottom-right, not
    // inline — the chip stays a tight WIN/LOSS/DRAW pill and the row cannot
    // wrap at narrow card widths.
    const decision = lastResult && a.last_shootout
      ? "SO"
      : lastResult && a.last_overtime
        ? "OT"
        : "";
    const lastResultBadge = lastResult
      ? `<span class="result-badge ${esc(lastResult)}">${esc(lastResult)}${decision ? `<span class="decision-tag">${esc(decision)}</span>` : ""}</span>`
      : "";

    // next_* — the game after the one current_* is showing.
    const hasNextGame = !!a.next_game_date;

    const title = this._config.name || b.team_name || "Hockey Team";

    return `<style>${BASE_CSS}${SCOREBOARD_CSS}${compact ? COMPACT_CSS : ""}</style>
      <ha-card${compact ? ` class="compact"` : ""}>
        <div class="hockey-card-container">
          <div class="header-bar">
            <div class="team-title">${esc(title)}</div>
            ${statusBadge}
          </div>

          <div class="scoreboard">
            <div class="team-box">
              ${renderBadge(b.current_home_badge, homeTeam, "team-badge")}
              <div class="team-name">${esc(homeTeam || "Home")}</div>
            </div>

            <div class="center-score">
              ${scoreDisplay}
              <div class="venue-text">${esc(venue)}</div>
            </div>

            <div class="team-box">
              ${renderBadge(b.current_away_badge, awayTeam, "team-badge")}
              <div class="team-name">${esc(awayTeam || "Away")}</div>
            </div>
          </div>

          <div class="sub-games-grid">
            <div class="sub-game-box">
              <div class="sub-header">
                <span class="sub-title-tag">LAST MATCH</span>
                <span class="sub-date-tag">${esc(hasLastGame ? a.last_game_date : "")}</span>
              </div>
              <div class="sub-content">
                ${hasLastGame
                  ? `<div class="mini-badges-wrapper">
                      ${renderBadge(b.last_home_badge, a.last_home_team, "mini-badge")}
                      <span class="mini-score">${lastScoreText}</span>
                      ${renderBadge(b.last_away_badge, a.last_away_team, "mini-badge")}
                    </div>
                    ${lastResultBadge}`
                  : `<span class="no-match-note">No previous match</span>`}
              </div>
            </div>

            <div class="sub-game-box">
              <div class="sub-header">
                <span class="sub-title-tag">NEXT MATCH</span>
                <span class="sub-date-tag">${esc(hasNextGame ? a.next_game_date : "")}</span>
              </div>
              <div class="sub-content">
                ${hasNextGame
                  ? `<div class="mini-badges-wrapper">
                      ${renderBadge(b.next_home_badge, a.next_home_team, "mini-badge")}
                      <span class="vs-span">VS</span>
                      ${renderBadge(b.next_away_badge, a.next_away_team, "mini-badge")}
                    </div>
                    <span class="time-badge">${esc(a.next_game_time || "")}</span>`
                  : `<span class="no-match-note">No upcoming match</span>`}
              </div>
            </div>
          </div>
        </div>
      </ha-card>`;
  }
}

class HockeyScoreStandingsCard extends HockeyBaseCard {
  static getStubConfig() {
    return { type: "hockey-score-standings-card", entity: STANDINGS_ENTITY };
  }

  setConfig(config) {
    if (config.entity && typeof config.entity !== "string") {
      throw new Error("entity must be an entity id");
    }
    this._config = {
      entity: config.entity || STANDINGS_ENTITY,
      name: config.name || "",
      compact: !!config.compact,
    };
    this._sig = null;
    this._render();
  }

  getCardSize() {
    return 7;
  }

  _listenEntities() {
    return [this._config.entity];
  }

  _html(a) {
    const compact = this._config.compact;
    const rows = Array.isArray(a.standings) ? a.standings : [];
    const updated = a.standings_updated
      ? `updated ${esc(String(a.standings_updated).slice(0, 16))}`
      : "";
    const title = this._config.name || "League standings";

    const body = rows.length
      ? `<table class="standings-table">
          <thead>
            <tr>
              <th class="pos-col">#</th>
              <th class="team-col">Team</th>
              <th>GP</th>
              <th>W-T-L</th>
              <th>GD</th>
              <th>TP</th>
            </tr>
          </thead>
          <tbody>
            ${rows
              .map((r) => {
                const gd =
                  r.gd == null ? "" : r.gd > 0 ? `+${r.gd}` : String(r.gd);
                return `
                  <tr class="${r.tracked ? "tracked" : ""}">
                    <td class="pos">${esc(r.position ?? "")}</td>
                    <td class="team-col">${renderBadge(r.badge || "", r.team, "row-badge")}<span class="row-team">${esc(r.team)}</span></td>
                    <td>${esc(r.gp ?? "")}</td>
                    <td>${esc(r.w ?? "")}-${esc(r.t ?? "")}-${esc(r.l ?? "")}</td>
                    <td>${esc(gd)}</td>
                    <td class="tp">${esc(r.tp ?? "")}</td>
                  </tr>`;
              })
              .join("")}
          </tbody>
        </table>`
      : `<div class="no-match-note">No standings fetched yet${updated ? ` (${updated})` : ""}.</div>`;

    return `<style>${BASE_CSS}${STANDINGS_CSS}${compact ? COMPACT_TABLE_CSS : ""}</style>
      <ha-card${compact ? ` class="compact"` : ""}>
        <div class="hockey-card-container">
          <div class="header-bar">
            <span class="sub-title-tag">${esc(title)}</span>
            <span class="sub-date-tag">${updated}</span>
          </div>
          ${body}
        </div>
      </ha-card>`;
  }
}

customElements.define("hockey-score-card", HockeyScoreCard);
customElements.define("hockey-score-standings-card", HockeyScoreStandingsCard);

// Make both cards findable in the dashboard editor's card picker.
(window.customCards = window.customCards || []).push(
  {
    type: "hockey-score-card",
    name: "Hockey Score",
    description: "Scoreboard: last match, live score with period, next match.",
  },
  {
    type: "hockey-score-standings-card",
    name: "Hockey Score Standings",
    description: "League table with the tracked team highlighted.",
  }
);
