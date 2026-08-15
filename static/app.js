/* The player's phone: private role, private night action, private results. */
(() => {
  "use strict";

  const app = document.getElementById("app");
  const KEY = "mafia.token";
  let token = localStorage.getItem(KEY);
  let state = null;
  let error = "";
  let roleVisible = false;
  let clockOffset = 0;   // serverTime - localTime
  let source = null;

  const ROLE_BLURB = {
    mafia: "Each night you and your partners choose someone to kill. By day, blend in.",
    detective: "Each night you may investigate one player and learn if they are mafia.",
    doctor: "Each night you may protect one player. Never the same one twice in a row.",
    villager: "You have no night action. Your weapon is the vote.",
  };

  const PHASE_TITLE = {
    lobby: "Gathering", night: "Night", day: "Discussion",
    vote: "The vote", over: "Game over",
  };

  const esc = (s) => String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------------------------------------------------------- network

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "something went wrong");
    return data;
  }

  function act(type, extra) {
    error = "";
    post("/api/act", Object.assign({ token, type }, extra || {}))
      .catch((e) => { error = e.message; render(); });
  }

  function connect() {
    if (source) source.close();
    source = new EventSource(`/api/events?token=${encodeURIComponent(token || "")}`);
    source.onmessage = (event) => {
      state = JSON.parse(event.data);
      clockOffset = state.server_time * 1000 - Date.now();
      // Back in the lobby means a fresh deal is coming: re-hide the old secret.
      if (state.public.phase === "lobby") roleVisible = false;
      render();
    };
    source.onerror = () => { /* EventSource retries on its own */ };
  }

  // ----------------------------------------------------------------- pieces

  function clock() {
    const deadline = state.public.deadline;
    if (!deadline) return "";
    const left = Math.max(0, Math.round(deadline - (Date.now() + clockOffset) / 1000));
    const mm = String(Math.floor(left / 60)).padStart(1, "0");
    const ss = String(left % 60).padStart(2, "0");
    return `<span class="clock ${left <= 10 ? "urgent" : ""}">${mm}:${ss}</span>`;
  }

  function banner() {
    const p = state.public;
    const round = p.round ? `Night ${p.round}` : "";
    return `<div class="card banner">
      <div>
        <div class="phase">${PHASE_TITLE[p.phase] || p.phase}</div>
        <div class="muted small">${round} &middot; ${p.alive_count} alive</div>
      </div>${clock()}</div>`;
  }

  function roleCard() {
    const me = state.private;
    if (!me.role) return "";
    const body = `
      <div class="role-name">${esc(me.role)}</div>
      <p class="muted small">${ROLE_BLURB[me.role] || ""}</p>
      ${me.partners && me.partners.length
        ? `<p class="small">With you: ${me.partners.map((p) =>
            `<span class="pill mafia">${esc(p.name)}${p.alive ? "" : " (dead)"}</span>`).join("")}</p>`
        : ""}
      ${me.role === "detective" && me.investigations
        ? investigations(me.investigations) : ""}
      ${me.alive ? "" : `<p class="small muted">You are out. Watch quietly — no talking.</p>`}`;

    return `<div class="card role-card role-${esc(me.role)}">
      ${body}
      ${roleVisible ? "" : `<div class="veil" data-reveal>Tap to see your role</div>`}
    </div>`;
  }

  function investigations(notes) {
    if (!notes.length) return `<p class="small muted">No investigations yet.</p>`;
    return `<p class="small">Your findings: ${notes.map((n) =>
      `<span class="pill ${n.is_mafia ? "mafia" : "clear"}">${esc(n.name)}: ${
        n.is_mafia ? "MAFIA" : "not mafia"}</span>`).join("")}</p>`;
  }

  function lobby() {
    const p = state.public;
    const enough = p.players.length >= p.min_players;
    return `<div class="card">
      <h2>Players (${p.players.length})</h2>
      <ul class="players">${p.players.map((x) =>
        `<li><span class="dot ${x.connected ? "" : "off"}"></span>${esc(x.name)}
         ${x.id === state.you ? '<span class="tag">you</span>' : ""}</li>`).join("")}</ul>
      </div>
      <div class="card">
      ${state.is_host
        ? `<button class="primary" data-act="start" ${enough ? "" : "disabled"}>
             ${enough ? "Start the game" : `Need ${p.min_players - p.players.length} more`}
           </button>
           <p class="small muted center" style="margin-top:10px">
             Roles are dealt at random. Nobody, including you, sees anyone else's.</p>`
        : `<p class="center muted">Waiting for the host to start${enough ? "" : " — more players needed"}.</p>`}
      </div>`;
  }

  function nightPanel() {
    const me = state.private;
    if (!me.alive) return `<div class="card"><p class="muted">The night passes without you.</p></div>`;
    if (!me.action) {
      return `<div class="card">
        <h2>Sleep tight</h2>
        <p class="muted">You have no night action. Wait for morning.</p></div>`;
    }
    const verb = { kill: "Kill", investigate: "Investigate", protect: "Protect" }[me.action];
    const chosen = me.submitted;
    const buttons = (me.targets || []).map((t) =>
      `<button data-target="${t.id}" class="${chosen === t.id ? "selected" : ""}">
         ${verb} ${esc(t.name)}</button>`).join("");

    const skip = me.action === "kill" ? "" :
      `<button data-target="none" class="ghost ${me.has_submitted && chosen === null ? "selected" : ""}">
         Do nothing tonight</button>`;

    const partnerVotes = me.partner_votes && me.partner_votes.length > 1
      ? `<p class="small muted">Your side so far: ${me.partner_votes.map((v) =>
          `${esc(v.voter)} &rarr; ${esc(v.target)}`).join(", ")}</p>` : "";

    const noTargets = (me.targets || []).length === 0
      ? `<p class="small muted">No legal target tonight.</p>` : "";

    return `<div class="card">
      <h2>${verb} someone</h2>
      ${me.role === "doctor" && me.last_protected
        ? `<p class="small muted">You protected someone last night — you cannot repeat them.</p>` : ""}
      ${noTargets}${buttons}${skip}${partnerVotes}
      <p class="small muted" style="margin-top:10px">You can change your mind until the night ends.</p>
    </div>`;
  }

  function dayPanel() {
    const me = state.private;
    if (!me.alive) return `<div class="card"><p class="muted">You are dead. No talking.</p></div>`;
    const ready = (state.public.ready || []).includes(state.you);
    const count = (state.public.ready || []).length;
    return `<div class="card">
      <h2>Talk it out</h2>
      <p class="muted small">Accuse, defend, lie. The vote opens when everyone is ready
        or the clock runs out.</p>
      <button class="${ready ? "selected" : "primary"}" data-act="ready" data-ready="${ready ? "0" : "1"}">
        ${ready ? "Ready — tap to undo" : "I'm ready to vote"}</button>
      <p class="small muted center" style="margin-top:10px">
        ${count} of ${state.public.alive_count} ready</p>
    </div>`;
  }

  function votePanel() {
    const me = state.private;
    if (!me.alive) return `<div class="card"><p class="muted">The dead do not vote.</p></div>`;
    const chosen = me.submitted_vote;
    const alive = state.public.players.filter((p) => p.alive);
    const buttons = alive.map((p) =>
      `<button data-vote="${p.id}" class="${chosen === p.id ? "selected" : ""}">
         Vote out ${esc(p.name)}${p.id === state.you ? " (you)" : ""}</button>`).join("");
    return `<div class="card">
      <h2>Who goes?</h2>
      ${buttons}
      <button class="ghost ${chosen === null ? "selected" : ""}" data-vote="none">Abstain</button>
      <p class="small muted" style="margin-top:10px">
        A tie eliminates nobody. ${(state.public.voted || []).length} of
        ${state.public.alive_count} have voted.</p>
    </div>`;
  }

  function overPanel() {
    const p = state.public;
    const won = p.winner === "mafia" ? "The mafia win." : "The town wins.";
    return `<div class="card center">
      <h1>${won}</h1>
      <ul class="players" style="text-align:left;margin-top:14px">
        ${p.players.map((x) =>
          `<li class="${x.alive ? "" : "dead"}">${esc(x.name)}
           <span class="tag ${x.role === "mafia" ? "mafia" : ""}">${esc(x.role || "?")}</span></li>`).join("")}
      </ul>
      ${state.is_host ? `<button class="primary" data-act="reset" style="margin-top:14px">
        Deal again, same players</button>` : `<p class="muted small" style="margin-top:12px">
        Waiting for the host to deal again.</p>`}
    </div>`;
  }

  function logCard() {
    const entries = state.public.log.slice(-12).reverse();
    if (!entries.length) return "";
    return `<div class="card"><h2>What happened</h2>
      <ul class="log">${entries.map((e) =>
        `<li><div class="round">${e.round ? `Round ${e.round}` : "Start"}</div>${esc(e.text)}</li>`
      ).join("")}</ul></div>`;
  }

  function rosterCard() {
    const p = state.public;
    return `<div class="card"><h2>At the table</h2>
      <ul class="players">${p.players.map((x) =>
        `<li class="${x.alive ? "" : "dead"}">
          <span class="dot ${x.connected ? "" : "off"}"></span>${esc(x.name)}
          ${x.id === state.you ? '<span class="tag">you</span>' : ""}
          ${!x.alive && x.role ? `<span class="tag ${x.role === "mafia" ? "mafia" : ""}">${esc(x.role)}</span>` : ""}
        </li>`).join("")}</ul></div>`;
  }

  function joinScreen() {
    const open = !state || state.can_join;
    return `<div class="card">
      <h1>Mafia</h1>
      <p class="muted">No host needed. This phone is your private screen —
        keep it to yourself.</p>
      ${open
        ? `<input type="text" id="name" placeholder="Your name" maxlength="20" autocomplete="off">
           <button class="primary" data-act="join">Join the table</button>`
        : `<p class="notice">A game is already in progress. You can watch the shared
           screen and join the next one.</p>`}
    </div>`;
  }

  // ----------------------------------------------------------------- render

  function render() {
    if (!state) { app.innerHTML = `<div class="card"><p class="muted">Connecting…</p></div>`; return; }
    document.body.dataset.phase = state.public.phase;

    if (!state.you) {
      app.innerHTML = (error ? `<div class="notice">${esc(error)}</div>` : "") +
        joinScreen() + (state.public.players.length ? rosterCard() : "");
      return;
    }

    const phase = state.public.phase;
    let panel = "";
    if (phase === "lobby") panel = lobby();
    else if (phase === "night") panel = nightPanel();
    else if (phase === "day") panel = dayPanel();
    else if (phase === "vote") panel = votePanel();
    else if (phase === "over") panel = overPanel();

    app.innerHTML =
      (error ? `<div class="notice">${esc(error)}</div>` : "") +
      (phase === "lobby" || phase === "over" ? "" : banner()) +
      (phase === "lobby" ? "" : roleCard()) +
      panel +
      (phase === "lobby" || phase === "over" ? "" : rosterCard()) +
      (phase === "lobby" ? "" : logCard());
  }

  // ------------------------------------------------------------------ input

  app.addEventListener("click", (event) => {
    const el = event.target.closest("[data-act],[data-target],[data-vote],[data-reveal]");
    if (!el) return;

    if (el.hasAttribute("data-reveal")) { roleVisible = true; return render(); }

    if (el.dataset.act === "join") {
      const name = (document.getElementById("name") || {}).value || "";
      error = "";
      post("/api/join", { name })
        .then((data) => { token = data.token; localStorage.setItem(KEY, token); connect(); })
        .catch((e) => { error = e.message; render(); });
      return;
    }
    if (el.dataset.act === "start") return act("start");
    if (el.dataset.act === "reset") { roleVisible = false; return act("reset"); }
    if (el.dataset.act === "ready") return act("ready", { ready: el.dataset.ready === "1" });
    if (el.dataset.target !== undefined) {
      const t = el.dataset.target === "none" ? null : Number(el.dataset.target);
      return act("night", { target: t });
    }
    if (el.dataset.vote !== undefined) {
      const t = el.dataset.vote === "none" ? null : Number(el.dataset.vote);
      return act("vote", { target: t });
    }
  });

  // Tick the countdown locally so it moves between server pushes.
  setInterval(() => {
    if (!state || !state.public.deadline) return;
    const el = document.querySelector(".clock");
    if (el) el.outerHTML = clock();
  }, 1000);

  connect();
  render();
})();
