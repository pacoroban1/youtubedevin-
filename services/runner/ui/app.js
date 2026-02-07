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
  btnJobsRefresh: $("btnJobsRefresh"),

  btnDiscover: $("btnDiscover"),
  btnReport: $("btnReport"),
  btnFull: $("btnFull"),
  btnCancelJob: $("btnCancelJob"),

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

  jobsList: $("jobsList"),
  jobDetailEmpty: $("jobDetailEmpty"),
  jobDetailBody: $("jobDetailBody"),
  jobTitle: $("jobTitle"),
  jobMeta: $("jobMeta"),
  jobBar: $("jobBar"),
  jobPct: $("jobPct"),
  jobHint: $("jobHint"),
  jobSteps: $("jobSteps"),
  jobEvents: $("jobEvents"),
};

const btns = [
  els.btnRefresh,
  els.btnCopy,
  els.btnClear,
  els.btnJobsRefresh,
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

const PIPELINE_STEPS = [
  "discover",
  "ingest",
  "script",
  "voice",
  "render",
  "thumbnail",
  "upload",
  "distribute",
];

let currentJobId = null;
let currentJobStatus = null;
let jobPollInFlight = false;

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

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
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

function jobLabel(job) {
  const st = (job?.status || "").toLowerCase();
  const step = job?.current_step ? ` · ${job.current_step}` : "";
  return `${job?.job_type || "job"}${step} (${st || "unknown"})`;
}

function setPipelineRunning(running) {
  if (els.btnFull) els.btnFull.disabled = !!running;
  if (els.btnCancelJob) els.btnCancelJob.disabled = !running;
}

function shortId(id) {
  const s = String(id || "");
  return s.length > 8 ? s.slice(0, 8) : s;
}

function badgeKindForStatus(st) {
  const s = String(st || "").toLowerCase();
  if (s === "succeeded") return "ok";
  if (s === "failed") return "err";
  if (s === "canceled" || s === "cancel_requested") return "warn";
  if (s === "queued" || s === "running") return "work";
  return "idle";
}

function stepClassForStatus(st) {
  const s = String(st || "").toLowerCase();
  if (s === "ok") return "step--ok";
  if (s === "error") return "step--err";
  if (s === "skipped") return "step--skip";
  if (s === "running") return "step--work";
  if (s === "pending" || s === "") return "";
  return "";
}

function statusKindForJob(job) {
  const st = (job?.status || "").toLowerCase();
  if (st === "succeeded") return "ok";
  if (st === "failed") return "err";
  if (st === "canceled" || st === "cancel_requested") return "warn";
  if (st === "queued" || st === "running") return "working";
  return "idle";
}

function renderJobsList(jobs) {
  if (!els.jobsList) return;
  const root = els.jobsList;
  root.innerHTML = "";

  if (!jobs || jobs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "jobs__empty";
    empty.textContent = "No jobs yet.";
    root.appendChild(empty);
    return;
  }

  for (const j of jobs) {
    const st = String(j?.status || "").toLowerCase();
    const kind = badgeKindForStatus(st);
    const active = currentJobId && j.id === currentJobId;

    const item = document.createElement("div");
    item.className = `jobitem${active ? " jobitem--active" : ""}`;
    item.addEventListener("click", () => selectJob(j.id, { pollIfRunning: true }));

    const left = document.createElement("div");
    left.className = "jobitem__left";

    const top = document.createElement("div");
    top.className = "jobitem__top";
    top.innerHTML = `<span class="jobitem__id">${escapeHtml(shortId(j.id))}</span><span class="jobitem__type">${escapeHtml(j.job_type || "job")}</span>`;
    left.appendChild(top);

    const meta = document.createElement("div");
    meta.className = "jobitem__meta";
    const vid = j.video_id ? `video=${j.video_id}` : "no video_id yet";
    meta.textContent = `${vid}${j.updated_at ? ` · updated ${j.updated_at}` : ""}`;
    left.appendChild(meta);

    const badge = document.createElement("div");
    badge.className = `badge badge--${kind}`;
    badge.textContent = st || "unknown";

    item.appendChild(left);
    item.appendChild(badge);
    root.appendChild(item);
  }
}

function renderJobDetail(job) {
  if (!els.jobDetailEmpty || !els.jobDetailBody) return;

  if (!job) {
    els.jobDetailEmpty.hidden = false;
    els.jobDetailBody.hidden = true;
    currentJobStatus = null;
    setPipelineRunning(false);
    return;
  }

  els.jobDetailEmpty.hidden = true;
  els.jobDetailBody.hidden = false;

  currentJobStatus = String(job.status || "").toLowerCase();
  setPipelineRunning(["queued", "running", "cancel_requested"].includes(currentJobStatus));

  const title = `${job.job_type || "job"} · ${shortId(job.id)} · ${currentJobStatus || "unknown"}`;
  if (els.jobTitle) els.jobTitle.textContent = title;

  const parts = [];
  if (job.video_id) parts.push(`video_id=${job.video_id}`);
  if (job.current_step) parts.push(`step=${job.current_step}`);
  if (job.updated_at) parts.push(`updated=${job.updated_at}`);
  if (els.jobMeta) els.jobMeta.textContent = parts.join(" · ");

  const pct = Math.max(0, Math.min(1, Number(job.progress || 0))) * 100;
  if (els.jobBar) els.jobBar.style.width = `${pct.toFixed(0)}%`;
  if (els.jobPct) els.jobPct.textContent = `${pct.toFixed(0)}%`;
  if (els.jobHint) els.jobHint.textContent = job.current_step ? `Running: ${job.current_step}` : "";

  // Steps
  if (els.jobSteps) {
    els.jobSteps.innerHTML = "";
    const steps = job.steps || {};
    for (const name of PIPELINE_STEPS) {
      const st = (steps?.[name]?.status || "").toLowerCase();
      const cls = stepClassForStatus(st);
      const el = document.createElement("div");
      el.className = `step ${cls}`.trim();
      el.innerHTML = `<span class="step__dot"></span>${escapeHtml(name)}${st ? `: ${escapeHtml(st)}` : ""}`;
      els.jobSteps.appendChild(el);
    }
  }

  // Events
  if (els.jobEvents) {
    els.jobEvents.innerHTML = "";
    const events = Array.isArray(job.events) ? job.events.slice() : [];
    events.reverse(); // most recent first
    for (const ev of events.slice(0, 16)) {
      const line = document.createElement("div");
      line.className = "eventline";
      const lvl = String(ev?.level || "info").toUpperCase();
      line.innerHTML = `<div class="eventline__ts">${escapeHtml(ev?.ts || "")}</div><div class="eventline__lvl">${escapeHtml(lvl)}</div><div class="eventline__msg">${escapeHtml(ev?.msg || "")}</div>`;
      els.jobEvents.appendChild(line);
    }
    if (events.length === 0) {
      const empty = document.createElement("div");
      empty.className = "jobs__empty";
      empty.textContent = "No events yet.";
      els.jobEvents.appendChild(empty);
    }
  }
}

async function fetchJobs() {
  const wrap = await api("GET", "/api/jobs?limit=20");
  return wrap?.jobs || [];
}

async function refreshJobs() {
  try {
    const jobs = await fetchJobs();
    renderJobsList(jobs);

    if (!currentJobId && jobs.length > 0) {
      const active = jobs.find((j) => ["queued", "running", "cancel_requested"].includes(String(j.status || "").toLowerCase()));
      const pick = active || jobs[0];
      if (pick) {
        await selectJob(pick.id, { pollIfRunning: true, silent: true });
      }
    }
    return jobs;
  } catch (e) {
    const payload = e?.data ? e.data : { error: String(e) };
    log("jobs", payload?.detail ? payload.detail : String(e));
    if (els.jobsList) {
      els.jobsList.innerHTML = `<div class="jobs__empty">Jobs list unavailable.</div>`;
    }
    return [];
  }
}

async function selectJob(jobId, opts = {}) {
  const { pollIfRunning = false, silent = false } = opts;
  if (!jobId) return;
  currentJobId = jobId;
  if (!silent) {
    setStatus("working", `job: ${shortId(jobId)}`);
    log("job", `loading: ${jobId}`);
  }

  const wrap = await api("GET", `/api/jobs/${encodeURIComponent(jobId)}`);
  const job = wrap?.job || null;
  renderJobDetail(job);
  els.jsonOut.textContent = pretty(wrap);

  // Refresh list highlighting.
  refreshJobs().catch(() => {});

  const st = String(job?.status || "").toLowerCase();
  if (pollIfRunning && ["queued", "running", "cancel_requested"].includes(st)) {
    pollJob(jobId);
  }
}

async function pollJob(jobId) {
  if (jobPollInFlight) return;
  jobPollInFlight = true;

  try {
    while (currentJobId === jobId) {
      const wrap = await api("GET", `/api/jobs/${encodeURIComponent(jobId)}`);
      const job = wrap?.job || {};
      els.jsonOut.textContent = pretty(wrap);
      renderJobDetail(job);

      const kind = statusKindForJob(job);
      setStatus(kind, jobLabel(job));

      const st = (job?.status || "").toLowerCase();
      if (["succeeded", "failed", "canceled"].includes(st)) {
        log("job", `finished: ${jobId} (${st})`);
        setPipelineRunning(false);
        refreshJobs().catch(() => {});
        break;
      }

      await sleep(1500);
    }
  } catch (e) {
    const payload = e?.data ? e.data : { error: String(e) };
    els.jsonOut.textContent = pretty(payload);
    setStatus("err", "job poll: ERROR");
    log("job", payload?.detail ? payload.detail : String(e));
    setPipelineRunning(false);
  } finally {
    jobPollInFlight = false;
  }
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
    const jobs = await refreshJobs();
    return { health, config: cfg, jobs: { count: jobs.length } };
  });
}

function wire() {
  els.btnRefresh?.addEventListener("click", refresh);
  els.btnJobsRefresh?.addEventListener("click", () => refreshJobs().catch(() => {}));

  els.btnClear?.addEventListener("click", () => {
    els.jsonOut.textContent = "{}";
    setStatus("idle", "Idle");
    log("ui", "cleared output");
    renderJobDetail(null);
    currentJobId = null;
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

  els.btnFull?.addEventListener("click", async () => {
    const jobs = await refreshJobs();
    const active = jobs.find((j) => ["queued", "running", "cancel_requested"].includes(String(j.status || "").toLowerCase()));
    if (active) {
      log("pipeline", `job already running: ${active.id}`);
      await selectJob(active.id, { pollIfRunning: true });
      return;
    }
    const v = (els.videoId.value || "").trim();
    const body = v ? { video_id: v, auto_select: false } : { auto_select: true };

    setPipelineRunning(true);
    setStatus("working", "pipeline: creating job");
    log("pipeline", "creating job…");

    try {
      const wrap = await api("POST", "/api/jobs/pipeline/full", body);
      const job = wrap?.job || {};
      currentJobId = job.id;
      els.jsonOut.textContent = pretty(wrap);
      renderJobDetail(job);
      log("pipeline", `started job: ${currentJobId}`);
      refreshJobs().catch(() => {});
      pollJob(currentJobId);
    } catch (e) {
      const payload = e?.data ? e.data : { error: String(e) };
      els.jsonOut.textContent = pretty(payload);
      setStatus("err", "pipeline: ERROR");
      log("pipeline", payload?.detail ? payload.detail : String(e));
      setPipelineRunning(false);
    }
  });

  els.btnCancelJob?.addEventListener("click", async () => {
    if (!currentJobId) return;
    const id = currentJobId;
    setStatus("warn", "cancel requested");
    log("pipeline", `cancel requested: ${id}`);
    try {
      await api("POST", `/api/jobs/${encodeURIComponent(id)}/cancel`);
      refreshJobs().catch(() => {});
    } catch (e) {
      const payload = e?.data ? e.data : { error: String(e) };
      els.jsonOut.textContent = pretty(payload);
      setStatus("err", "cancel: ERROR");
      log("pipeline", payload?.detail ? payload.detail : String(e));
    }
  });

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
