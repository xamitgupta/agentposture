/* AgentPosture dashboard. Vanilla JS, no build step, no dependencies.
   Works against the live API or, in a static report, against an embedded snapshot. */
(() => {
  "use strict";

  const TIERS = ["low", "medium", "high", "critical"];
  const TOKEN_KEY = "agentposture-token";
  const snapEl = document.getElementById("snapshot");
  const SNAP = snapEl ? JSON.parse(snapEl.textContent) : null;
  const $ = (sel, root = document) => root.querySelector(sel);
  const state = { summary: null, agents: [], status: null, polling: null, refreshTimer: null };

  // ------------------------------------------------------------------ utils
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const human = (v) => (v == null || v === "" ? "not set" : String(v).replace(/^unknown:/, "unrecognized: ").replace(/_/g, " "));
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;
  const tierPill = (t) => `<span class="tier t-${esc(t)}">${esc(t)}</span>`;
  function ago(iso) {
    if (!iso) return "never";
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 0) return "in " + until(iso);
    if (s < 90) return "just now";
    if (s < 5400) return `${Math.round(s / 60)} min ago`;
    if (s < 129600) return `${Math.round(s / 3600)} h ago`;
    return `${Math.round(s / 86400)} days ago`;
  }
  function until(iso) {
    const s = (new Date(iso).getTime() - Date.now()) / 1000;
    if (s < 90) return "in a minute";
    if (s < 5400) return `in ${Math.round(s / 60)} min`;
    if (s < 129600) return `in ${Math.round(s / 3600)} h`;
    return `in ${Math.round(s / 86400)} days`;
  }
  const date = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "never");

  // -------------------------------------------------------------- data layer
  async function api(path, opts = {}) {
    if (SNAP) return fromSnapshot(path);
    const headers = { "Content-Type": "application/json" };
    let token = null;
    try { token = localStorage.getItem(TOKEN_KEY); } catch (_) { /* storage may be unavailable */ }
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(path, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
    if (res.status === 401) { const e = new Error("unauthorized"); e.status = 401; throw e; }
    const body = await res.json().catch(() => ({}));
    if (!res.ok && res.status !== 409) throw Object.assign(new Error(body.error || res.statusText), { status: res.status });
    return body;
  }
  function fromSnapshot(path) {
    if (path.startsWith("/api/summary")) return SNAP.summary;
    if (path.startsWith("/api/agents/")) return SNAP.details[decodeURIComponent(path.slice(12))] || null;
    if (path.startsWith("/api/agents")) return SNAP.agents;
    if (path.startsWith("/api/status")) return { scanning: null, write_allowed: false, snapshot: true };
    if (path.startsWith("/api/runs")) return [];
    return null;
  }

  async function load() {
    try {
      const [summary, agents, status] = await Promise.all([api("/api/summary"), api("/api/agents"), api("/api/status")]);
      Object.assign(state, { summary, agents, status });
      hideBanner();
      renderChrome();
      route();
      if (status && status.scanning) pollScan();
    } catch (err) {
      if (err.status === 401) return askToken();
      showBanner(`Cannot reach the AgentPosture API (${esc(err.message)}). Is \`agentposture serve\` running?`, true);
    }
  }

  // ----------------------------------------------------------------- chrome
  function showBanner(html, error) { const b = $("#banner"); b.innerHTML = html; b.hidden = false; b.classList.toggle("error", !!error); }
  function hideBanner() { $("#banner").hidden = true; }

  function renderChrome() {
    const s = state.summary;
    $("#org").textContent = s.organization;
    document.title = `AgentPosture: ${s.organization}`;
    $("#policy-line").textContent = `${s.policy.name}, version ${s.version}` + (SNAP ? `. Static report generated ${date(s.generated_at)}.` : "");
    if (s.repo_url) $("#docs-link").href = s.repo_url;
    const btn = $("#scan-btn");
    if (SNAP) {
      btn.hidden = true;
      $("#freshness").textContent = `Snapshot from ${date(s.generated_at)}`;
    } else {
      $("#freshness").textContent = state.status && state.status.scanning ? "Scanning…" : `Assessed ${ago(s.last_reconcile)}`;
      btn.disabled = !!(state.status && state.status.scanning);
    }
    clearInterval(state.refreshTimer);
    if (!SNAP && s.refresh_seconds) state.refreshTimer = setInterval(load, s.refresh_seconds * 1000);
  }

  async function scanNow(source) {
    const btn = $("#scan-btn");
    btn.disabled = true;
    $("#freshness").textContent = "Scanning…";
    try {
      const r = await api("/api/scan", { method: "POST", body: JSON.stringify(source ? { source } : {}) });
      if (!r.started && !r.scanning) throw new Error("scan did not start");
      pollScan();
    } catch (err) {
      btn.disabled = false;
      if (err.status === 401) return askToken("Starting a scan needs the API token.");
      showBanner(`Scan failed to start: ${esc(err.message)}`, true);
    }
  }
  function pollScan() {
    clearTimeout(state.polling);
    state.polling = setTimeout(async () => {
      const st = await api("/api/status").catch(() => null);
      if (st && st.scanning) return pollScan();
      await load();
      const rep = st && st.last_report;
      if (rep && !rep.ok) {
        const bad = Object.entries(rep.sources).filter(([, v]) => v.status !== "ok").map(([k]) => esc(k));
        showBanner(`Scan finished, but ${bad.join(", ")} failed. See <a href="#/sources">Sources</a>.`, true);
      }
    }, 1500);
  }

  function askToken(message) {
    const main = $("#main");
    document.querySelectorAll(".view").forEach((v) => (v.hidden = true));
    let form = $("#token-form");
    if (!form) {
      form = document.createElement("form");
      form.id = "token-form";
      form.className = "token-form";
      main.appendChild(form);
    }
    form.innerHTML = `<h1>Enter the API token</h1>
      <p class="muted">${esc(message || "This AgentPosture server requires a token.")} Ask whoever runs it for the value of <code>server.api_token</code>.</p>
      <label for="tok">API token</label><input id="tok" type="password" autocomplete="off" required>
      <button class="btn" type="submit">Save token</button>`;
    form.onsubmit = (e) => {
      e.preventDefault();
      try { localStorage.setItem(TOKEN_KEY, $("#tok").value.trim()); } catch (_) { /* ignore */ }
      form.remove();
      load();
    };
    $("#tok").focus();
  }

  // ----------------------------------------------------------------- router
  function parseHash() {
    const h = location.hash.replace(/^#\/?/, "") || "posture";
    const [path, query] = h.split("?");
    const params = new URLSearchParams(query || "");
    const parts = path.split("/");
    return { view: parts[0] || "posture", arg: parts.slice(1).join("/"), params };
  }
  function route() {
    if (!state.summary) return;
    const { view, arg, params } = parseHash();
    const main = view === "agent" ? (lastView || "agents") : view;
    document.querySelectorAll(".tabs a").forEach((a) => {
      if (a.dataset.view === main) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    for (const v of ["posture", "agents", "sources"]) $(`#view-${v}`).hidden = v !== main;
    if (main === "posture") renderPosture();
    if (main === "agents") renderAgents(params);
    if (main === "sources") renderSources();
    if (view === "agent" && arg) openDrawer(decodeURIComponent(arg));
    else { closeDrawer(false); lastView = main; }
  }
  let lastView = null;

  // ---------------------------------------------------------------- posture
  function renderPosture() {
    const s = state.summary, t = s.totals, el = $("#view-posture");
    if (!t.agents) {
      el.innerHTML = `<div class="headline"><h1 id="headline">No agents found yet.</h1>
        <p>Add an <code>agent.yaml</code> next to an agent's code, or connect a platform in <code>agentposture.yaml</code>, then scan.
        Run <code>agentposture demo</code> to see a sample organization.</p></div>`;
      return;
    }
    const bt = t.by_tier;
    const worst = bt.critical ? `${bt.critical} critical` : bt.high ? `${bt.high} high` : "none high or critical";
    const second = bt.critical && bt.high ? `, ${bt.high} high` : "";
    const lines = [];
    lines.push(t.needs_action ? `${plural(t.needs_action, "agent")} ${t.needs_action === 1 ? "has" : "have"} a critical or high finding to fix.` : "No agent has an open critical or high finding.");
    if (t.shadow) lines.push(`${t.shadow} ${t.shadow === 1 ? "was" : "were"} found running without a declaration.`);
    const sorted = [...state.agents].sort((a, b) => TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier) || a.score - b.score);
    el.innerHTML = `
      <div class="headline">
        <h1 id="headline">${plural(t.agents, "agent")}. ${worst}${second}.</h1>
        <p>${lines.join(" ")}</p>
      </div>
      <figure class="fleet" aria-label="Every agent as a bar, ordered from lowest to highest residual risk">
        <div class="fleet-bars">${sorted.map((a, i) => `<button type="button" style="--c:var(--${a.tier});--i:${i};height:${Math.max(4, a.score)}%" data-id="${esc(a.id)}" aria-label="${esc(a.name)}, ${a.tier}, score ${a.score}"></button>`).join("")}</div>
        <figcaption class="fleet-legend">${[...TIERS].reverse().map((tr) => `<span><span class="swatch" style="--c:var(--${tr})"></span><b>${bt[tr]}</b>${tr}</span>`).join("")}
          <span>Bar height is the residual risk score; select a bar to open the agent.</span></figcaption>
      </figure>
      <div class="grid">
        <div class="block span-7">
          <h2>Needs action</h2>
          <p class="sub">Agents with a critical or high finding, riskiest first. Each one lists its most important fix.</p>
          ${s.attention.length ? `<ul class="attention">${s.attention.map((a) => `
            <li><a href="#/agent/${encodeURIComponent(a.id)}">${tierPill(a.tier)}
              <span><span class="name">${esc(a.name)}</span><span class="what">${esc(a.top_finding || "")}${a.team ? ` for ${esc(a.team)}` : ", no team recorded"}</span></span>
              <span class="count">${plural(a.urgent_findings, "urgent finding")}</span></a></li>`).join("")}</ul>` :
            `<p class="empty">Nothing urgent. Every critical and high finding is resolved.</p>`}
        </div>
        <div class="block span-5">
          <h2>Where risk concentrates</h2>
          <p class="sub">Tier mix per team. Select a team to see its agents.</p>
          <div class="table-wrap"><table>
            <thead><tr><th>Team</th><th class="num">Agents</th><th>Tier mix</th><th class="num">Urgent</th></tr></thead>
            <tbody>${s.teams.map((tm) => `<tr class="clickable" data-team="${esc(tm.team)}"><td>${esc(tm.team)}</td><td class="num">${tm.agents}</td>
              <td><div class="stack" title="${TIERS.map((x) => `${tm[x]} ${x}`).join(", ")}">${[...TIERS].reverse().map((x) => tm[x] ? `<span style="--c:var(--${x});flex:${tm[x]}"></span>` : "").join("")}</div></td>
              <td class="num">${tm.open_urgent}</td></tr>`).join("")}</tbody></table></div>
        </div>
        <div class="block span-6">
          <h2>Most common findings</h2>
          <p class="sub">Fixing a pattern once, in a shared library or platform default, clears it for every agent.</p>
          <ul class="rules">${s.top_findings.slice(0, 8).map((f) => `<li><span>${esc(f.title)}<span class="sev t-${f.severity}">${f.severity}</span></span><span class="muted">${plural(f.agents, "agent")}</span></li>`).join("") || `<li>No findings.</li>`}</ul>
        </div>
        <div class="block span-6">
          <h2>Controls in place</h2>
          <p class="sub">Of the agents each control applies to, how many have it.</p>
          <div class="coverage">${s.controls.map((c) => { const pct = Math.round(100 * c.in_place / c.applies); return `<div class="row"><span>${esc(human(c.control))}</span><div class="meter" role="img" aria-label="${pct}%"><span style="width:${pct}%"></span></div><span class="num small">${c.in_place}/${c.applies}</span></div>`; }).join("")}</div>
        </div>
        <div class="block span-8 trend">
          <h2>Trend</h2>
          <p class="sub">Agents at high or critical, against the size of the fleet.</p>
          ${trendChart(s.trend)}
        </div>
        <div class="block span-4">
          <h2>Inventory health</h2>
          <p class="sub">How complete and current the registry is.</p>
          <dl class="facts">
            ${fact("Declared", t.declared, "")}
            ${fact("Shadow", t.shadow, "shadow")}
            ${fact("Drifted", t.drift, "drift")}
            ${fact("Unowned", t.unowned, "unowned")}
            ${fact("Stale", t.stale, "stale")}
            <div><dt>Complete records</dt><dd>${t.record_completeness}%</dd></div>
          </dl>
        </div>
      </div>`;
    el.querySelectorAll(".fleet-bars button").forEach((b) => {
      b.addEventListener("click", () => (location.hash = `#/agent/${encodeURIComponent(b.dataset.id)}`));
      b.addEventListener("mouseenter", (e) => tip(e, b.getAttribute("aria-label")));
      b.addEventListener("mouseleave", () => ($("#tooltip").hidden = true));
    });
    el.querySelectorAll("tr[data-team]").forEach((r) => r.addEventListener("click", () => (location.hash = `#/agents?team=${encodeURIComponent(r.dataset.team)}`)));
  }
  const fact = (label, n, flag) => `<div><a href="#/agents${flag ? `?flag=${flag}` : ""}"><dt>${label}</dt><dd>${n}</dd></a></div>`;
  function tip(e, text) {
    const t = $("#tooltip");
    t.textContent = text; t.hidden = false;
    const r = e.target.getBoundingClientRect();
    t.style.left = `${Math.min(window.innerWidth - 200, Math.max(8, r.left - 40))}px`;
    t.style.top = `${r.top - 38}px`;
  }

  function trendChart(points) {
    if (!points || points.length < 2) return `<p class="empty">The trend appears after the second day of scans.</p>`;
    const W = 640, H = 150, P = { l: 30, r: 70, t: 10, b: 22 };
    const maxY = Math.max(...points.map((p) => p.total), 1);
    const x = (i) => P.l + (i * (W - P.l - P.r)) / (points.length - 1);
    const y = (v) => H - P.b - (v * (H - P.t - P.b)) / maxY;
    const line = (f) => points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(f(p)).toFixed(1)}`).join("");
    const hc = (p) => (p.by_tier.critical || 0) + (p.by_tier.high || 0);
    const last = points[points.length - 1];
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Trend of high and critical agents">
      <line class="axis" x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}"/>
      <path d="${line((p) => p.total)}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="3 3"/>
      <path d="${line(hc)}" fill="none" stroke="var(--critical)" stroke-width="2.5"/>
      <text x="${W - P.r + 6}" y="${y(last.total) + 4}">${last.total} total</text>
      <text x="${W - P.r + 6}" y="${y(hc(last)) + 4}" style="fill:var(--critical)">${hc(last)} high+</text>
      <text x="${P.l}" y="${H - 5}">${esc(points[0].date)}</text>
      <text x="${W - P.r}" y="${H - 5}" text-anchor="end">${esc(last.date)}</text>
      <text x="${P.l - 6}" y="${y(maxY) + 4}" text-anchor="end">${maxY}</text>
    </svg>`;
  }

  // ----------------------------------------------------------------- agents
  function renderAgents(params) {
    const el = $("#view-agents");
    const teams = [...new Set(state.agents.map((a) => a.team || "unassigned"))].sort();
    const f = { q: params.get("q") || "", tier: params.get("tier") || "", team: params.get("team") || "", flag: params.get("flag") || "" };
    if (!el.dataset.ready) {
      el.innerHTML = `<h1 class="sr-title" style="font-size:var(--step-2);margin:0 0 1rem">Agents</h1>
        <div class="filters" role="search">
          <input id="f-q" type="search" placeholder="Search by name, id, owner or team" aria-label="Search agents">
          <select id="f-tier" aria-label="Tier"><option value="">All tiers</option>${[...TIERS].reverse().map((t) => `<option value="${t}">${t}</option>`).join("")}</select>
          <select id="f-team" aria-label="Team"></select>
          ${["shadow", "drift", "unowned", "stale", "incomplete"].map((fl) => `<button type="button" class="chip" data-flag="${fl}" aria-pressed="false">${fl}</button>`).join("")}
        </div>
        <div id="agent-table"></div>`;
      el.dataset.ready = "1";
      const push = () => {
        const p = new URLSearchParams();
        const q = $("#f-q").value.trim(), t = $("#f-tier").value, tm = $("#f-team").value;
        const fl = el.querySelector(".chip[aria-pressed='true']");
        if (q) p.set("q", q); if (t) p.set("tier", t); if (tm) p.set("team", tm); if (fl) p.set("flag", fl.dataset.flag);
        history.replaceState(null, "", `#/agents${p.toString() ? "?" + p : ""}`);
        route();
      };
      $("#f-q").addEventListener("input", push);
      $("#f-tier").addEventListener("change", push);
      $("#f-team").addEventListener("change", push);
      el.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
        const on = c.getAttribute("aria-pressed") === "true";
        el.querySelectorAll(".chip").forEach((x) => x.setAttribute("aria-pressed", "false"));
        c.setAttribute("aria-pressed", on ? "false" : "true");
        push();
      }));
    }
    $("#f-team").innerHTML = `<option value="">All teams</option>` + teams.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    if (document.activeElement !== $("#f-q")) $("#f-q").value = f.q;
    $("#f-tier").value = f.tier; $("#f-team").value = f.team;
    el.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.flag === f.flag)));

    const q = f.q.toLowerCase();
    const rows = state.agents.filter((a) => (!f.tier || a.tier === f.tier) && (!f.team || (a.team || "unassigned") === f.team)
      && (!f.flag || a.flags.includes(f.flag)) && (!q || `${a.id} ${a.name} ${a.owner || ""} ${a.team || ""}`.toLowerCase().includes(q)));
    $("#agent-table").innerHTML = rows.length ? `<p class="muted small">${plural(rows.length, "agent")}</p><div class="table-wrap"><table>
      <thead><tr><th>Tier</th><th>Agent</th><th>Team</th><th class="hide-sm">Owner</th><th class="hide-sm">Autonomy</th><th class="hide-sm">Exposure</th><th class="num">Score</th><th class="num">Findings</th><th>Flags</th></tr></thead>
      <tbody>${rows.map((a) => `<tr class="clickable" data-id="${esc(a.id)}" tabindex="0">
        <td>${tierPill(a.tier)}</td>
        <td><span class="name">${esc(a.name)}</span><span class="id">${esc(a.id)}</span></td>
        <td>${esc(a.team || "unassigned")}</td>
        <td class="hide-sm">${esc(a.owner || "nobody")}</td>
        <td class="hide-sm">${esc(human(a.autonomy))}</td>
        <td class="hide-sm">${esc(human(a.exposure))}</td>
        <td class="num">${a.score.toFixed(0)}</td>
        <td class="num">${a.findings}</td>
        <td>${a.flags.map((x) => `<span class="flag ${x}">${x}</span>`).join("")}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="empty">No agents match these filters. Clear a filter to see more.</p>`;
    $("#agent-table").querySelectorAll("tr[data-id]").forEach((r) => {
      const open = () => (location.hash = `#/agent/${encodeURIComponent(r.dataset.id)}`);
      r.addEventListener("click", open);
      r.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
    });
  }

  // ----------------------------------------------------------------- drawer
  let lastFocus = null;
  async function openDrawer(id) {
    const d = await api(`/api/agents/${encodeURIComponent(id)}`).catch(() => null);
    const body = $("#drawer-body");
    if (!d || !d.assessment) {
      body.innerHTML = `<button class="btn ghost close" type="button">Close</button><h2>Agent not found</h2><p class="muted">It may have been merged or removed in the latest scan.</p>`;
    } else {
      body.innerHTML = agentDetail(d);
    }
    lastFocus = lastFocus || document.activeElement;
    $("#drawer").classList.add("open");
    $("#drawer").setAttribute("aria-hidden", "false");
    $("#scrim").hidden = false;
    body.querySelector(".close").addEventListener("click", () => closeDrawer(true));
    body.querySelector(".close").focus();
  }
  function closeDrawer(navigate) {
    if (!$("#drawer").classList.contains("open")) return;
    $("#drawer").classList.remove("open");
    $("#drawer").setAttribute("aria-hidden", "true");
    $("#scrim").hidden = true;
    if (navigate) location.hash = `#/${lastView || "agents"}`;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    lastFocus = null;
  }
  $("#scrim").addEventListener("click", () => closeDrawer(true));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(true); });

  function agentDetail(d) {
    const a = d.agent, s = d.assessment, at = a.attributes;
    const dims = s.dimensions;
    const fixedLower = s.target_tier && TIERS.indexOf(s.target_tier) < TIERS.indexOf(s.tier);
    const verdict = s.findings.length
      ? (fixedLower ? `Fixing all ${plural(s.findings.length, "finding")} brings this agent from <strong>${s.tier}</strong> to <strong>${s.target_tier}</strong>.`
                    : `Fixing the ${plural(s.findings.length, "finding")} removes known gaps, but the agent stays <strong>${s.tier}</strong> because of what it is allowed to do.`)
      : `No open findings. The <strong>${s.tier}</strong> tier reflects what the agent can do, with its controls already counted.`;
    const dimRow = (k, label) => {
      const x = dims[k];
      return `<div class="row"><span>${label}</span><div class="pips t-${TIERS[x.level] || "low"}" role="img" aria-label="level ${x.level} of 3">${[1, 2, 3].map((i) => `<span class="${x.level >= i ? "on" : ""}"></span>`).join("")}</div><span class="muted small">${esc(human(x.value))}${x.known ? "" : " (scored as risky)"}</span></div>`;
    };
    const ctrl = Object.entries(s.controls || {}).filter(([, v]) => v.applies);
    const tools = at.tools || [];
    return `
      <button class="btn ghost close" type="button">Close</button>
      <p style="margin:0 0 .4rem">${tierPill(s.tier)} <span class="muted small">score ${s.score} (${s.inherent_score} before controls, ${s.control_reduction}% reduced)</span></p>
      <h2>${esc(at.name || a.id)}</h2>
      <p class="muted" style="margin:.25rem 0 0">${esc(at.description || "")}</p>
      <p class="verdict">${verdict}</p>

      <h3>Why this tier</h3>
      <div class="dims">
        ${dimRow("autonomy", "Autonomy")}${dimRow("privilege", "Privilege")}${dimRow("data_sensitivity", "Data")}
        ${dimRow("exposure", "Exposure")}${dimRow("business_impact", "Business impact")}${dimRow("ownership", "Ownership")}
      </div>
      ${s.overrides.length ? `<p class="small muted">Minimum tier raised by: ${s.overrides.map((o) => esc(human(o).replace(/-/g, " "))).join("; ")}.</p>` : ""}

      <h3>Findings</h3>
      ${s.findings.length ? s.findings.map((f) => `<div class="finding t-${f.severity}">
        <h4>${esc(f.title)} <span class="small" style="color:var(--c)">${f.severity}</span></h4>
        <p>${esc(f.detail)}</p>
        <p><strong>Fix:</strong> ${esc(f.remediation)}</p>
        <p class="fix">${f.tier_if_fixed && f.tier_if_fixed !== s.tier ? `Fixing only this moves the agent to ${esc(f.tier_if_fixed)}. ` : ""}${f.rule_id}${f.frameworks.length ? `, ${esc(f.frameworks.join(", "))}` : ""}</p>
      </div>`).join("") : `<p class="muted">None.</p>`}

      ${ctrl.length ? `<h3>Controls that apply</h3><ul class="controls-list">${ctrl.map(([k, v]) => `<li class="${v.in_place ? "yes" : ""}">${esc(human(k))}${v.in_place ? "" : " (missing)"}</li>`).join("")}</ul>` : ""}

      ${a.drift && a.drift.length ? `<h3>Declared versus observed</h3><div class="table-wrap"><table class="drift-table"><thead><tr><th>Attribute</th><th>Declared</th><th>Observed</th></tr></thead><tbody>
        ${a.drift.map((x) => `<tr><td>${esc(human(x.attribute))}</td><td>${esc([].concat(x.declared).join(", ") || "nothing")}</td><td>${esc([].concat(x.observed).join(", "))}</td></tr>`).join("")}</tbody></table></div>` : ""}

      <h3>Record</h3>
      <dl class="kv">
        <dt>Id</dt><dd>${esc(a.id)}</dd>
        <dt>Owner</dt><dd>${esc(at.owner || "nobody")}</dd>
        <dt>Team</dt><dd>${esc(at.team || "unassigned")}</dd>
        <dt>Lifecycle</dt><dd>${esc(human(at.lifecycle))}</dd>
        <dt>Data types</dt><dd>${esc((at.data_types || []).join(", ") || "none recorded")}</dd>
        <dt>Tools</dt><dd>${tools.length ? tools.map((t) => `${esc(t.name)} <span class="muted">(${esc(t.action)}${t.requires_approval ? ", approval" : ""})</span>`).join(", ") : "none recorded"}</dd>
        <dt>Privileges</dt><dd>${esc((at.privileges || []).join(", ") || "none recorded")}</dd>
        ${at.model ? `<dt>Model</dt><dd>${esc(at.model)}</dd>` : ""}
        ${at.repo ? `<dt>Repository</dt><dd>${esc(at.repo)}</dd>` : ""}
        <dt>Found in</dt><dd>${esc(a.sources.join(", "))} (${a.is_declared ? "declared" : "not declared"})</dd>
        <dt>First seen</dt><dd>${date(a.first_seen)}</dd>
        <dt>Last seen</dt><dd>${date(a.last_seen)}${a.status === "stale" ? " (stale)" : ""}</dd>
        <dt>Assessed</dt><dd>${date(s.assessed_at)}</dd>
      </dl>

      ${d.history && d.history.length > 1 ? `<h3>History</h3><div class="table-wrap"><table><thead><tr><th>Assessed</th><th>Tier</th><th class="num">Score</th><th class="num">Findings</th></tr></thead><tbody>
        ${d.history.slice(0, 12).map((h) => `<tr><td>${date(h.assessed_at)}</td><td>${tierPill(h.tier)}</td><td class="num">${h.score}</td><td class="num">${h.findings.length}</td></tr>`).join("")}</tbody></table></div>` : ""}
    `;
  }

  // ---------------------------------------------------------------- sources
  async function renderSources() {
    const el = $("#view-sources"), s = state.summary;
    const runs = await api("/api/runs?limit=15").catch(() => []);
    const canScan = !SNAP;
    el.innerHTML = `
      <div class="headline"><h1>Where agents come from</h1>
        <p>Each source is scanned on its schedule, when a webhook arrives, or when you select Scan. Cadence is set per source in <code>agentposture.yaml</code>; riskier agents are also re-checked more often even when nothing changes.</p></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Source</th><th>Runs on</th><th>Last result</th><th>Last success</th><th class="num">Records</th><th>Next run</th>${canScan ? "<th></th>" : ""}</tr></thead>
        <tbody>${s.sources.map((x) => `<tr>
          <td><span class="name">${esc(x.name)}</span><span class="id">${esc(x.type)}${x.enabled ? "" : ", disabled"}</span></td>
          <td>${x.schedule ? `<code>${esc(x.schedule)}</code>` : ""}${x.trigger === "webhook" ? `${x.schedule ? " and " : ""}webhook` : ""}${!x.schedule && x.trigger !== "webhook" ? "on demand" : ""}</td>
          <td>${x.last_status ? `<span class="status-${x.last_status === "ok" ? "ok" : "error"}">${x.last_status === "ok" ? "ok" : esc(x.last_status)}</span> <span class="muted small">${ago(x.last_run)}</span>${x.error ? `<div class="small">${esc(x.error)}</div>` : ""}` : `<span class="muted">not scanned yet</span>`}</td>
          <td>${x.last_success ? ago(x.last_success) : "never"}</td>
          <td class="num">${x.found ?? ""}</td>
          <td>${x.next_run ? until(x.next_run) : "not scheduled"}</td>
          ${canScan ? `<td><button type="button" class="btn ghost" data-scan="${esc(x.name)}">Scan</button></td>` : ""}</tr>`).join("") || `<tr><td colspan="7" class="empty">No sources configured. Add one under <code>sources:</code> in agentposture.yaml.</td></tr>`}</tbody>
      </table></div>
      ${runs.length ? `<div class="block recent"><h2>Recent scans</h2><div class="table-wrap"><table><thead><tr><th>Source</th><th>Trigger</th><th>Started</th><th>Result</th><th class="num">Records</th></tr></thead><tbody>
        ${runs.map((r) => `<tr><td>${esc(r.source)}</td><td>${esc(human(r.trigger))}</td><td>${date(r.started_at)}</td><td class="status-${r.status === "ok" ? "ok" : "error"}">${esc(r.status)}</td><td class="num">${r.found}</td></tr>`).join("")}</tbody></table></div></div>` : ""}`;
    el.querySelectorAll("[data-scan]").forEach((b) => b.addEventListener("click", () => scanNow(b.dataset.scan)));
  }

  // ------------------------------------------------------------------- boot
  $("#scan-btn").addEventListener("click", () => scanNow());
  window.addEventListener("hashchange", route);
  load();
})();
