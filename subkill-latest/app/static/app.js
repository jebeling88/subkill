const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let ME = null, signup = false;

async function api(path, { method = "GET", body, form } = {}) {
  const opt = { method, headers: { "X-SubKill": "1" }, credentials: "same-origin" };
  if (body) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  if (form) opt.body = form;
  const r = await fetch(path, opt);
  let data = null; try { data = await r.json(); } catch {}
  if (r.status === 401 && path !== "/api/login" && path !== "/api/signup") { showAuth(); throw new Error("Please sign in."); }
  if (!r.ok) throw new Error((data && data.detail) || "Something went wrong.");
  return data;
}
const money = (c, cur = "USD") => { try { return new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(c / 100); } catch { return "$" + (c / 100).toFixed(2); } };
const money0 = c => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(c / 100);
function toast(t) { const e = $("#toast"); e.textContent = t; e.classList.remove("hidden"); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.add("hidden"), 3000); }
function ago(d) {
  if (!d) return null;
  const n = Math.round((Date.now() - new Date(d + "T12:00:00")) / 864e5);
  if (n <= 0) return "today"; if (n === 1) return "yesterday"; if (n < 60) return n + "d ago";
  if (n < 700) return Math.round(n / 30) + " mo ago"; return Math.round(n / 365) + "y ago";
}
function until(d) {
  if (!d) return null;
  const n = Math.round((new Date(d + "T12:00:00") - Date.now()) / 864e5);
  return n < 0 ? "renewal passed" : n === 0 ? "renews today" : n === 1 ? "renews tomorrow" : "renews in " + n + "d";
}

/* ---------- auth ---------- */
function showAuth() { $("#app").classList.add("hidden"); $("#auth").classList.remove("hidden"); }
$("#authToggle").onclick = () => {
  signup = !signup;
  $("#authBtn").textContent = signup ? "Create account" : "Sign in";
  $("#authToggle").textContent = signup ? "Have an account? Sign in" : "New here? Create an account";
  $("#password").autocomplete = signup ? "new-password" : "current-password";
  $("#invite").classList.toggle("hidden", !signup);
};
$("#authForm").onsubmit = async e => {
  e.preventDefault(); $("#authErr").textContent = "";
  try { await api(signup ? "/api/signup" : "/api/login", { method: "POST", body: { email: $("#email").value, password: $("#password").value, invite: $("#invite").value } }); await boot(); }
  catch (x) { $("#authErr").textContent = x.message; }
};
$("#logout").onclick = async () => { await api("/api/logout", { method: "POST" }); showAuth(); };

/* ---------- boot / dashboard ---------- */
async function boot() {
  try { ME = await api("/api/me"); } catch { return showAuth(); }
  $("#auth").classList.add("hidden"); $("#app").classList.remove("hidden");
  fillSelects(); $("#chat").classList.remove("hidden"); await refresh();
  const g = new URLSearchParams(location.search).get("gmail");
  if (g) { history.replaceState({}, "", "/"); toast(g === "connected" ? "Gmail connected." : "Gmail connection failed."); if (g === "connected") openAdd("gmail"); }
}
function fillSelects() {
  const keep = $("#fOwner").value;
  $("#fOwner").innerHTML = '<option value="">Everyone</option>' + ME.members.map(m => `<option>${esc(m)}</option>`).join("");
  $("#fOwner").value = keep;
  $("#ownerSel").innerHTML = ME.members.map(m => `<option>${esc(m)}</option>`).join("");
  if (!$("#fCat").dataset.done) { $("#fCat").innerHTML += ME.categories.map(c => `<option>${esc(c)}</option>`).join(""); $("#fCat").dataset.done = 1; }
  $("#mCat").innerHTML = ME.categories.map(c => `<option>${esc(c)}</option>`).join("");
  $("#membersIn").value = ME.members.join(", ");
}
async function refresh() { await Promise.all([loadStats(), loadList()]); }

async function loadStats() {
  const s = await api("/api/summary");
  $("#stats").innerHTML = `
    <div class="card stat hero"><div class="n">${money(s.monthly_cents)}<span class="muted" style="font-size:15px;font-weight:400"> / mo</span></div><div class="l">Quietly leaving your account · ${money0(s.yearly_cents)} a year</div></div>
    <div class="card stat"><div class="n">${s.live_count}</div><div class="l">Still active</div></div>
    <div class="card stat"><div class="n">${money0(s.unused_monthly_cents)}<span class="muted" style="font-size:13px;font-weight:400">/mo</span></div><div class="l">${s.unused_count} unused 60+ days</div></div>
    <div class="card stat"><div class="n" style="color:var(--ok)">${money0(s.saved_yearly_cents)}</div><div class="l">Saved per year (${s.cancelled_count} killed)</div></div>`;
  let a = "";
  if (s.still_charging) a += `<div class="banner">⚠️ ${s.still_charging} subscription${s.still_charging > 1 ? "s" : ""} charged you <b>after</b> you cancelled. Open ${s.still_charging > 1 ? "them" : "it"} below and dispute the charge.</div>`;
  if (s.renewing_soon) a += `<div class="banner" style="background:var(--chip);border-color:var(--line)">${s.renewing_soon} renewing in the next 7 days.</div>`;
  $("#alert").innerHTML = a;
}

const hue = s => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
async function loadList() {
  const p = new URLSearchParams({ sort: $("#sort").value, status: $("#fStatus").value === "all" ? "all" : $("#fStatus").value });
  if ($("#q").value.trim()) p.set("q", $("#q").value.trim());
  if ($("#fOwner").value) p.set("owner", $("#fOwner").value);
  if ($("#fCat").value) p.set("category", $("#fCat").value);
  if ($("#fCycle").value) p.set("cycle", $("#fCycle").value);
  if ($("#fUnused").checked) p.set("unused", "true");
  const rows = await api("/api/subscriptions?" + p);
  const el = $("#list");
  if (!rows.length) {
    el.innerHTML = `<div class="card empty"><p><b>Nothing here yet.</b></p><p class="muted">Add your emails or a bank statement and Claude will dig out every recurring charge.</p><button class="btn primary" id="emptyAdd">Add subscriptions</button> <button class="btn ghost" id="emptyDemo">Load sample data</button></div>`;
    $("#emptyAdd").onclick = () => openAdd("paste");
    $("#emptyDemo").onclick = async () => { await api("/api/demo/seed", { method: "POST" }); ME = await api("/api/me"); fillSelects(); refresh(); };
    return;
  }
  el.innerHTML = rows.map(row).join("");
  $$(".js-kill", el).forEach(b => b.onclick = () => openKill(rows.find(r => r.id == b.dataset.id)));
  $$(".js-used", el).forEach(b => b.onclick = async () => { await api(`/api/subscriptions/${b.dataset.id}/used`, { method: "POST" }); toast("Marked as used today."); refresh(); });
  $$(".js-restore", el).forEach(b => b.onclick = async () => { await api(`/api/subscriptions/${b.dataset.id}/restore`, { method: "POST" }); refresh(); });
  $$(".js-del", el).forEach(b => b.onclick = async () => { if (confirm("Remove this from your list? (This does not cancel anything.)")) { await api(`/api/subscriptions/${b.dataset.id}`, { method: "DELETE" }); refresh(); } });
}
function row(r) {
  const dead = r.status === "cancelled";
  const cyc = { weekly: "wk", monthly: "mo", quarterly: "qtr", yearly: "yr" }[r.cycle];
  const used = ago(r.last_used_at), old = !r.last_used_at || (Date.now() - new Date(r.last_used_at + "T12:00:00")) / 864e5 > 60;
  const chips = [`<span class="chip">${esc(r.owner)}</span>`, `<span class="chip">${esc(r.category)}</span>`];
  if (r.status === "trial") chips.push('<span class="chip amber">Free trial</span>');
  if (r.status === "cancelling") chips.push('<span class="chip amber">Cancelling…</span>');
  if (dead) chips.push('<span class="chip green">Killed</span>');
  if (r.still_charging) chips.push('<span class="chip red">Still charging!</span>');
  const meta = [];
  meta.push(used ? `Used ${used}` : "No use seen");
  if (r.use_count) meta.push(`${r.use_count} uses`);
  if (r.started_at) meta.push("Since " + esc(r.started_at.slice(0, 7)));
  if (!dead && until(r.next_renewal)) meta.push(until(r.next_renewal));
  const sub = r.cycle === "monthly" ? "per month" : `${money(r.amount_cents, r.currency)} / ${cyc}`;
  const big = r.cycle === "monthly" ? money(r.amount_cents, r.currency) : "≈ " + money(r.monthly_cents, r.currency) + "/mo";
  return `<article class="card sub ${dead ? "dead" : ""}">
    <div class="av" style="background:hsl(${hue(r.merchant)} 55% 45%)">${esc(r.merchant[0].toUpperCase())}</div>
    <div><div class="name">${esc(r.merchant)}${r.plan ? ` <span class="muted" style="font-weight:400">· ${esc(r.plan)}</span>` : ""}</div>
      <div class="meta">${chips.join("")}<span ${old && !dead ? 'style="color:var(--warn)"' : ""}>${meta.join(" · ")}</span></div></div>
    <div class="cost"><div class="m">${big}</div><div class="s">${sub}</div></div>
    <div class="acts">${dead
      ? `<button class="btn js-restore" data-id="${r.id}">Restore</button><button class="btn ghost js-del" data-id="${r.id}">Remove</button>`
      : `<button class="btn js-used" data-id="${r.id}" title="I used this today">Used</button><button class="btn kill js-kill" data-id="${r.id}">Kill</button>`}</div>
  </article>`;
}
["#sort", "#fOwner", "#fCat", "#fCycle", "#fStatus", "#fUnused"].forEach(s => $(s).onchange = loadList);
let qt; $("#q").oninput = () => { clearTimeout(qt); qt = setTimeout(loadList, 200); };

/* ---------- add dialog ---------- */
function openAdd(tab = "paste") { setTab(tab); $("#addMsg").textContent = ""; $("#addDlg").showModal(); }
function setTab(t) {
  $$(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  $$(".pane").forEach(p => p.classList.toggle("hidden", p.dataset.pane !== t));
  if (t === "gmail") renderGmail();
}
$$(".tabs button").forEach(b => b.onclick = () => setTab(b.dataset.tab));
$("#openAdd").onclick = () => openAdd();
$$("[data-close]").forEach(b => b.onclick = e => e.target.closest("dialog").close());
function renderGmail() {
  const p = $("#gmailPane");
  if (!ME.gmail_available) p.innerHTML = '<p class="muted">Gmail isn’t set up on this server yet. Add Google OAuth keys (see <code>.env.example</code>) to scan your inbox and send cancellations from your own address.</p>';
  else if (!ME.gmail_connected) p.innerHTML = '<p class="muted">Connect Gmail so Claude can read receipts and renewal notices from the last 12 months. Only matching billing emails are read; nothing is stored except the subscriptions found.</p><a class="btn primary" href="/api/gmail/connect">Connect Gmail</a>';
  else { p.innerHTML = '<p class="muted">Gmail connected.</p><div class="row"><button class="btn primary" id="goGmail">Scan my inbox</button><button class="btn ghost" id="dcGmail">Disconnect</button></div>';
    $("#goGmail").onclick = () => run($("#goGmail"), () => api("/api/gmail/scan?owner=" + encodeURIComponent($("#ownerSel").value), { method: "POST" }));
    $("#dcGmail").onclick = async () => { await api("/api/gmail/disconnect", { method: "POST" }); ME.gmail_connected = false; renderGmail(); }; }
}
async function run(btn, fn) {
  btn.disabled = true; const t = btn.textContent; btn.textContent = "Claude is reading…"; $("#addMsg").textContent = "";
  try { const r = await fn(); $("#addMsg").style.color = "var(--ok)"; $("#addMsg").textContent = `Found ${r.found}: ${r.new} new, ${r.updated} updated.`; await refresh(); }
  catch (e) { $("#addMsg").style.color = "var(--accent)"; $("#addMsg").textContent = e.message; }
  btn.disabled = false; btn.textContent = t;
}
$("#goPaste").onclick = () => run($("#goPaste"), () => api("/api/ingest/text", { method: "POST", body: { text: $("#pasteTxt").value, kind: "email", owner: $("#ownerSel").value } }));
$("#goFile").onclick = () => {
  const f = $("#fileIn").files[0]; if (!f) return ($("#addMsg").textContent = "Choose a file first.");
  const fd = new FormData(); fd.append("file", f); fd.append("owner", $("#ownerSel").value);
  run($("#goFile"), () => api("/api/ingest/upload", { method: "POST", form: fd }));
};
$("#goManual").onclick = async () => {
  try { await api("/api/subscriptions", { method: "POST", body: { merchant: $("#mName").value, amount: +$("#mAmt").value, cycle: $("#mCycle").value, category: $("#mCat").value, owner: $("#ownerSel").value } });
    $("#mName").value = ""; $("#mAmt").value = ""; $("#addMsg").style.color = "var(--ok)"; $("#addMsg").textContent = "Added."; refresh(); }
  catch (e) { $("#addMsg").style.color = "var(--accent)"; $("#addMsg").textContent = e.message; }
};
$("#saveMembers").onclick = async () => {
  const r = await api("/api/members", { method: "PUT", body: { members: $("#membersIn").value.split(",") } });
  ME.members = r.members; fillSelects(); toast("Saved.");
};

/* ---------- kill dialog ---------- */
async function openKill(s) {
  const d = $("#killDlg"), b = $("#killBody");
  b.innerHTML = `<div class="dlg-h"><h2>Killing ${esc(s.merchant)}</h2><button class="x" data-x>×</button></div><p class="muted">Claude is working out the fastest way to cancel…</p>`;
  $("[data-x]", b).onclick = () => d.close(); d.showModal();
  let p; try { p = await api(`/api/subscriptions/${s.id}/kill`, { method: "POST" }); }
  catch (e) { b.innerHTML = `<div class="dlg-h"><h2>Killing ${esc(s.merchant)}</h2><button class="x" data-x>×</button></div><p class="err">${esc(e.message)}</p>`; $("[data-x]", b).onclick = () => d.close(); return; }
  const url = p.cancel_url || s.cancel_url;
  const canSend = ME.gmail_connected && p.contact_email;
  b.innerHTML = `
    <div class="dlg-h"><h2>Killing ${esc(s.merchant)}</h2><button class="x" data-x>×</button></div>
    <div class="row" style="flex-wrap:wrap"><span class="chip">${esc(p.method)}</span><span class="chip ${p.difficulty === "easy" ? "green" : p.difficulty === "hard" ? "red" : "amber"}">${esc(p.difficulty)}</span><span class="chip">${money(s.monthly_cents, s.currency)}/mo</span></div>
    ${p.caveats ? `<div class="note">${esc(p.caveats)}</div>` : ""}
    <ol class="steps">${(p.steps || []).map(x => `<li>${esc(x)}</li>`).join("")}</ol>
    ${url ? `<a class="btn kill" id="goUrl" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open cancel page</a>` : ""}
    <details ${url ? "" : "open"}><summary>Cancellation email (review before sending)</summary>
      <div class="email"><input id="eTo" placeholder="To (support address)" value="${esc(p.contact_email || "")}"><input id="eSub" value="${esc(p.email_subject)}"><textarea id="eBody">${esc(p.email_body)}</textarea>
      <div class="row">${ME.gmail_connected ? '<button class="btn primary" id="eSend">Send from my Gmail</button>' : ""}<button class="btn" id="eCopy">Copy email</button></div></div></details>
    <div class="note">${canSend || ME.gmail_connected ? "" : "Connect Gmail to send this for you. "}SubKill can’t log in to other companies’ websites for you; it gets you the exact path and the words. Once it’s done, confirm below and we’ll keep watching for any charge that sneaks through.</div>
    <div class="row"><button class="btn primary" id="done">✓ I cancelled it</button><button class="btn ghost" data-x>Not now</button></div>`;
  $$("[data-x]", b).forEach(x => x.onclick = () => d.close());
  if (url) $("#goUrl").onclick = () => api(`/api/subscriptions/${s.id}/mark-cancelling`, { method: "POST" }).then(refresh);
  $("#eCopy").onclick = () => { navigator.clipboard.writeText(`To: ${$("#eTo").value}\nSubject: ${$("#eSub").value}\n\n${$("#eBody").value}`); toast("Copied."); };
  const send = $("#eSend");
  if (send) send.onclick = async () => {
    if (!$("#eTo").value.includes("@")) return toast("Add the support email address first.");
    send.disabled = true;
    try { await api(`/api/subscriptions/${s.id}/send-cancel-email`, { method: "POST", body: { to: $("#eTo").value, subject: $("#eSub").value, body: $("#eBody").value } }); toast("Sent. Marked as cancelling."); refresh(); }
    catch (e) { toast(e.message); } send.disabled = false;
  };
  $("#done").onclick = async () => { await api(`/api/subscriptions/${s.id}/mark-cancelled`, { method: "POST" }); d.close(); toast("Killed 🎯 We’ll watch for rogue charges."); refresh(); };
}

/* ---------- chat ---------- */
const chatMsgs = [];
function chatOpen(on) { $("#chatLog").classList.toggle("hidden", !on); $("#chatChev").textContent = on ? "▼" : "▲"; }
$("#chatHead").onclick = () => chatOpen($("#chatLog").classList.contains("hidden"));
function bubble(text, me) { const d = document.createElement("div"); d.className = "bub" + (me ? " me" : ""); d.textContent = text; $("#chatLog").append(d); $("#chatLog").scrollTop = 1e9; return d; }
function planCard(a) {
  const p = a.plan || {}, d = document.createElement("div"); d.className = "plan";
  const url = /^https:\/\//.test(p.cancel_url || "") ? p.cancel_url : "";
  d.innerHTML = `<b>Cancel ${esc(a.merchant)}</b> <span class="muted">${money(a.monthly_cents || 0)}/mo · ${esc(p.method || "")} · ${esc(p.difficulty || "")}</span>
    ${p.caveats ? `<div class="note">${esc(p.caveats)}</div>` : ""}<ol>${(p.steps || []).map(x => `<li>${esc(x)}</li>`).join("")}</ol>
    <div class="row">${url ? `<a class="btn kill" target="_blank" rel="noopener noreferrer" href="${esc(url)}">Open cancel page</a>` : ""}<button class="btn" data-copy>Copy email</button><button class="btn" data-done>✓ I cancelled it</button></div>`;
  const a1 = $("a", d); if (a1) a1.onclick = () => api(`/api/subscriptions/${a.subscription_id}/mark-cancelling`, { method: "POST" }).then(refresh);
  $("[data-copy]", d).onclick = () => { navigator.clipboard.writeText(`To: ${p.contact_email || ""}\nSubject: ${p.email_subject || ""}\n\n${p.email_body || ""}`); toast("Copied."); };
  $("[data-done]", d).onclick = async e => { await api(`/api/subscriptions/${a.subscription_id}/mark-cancelled`, { method: "POST" }); e.target.textContent = "Killed ✓"; refresh(); };
  $("#chatLog").append(d); $("#chatLog").scrollTop = 1e9;
}
$("#chatForm").onsubmit = async e => {
  e.preventDefault(); const t = $("#chatIn").value.trim(); if (!t) return;
  $("#chatIn").value = ""; chatOpen(true); chatMsgs.push({ role: "user", content: t }); bubble(t, true);
  const wait = bubble("Thinking…", false);
  try {
    const r = await api("/api/chat", { method: "POST", body: { messages: chatMsgs.slice(-20) } });
    wait.textContent = r.reply; chatMsgs.push({ role: "assistant", content: r.reply });
    r.actions.filter(a => a.type === "cancel_plan").forEach(planCard);
    if (r.actions.length) refresh();
  } catch (x) { wait.textContent = "⚠️ " + x.message; chatMsgs.pop(); }
};
boot();
