/* UI for the runner service (no build step). */

const $ = (id) => document.getElementById(id);

const els = {
  statusPill: $("statusPill"),
  statusLed: $("statusLed"),
  statusText: $("statusText"),
  jsonOut: $("jsonOut"),
  logOut: $("logOut"),
  videoId: $("videoId"),

  btnRefresh: $("btnRefresh"),
  btnCopy: $("btnCopy"),
  btnClear: $("btnClear"),

  btnDiscover: $("btnDiscover"),
  btnReport: $("btnReport"),
  btnFull: $("btnFull"),

  btnIngest: $("btnIngest"),
  btnScript: $("btnScript"),
  btnVoice: $("btnVoice"),
  btnRender: $("btnRender"),
  btnThumb: $("btnThumb"),
  btnUpload: $("btnUpload"),

  btnVerifyVoice: $("btnVerifyVoice"),
  btnVerifyTranslate: $("btnVerifyTranslate"),
  btnVerifyZthumb: $("btnVerifyZthumb"),
  btnConfig: $("btnConfig"),
};

const btns = [
  els.btnRefresh,
  els.btnCopy,
  els.btnClear,
  els.btnDiscover,
  els.btnReport,
  els.btnFull,
  els.btnIngest,
  els.btnScript,
  els.btnVoice,
  els.btnRender,
  els.btnThumb,
  els.btnUpload,
  els.btnVerifyVoice,
  els.btnVerifyTranslate,
  els.btnVerifyZthumb,
  els.btnConfig,
].filter(Boolean);

function ts() {
  const d = new Date();
  return d.toLocaleTimeString([], { hour12: false });
}

function log(tag, msg) {
  const line = document.createElement("div");
  line.className = "logline";
  line.innerHTML = `<div class="time">${ts()}</div><div class="tag">${escapeHtml(tag)}</div><div class="msg">${escapeHtml(msg)}</div>`;
  els.logOut.prepend(line);
}

function setStatus(kind, text) {
  els.statusText.textContent = text;
  const led = els.statusLed;
  let bg = "rgba(20,19,26,0.20)";
  if (kind === "working") bg = "rgba(14,165,164,0.95)";
  if (kind === "ok") bg = "rgba(18,185,129,0.95)";
  if (kind === "warn") bg = "rgba(249,115,22,0.95)";
  if (kind === "err") bg = "rgba(239,68,68,0.95)";
  led.style.background = bg;
}

function setBusy(busy) {
  for (const b of btns) b.disabled = !!busy;
}

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }

  const res = await fetch(path, opts);
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.data = data;
    throw err;
  }
  return data;
}

function getVideoIdRequired() {
  const v = (els.videoId.value || "").trim();
  if (!v) throw new Error("Missing video ID");
  return v;
}

async function run(tag, fn) {
  setBusy(true);
  setStatus("working", tag);
  log(tag, "starting…");
  try {
    const out = await fn();
    els.jsonOut.textContent = pretty(out);
    setStatus("ok", tag + ": OK");
    log(tag, "ok");
    return out;
  } catch (e) {
    const payload = e?.data ? e.data : { error: String(e) };
    els.jsonOut.textContent = pretty(payload);
    setStatus("err", tag + ": ERROR");
    log(tag, payload?.detail ? payload.detail : String(e));
  } finally {
    setBusy(false);
  }
}

async function refresh() {
  await run("refresh", async () => {
    const health = await api("GET", "/health");
    const cfg = await api("GET", "/api/config");
    return { health, config: cfg };
  });
}

function wire() {
  els.btnRefresh?.addEventListener("click", refresh);

  els.btnClear?.addEventListener("click", () => {
    els.jsonOut.textContent = "{}";
    setStatus("idle", "Idle");
    log("ui", "cleared output");
  });

  els.btnCopy?.addEventListener("click", async () => {
    const txt = els.jsonOut.textContent || "{}";
    try {
      await navigator.clipboard.writeText(txt);
      log("ui", "copied JSON");
      setStatus("ok", "Copied");
      setTimeout(() => setStatus("idle", "Idle"), 700);
    } catch {
      log("ui", "clipboard copy failed (browser permissions)");
      setStatus("warn", "Copy failed");
      setTimeout(() => setStatus("idle", "Idle"), 900);
    }
  });

  els.btnDiscover?.addEventListener("click", () =>
    run("discover", () => api("POST", "/api/discover", {}))
  );

  els.btnReport?.addEventListener("click", () =>
    run("report", () => api("GET", "/api/report/daily"))
  );

  els.btnIngest?.addEventListener("click", () =>
    run("ingest", () => api("POST", `/api/ingest/${encodeURIComponent(getVideoIdRequired())}`))
  );
  els.btnScript?.addEventListener("click", () =>
    run("script", () => api("POST", `/api/script/${encodeURIComponent(getVideoIdRequired())}`))
  );
  els.btnVoice?.addEventListener("click", () =>
    run("voice", () => api("POST", `/api/voice/${encodeURIComponent(getVideoIdRequired())}`))
  );
  els.btnRender?.addEventListener("click", () =>
    run("render", () => api("POST", `/api/render/${encodeURIComponent(getVideoIdRequired())}`))
  );
  els.btnThumb?.addEventListener("click", () =>
    run("thumbnail", () => api("POST", `/api/thumbnail/${encodeURIComponent(getVideoIdRequired())}`))
  );
  els.btnUpload?.addEventListener("click", () =>
    run("upload", () => api("POST", `/api/upload/${encodeURIComponent(getVideoIdRequired())}`))
  );

  els.btnFull?.addEventListener("click", () =>
    run("pipeline", async () => {
      const v = (els.videoId.value || "").trim();
      const body = v ? { video_id: v, auto_select: false } : { auto_select: true };
      return api("POST", "/api/pipeline/full", body);
    })
  );

  els.btnVerifyVoice?.addEventListener("click", () =>
    run("verify_voice", () => api("GET", "/api/verify/voice"))
  );
  els.btnVerifyTranslate?.addEventListener("click", () =>
    run("verify_translate", () => api("GET", "/api/verify/translate"))
  );
  els.btnVerifyZthumb?.addEventListener("click", () =>
    run("verify_zthumb", () => api("GET", "/api/verify/zthumb"))
  );
  els.btnConfig?.addEventListener("click", () =>
    run("config", () => api("GET", "/api/config"))
  );
}

setStatus("idle", "Idle");
wire();
refresh().catch(() => {});

