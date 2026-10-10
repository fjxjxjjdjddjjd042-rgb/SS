/* kill_pv2 panel — vanilla JS, zero dependencies */
(() => {
  const P = window.PREFIX || "/KILLPV2";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const GB = 1024 ** 3, MB = 1024 ** 2;

  const fmtB = (b, zero = "نامحدود") => { b = +b || 0; if (!b) return zero; if (b >= 1024 ** 4) return (b / 1024 ** 4).toFixed(2) + " TB"; if (b >= GB) return (b / GB).toFixed(2) + " GB"; if (b >= MB) return (b / MB).toFixed(1) + " MB"; if (b >= 1024) return (b / 1024).toFixed(0) + " KB"; return b + " B"; };
  const ago = ts => { if (!ts) return "—"; const d = Math.max(0, Date.now() / 1000 - ts); if (d < 60) return "الان"; if (d < 3600) return Math.floor(d / 60) + " دقیقه پیش"; if (d < 86400) return Math.floor(d / 3600) + " ساعت پیش"; return Math.floor(d / 86400) + " روز پیش"; };
  const dt = ts => new Date(ts * 1000).toLocaleString("fa-IR", { hour12: false });
  const dur = s => { s = Math.max(0, s | 0); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return d ? `${d} روز ${h} ساعت` : h ? `${h} ساعت ${m} دقیقه` : `${m} دقیقه`; };

  async function api(path, opt = {}) {
    const o = { method: opt.method || "GET", headers: {}, credentials: "same-origin" };
    if (opt.body !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opt.body); }
    const r = await fetch(P + "/api/" + path, o);
    if (r.status === 401 && path !== "login" && path !== "ping") { showLogin(); throw new Error("unauthorized"); }
    const ct = r.headers.get("content-type") || "";
    const data = ct.includes("json") ? await r.json() : await r.text();
    if (!r.ok) throw Object.assign(new Error(data?.error || r.statusText), { status: r.status, data });
    return data;
  }

  let toastT;
  function toast(msg, cls = "") { let t = $("#toast-root .toast"); if (!t) { t = document.createElement("div"); $("#toast-root").appendChild(t); } t.className = "toast " + cls; t.textContent = msg; clearTimeout(toastT); toastT = setTimeout(() => t.remove(), 2600); }
  function copy(text, msg = "کپی شد") { (navigator.clipboard?.writeText(text) || Promise.reject()).then(() => toast(msg, "ok")).catch(() => { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); toast(msg, "ok"); }); }
  function modal(html) { const root = $("#modal-root"); root.innerHTML = `<div class="modal-bg"><div class="modal">${html}</div></div>`; root.firstChild.addEventListener("click", e => { if (e.target === root.firstChild) closeModal(); }); return root.querySelector(".modal"); }
  function closeModal() { $("#modal-root").innerHTML = ""; }
  const confirm2 = msg => new Promise(res => { const m = modal(`<h3>${esc(msg)}</h3><div class="row"><button class="btn bad" id="c-ok">بله</button><button class="btn ghost" id="c-no">خیر</button></div>`); $("#c-ok", m).onclick = () => { closeModal(); res(true); }; $("#c-no", m).onclick = () => { closeModal(); res(false); }; });

  // ---------------------------------------------------------------- auth
  function showLogin() { $("#login").classList.remove("hidden"); $("#app").classList.add("hidden"); stopPolling(); }
  function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); startPolling(); loadAll(); }
  $("#login-form").onsubmit = async e => {
    e.preventDefault(); const btn = $("#lg-btn"), msg = $("#lg-msg"); btn.disabled = true; msg.textContent = "";
    try { await api("login", { method: "POST", body: { username: $("#lg-user").value.trim(), password: $("#lg-pass").value } }); $("#lg-pass").value = ""; showApp(); }
    catch (err) { const d = err.data || {}; msg.textContent = err.status === 429 ? `🔒 قفل شد. ${Math.ceil((d.retry_after || 0) / 60)} دقیقه دیگر تلاش کن` : err.status === 401 ? `❌ اشتباه است. ${d.attempts_left ?? ""} تلاش باقی مانده` : "خطا: " + err.message; }
    btn.disabled = false;
  };
  $("#btn-logout").onclick = async () => { await api("logout", { method: "POST" }).catch(() => { }); showLogin(); };
  $("#btn-refresh").onclick = () => loadAll(true);

  // ---------------------------------------------------------------- tabs
  let page = "dash";
  $$(".tabs button").forEach(b => b.onclick = () => go(b.dataset.p));
  function go(p) { page = p; $$(".tabs button").forEach(b => b.classList.toggle("active", b.dataset.p === p)); $$(".page").forEach(s => s.classList.toggle("active", s.id === "page-" + p)); window.scrollTo(0, 0); loadPage(p); }
  function loadPage(p) { ({ dash: loadDash, clients: loadClients, logs: loadLogs, noads: loadNoads, bypass: loadBypass, settings: loadSettings })[p]?.(); }
  async function loadAll(all) { loadPage(page); if (all) toast("بروزرسانی شد", "ok"); }
  let pollT; function startPolling() { stopPolling(); pollT = setInterval(() => { if (document.hidden) return; if (page === "dash") loadDash(); else if (page === "clients") loadClients(true); else if (page === "logs" && logsView === "live") loadLogs(); }, 4000); }
  function stopPolling() { clearInterval(pollT); }

  // ---------------------------------------------------------------- dashboard
  let ov = {};
  async function loadDash() {
    try { ov = await api("overview"); } catch { return; }
    $("#xray-dot").classList.toggle("on", !!ov.xray_running);
    $("#tunnel-tag").textContent = ov.tunnel_host || "";
    $("#pw-hint").classList.toggle("hidden", !ov.generated_password);
    const st = [
      ["آنلاین", ov.online, `از ${ov.clients_active} فعال`], ["کل کانفیگ‌ها", ov.clients_total, ""],
      ["مصرف کل", fmtB(ov.used_total, "0 B"), "دقیق از Xray"], ["دانلود ۲۴h", fmtB(ov.day_down, "0 B"), `آپلود ${fmtB(ov.day_up, "0 B")}`],
      ["تبلیغ مسدود ۲۴h", ov.ads_blocked_24h, `از ${ov.requests_24h} درخواست`], ["Xray", ov.xray_running ? "فعال" : "خاموش", `RAM ${fmtB(ov.xray_mem, "0")}`],
      ["زمان باقی ران", dur(ov.run_remaining), "تا چرخش بعدی"], ["NoAds", { off: "خاموش", balanced: "متعادل", aggressive: "تهاجمی", strict: "سخت‌گیر" }[ov.noads_level] || ov.noads_level, "بای‌پس: " + (ov.bypass_mode === "direct" ? "مستقیم" : "VPN")],
    ];
    $("#dash-stats").innerHTML = st.map(([l, v, s]) => `<div class="stat"><div class="l">${l}</div><div class="v">${esc(v)}</div><div class="s">${esc(s)}</div></div>`).join("");
    $("#dash-day").textContent = fmtB((ov.day_up || 0) + (ov.day_down || 0), "0 B");
    $("#dash-blocked").innerHTML = (ov.top_blocked || []).map(r => `<div class="item"><span class="mono">${esc(r.host)}</span><small>${r.hits}</small></div>`).join("") || `<div class="empty">هنوز چیزی مسدود نشده</div>`;
    renderSpark();
  }
  async function renderSpark() {
    try {
      const cl = (await api("clients")).clients; const buckets = new Array(24).fill(0); const now = Math.floor(Date.now() / 1000);
      await Promise.all(cl.slice(0, 12).map(async c => { const s = (await api(`traffic/${encodeURIComponent(c.name)}?hours=24`)).series; s.forEach(p => { const i = 23 - Math.min(23, Math.floor((now - p.ts) / 3600)); buckets[i] += p.up + p.down; }); }));
      const mx = Math.max(1, ...buckets); $("#dash-spark").innerHTML = buckets.map(v => `<i style="height:${Math.max(2, v / mx * 100)}%" title="${fmtB(v, '0')}"></i>`).join("");
    } catch { }
  }

  // ---------------------------------------------------------------- clients
  let clients = [];
  $("#cl-search").oninput = () => renderClients();
  $("#btn-new").onclick = () => clientModal(null);
  async function loadClients(silent) { try { clients = (await api("clients")).clients; renderClients(); } catch (e) { if (!silent) toast(e.message, "bad"); } }
  const badge = s => ({ ONLINE: ["b-on", "🟢 آنلاین"], OFFLINE: ["b-off", "⚪ آفلاین"], EXPIRED: ["b-exp", "⏳ تمام شده"], DISABLED: ["b-dis", "⏸ غیرفعال"] }[s] || ["b-off", s]);
  function renderClients() {
    const q = $("#cl-search").value.trim().toLowerCase();
    const list = clients.filter(c => !q || c.name.toLowerCase().includes(q) || (c.note || "").toLowerCase().includes(q));
    $("#clients-list").innerHTML = list.map(c => {
      const [bc, bt] = badge(c.status); const hot = c.progress > 85;
      return `<article class="client" data-n="${esc(c.name)}">
        <div class="hd"><div class="nm">${esc(c.name)} ${c.noads ? '<span class="tag" title="NoAds">🛡</span>' : ""}${c.bypass_iran ? '<span class="tag" title="Bypass IR">IR</span>' : ""}</div><span class="badge ${bc}">${bt}</span></div>
        <div class="meta">
          <div>مصرف: <b>${esc(c.used)}</b> / ${esc(c.total)}</div><div>باقی: <b>${esc(c.remaining)}</b></div>
          <div>زمان: <b>${esc(c.rem_text)}</b></div><div>IP فعال: <b>${c.online_ips}</b>${c.ip_limit ? "/" + c.ip_limit : ""}</div>
          <div>⬇ <b>${esc(c.down_speed)}</b></div><div>⬆ <b>${esc(c.up_speed)}</b></div>
          ${c.note ? `<div style="grid-column:1/-1">📝 ${esc(c.note)}</div>` : ""}
        </div>
        <div class="bar"><i class="${hot ? "hot" : ""}" style="width:${c.progress}%"></i></div>
        <div class="acts">
          <button class="btn sm" data-a="links">🔗 لینک‌ها</button>
          <button class="btn sm pur" data-a="edit">✏️ ویرایش</button>
          <button class="btn sm ghost" data-a="hist">📜 تاریخچه</button>
          <button class="btn sm ${c.active ? "warn" : "ok"}" data-a="toggle">${c.active ? "⏸ توقف" : "▶ فعال"}</button>
          <button class="btn sm bad" data-a="del">🗑</button>
        </div></article>`;
    }).join("") || `<div class="empty">کانفیگی نیست. یکی بساز!</div>`;
  }
  $("#clients-list").onclick = async e => {
    const b = e.target.closest("button[data-a]"); if (!b) return; const name = b.closest(".client").dataset.n; const c = clients.find(x => x.name === name);
    const a = b.dataset.a;
    if (a === "links") return linksModal(c);
    if (a === "edit") return clientModal(c);
    if (a === "hist") { go("logs"); setLogsView("history"); return openHistory(name); }
    if (a === "toggle") { b.disabled = true; try { await api(`clients/${encodeURIComponent(name)}/toggle`, { method: "POST" }); toast("انجام شد", "ok"); } catch (err) { toast(err.message, "bad"); } return loadClients(); }
    if (a === "del") { if (!await confirm2(`حذف «${name}»؟`)) return; const purge = await confirm2("تاریخچه‌اش هم پاک شود؟ (خیر = تاریخچه بماند)"); try { await api(`clients/${encodeURIComponent(name)}`, { method: "DELETE", body: { purge_history: purge } }); toast("حذف شد", "ok"); } catch (err) { toast(err.message, "bad"); } return loadClients(); }
  };
  const volUnit = id => `<select class="in" id="${id}" style="flex:0 0 80px"><option>GB</option><option>MB</option></select>`;
  function clientModal(c) {
    const isNew = !c;
    const tot = isNew ? 0 : c.total_bytes; const totGB = tot ? +(tot / GB).toFixed(2) : "";
    const expD = isNew ? 30 : Math.floor(c.expire_seconds / 86400), expH = isNew ? 0 : Math.floor(c.expire_seconds % 86400 / 3600);
    const m = modal(`<h3>${isNew ? "➕ کانفیگ جدید" : "✏️ ویرایش " + esc(c.name)}</h3>
      <input class="in" id="f-name" placeholder="نام (انگلیسی، بدون فاصله)" value="${esc(isNew ? "" : c.name)}">
      <label class="chk"><input type="checkbox" id="f-unl" ${!isNew && !tot ? "checked" : ""}> حجم نامحدود</label>
      <div class="row"><input class="in" id="f-vol" type="number" step="0.1" min="0" placeholder="حجم کل" value="${isNew ? 50 : totGB}">${volUnit("f-volu")}</div>
      <div class="row" style="margin-top:8px"><input class="in" id="f-days" type="number" min="0" placeholder="روز" value="${expD}"><input class="in" id="f-hours" type="number" min="0" max="23" placeholder="ساعت" value="${expH}"></div>
      <input class="in" id="f-ip" placeholder="آی‌پی/دامنه تمیز (پیش‌فرض speed.cloudflare.com)" value="${esc(isNew ? "" : c.clean_ip)}" style="margin-top:8px;direction:ltr">
      <input class="in" id="f-note" placeholder="یادداشت (اختیاری)" value="${esc(isNew ? "" : c.note || "")}" style="margin-top:8px">
      <div class="row" style="margin-top:8px"><label class="chk"><input type="checkbox" id="f-noads" ${isNew || c.noads ? "checked" : ""}> NoAds</label><label class="chk"><input type="checkbox" id="f-byp" ${isNew || c.bypass_iran ? "checked" : ""}> بای‌پس ایران</label><input class="in" id="f-iplim" type="number" min="0" placeholder="حد IP (0=نامحدود)" value="${isNew ? 0 : c.ip_limit}"></div>
      ${isNew ? `<div class="sec"><h4>مصرف اولیه (اختیاری)</h4><div class="row"><input class="in" id="f-init" type="number" step="0.1" min="0" placeholder="0">${volUnit("f-initu")}</div></div>` : `
      <div class="sec"><h4>عملیات سریع</h4>
        <div class="row"><input class="in" id="f-add" type="number" step="0.1" placeholder="＋ افزودن حجم (منفی = کم کردن)">${volUnit("f-addu")}</div>
        <div class="row" style="margin-top:8px"><input class="in" id="f-adddays" type="number" placeholder="＋ افزودن روز"><input class="in" id="f-setused" type="number" step="0.01" min="0" placeholder="تنظیم مصرف‌شده">${volUnit("f-setusedu")}</div>
        <div class="row" style="margin-top:8px"><label class="chk"><input type="checkbox" id="f-reset"> صفر کردن مصرف</label><label class="chk"><input type="checkbox" id="f-rtime"> شروع زمان از الان</label><label class="chk"><input type="checkbox" id="f-uuid"> UUID جدید</label></div>
      </div>`}
      <div class="row" style="margin-top:14px"><button class="btn ok" id="f-save">${isNew ? "ایجاد" : "ذخیره"}</button><button class="btn ghost" id="f-cancel">انصراف</button></div>`);
    $("#f-unl", m).onchange = e => { $("#f-vol", m).disabled = e.target.checked; }; $("#f-unl", m).onchange({ target: $("#f-unl", m) });
    $("#f-cancel", m).onclick = closeModal;
    $("#f-save", m).onclick = async () => {
      const v = id => $("#" + id, m)?.value?.trim(); const chk = id => !!$("#" + id, m)?.checked;
      const body = { unlimited: chk("f-unl"), volume_value: v("f-vol") || 0, volume_unit: v("f-volu"), expire_days: v("f-days") || 0, expire_hours: v("f-hours") || 0,
        clean_ip: v("f-ip"), note: v("f-note"), noads: chk("f-noads"), bypass_iran: chk("f-byp"), ip_limit: v("f-iplim") || 0 };
      $("#f-save", m).disabled = true;
      try {
        if (isNew) { body.name = v("f-name"); body.initial_used_value = v("f-init") || 0; body.initial_used_unit = v("f-initu"); await api("clients", { method: "POST", body }); toast("ساخته شد ✓", "ok"); }
        else {
          if (v("f-name") && v("f-name") !== c.name) body.new_name = v("f-name");
          if (v("f-add")) { body.add_volume_value = v("f-add"); body.add_volume_unit = v("f-addu"); }
          if (v("f-adddays")) body.add_days = v("f-adddays");
          if (v("f-setused")) { body.set_used_value = v("f-setused"); body.set_used_unit = v("f-setusedu"); }
          body.reset_usage = chk("f-reset"); body.reset_time = chk("f-rtime"); body.regen_uuid = chk("f-uuid");
          await api(`clients/${encodeURIComponent(c.name)}`, { method: "PUT", body }); toast("ذخیره شد ✓", "ok");
        }
        closeModal(); loadClients();
      } catch (err) { toast(err.message, "bad"); $("#f-save", m).disabled = false; }
    };
  }
  async function linksModal(c) {
    let L; try { L = await api(`clients/${encodeURIComponent(c.name)}/links`); } catch (e) { return toast(e.message, "bad"); }
    const row = (t, v, hint) => v ? `<div class="sec"><h4>${t} ${hint ? `<span class="tag">${hint}</span>` : ""}</h4><div class="row"><input class="in mono" readonly value="${esc(v)}"><button class="btn sm ghost" data-c="${esc(v)}" style="flex:0">کپی</button></div></div>` : "";
    const m = modal(`<h3>🔗 لینک‌های ${esc(c.name)}</h3>
      ${row("ساب دائمی GitHub (پیشنهادی)", L.sub_github, "v2rayNG / Hiddify")}
      ${row("ساب Smart JSON — بالانسر + فرگمنت + NoAds + بای‌پس", L.sub_json_github || L.sub_json_live, "v2rayNG custom / Hiddify")}
      ${row("ساب sing-box", L.sub_singbox_github || L.sub_singbox_live, "sing-box / Hiddify / NekoBox")}
      ${row("ساب زنده (موقت تا پایان ران)", L.sub_live)}
      ${row("کانفیگ تکی Clean", L.config)}
      ${row("کانفیگ تکی Direct", L.direct)}
      <button class="btn ghost full" id="l-close" style="margin-top:12px">بستن</button>`);
    m.onclick = e => { const b = e.target.closest("button[data-c]"); if (b) copy(b.dataset.c); }; $("#l-close", m).onclick = closeModal;
  }

  // ---------------------------------------------------------------- logs / history
  let logsView = "history", histName = null, histIp = null;
  $("#logs-seg").onclick = e => { const b = e.target.closest("button[data-v]"); if (b) setLogsView(b.dataset.v); };
  function setLogsView(v) { logsView = v; $$("#logs-seg button").forEach(b => b.classList.toggle("active", b.dataset.v === v)); ["history", "events", "live"].forEach(k => $("#logs-" + k).classList.toggle("hidden", k !== v)); loadLogs(); }
  async function loadLogs() {
    if (logsView === "history") {
      if (!clients.length) { try { clients = (await api("clients")).clients; } catch { } }
      $("#hist-clients").innerHTML = clients.map(c => `<div class="item ${histName === c.name ? "sel" : ""}" data-n="${esc(c.name)}"><span>${esc(c.name)}</span><small>${esc(c.used)} · ${c.online_ips} IP</small></div>`).join("") || `<div class="empty">کانفیگی نیست</div>`;
      if (histName) openHistory(histName, true);
      return;
    }
    let d; try { d = await api("logs?limit=300"); } catch { return; }
    if (logsView === "events") {
      $("#ev-log").innerHTML = d.events.map(e => `<div class="${esc(e.level)} ${esc(e.kind)}"><time>${dt(e.ts)}</time>[${esc(e.kind)}] ${esc(e.message)}</div>`).join("") || `<div class="empty">خالی</div>`;
    } else {
      $("#live-log").innerHTML = d.recent_visits.map(v => `<div class="${v.blocked ? "error" : ""}"><time>${dt(v.last_seen)}</time>${esc(v.client)} <span style="color:#5b6678">${esc(v.ip)}</span> → ${esc(v.host)}:${v.port} ${v.blocked ? "⛔" : ""}</div>`).join("") || `<div class="empty">هنوز ترافیکی نیست</div>`;
    }
  }
  $("#hist-clients").onclick = e => { const it = e.target.closest(".item[data-n]"); if (it) openHistory(it.dataset.n); };
  async function openHistory(name, keepIp) {
    histName = name; if (!keepIp) histIp = null;
    $$("#hist-clients .item").forEach(i => i.classList.toggle("sel", i.dataset.n === name));
    let h; try { h = await api(`history/${encodeURIComponent(name)}`); } catch (e) { return toast(e.message, "bad"); }
    $("#hist-ips-card").classList.remove("hidden");
    $("#hist-title").textContent = `${name} — ${h.ips.length} آی‌پی · ${h.summary.hosts} دامنه · ${h.summary.hits} اتصال · ${h.summary.blocked} مسدود`;
    const live = h.live_ips || {};
    $("#hist-ips").innerHTML = h.ips.map(r => `<div class="item ${histIp === r.ip ? "sel" : ""}" data-ip="${esc(r.ip)}"><span class="mono">${esc(r.ip)} ${live[r.ip] ? '<span class="tag" style="color:#4ade80">live</span>' : ""}</span><small>${r.hits} اتصال · ${ago(r.last_seen)}</small></div>`).join("") || `<div class="empty">هنوز اتصالی ثبت نشده</div>`;
    if (histIp) loadVisits(); else $("#hist-visits-card").classList.add("hidden");
  }
  $("#hist-ips").onclick = e => { const it = e.target.closest(".item[data-ip]"); if (!it) return; histIp = it.dataset.ip; $$("#hist-ips .item").forEach(i => i.classList.toggle("sel", i.dataset.ip === histIp)); loadVisits(); };
  let hq; $("#hist-q").oninput = () => { clearTimeout(hq); hq = setTimeout(loadVisits, 250); };
  async function loadVisits() {
    if (!histName || !histIp) return;
    const q = $("#hist-q").value.trim();
    let d; try { d = await api(`history/${encodeURIComponent(histName)}/visits?ip=${encodeURIComponent(histIp)}&q=${encodeURIComponent(q)}&limit=600`); } catch { return; }
    $("#hist-visits-card").classList.remove("hidden");
    $("#hist-visits-title").textContent = `سایت‌های ${histIp} (${d.visits.length})`;
    $("#hist-visits").innerHTML = d.visits.map(v => `<div class="item" style="cursor:default"><span class="mono">${v.blocked ? "⛔ " : ""}${esc(v.host)}<small>:${v.port}</small></span><small>${v.hits}× · ${ago(v.last_seen)}</small></div>`).join("") || `<div class="empty">چیزی پیدا نشد</div>`;
  }
  $("#hist-export").onclick = () => { if (histName) window.open(`${P}/api/history/${encodeURIComponent(histName)}/export`, "_blank"); };
  $("#ev-refresh").onclick = loadLogs;

  // ---------------------------------------------------------------- noads
  let noadsLevel = "balanced";
  $("#noads-level").onclick = e => { const b = e.target.closest("button[data-v]"); if (!b) return; noadsLevel = b.dataset.v; $$("#noads-level button").forEach(x => x.classList.toggle("active", x.dataset.v === noadsLevel)); };
  async function loadNoads() {
    let d; try { d = await api("noads"); } catch { return; }
    noadsLevel = d.level; $$("#noads-level button").forEach(x => x.classList.toggle("active", x.dataset.v === d.level));
    $("#noads-iran").checked = !!d.block_iran_ads;
    $("#noads-block").value = (d.custom_block || []).join("\n"); $("#noads-white").value = (d.whitelist || []).join("\n");
    $("#noads-stats").innerHTML = [["دامنه‌های فعال", d.curated_domains, "+ geosite:category-ads-all"], ["یوتیوب/گوگل", d.youtube_domains, ""], ["جهانی", d.global_domains, ""], ["ایرانی", d.iran_domains, ""], ["الگوی هوشمند", d.heuristic_patterns, ""], ["مسدود ۲۴h", d.blocked_24h?.blocked ?? 0, `از ${d.blocked_24h?.total ?? 0}`]]
      .map(([l, v, s]) => `<div class="stat"><div class="l">${l}</div><div class="v">${esc(v)}</div><div class="s">${esc(s)}</div></div>`).join("");
    $("#noads-top").innerHTML = (d.top_blocked || []).map(r => `<div class="item"><span class="mono">${esc(r.host)}</span><small>${r.hits}</small></div>`).join("") || `<div class="empty">هنوز چیزی مسدود نشده</div>`;
  }
  $("#noads-save").onclick = async () => { try { await api("noads", { method: "PUT", body: { level: noadsLevel, block_iran_ads: $("#noads-iran").checked, custom_block: $("#noads-block").value, whitelist: $("#noads-white").value } }); toast("اعمال شد ✓", "ok"); loadNoads(); } catch (e) { toast(e.message, "bad"); } };
  $("#noads-test").onclick = async () => { const t = $("#noads-test-in").value.trim(); if (!t) return; try { const d = await api("noads", { method: "PUT", body: { test: t } }); $("#noads-test-out").innerHTML = Object.entries(d.test_result || {}).map(([h, b]) => `<div class="item" style="cursor:default"><span class="mono">${esc(h)}</span><small>${b ? "⛔ مسدود" : "✅ آزاد"}</small></div>`).join(""); } catch (e) { toast(e.message, "bad"); } };

  // ---------------------------------------------------------------- bypass
  let bypMode = "direct";
  $("#bypass-mode").onclick = e => { const b = e.target.closest("button[data-v]"); if (!b) return; bypMode = b.dataset.v; $$("#bypass-mode button").forEach(x => x.classList.toggle("active", x.dataset.v === bypMode)); };
  async function loadBypass() {
    let d; try { d = await api("bypass"); } catch { return; }
    bypMode = d.iran_mode; $$("#bypass-mode button").forEach(x => x.classList.toggle("active", x.dataset.v === d.iran_mode));
    $("#bypass-core").textContent = d.core_iran_domains; $("#bypass-direct").value = (d.custom_direct || []).join("\n"); $("#bypass-proxy").value = (d.custom_proxy || []).join("\n");
  }
  $("#bypass-save").onclick = async () => { try { await api("bypass", { method: "PUT", body: { iran_mode: bypMode, custom_direct: $("#bypass-direct").value, custom_proxy: $("#bypass-proxy").value } }); toast("اعمال شد ✓", "ok"); loadBypass(); } catch (e) { toast(e.message, "bad"); } };
  $("#bypass-test").onclick = async () => { const t = $("#bypass-test-in").value.trim(); if (!t) return; try { const d = await api("bypass", { method: "PUT", body: { test: t } }); $("#bypass-test-out").innerHTML = Object.entries(d.test_result || {}).map(([h, b]) => `<div class="item" style="cursor:default"><span class="mono">${esc(h)}</span><small>${b ? "🇮🇷 مستقیم" : "🌐 از VPN"}</small></div>`).join(""); } catch (e) { toast(e.message, "bad"); } };

  // ---------------------------------------------------------------- settings
  async function loadSettings() {
    let d; try { d = await api("settings"); } catch { return; }
    $("#set-pool").value = (d.clean_pool || []).join("\n");
    const kv = [["آدرس تانل", d.tunnel_host], ["ریپو", d.repo || "—"], ["کلید رمزنگاری", d.vault_key_id], ["کاربر پنل", d.panel_user], ["محدودیت ورود", `${d.login_max_attempts} تلاش / قفل ${Math.round(d.lock_seconds / 60)} دقیقه`], ["رمز", d.generated_password ? "موقت (سکرت تنظیم نشده!)" : "از سکرت PANEL_PASS"], ["مدت هر ران", dur(d.run_duration)]];
    $("#set-info").innerHTML = kv.map(([k, v]) => `<div class="kv"><span>${k}</span><span>${esc(v)}</span></div>`).join("");
  }
  $("#set-save").onclick = async () => { try { await api("settings", { method: "PUT", body: { clean_pool: $("#set-pool").value } }); toast("ذخیره شد ✓", "ok"); } catch (e) { toast(e.message, "bad"); } };

  // clean-IP scanner (browser side, no backend load)
  $("#scan-btn").onclick = async () => {
    const btn = $("#scan-btn"), out = $("#scan-out"), st = $("#scan-status"); btn.disabled = true; out.value = "";
    const subnets = ["104.16.", "104.17.", "104.18.", "104.19.", "104.21.", "172.64.", "172.67.", "162.159.", "188.114.96.", "188.114.97."];
    const ips = []; subnets.forEach(s => { for (let i = 0; i < 6; i++) { const a = s.split(".").length === 3 ? s + (Math.floor(Math.random() * 250) + 2) : s + Math.floor(Math.random() * 254) + "." + (Math.floor(Math.random() * 250) + 2); ips.push(a); } });
    const results = []; let done = 0;
    const test = async ip => { const t0 = performance.now(); try { const c = new AbortController(); const to = setTimeout(() => c.abort(), 1500); await fetch(`https://${ip}/cdn-cgi/trace`, { mode: "no-cors", cache: "no-store", signal: c.signal }); clearTimeout(to); results.push([ip, Math.round(performance.now() - t0)]); } catch { } done++; st.textContent = `${done}/${ips.length}`; };
    for (let i = 0; i < ips.length; i += 8) await Promise.all(ips.slice(i, i + 8).map(test));
    results.sort((a, b) => a[1] - b[1]); out.value = results.map(([ip, ms]) => `${ip}  ${ms}ms`).join("\n") || "هیچ آی‌پی پاسخ نداد";
    st.textContent = `✅ ${results.length} آی‌پی فعال`; btn.disabled = false;
  };

  // ---------------------------------------------------------------- boot
  api("ping").then(d => d.authed ? showApp() : showLogin()).catch(showLogin);
})();
