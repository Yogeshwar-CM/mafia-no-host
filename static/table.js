/* The shared screen. Subscribes without a token, so it can only ever
   receive public state — there is no secret here to leak. */
(() => {
  "use strict";

  const root = document.getElementById("table");
  let state = null;
  let clockOffset = 0;

  const esc = (s) => String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const HEADLINE = {
    lobby: "Join the table",
    night: "Night falls — phones only",
    day: "Talk it out",
    vote: "The vote is open",
    over: "Game over",
  };

  const SUBTITLE = {
    night: "Mafia, detective and doctor are choosing. Everyone else, sit tight.",
    day: "Accuse. Defend. Lie. The vote opens when everyone is ready.",
    vote: "A tie eliminates nobody.",
  };

  function clock() {
    if (!state.public.deadline) return "";
    const left = Math.max(0, Math.round(
      state.public.deadline - (Date.now() + clockOffset) / 1000));
    const ss = String(left % 60).padStart(2, "0");
    return `<div class="clock ${left <= 10 ? "urgent" : ""}">${Math.floor(left / 60)}:${ss}</div>`;
  }

  function seats() {
    const p = state.public;
    const voted = new Set(p.voted || []);
    const ready = new Set(p.ready || []);
    return `<div>${p.players.map((x) => {
      let tag = "";
      if (!x.alive && x.role) tag = `<span class="tag ${x.role === "mafia" ? "mafia" : ""}">${esc(x.role)}</span>`;
      else if (p.phase === "vote") tag = voted.has(x.id) ? `<span class="tag ok">voted</span>` : `<span class="tag">thinking</span>`;
      else if (p.phase === "day") tag = ready.has(x.id) ? `<span class="tag ok">ready</span>` : "";
      else if (!x.connected) tag = `<span class="tag">away</span>`;
      return `<div class="seat ${x.alive ? "" : "dead"}">
        <span class="dot ${x.connected ? "" : "off"}"></span>${esc(x.name)}${tag}</div>`;
    }).join("")}</div>`;
  }

  function story() {
    const entries = state.public.log.slice(-8).reverse();
    return `<div><ul class="log">${entries.map((e) =>
      `<li><div class="round">${e.round ? `Round ${e.round}` : "Start"}</div>${esc(e.text)}</li>`
    ).join("")}</ul></div>`;
  }

  function render() {
    if (!state) { root.innerHTML = `<h1>Connecting…</h1>`; return; }
    const p = state.public;
    document.body.dataset.phase = p.phase;

    const header = `<div class="banner" style="margin-bottom:22px">
      <div>
        <h1>${HEADLINE[p.phase] || p.phase}</h1>
        <p class="muted">${p.phase === "over"
          ? (p.winner === "mafia" ? "The mafia win." : "The town wins.")
          : (SUBTITLE[p.phase] || "")}</p>
      </div>${clock()}</div>`;

    const hint = p.phase === "lobby"
      ? `<div class="card join-hint">
           <p>Open <code>${esc(location.host)}</code> on your phone.</p>
           <p class="muted">${p.players.length} seated &middot; ${p.min_players} needed to start.
              The first player to join is the host.</p>
         </div>`
      : "";

    root.innerHTML = header + hint +
      `<div class="table-grid">${seats()}${p.phase === "lobby" ? "" : story()}</div>`;
  }

  const source = new EventSource("/api/events");
  source.onmessage = (event) => {
    state = JSON.parse(event.data);
    clockOffset = state.server_time * 1000 - Date.now();
    render();
  };

  setInterval(() => {
    if (!state || !state.public.deadline) return;
    const el = document.querySelector(".clock");
    if (el) el.outerHTML = clock();
  }, 1000);

  render();
})();
