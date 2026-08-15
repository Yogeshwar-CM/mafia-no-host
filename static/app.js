/* The player's phone: a private script. Role, night action, and the
   detective's findings live here and nowhere else. */
(() => {
  "use strict";

  const app = document.getElementById("app");
  const KEY = "mafia.token";

  let token = localStorage.getItem(KEY);
  let state = null;
  let error = "";
  let peeking = false;      // held, never toggled
  let clockOffset = 0;      // serverTime - localTime
  let lastScene = null;     // so title cards fire on change, not on every push
  let source = null;

  const BRIEF = {
    mafia: "Each night you and your partners choose someone to kill. By day, blend in.",
    detective: "Each night you may investigate one player and learn if they are mafia.",
    doctor: "Each night you may protect one player. Never the same one twice running.",
    villager: "You have no night action. Your weapon is the vote.",
  };

  const esc = (s) => String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* --- The performance ---------------------------------------------------
     Every phase is an act with a name. The mood re-lights the whole room. */

  function scene() {
    const p = state.public;
    const n = p.round;
    switch (p.phase) {
      case "lobby": return { mood: "ink", act: "The company", title: "Take your seats" };
      case "night": return { mood: "ink", act: `Act ${n} · Night`, title: "The town sleeps" };
      case "day": return { mood: "light", act: `Act ${n} · Morning`, title: "The town wakes" };
      case "vote": return { mood: "light", act: `Act ${n} · The vote`, title: "The floor is open" };
      case "over": return {
        mood: "light", act: "Curtain",
        title: p.winner === "mafia" ? "The mafia win" : "The town wins",
      };
      default: return { mood: "ink", act: "", title: "" };
    }
  }

  function applyMood(mood) {
    document.body.dataset.mood = mood;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", mood === "ink" ? "#0e1020" : "#efe7d6");
  }

  function titleCard(sc) {
    const el = document.createElement("div");
    el.className = "titlecard";
    el.innerHTML =
      `<div class="act">${esc(sc.act)}</div>
       <h1 class="title">${esc(sc.title)}</h1>
       <div class="ornament"><span>&#9670;</span></div>`;
    document.body.appendChild(el);
    el.addEventListener("animationend", () => el.remove());
  }

  /* --- Network ----------------------------------------------------------- */

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "That did not work.");
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
      render();
    };
  }

  /* --- Pieces ------------------------------------------------------------ */

  function clock() {
    const deadline = state.public.deadline;
    if (!deadline) return "";
    const left = Math.max(0, Math.round(deadline - (Date.now() + clockOffset) / 1000));
    const ss = String(left % 60).padStart(2, "0");
    return `<div class="clock ${left <= 10 ? "urgent" : ""}">${Math.floor(left / 60)}:${ss}</div>`;
  }

  function topbar(sc) {
    return `<div class="topbar">
      <div>
        <div class="act">${esc(sc.act)}</div>
        <div class="small dim">${state.public.alive_count} still standing</div>
      </div>${clock()}</div>`;
  }

  function roleCard() {
    const me = state.private;
    if (!me.role) return "";
    return `<div class="card-hold role-${esc(me.role)} ${peeking ? "peeking" : ""}"
                 tabindex="0" role="button" aria-label="Hold to see your role">
      <div class="card-inner">
        <div class="card-face card-back">
          <div class="monogram">M</div>
          <div class="instruction">Hold to look</div>
        </div>
        <div class="card-face card-front">
          <div class="role">${esc(me.role)}</div>
          <p class="brief">${esc(BRIEF[me.role] || "")}</p>
          ${me.partners && me.partners.length
            ? `<p class="small">Alongside you:
                 ${me.partners.map((p) => esc(p.name) + (p.alive ? "" : " (dead)")).join(", ")}</p>`
            : ""}
        </div>
      </div>
    </div>`;
  }

  function findings() {
    const me = state.private;
    if (me.role !== "detective") return "";
    const notes = me.investigations || [];
    return `<div class="panel">
      <h2>Your findings</h2>
      ${notes.length
        ? notes.map((n) => `<span class="finding ${n.is_mafia ? "guilty" : "clear"}">
             ${esc(n.name)} — ${n.is_mafia ? "mafia" : "not mafia"}</span>`).join("")
        : `<p class="small dim">Nothing yet. You get one name a night.</p>`}
    </div>`;
  }

  function nightPanel() {
    const me = state.private;
    if (!me.alive) {
      return `<div class="panel"><h2>You are out</h2>
        <p class="small dim">Watch, and say nothing.</p></div>`;
    }
    if (!me.action) {
      return `<div class="panel"><h2>You sleep</h2>
        <p class="small dim">No night action. Wait for morning.</p></div>`;
    }

    const verb = { kill: "Kill", investigate: "Investigate", protect: "Protect" }[me.action];
    const heading = {
      kill: "Choose tonight's victim",
      investigate: "Investigate one player",
      protect: "Protect one player",
    }[me.action];

    const targets = (me.targets || []).map((t) =>
      `<button data-target="${t.id}" class="${me.submitted === t.id ? "chosen" : ""}">
         ${verb} ${esc(t.name)}</button>`).join("");

    const skip = me.action === "kill" ? "" :
      `<button data-target="none"
               class="quiet ${me.has_submitted && me.submitted === null ? "chosen" : ""}">
         Do nothing tonight</button>`;

    const partners = me.partner_votes && me.partner_votes.length > 1
      ? `<p class="small dim" style="margin-top:12px">Your side so far —
           ${me.partner_votes.map((v) => `${esc(v.voter)} picks ${esc(v.target)}`).join("; ")}</p>`
      : "";

    return `<div class="panel">
      <h2>${heading}</h2>
      ${me.role === "doctor" && me.last_protected !== null && me.last_protected !== undefined
        ? `<p class="small dim">You protected someone last night. Not them again.</p>` : ""}
      ${targets || `<p class="small dim">No one you may choose tonight.</p>`}
      ${skip}
      ${partners}
    </div>`;
  }

  function dayPanel() {
    const me = state.private;
    if (!me.alive) {
      return `<div class="panel"><h2>You are out</h2>
        <p class="small dim">No talking. Let them work it out.</p></div>`;
    }
    const ready = (state.public.ready || []).includes(state.you);
    return `<div class="panel">
      <h2>Talk it out</h2>
      <p class="small dim">Accuse, defend, lie. The vote opens when everyone is ready.</p>
      <button class="${ready ? "chosen" : "primary"}"
              data-act="ready" data-ready="${ready ? "0" : "1"}">
        ${ready ? "Ready — tap to take it back" : "I'm ready to vote"}</button>
      <p class="small dim center" style="margin-top:12px">
        ${(state.public.ready || []).length} of ${state.public.alive_count} ready</p>
    </div>`;
  }

  function votePanel() {
    const me = state.private;
    if (!me.alive) {
      return `<div class="panel"><h2>You are out</h2>
        <p class="small dim">The dead do not vote.</p></div>`;
    }
    const alive = state.public.players.filter((p) => p.alive);
    return `<div class="panel">
      <h2>Who goes?</h2>
      ${alive.map((p) => `<button data-vote="${p.id}"
           class="${me.submitted_vote === p.id ? "chosen" : ""}">
           Vote out ${esc(p.name)}${p.id === state.you ? " (you)" : ""}</button>`).join("")}
      <button class="quiet ${me.submitted_vote === null ? "chosen" : ""}" data-vote="none">
        Abstain</button>
      <p class="small dim" style="margin-top:12px">
        A tie sends no one home. ${(state.public.voted || []).length} of
        ${state.public.alive_count} have voted.</p>
    </div>`;
  }

  function castList(revealAll) {
    const p = state.public;
    return `<ul class="cast">${p.players.map((x) => {
      let billing = "", cls = "";
      if (x.role && (revealAll || !x.alive)) {
        billing = x.role;
        cls = x.role === "mafia" ? "blood" : "gilt";
      } else if (!x.connected) {
        billing = "away";
      } else if (p.phase === "vote") {
        billing = (p.voted || []).includes(x.id) ? "voted" : "";
      } else if (p.phase === "day") {
        billing = (p.ready || []).includes(x.id) ? "ready" : "";
      }
      if (x.id === state.you && !billing) billing = "you";
      return `<li class="${x.alive ? "" : "gone"}">
        <span class="name">${esc(x.name)}</span>
        <span class="leaders"></span>
        <span class="billing ${cls}">${esc(billing)}</span></li>`;
    }).join("")}</ul>`;
  }

  function directions() {
    const entries = state.public.log.slice(-10).reverse();
    if (!entries.length) return "";
    return `<div class="panel"><h2>What happened</h2>
      <ul class="directions">${entries.map((e) =>
        `<li>${esc(e.text)}</li>`).join("")}</ul></div>`;
  }

  function lobbyPanel() {
    const p = state.public;
    const short = p.min_players - p.players.length;
    return `<div class="panel">
      <h2>The company</h2>
      ${castList(false)}
      </div>
      <div class="panel">
      ${state.is_host
        ? `<button class="primary" data-act="start" ${short > 0 ? "disabled" : ""}>
             ${short > 0 ? `${short} more to start` : "Begin"}</button>
           <p class="small dim center" style="margin-top:12px">
             Roles are dealt at random. No one sees another's.</p>`
        : `<p class="small dim center">Waiting for the host to begin${
             short > 0 ? ` — ${short} more needed` : ""}.</p>`}
      </div>`;
  }

  function curtainPanel() {
    return `<div class="panel">
      <h2>The company</h2>
      <div class="ornament"><span>&#9670;</span></div>
      ${castList(true)}
      ${state.is_host
        ? `<button class="primary" data-act="reset" style="margin-top:16px">Deal again</button>`
        : `<p class="small dim center" style="margin-top:14px">
             Waiting for the host to deal again.</p>`}
    </div>`;
  }

  function joinScreen() {
    const open = !state || state.can_join;
    return `<div class="panel">
      <div class="act">A game for four or more</div>
      <h1 class="title" style="font-size:2.4rem;margin:6px 0 4px">Mafia</h1>
      <div class="ornament"><span>&#9670;</span></div>
      <p class="small dim">No host needed. This phone is your private script —
        keep it to yourself.</p>
      ${open
        ? `<input type="text" id="name" placeholder="Your name" maxlength="20"
                  autocomplete="off" enterkeyhint="go">
           <button class="primary" data-act="join">Take a seat</button>`
        : `<p class="notice">A game is already running. Watch the shared screen —
             you can join the next one.</p>`}
    </div>`;
  }

  /* --- Render ------------------------------------------------------------ */

  function render() {
    if (!state) {
      app.innerHTML = `<div class="panel"><p class="dim">Connecting…</p></div>`;
      return;
    }

    const sc = scene();
    applyMood(sc.mood);
    const key = `${state.public.phase}:${state.public.round}`;
    if (lastScene !== null && lastScene !== key) titleCard(sc);
    lastScene = key;

    if (state.public.phase === "lobby") peeking = false;

    const notice = error ? `<div class="notice">${esc(error)}</div>` : "";

    if (!state.you) {
      app.innerHTML = notice + joinScreen();
      return;
    }

    const phase = state.public.phase;
    let panel = "";
    if (phase === "lobby") panel = lobbyPanel();
    else if (phase === "night") panel = nightPanel();
    else if (phase === "day") panel = dayPanel();
    else if (phase === "vote") panel = votePanel();
    else if (phase === "over") panel = curtainPanel();

    const playing = phase !== "lobby" && phase !== "over";

    app.innerHTML =
      (phase === "lobby" ? "" : topbar(sc)) +
      notice +
      (phase === "lobby" ? "" : roleCard()) +
      panel +
      (playing ? findings() : "") +
      (playing ? `<div class="panel"><h2>The company</h2>
         ${castList(false)}</div>` : "") +
      (phase === "lobby" ? "" : directions());
  }

  /* --- Input -------------------------------------------------------------
     Peek listeners live on window so a re-render mid-hold can never leave a
     role stranded face-up. */

  function setPeek(on) {
    if (peeking === on) return;
    peeking = on;
    const el = document.querySelector(".card-hold");
    if (el) el.classList.toggle("peeking", on);
  }

  app.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".card-hold")) { event.preventDefault(); setPeek(true); }
  });
  window.addEventListener("pointerup", () => setPeek(false));
  window.addEventListener("pointercancel", () => setPeek(false));
  window.addEventListener("blur", () => setPeek(false));

  app.addEventListener("keydown", (event) => {
    if ((event.key === " " || event.key === "Enter") && event.target.closest(".card-hold")) {
      event.preventDefault();
      setPeek(true);
    }
  });
  window.addEventListener("keyup", () => setPeek(false));

  app.addEventListener("click", (event) => {
    const el = event.target.closest("[data-act],[data-target],[data-vote]");
    if (!el) return;

    if (el.dataset.act === "join") {
      const name = (document.getElementById("name") || {}).value || "";
      error = "";
      post("/api/join", { name })
        .then((data) => { token = data.token; localStorage.setItem(KEY, token); connect(); })
        .catch((e) => { error = e.message; render(); });
      return;
    }
    if (el.dataset.act === "start") return act("start");
    if (el.dataset.act === "reset") { peeking = false; return act("reset"); }
    if (el.dataset.act === "ready") return act("ready", { ready: el.dataset.ready === "1" });
    if (el.dataset.target !== undefined) {
      return act("night", { target: el.dataset.target === "none" ? null : Number(el.dataset.target) });
    }
    if (el.dataset.vote !== undefined) {
      return act("vote", { target: el.dataset.vote === "none" ? null : Number(el.dataset.vote) });
    }
  });

  app.addEventListener("keypress", (event) => {
    if (event.key === "Enter" && event.target.id === "name") {
      const button = app.querySelector('[data-act="join"]');
      if (button) button.click();
    }
  });

  setInterval(() => {
    if (!state || !state.public.deadline) return;
    const el = document.querySelector(".clock");
    if (el) el.outerHTML = clock();
  }, 1000);

  connect();
  render();
})();
