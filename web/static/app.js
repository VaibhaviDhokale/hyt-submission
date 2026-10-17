// Tally triage inbox. Hash routes: #/  ·  #/job/J01[/CAND]  ·  #/metrics
const $view = document.getElementById("view");
const LANE = {
  shortlist: { label: "Shortlist", dot: "bg-met", chip: "text-met border-met/40 bg-met/10" },
  review: { label: "Needs review", dot: "bg-part", chip: "text-part border-part/40 bg-part/10" },
  low_priority: { label: "Low priority", dot: "bg-muted", chip: "text-muted border-rule bg-paper" },
};
const VERDICT = {
  met: { icon: "✓", cls: "text-met", label: "met" },
  partial: { icon: "◐", cls: "text-part", label: "partial" },
  not_met: { icon: "✗", cls: "text-miss", label: "not shown" },
  unverified: { icon: "?", cls: "text-miss", label: "quote not found" },
};
const ACTION = { advance: "Advanced", hold: "On hold", pass: "Passed" };
let state = { job: null, cands: [], filter: "all", reasonHelp: {} };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const api = async (url, opts) => {
  const r = await fetch(url, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok && r.status !== 202) throw new Error(body.error || `HTTP ${r.status}`);
  return { status: r.status, ...body };
};
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 2600);
}

// ---------------------------------------------------------------- theme
(function theme() {
  const root = document.documentElement;
  let saved = null;
  try { saved = localStorage.getItem("tally-theme"); } catch (e) {}
  const dark = saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.classList.toggle("dark", dark);
  document.getElementById("theme").onclick = () => {
    const d = !root.classList.contains("dark");
    root.classList.toggle("dark", d);
    try { localStorage.setItem("tally-theme", d ? "dark" : "light"); } catch (e) {}
  };
})();

// ---------------------------------------------------------------- router
window.addEventListener("hashchange", route);
route();
async function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  document.querySelectorAll("[data-nav]").forEach((a) =>
    a.classList.toggle("bg-paper", (parts[0] === "metrics") === (a.dataset.nav === "metrics")));
  try {
    if (parts[0] === "job") await inbox(parts[1], parts[2]);
    else if (parts[0] === "metrics") await metrics();
    else await jobs();
  } catch (e) {
    $view.innerHTML = `<p class="text-miss">${esc(e.message)}</p>`;
  }
}

// ---------------------------------------------------------------- jobs list
async function jobs() {
  $view.innerHTML = `<p class="text-muted">Loading jobs…</p>`;
  const d = await api("/api/jobs");
  const pend = Object.values(d.llm.pending || {}).reduce((a, b) => a + b, 0);
  const sum = (k) => d.jobs.reduce((a, j) => a + (k === "total" ? j.total : j.lanes[k]), 0);
  const kpi = [["Open roles", d.jobs.length, "bg-accent/10 text-accent"], ["Applicants", sum("total"), "bg-met/10 text-met"],
               ["Shortlisted", sum("shortlist"), "bg-met/10 text-met"], ["Needs review", sum("review"), "bg-part/10 text-part"]];
  $view.innerHTML = `
    <div class="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div><h1 class="text-2xl font-semibold tracking-tight">Screen at scale with Tally</h1>
        <p class="text-muted text-sm mt-1">Every applicant is checked against the posting's requirements and sorted into three lanes. It never rejects anyone.</p></div>
      <div class="flex items-center gap-3"><span class="text-xs text-muted">LLM: <span class="font-mono">${esc(d.llm.model)}</span>${pend ? ` · ${pend} queued` : ""}</span>
        <button id="new-role" class="text-sm px-4 py-2 rounded-lg bg-accent text-white hover:opacity-90">+ New role</button></div>
    </div>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
      ${kpi.map(([l, v, c]) => `<div class="rounded-2xl border border-rule bg-card p-4 flex items-center gap-3">
        <span class="grid place-items-center w-11 h-11 rounded-full ${c} text-lg font-semibold">${v}</span>
        <div class="text-sm text-muted leading-tight">${l}</div></div>`).join("")}
    </div>
    <div class="rounded-2xl border border-rule bg-card overflow-hidden">
      <div class="hidden md:grid grid-cols-[2.2fr_1.4fr_1fr_1.6fr_.8fr_24px] gap-3 px-4 py-2.5 text-xs text-muted bg-paper/70">
        <span>Role</span><span>Company</span><span>Level</span><span>Lanes</span><span>Shortlist rate</span><span></span></div>
      ${d.jobs.map(jobCard).join("")}
    </div>`;
  document.getElementById("new-role").onclick = openNewRole;
}

function openNewRole() {
  const wrap = document.createElement("div");
  wrap.className = "fixed inset-0 z-40 bg-black/40 grid place-items-center p-4 overflow-y-auto";
  const inp = "w-full rounded-lg border border-rule bg-paper p-2.5 text-sm";
  wrap.innerHTML = `
    <form class="w-full max-w-xl rounded-2xl bg-card border border-rule p-5 space-y-3">
      <h2 class="font-semibold">Add a role</h2>
      <p class="text-sm text-muted">Paste the job description or choose a PDF or .txt file. The LLM turns it into a must-have / nice-to-have checklist; the roles you add live in memory only.</p>
      <div class="grid grid-cols-2 gap-2">
        <input name="title" required placeholder="Job title *" class="${inp} col-span-2">
        <input name="company" placeholder="Company" class="${inp}">
        <input name="location" placeholder="Location" class="${inp}">
        <select name="level" class="${inp} col-span-2"><option value="">Level (optional)</option>
          ${["Internship", "Entry level", "Associate", "Mid-Senior level", "Director"].map((l) => `<option>${l}</option>`).join("")}</select>
      </div>
      <textarea name="text" rows="9" class="${inp} font-mono" placeholder="Paste the job description…"></textarea>
      <input type="file" name="file" accept=".pdf,.txt,application/pdf,text/plain" class="text-sm">
      <div class="flex justify-end gap-2">
        <button type="button" data-close class="px-3 py-1.5 rounded-md border border-rule text-sm">Cancel</button>
        <button class="px-3 py-1.5 rounded-md bg-accent text-white text-sm">Create role</button>
      </div>
    </form>`;
  document.body.appendChild(wrap);
  wrap.querySelector("[data-close]").onclick = () => wrap.remove();
  wrap.querySelector("form").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const r = await fetch("/api/jobs", { method: "POST", body: new FormData(ev.target) });
      const d = await r.json();
      if (!r.ok) return toast(d.error);
      wrap.remove();
      toast(d.pending ? d.message : "Role created");
      location.hash = `#/job/${d.id}`;
      route();
    } catch (e) { toast(e.message); }
  };
}

function ring(pct, color = "var(--color-accent)") {
  return `<span class="relative inline-grid place-items-center w-10 h-10 rounded-full" style="background:conic-gradient(${color} ${pct * 3.6}deg, var(--color-rule) 0)">
    <span class="grid place-items-center w-7 h-7 rounded-full bg-card text-[10px] font-semibold">${Math.round(pct)}%</span></span>`;
}

function jobCard(j) {
  const total = Math.max(1, j.total), rate = (100 * j.lanes.shortlist) / total;
  const pill = (n, cls, l) => `<span class="px-2 py-0.5 rounded-full text-xs ${cls}">${n} ${l}</span>`;
  return `
    <a href="#/job/${j.id}" class="group grid md:grid-cols-[2.2fr_1.4fr_1fr_1.6fr_.8fr_24px] gap-3 items-center px-4 py-3.5 border-t border-rule hover:bg-paper/60 transition">
      <div class="flex items-center gap-3 min-w-0">
        <span class="grid place-items-center w-10 h-10 rounded-xl bg-accent/10 text-accent font-semibold shrink-0">${esc(j.title.slice(0, 1))}</span>
        <div class="min-w-0"><div class="font-medium leading-snug truncate group-hover:text-accent">${esc(j.title)}</div>
          <div class="text-xs text-muted font-mono">${j.id} · ${j.decided}/${j.total} triaged${j.pending ? ` · ${j.pending} queued` : ""}</div></div>
      </div>
      <div class="text-sm min-w-0"><div class="truncate">${esc(j.company)}</div><div class="text-xs text-muted truncate">${esc(j.location)}</div></div>
      <div class="text-sm text-muted">${esc(j.level || "n/a")}</div>
      <div class="flex flex-wrap gap-1.5">${pill(j.lanes.shortlist, "bg-met/10 text-met", "shortlist")}${pill(j.lanes.review, "bg-part/10 text-part", "review")}${pill(j.lanes.low_priority, "bg-paper text-muted", "low")}</div>
      <div>${ring(rate, "var(--color-met)")}</div>
      <span class="text-muted hidden md:block">›</span>
    </a>`;
}

// ---------------------------------------------------------------- inbox
async function inbox(jobId, candId) {
  if (!state.job || state.job.id !== jobId) {
    $view.innerHTML = `<p class="text-muted">Loading ${esc(jobId)}…</p>`;
    const d = await api(`/api/jobs/${jobId}`);
    state = { ...state, job: d.job, checklist: d.checklist, cands: d.candidates, pending: d.pending,
              thresholds: d.thresholds, reasonHelp: d.reason_help };
  }
  const visible = filtered();
  if (!candId && visible.length) return (location.hash = `#/job/${jobId}/${visible[0].cand}`);
  renderInboxShell(candId);
  if (candId) await renderCard(candId);
  else document.getElementById("card").innerHTML = `<p class="text-muted p-6">No candidates in this lane.</p>`;
}

function filtered() {
  const f = state.filter;
  return state.cands.filter((c) => f === "all" || (f === "done" ? c.action : c.lane === f && !c.action));
}

function renderInboxShell(candId) {
  const j = state.job;
  const done = state.cands.filter((c) => c.action).length;
  const counts = { all: state.cands.length, done };
  for (const l of Object.keys(LANE)) counts[l] = state.cands.filter((c) => c.lane === l && !c.action).length;
  const tabs = [["all", "All"], ["shortlist", "Shortlist"], ["review", "Needs review"], ["low_priority", "Low priority"], ["done", "Triaged"]];
  $view.innerHTML = `
    <div class="flex flex-wrap items-start gap-3 mb-4">
      <a href="#/" class="text-sm text-muted hover:text-ink">← Jobs</a>
      <div class="min-w-0 flex-1">
        <h1 class="text-xl font-semibold tracking-tight">${esc(j.title)}</h1>
        <div class="flex flex-wrap gap-1.5 mt-1.5 text-xs">${[j.company, j.location, j.work_type, j.level, state.cands.length + " applicants"].filter(Boolean).map((x) => `<span class="px-2.5 py-1 rounded-md bg-card border border-rule">${esc(x)}</span>`).join("")}</div>
      </div>
      <button id="toggle-posting" class="text-sm px-3 py-2 rounded-lg border border-rule bg-card hover:bg-paper">Posting &amp; checklist</button>
      <button id="open-upload" class="text-sm px-4 py-2 rounded-lg bg-accent text-white hover:opacity-90">+ Add resume</button>
    </div>
    <div class="mb-3">
      <div class="flex items-center justify-between text-xs text-muted mb-1">
        <span>${done} of ${state.cands.length} triaged${state.pending ? ` · ${state.pending} waiting on the LLM queue` : ""}</span>
        <span class="hidden sm:inline">Shortlist at score ≥ ${state.thresholds.shortlist_at.toFixed(2)} with at most ${state.thresholds.max_unmet_musts} must-have gap</span>
      </div>
      <div class="h-1.5 rounded-full bg-rule overflow-hidden"><div class="h-full bg-accent" style="width:${(100 * done) / Math.max(1, state.cands.length)}%"></div></div>
    </div>
    <div id="posting" class="hidden mb-4"></div>
    <div class="flex gap-6 overflow-x-auto text-sm border-b border-rule">
      ${tabs.map(([k, label]) => `<button data-filter="${k}" class="shrink-0 py-2.5 -mb-px border-b-2 ${state.filter === k ? "border-accent text-accent font-medium" : "border-transparent text-muted hover:text-ink"}">${label} (${counts[k]})</button>`).join("")}
    </div>
    <div class="mt-4 rounded-2xl border border-rule bg-card overflow-hidden" id="strip">
      <div class="grid grid-cols-[2fr_1fr_.8fr_.8fr_1fr] gap-3 px-4 py-2.5 text-xs text-muted bg-paper/70"><span>Candidate</span><span>Must-haves</span><span>Exp.</span><span>AI match</span><span>Status</span></div>
      <div class="max-h-80 overflow-y-auto">${filtered().map((c) => stripChip(c, candId)).join("") || `<div class="p-4 text-sm text-muted">Nothing here.</div>`}</div>
    </div>
    <div id="card" class="mt-4"></div>`;
  document.querySelectorAll("[data-filter]").forEach((b) => (b.onclick = () => {
    state.filter = b.dataset.filter;
    const first = filtered()[0];
    location.hash = `#/job/${j.id}${first ? "/" + first.cand : ""}`;
    if (!first) route();
  }));
  document.getElementById("toggle-posting").onclick = togglePosting;
  document.getElementById("open-upload").onclick = openUpload;
  document.getElementById(`chip-${candId}`)?.scrollIntoView({ block: "nearest", inline: "center" });
}

function stripChip(c, active) {
  const on = c.cand === active, pct = Math.round(c.score * 100);
  const badge = pct >= 70 ? "bg-met/15 text-met" : pct >= 50 ? "bg-part/15 text-part" : "bg-paper text-muted";
  const status = c.action ? ACTION[c.action] : LANE[c.lane].label;
  const hue = [...c.cand].reduce((a, ch) => a + ch.charCodeAt(0), 0) % 360;
  return `<a id="chip-${c.cand}" href="#/job/${state.job.id}/${c.cand}" title="${esc(c.headline)}"
      class="grid grid-cols-[2fr_1fr_.8fr_.8fr_1fr] gap-3 items-center px-4 py-2.5 border-t border-rule text-sm ${on ? "bg-accent/5" : "hover:bg-paper/60"}">
      <div class="flex items-center gap-3 min-w-0">
        <span class="grid place-items-center w-9 h-9 rounded-full text-xs font-semibold shrink-0" style="background:hsl(${hue} 70% 90%);color:hsl(${hue} 55% 32%)">${esc(c.headline.slice(0, 2).toUpperCase())}</span>
        <div class="min-w-0"><div class="font-medium truncate capitalize">${esc(c.headline.toLowerCase())}</div><div class="text-xs text-muted font-mono">${esc(c.cand)}</div></div>
      </div>
      <div class="flex items-center gap-1.5 text-xs"><span class="px-2 py-0.5 rounded-md bg-paper">${c.musts_met}/${c.musts} musts</span></div>
      <div><span class="px-2 py-1 rounded-md bg-paper text-xs font-medium">${c.years}<sup class="text-[8px] ml-0.5">Yrs</sup></span></div>
      <div><span class="px-2.5 py-1 rounded-md text-xs font-semibold ${badge}">${pct}%</span></div>
      <div class="text-accent text-xs leading-tight">${esc(status)}</div>
    </a>`;
}

function togglePosting() {
  const el = document.getElementById("posting");
  if (!el.classList.contains("hidden")) return el.classList.add("hidden");
  const reqs = state.checklist?.requirements || [];
  el.innerHTML = `
    <div class="grid md:grid-cols-2 gap-3">
      <div class="rounded-xl border border-rule bg-card p-4">
        <h2 class="font-medium mb-2">Checklist read from the posting</h2>
        <ul class="space-y-1.5 text-sm">
          ${reqs.map((r) => `<li class="flex gap-2"><span class="font-mono text-xs text-muted w-7 shrink-0 pt-0.5">${r.id}</span>
            <span class="flex-1">${esc(r.text)} <span class="text-xs ${r.kind === "must" ? "text-miss" : "text-muted"}">${r.kind === "must" ? "must" : "nice"}</span>
            <span class="block text-xs text-muted italic">“${esc(r.jd_quote)}”</span></span></li>`).join("") || "<li class='text-muted'>Not extracted yet.</li>"}
        </ul>
      </div>
      <div class="rounded-xl border border-rule bg-card p-4 max-h-96 overflow-auto">
        <h2 class="font-medium mb-2">Posting</h2>
        <p class="text-sm whitespace-pre-line text-muted">${esc(state.job.text)}</p>
      </div>
    </div>`;
  el.classList.remove("hidden");
}

async function renderCard(candId) {
  const box = document.getElementById("card");
  box.innerHTML = `<p class="text-muted p-6">Loading ${esc(candId)}…</p>`;
  const r = await api(`/api/jobs/${state.job.id}/candidates/${candId}`);
  if (r.pending) return (box.innerHTML = `<p class="text-muted p-6">This candidate is waiting on the LLM queue.</p>`);
  const lane = LANE[r.lane];
  const musts = r.checklist.filter((c) => c.kind === "must");
  const ring = Math.round(r.score * 100);
  box.innerHTML = `
    <article class="rounded-2xl border border-rule bg-card shadow-sm overflow-hidden">
      <div class="p-5 grid gap-5 md:grid-cols-[200px_1fr]">
        <div class="flex md:flex-col items-center md:items-start gap-4">
          <div class="relative w-24 h-24 shrink-0">
            <svg viewBox="0 0 36 36" class="w-24 h-24 -rotate-90">
              <circle cx="18" cy="18" r="15.9" fill="none" class="stroke-rule" stroke-width="3"></circle>
              <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" class="${lane.dot.replace("bg-", "text-")}" stroke-width="3" stroke-dasharray="${ring} 100" stroke-linecap="round"></circle>
            </svg>
            <div class="absolute inset-0 grid place-items-center font-mono text-xl font-semibold">${r.score.toFixed(2)}</div>
          </div>
          <div class="space-y-2 min-w-0">
            <div class="font-mono text-xs text-muted">${esc(r.cand)}</div>
            <div class="font-medium leading-snug">${esc(r.profile.headline)}</div>
            <span class="inline-block text-xs px-2 py-0.5 rounded-full border ${lane.chip}">${lane.label}</span>
            <dl class="text-xs text-muted grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 pt-1">
              <dt>Finance yrs</dt><dd class="text-ink font-mono">${r.years.relevant}</dd>
              <dt>Total yrs</dt><dd class="text-ink font-mono">${r.years.all}</dd>
              <dt>Must-haves</dt><dd class="text-ink font-mono">${musts.filter((m) => m.verdict === "met").length}/${musts.length}</dd>
              <dt>Certs</dt><dd class="text-ink">${esc(r.profile.certifications.join(", ") || "none listed")}</dd>
            </dl>
          </div>
        </div>
        <div class="min-w-0">
          ${r.reasons.length ? `<div class="flex flex-wrap gap-1.5 mb-3">${r.reasons.map((x) => `<span title="${esc(state.reasonHelp[x] || "")}" class="text-[11px] font-mono px-2 py-0.5 rounded border border-rule bg-paper">${esc(x)}</span>`).join("")}</div>` : ""}
          <p class="text-sm leading-relaxed">${esc(r.explanation)}</p>
          <table class="w-full mt-4 text-sm">
            <tbody class="divide-y divide-rule">
              ${r.checklist.map(checkRow).join("")}
            </tbody>
          </table>
        </div>
      </div>
      <details class="border-t border-rule group">
        <summary class="px-5 py-3 text-sm cursor-pointer select-none text-muted hover:text-ink">Resume (masked) with evidence highlighted</summary>
        <div class="px-5 pb-5 text-sm whitespace-pre-line leading-relaxed max-h-[28rem] overflow-auto">${highlight(r.resume, r.checklist.map((c) => c.quote).filter(Boolean))}</div>
      </details>
      <footer class="border-t border-rule bg-paper/60 px-5 py-3 flex flex-wrap items-center gap-2">
        ${r.action && r.action.action !== "undo" ? `<span class="text-sm">Your call: <b>${ACTION[r.action.action]}</b>${r.action.note ? ` · <span class="text-muted">${esc(r.action.note)}</span>` : ""}</span>
          <button data-act="undo" class="text-sm px-3 py-1.5 rounded-md border border-rule hover:bg-card">Undo</button>` : `
          <button data-act="advance" class="text-sm px-3 py-1.5 rounded-md bg-met text-white hover:opacity-90">Advance <kbd class="ml-1 !bg-transparent !text-white/80 !border-white/40">A</kbd></button>
          <button data-act="hold" class="text-sm px-3 py-1.5 rounded-md border border-rule hover:bg-card">Hold <kbd class="ml-1">H</kbd></button>
          <button data-act="pass" class="text-sm px-3 py-1.5 rounded-md border border-miss/50 text-miss hover:bg-miss/10">Pass… <kbd class="ml-1">P</kbd></button>`}
        <span class="ml-auto text-xs text-muted hidden sm:inline"><kbd>J</kbd> <kbd>K</kbd> next / previous</span>
      </footer>
    </article>`;
  box.querySelectorAll("[data-act]").forEach((b) => (b.onclick = () => decide(candId, b.dataset.act)));
}

function checkRow(c) {
  const v = VERDICT[c.verdict] || VERDICT.not_met;
  const ev = c.quote ? `<span class="block text-xs text-muted mt-0.5">“${esc(c.quote)}”</span>`
    : c.note ? `<span class="block text-xs text-muted mt-0.5">${esc(c.note)}</span>` : "";
  return `<tr class="align-top">
    <td class="py-2 pr-2 w-6 text-base leading-none ${v.cls}" title="${v.label}">${v.icon}</td>
    <td class="py-2 pr-2">${esc(c.text)}${ev}</td>
    <td class="py-2 text-right text-xs whitespace-nowrap ${c.kind === "must" ? "text-miss" : "text-muted"}">${c.kind}${c.source === "code" ? ` <span class="text-muted">· computed</span>` : ""}</td>
  </tr>`;
}

function highlight(text, quotes) {
  let html = esc(text);
  for (const q of quotes.sort((a, b) => b.length - a.length)) {
    const eq = esc(q).trim();
    if (eq.length < 6) continue;
    const i = html.toLowerCase().indexOf(eq.toLowerCase());
    if (i >= 0) html = html.slice(0, i) + `<mark class="ev">` + html.slice(i, i + eq.length) + "</mark>" + html.slice(i + eq.length);
  }
  return html;
}

async function decide(candId, action) {
  let note = "";
  if (action === "pass") {
    note = prompt("Why pass on this candidate? (required, the agent never rejects on its own)") || "";
    if (note.trim().length < 5) return toast("A reason of at least 5 characters is required.");
  }
  try {
    await api(`/api/jobs/${state.job.id}/candidates/${candId}/action`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, note }) });
  } catch (e) { return toast(e.message); }
  const c = state.cands.find((x) => x.cand === candId);
  if (c) c.action = action === "undo" ? null : action;
  toast(action === "undo" ? "Undone" : `${ACTION[action]}: ${candId}`);
  if (action !== "undo") step(1, candId); else route();
}

function step(dir, from) {
  const list = state.filter === "all" ? state.cands : filtered();
  const cur = from || location.hash.split("/")[3];
  let i = state.cands.findIndex((c) => c.cand === cur);
  const order = state.cands;
  for (let k = 0; k < order.length; k++) {
    i = (i + dir + order.length) % order.length;
    if (list.includes(order[i]) || state.filter === "all") break;
  }
  const next = order[i];
  if (next) location.hash = `#/job/${state.job.id}/${next.cand}`; else route();
}

document.addEventListener("keydown", (e) => {
  if (!location.hash.startsWith("#/job/") || e.target.closest("input,textarea") || e.metaKey || e.ctrlKey) return;
  const cand = location.hash.split("/")[3];
  const k = e.key.toLowerCase();
  if (k === "j") step(1);
  else if (k === "k") step(-1);
  else if (cand && ["a", "h", "p"].includes(k) && document.querySelector(`[data-act="${{ a: "advance", h: "hold", p: "pass" }[k]}"]`))
    decide(cand, { a: "advance", h: "hold", p: "pass" }[k]);
});

function openUpload() {
  const wrap = document.createElement("div");
  wrap.className = "fixed inset-0 z-40 bg-black/40 grid place-items-center p-4";
  wrap.innerHTML = `
    <form class="w-full max-w-xl rounded-2xl bg-card border border-rule p-5 space-y-3">
      <h2 class="font-semibold">Add a resume to ${esc(state.job.title)}</h2>
      <p class="text-sm text-muted">Paste text or choose a PDF or .txt file (PDFs need a text layer; scans are not read). Contact details are masked before anything is sent to the LLM. Uploads live in memory only.</p>
      <textarea name="text" rows="10" class="w-full rounded-lg border border-rule bg-paper p-3 text-sm font-mono" placeholder="Paste resume text…"></textarea>
      <input type="file" name="file" accept=".pdf,.txt,application/pdf,text/plain" class="text-sm">
      <div class="flex justify-end gap-2">
        <button type="button" data-close class="px-3 py-1.5 rounded-md border border-rule text-sm">Cancel</button>
        <button class="px-3 py-1.5 rounded-md bg-ink text-paper text-sm">Screen it</button>
      </div>
    </form>`;
  document.body.appendChild(wrap);
  wrap.querySelector("[data-close]").onclick = () => wrap.remove();
  wrap.querySelector("form").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const r = await fetch(`/api/jobs/${state.job.id}/upload`, { method: "POST", body: new FormData(ev.target) });
      const d = await r.json();
      if (!r.ok) return toast(d.error);
      wrap.remove();
      toast(d.pending ? d.message : `Screened as ${d.cand}`);
      state.job = null;
      location.hash = `#/job/${(location.hash.split("/")[2])}/${d.pending ? "" : d.cand}`;
      route();
    } catch (e) { toast(e.message); }
  };
}

// ---------------------------------------------------------------- evaluation page
async function metrics() {
  $view.innerHTML = `<p class="text-muted">Loading evaluation…</p>`;
  const d = await api("/api/metrics");
  const m = d.metrics;
  if (!m) {
    $view.innerHTML = `<h1 class="text-2xl font-semibold mb-2">Evaluation</h1><p class="text-muted">No results yet. Run <code class="font-mono">make eval</code>.</p>`;
    return;
  }
  const fmt = (x) => (x == null ? "–" : typeof x === "number" ? x.toFixed(2) : esc(x));
  const rows = (d.baselines?.systems || []);
  const cols = ["ndcg@5", "p@5", "spearman", "shortlist_precision", "shortlist_recall", "review_rate", "cost"];
  $view.innerHTML = `
    <h1 class="text-2xl font-semibold tracking-tight">Evaluation</h1>
    <p class="text-sm text-muted mt-1 mb-5">Test split: ${m.test?.n_pairs ?? "?"} labelled pairs over ${m.test?.n_jobs ?? "?"} jobs. Shortlist threshold ${fmt(d.thresholds?.shortlist_at)} was tuned on the dev jobs only.</p>
    <div class="grid sm:grid-cols-4 gap-3 mb-6">
      ${[["NDCG@5", m.test?.["ndcg@5"]], ["Shortlist precision", m.test?.shortlist_precision], ["Shortlist recall", m.test?.shortlist_recall], ["Sent to review", m.test?.review_rate]]
        .map(([k, v]) => `<div class="rounded-xl border border-rule bg-card p-4"><div class="text-xs text-muted">${k}</div><div class="font-mono text-2xl mt-1">${fmt(v)}</div></div>`).join("")}
    </div>
    <h2 class="font-medium mb-2">Against baselines (test)</h2>
    <div class="overflow-x-auto rounded-xl border border-rule bg-card mb-6">
      <table class="w-full text-sm">
        <thead class="text-xs text-muted"><tr><th class="text-left p-3">system</th>${cols.map((c) => `<th class="text-right p-3">${c}</th>`).join("")}</tr></thead>
        <tbody class="divide-y divide-rule font-mono">${rows.map((r) => `<tr><td class="p-3 font-sans">${esc(r.system)}</td>${cols.map((c) => `<td class="p-3 text-right">${fmt(r[c])}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
    <div class="grid md:grid-cols-2 gap-3">
      <section class="rounded-xl border border-rule bg-card p-4"><h2 class="font-medium mb-2">Fairness (counterfactual swaps)</h2>${kv(d.fairness?.summary)}</section>
      <section class="rounded-xl border border-rule bg-card p-4"><h2 class="font-medium mb-2">Explanation judge vs reviewer</h2>${kv(d.judge?.agreement)}</section>
      <section class="rounded-xl border border-rule bg-card p-4"><h2 class="font-medium mb-2">Extraction</h2>${kv(d.extraction)}</section>
      <section class="rounded-xl border border-rule bg-card p-4"><h2 class="font-medium mb-2">Manipulation tests</h2>${kv(d.adversarial?.summary)}</section>
    </div>`;
}

function kv(o) {
  if (!o) return `<p class="text-sm text-muted">Not run yet.</p>`;
  return `<dl class="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">${Object.entries(o).map(([k, v]) =>
    `<dt class="text-muted">${esc(k)}</dt><dd class="font-mono text-right">${typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(3)) : esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("")}</dl>`;
}
