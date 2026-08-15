/* The shared screen: the stage, and the narrator's voice.

   It subscribes without a token, so the server can only ever send it public
   state. There is no secret here to leak, by construction rather than by
   care. */
(() => {
  "use strict";

  const root = document.getElementById("stage");
  let state = null;
  let clockOffset = 0;
  let lastScene = null;

  const esc = (s) => String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function scene() {
    const p = state.public;
    const n = p.round;
    switch (p.phase) {
      case "lobby": return {
        mood: "ink", act: "The company", title: "Take your seats",
        lead: "Everyone plays. No one sits out to run the game.",
      };
      case "night": return {
        mood: "ink", act: `Act ${n} · Night`, title: "The town sleeps",
        lead: "The mafia, the detective and the doctor are choosing. Everyone else, sit tight.",
      };
      case "day": return {
        mood: "light", act: `Act ${n} · Morning`, title: "The town wakes",
        lead: "Accuse. Defend. Lie. The vote opens when everyone is ready.",
      };
      case "vote": return {
        mood: "light", act: `Act ${n} · The vote`, title: "The floor is open",
        lead: "A tie sends no one home.",
      };
      case "over": return {
        mood: "light", act: "Curtain",
        title: p.winner === "mafia" ? "The mafia win" : "The town wins",
        lead: "Every role is shown below.",
      };
      default: return { mood: "ink", act: "", title: "", lead: "" };
    }
  }

  function applyMood(mood) {
    document.body.dataset.mood = mood;
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

  function clock() {
    if (!state.public.deadline) return "";
    const left = Math.max(0, Math.round(
      state.public.deadline - (Date.now() + clockOffset) / 1000));
    const ss = String(left % 60).padStart(2, "0");
    return `<div class="clock ${left <= 10 ? "urgent" : ""}">${
      Math.floor(left / 60)}:${ss}</div>`;
  }

  function castList() {
    const p = state.public;
    const over = p.phase === "over";
    return `<ul class="cast">${p.players.map((x) => {
      let billing = "", cls = "";
      if (x.role && (over || !x.alive)) {
        billing = x.role;
        cls = x.role === "mafia" ? "blood" : "gilt";
      } else if (!x.connected) {
        billing = "away";
      } else if (p.phase === "vote") {
        billing = (p.voted || []).includes(x.id) ? "voted" : "thinking";
      } else if (p.phase === "day") {
        billing = (p.ready || []).includes(x.id) ? "ready" : "";
      }
      return `<li class="${x.alive ? "" : "gone"}">
        <span class="name">${esc(x.name)}</span>
        <span class="leaders"></span>
        <span class="billing ${cls}">${esc(billing)}</span></li>`;
    }).join("")}</ul>`;
  }

  function directions() {
    const entries = state.public.log.slice(-8).reverse();
    if (!entries.length) return "";
    return `<ul class="directions">${entries.map((e) =>
      `<li>${esc(e.text)}</li>`).join("")}</ul>`;
  }

  function render() {
    if (!state) { root.innerHTML = `<h1 class="title">Connecting…</h1>`; return; }
    const p = state.public;
    const sc = scene();
    applyMood(sc.mood);

    const key = `${p.phase}:${p.round}`;
    if (lastScene !== null && lastScene !== key) titleCard(sc);
    lastScene = key;

    const head = `<div class="stage-head">
        <div>
          <div class="act">${esc(sc.act)}</div>
          <h1 class="title">${esc(sc.title)}</h1>
        </div>${clock()}</div>
      <p class="stage-lead">${esc(sc.lead)}</p>`;

    const callboard = p.phase === "lobby"
      ? `<div class="callboard">
           <div class="act">Join from your phone</div>
           <div class="address" style="margin:10px 0">${esc(location.host)}</div>
           <p class="small dim" style="margin:0">
             ${p.players.length} seated · ${p.min_players} needed to begin</p>
         </div>`
      : "";

    root.innerHTML = head + `<div class="stage-grid">
        <div>${castList()}</div>
        <div>${callboard}${directions()}</div>
      </div>`;
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
