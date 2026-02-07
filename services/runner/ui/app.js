/* UI for the runner service (no build step). */

const $ = (id) => document.getElementById(id);

const els = {
  statusPill: $("statusPill"),
  statusLed: $("statusLed"),
  statusText: $("statusText"),
  jsonOut: $("jsonOut"),
  logOut: $("logOut"),
  videoId: $("videoId"),
  engineNotes: $("engineNotes"),

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

  artifactMeta: $("artifactMeta"),
  thumbGrid: $("thumbGrid"),
  thumbHero: $("thumbHero"),
  thumbHeroImg: $("thumbHeroImg"),
  thumbHeroMeta: $("thumbHeroMeta"),
  audioEl: $("audioEl"),
  audioLink: $("audioLink"),
  audioMeta: $("audioMeta"),
  waveCanvas: $("waveCanvas"),

  scriptHook: $("scriptHook"),
  scriptMeta: $("scriptMeta"),
  btnCopyHook: $("btnCopyHook"),

  btnSafe: $("btnSafe"),
  btnDownloadThumb: $("btnDownloadThumb"),

  cmdk: $("cmdk"),
  cmdkBackdrop: $("cmdkBackdrop"),
  cmdkInput: $("cmdkInput"),
  cmdkList: $("cmdkList"),

  pipelineViz: $("pipelineViz"),
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
let selectedThumbUrl = null;
let lastHookText = "";
let safeAreaOn = false;
let waveformUrl = null;

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
  let bg = "rgba(246,246,249,0.20)";
  if (kind === "working") bg = "rgba(34,211,238,0.95)";
  if (kind === "ok") bg = "rgba(163,255,18,0.95)";
  if (kind === "warn") bg = "rgba(251,191,36,0.95)";
  if (kind === "err") bg = "rgba(251,113,133,0.95)";
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

function firstDefined(...vals) {
  for (const v of vals) if (v !== undefined && v !== null && v !== "") return v;
  return undefined;
}

function normalizeMediaUrl(pathOrUrl) {
  if (!pathOrUrl) return null;
  const s = String(pathOrUrl);
  if (s.startsWith("http://") || s.startsWith("https://") || s.startsWith("/")) return s;
  const idx = s.indexOf("/app/media/");
  if (idx >= 0) return "/api/media/" + s.slice(idx + "/app/media/".length);
  return null;
}

function clearArtifacts() {
  selectedThumbUrl = null;
  lastHookText = "";
  if (els.thumbGrid) els.thumbGrid.innerHTML = `<div class="thumbs__empty">Generate thumbnails to see previews here.</div>`;
  if (els.thumbHero) els.thumbHero.hidden = true;
  if (els.thumbHero) els.thumbHero.classList.remove("thumbhero--guides");
  if (els.thumbHeroImg) els.thumbHeroImg.removeAttribute("src");
  if (els.thumbHeroMeta) els.thumbHeroMeta.textContent = "";
  if (els.audioEl) els.audioEl.removeAttribute("src");
  if (els.waveCanvas) {
    const ctx = els.waveCanvas.getContext("2d");
    if (ctx) {
      ctx.clearRect(0, 0, els.waveCanvas.width, els.waveCanvas.height);
    }
  }
  waveformUrl = null;
  if (els.audioLink) {
    els.audioLink.hidden = true;
    els.audioLink.href = "#";
  }
  if (els.audioMeta) els.audioMeta.textContent = "Generate voice to preview audio.";
  if (els.scriptHook) els.scriptHook.textContent = "Generate script to preview the hook here.";
  if (els.scriptMeta) els.scriptMeta.textContent = "Waiting…";
  if (els.artifactMeta) els.artifactMeta.textContent = "Waiting for output…";
}

function setSelectedThumb(url, metaText) {
  selectedThumbUrl = url || null;
  if (!els.thumbHero || !els.thumbHeroImg || !els.thumbHeroMeta) return;
  if (!url) {
    els.thumbHero.hidden = true;
    els.thumbHeroImg.removeAttribute("src");
    els.thumbHeroMeta.textContent = "";
    if (els.btnDownloadThumb) els.btnDownloadThumb.disabled = true;
    return;
  }
  els.thumbHero.hidden = false;
  els.thumbHeroImg.src = url;
  els.thumbHeroMeta.textContent = metaText || "Selected thumbnail";
  if (els.btnDownloadThumb) els.btnDownloadThumb.disabled = false;
}

function renderArtifacts(payload) {
  if (!payload || typeof payload !== "object") return;

  // Script preview (hook)
  const hook = firstDefined(payload.hook_text, payload.hook, payload.script_preview);
  if (hook && els.scriptHook) {
    lastHookText = String(hook);
    els.scriptHook.textContent = lastHookText;
  }
  if (els.scriptMeta) {
    const beats = Array.isArray(payload.beats) ? payload.beats.length : payload.segments_count;
    const qs = payload.quality_score ? `q=${Number(payload.quality_score).toFixed(2)}` : "";
    const parts = [];
    if (beats !== undefined) parts.push(`beats=${beats}`);
    if (qs) parts.push(qs);
    if (payload.persona) parts.push(String(payload.persona));
    els.scriptMeta.textContent = parts.length ? parts.join(" • ") : (els.scriptMeta.textContent || "Waiting…");
  }

  // Thumbnails grid + hero
  const images = payload.images || payload.thumbnails;
  if (Array.isArray(images) && images.length && els.thumbGrid) {
    els.thumbGrid.innerHTML = "";

    const bestIdx = Number.isFinite(Number(payload.best_pick_index)) ? Number(payload.best_pick_index) : null;
    let firstUrl = null;
    let firstMeta = null;

    images.forEach((img, idx) => {
      const url = firstDefined(img?.url, normalizeMediaUrl(img?.path));
      if (!url) return;
      const score = img?.score;
      const badge = idx === bestIdx ? "best" : `#${idx + 1}`;
      const meta = `#${idx + 1}${typeof score === "number" ? ` • score=${score.toFixed(2)}` : ""}`;

      if (!firstUrl) {
        firstUrl = url;
        firstMeta = meta;
      }

      const a = document.createElement("a");
      a.className = `thumb${selectedThumbUrl === url ? " thumb--selected" : ""}`;
      a.href = url;
      a.target = "_blank";
      a.rel = "noreferrer";
      a.innerHTML = `
        <span class="thumb__badge">${escapeHtml(badge)}</span>
        <img alt="thumbnail" src="${escapeHtml(url)}" loading="lazy" />
      `;
      a.addEventListener("click", (ev) => {
        // Default click selects; Cmd/Ctrl-click opens.
        if (!ev.metaKey && !ev.ctrlKey) {
          ev.preventDefault();
          setSelectedThumb(url, meta);
          // Update selection styling without re-rendering.
          for (const el of els.thumbGrid.querySelectorAll(".thumb")) el.classList.remove("thumb--selected");
          a.classList.add("thumb--selected");
        }
      });
      els.thumbGrid.appendChild(a);
    });

    // Ensure hero shows something.
    if (!selectedThumbUrl && firstUrl) setSelectedThumb(firstUrl, firstMeta);
    if (selectedThumbUrl && els.thumbHero && els.thumbHero.hidden) setSelectedThumb(selectedThumbUrl, firstMeta);
  }

  const audioUrl = firstDefined(payload.audio_url, normalizeMediaUrl(payload.audio_path), normalizeMediaUrl(payload.audio_file));
  if (audioUrl && els.audioEl) {
    els.audioEl.src = audioUrl;
    if (audioUrl !== waveformUrl) {
      waveformUrl = audioUrl;
      drawWaveform(audioUrl).catch(() => {});
    }
    if (els.audioLink) {
      els.audioLink.hidden = false;
      els.audioLink.href = audioUrl;
      els.audioLink.textContent = "Open audio";
    }
    if (els.audioMeta) {
      const dur = payload.duration_sec ?? payload.duration;
      const ms = payload.model_used ? ` • ${payload.model_used}` : "";
      els.audioMeta.textContent = `Duration: ${dur ? Number(dur).toFixed(1) + "s" : "?"}${ms}`;
    }
  }

  if (els.artifactMeta) {
    const vid = payload.video_id ? `Video: ${payload.video_id}` : "Ready";
    const model = payload.model_used ? ` • ${payload.model_used}` : "";
    const st = payload.status ? ` • ${payload.status}` : "";
    els.artifactMeta.textContent = `${vid}${st}${model}`;
  }
}

// --- Command palette (Cmd+K / Ctrl+K) ---

let cmdkOpen = false;
let cmdkIndex = 0;
let cmdkFiltered = [];
let cmdkRestoreFocus = null;

function allCommands() {
  return [
    { name: "Discover", desc: "Find trending recap channels + videos", key: "D", run: () => run("discover", () => api("POST", "/api/discover", {})) },
    { name: "Ingest", desc: "Download + extract captions/transcript (YouTube ID)", key: "I", run: () => run("ingest", () => api("POST", `/api/ingest/${encodeURIComponent(getVideoIdRequired())}`)) },
    { name: "Script (Preview)", desc: "Generate hook + quick preview", key: "S", run: () => run("script", () => api("POST", `/api/script/${encodeURIComponent(getVideoIdRequired())}`)) },
    { name: "Script (Full)", desc: "Generate full structured recap script", key: "F", run: () => run("script_full", () => api("POST", `/api/script/full/${encodeURIComponent(getVideoIdRequired())}`)) },
    { name: "Voice (TTS)", desc: "Generate narration audio", key: "V", run: () => run("voice", () => api("POST", `/api/voice/${encodeURIComponent(getVideoIdRequired())}`)) },
    { name: "Thumbnail", desc: "Generate 4 thumbnails (Imagen/Gemini)", key: "T", run: () => run("thumbnail", () => api("POST", `/api/thumbnail/${encodeURIComponent(getVideoIdRequired())}`)) },
    { name: "Full Pipeline", desc: "Run the async job pipeline (best effort)", key: "P", run: () => els.btnFull?.click() },
    { name: "Refresh", desc: "Refresh config + jobs", key: "R", run: () => refresh() },
  ];
}

function filterCommands(q) {
  const query = String(q || "").trim().toLowerCase();
  const cmds = allCommands();
  if (!query) return cmds;
  return cmds.filter((c) => (c.name + " " + c.desc).toLowerCase().includes(query));
}

function renderCmdkList() {
  if (!els.cmdkList) return;
  els.cmdkList.innerHTML = "";

  if (!cmdkFiltered.length) {
    const empty = document.createElement("div");
    empty.className = "jobs__empty";
    empty.textContent = "No matches.";
    els.cmdkList.appendChild(empty);
    return;
  }

  cmdkFiltered.forEach((c, i) => {
    const item = document.createElement("div");
    item.className = `cmdk__item${i === cmdkIndex ? " cmdk__item--active" : ""}`;
    item.tabIndex = 0;
    item.innerHTML = `
      <div>
        <div class="cmdk__name">${escapeHtml(c.name)}</div>
        <div class="cmdk__desc">${escapeHtml(c.desc)}</div>
      </div>
      <div class="cmdk__right"><span class="cmdk__key">${escapeHtml(c.key)}</span></div>
    `;
    item.addEventListener("mouseenter", () => {
      cmdkIndex = i;
      renderCmdkList();
    });
    item.addEventListener("click", () => execCmdk(i));
    els.cmdkList.appendChild(item);
  });

  // Keep the active item in view while navigating.
  const active = els.cmdkList.querySelector(".cmdk__item--active");
  if (active && typeof active.scrollIntoView === "function") {
    active.scrollIntoView({ block: "nearest" });
  }
}

function openCmdk() {
  if (!els.cmdk) return;
  cmdkRestoreFocus = document.activeElement;
  cmdkOpen = true;
  cmdkIndex = 0;
  cmdkFiltered = filterCommands("");
  els.cmdk.hidden = false;
  document.body.style.overflow = "hidden";
  if (els.cmdkInput) {
    els.cmdkInput.value = "";
    els.cmdkInput.focus();
  }
  renderCmdkList();
}

function closeCmdk() {
  if (!els.cmdk) return;
  cmdkOpen = false;
  els.cmdk.hidden = true;
  document.body.style.overflow = "";
  const el = cmdkRestoreFocus;
  cmdkRestoreFocus = null;
  if (el && typeof el.focus === "function") el.focus();
}

function execCmdk(i) {
  const c = cmdkFiltered[i];
  if (!c) return;
  closeCmdk();
  try {
    const p = c.run();
    if (p && typeof p.then === "function") p.catch(() => {});
  } catch (e) {
    log("cmdk", String(e));
  }
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

function extractVideoId(raw) {
  const s = String(raw || "").trim();
  if (!s) return "";

  // Common copy/paste formats:
  // - youtu.be/<id>
  // - youtube.com/watch?v=<id>
  // - plain <id>
  try {
    if (s.includes("youtu.be/") || s.includes("youtube.com/")) {
      const u = new URL(s);
      if (u.hostname.includes("youtu.be")) {
        const id = u.pathname.split("/").filter(Boolean)[0];
        return id || s;
      }
      const v = u.searchParams.get("v");
      if (v) return v;
    }
  } catch {
    // ignore URL parse errors
  }

  const m = s.match(/(?:v=|youtu\.be\/)([A-Za-z0-9_-]{6,})/);
  if (m) return m[1];

  return s;
}

function normalizeVideoIdField() {
  if (!els.videoId) return "";
  const before = String(els.videoId.value || "");
  const id = extractVideoId(before);
  if (id && before.trim() !== id) els.videoId.value = id;
  return id;
}

function getVideoIdRequired() {
  const v = extractVideoId(els.videoId.value || "");
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

function vizClassForStatus(st) {
  const s = String(st || "").toLowerCase();
  if (s === "ok") return "viz__step--ok";
  if (s === "error") return "viz__step--err";
  if (s === "skipped") return "viz__step--skip";
  if (s === "running") return "viz__step--work";
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

  // Pipeline visualization
  if (els.pipelineViz) {
    els.pipelineViz.innerHTML = "";
    const steps = job.steps || {};
    for (const name of PIPELINE_STEPS) {
      const st = (steps?.[name]?.status || "").toLowerCase();
      const cls = vizClassForStatus(st);
      const cell = document.createElement("div");
      cell.className = `viz__step ${cls}`.trim();
      cell.innerHTML = `<div class="viz__dot"></div><div class="viz__name">${escapeHtml(name)}</div>`;
      els.pipelineViz.appendChild(cell);
    }
  }

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
    renderArtifacts(out);
    els.jsonOut.textContent = pretty(out);
    setStatus("ok", tag + ": OK");
    log(tag, "ok");
    return out;
  } catch (e) {
    const payload = e?.data ? e.data : { error: String(e) };
    renderArtifacts(payload);
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
    if (els.engineNotes) {
      const persona = cfg?.narrator_persona ? escapeHtml(cfg.narrator_persona) : "futuristic captain";
      const g = cfg?.gemini_configured ? "ready" : "missing GEMINI_API_KEY";
      els.engineNotes.innerHTML = `Engines: <span class="kbd">Gemini</span> ${g}. <span class="kbd">ZThumb</span> disabled. Persona: <span class="kbd">${persona}</span>`;
    }
    const jobs = await refreshJobs();
    return { health, config: cfg, jobs: { count: jobs.length } };
  });
}

function wire() {
  clearArtifacts();
  els.btnRefresh?.addEventListener("click", refresh);
  els.btnJobsRefresh?.addEventListener("click", () => refreshJobs().catch(() => {}));

  // Normalize YouTube URLs pasted into the input field.
  els.videoId?.addEventListener("blur", () => normalizeVideoIdField());
  els.videoId?.addEventListener("paste", () => setTimeout(() => normalizeVideoIdField(), 0));

  els.btnClear?.addEventListener("click", () => {
    clearArtifacts();
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

  els.btnCopyHook?.addEventListener("click", async () => {
    const txt = String(lastHookText || "").trim();
    if (!txt) {
      log("ui", "no hook to copy yet");
      setStatus("warn", "No hook");
      setTimeout(() => setStatus("idle", "Idle"), 900);
      return;
    }
    try {
      await navigator.clipboard.writeText(txt);
      log("ui", "copied hook");
      setStatus("ok", "Hook copied");
      setTimeout(() => setStatus("idle", "Idle"), 700);
    } catch {
      log("ui", "clipboard copy failed (browser permissions)");
      setStatus("warn", "Copy failed");
      setTimeout(() => setStatus("idle", "Idle"), 900);
    }
  });

  els.btnSafe?.addEventListener("click", () => {
    safeAreaOn = !safeAreaOn;
    if (els.thumbHero) els.thumbHero.classList.toggle("thumbhero--guides", safeAreaOn);
    log("ui", `safe area: ${safeAreaOn ? "on" : "off"}`);
  });

  els.btnDownloadThumb?.addEventListener("click", () => {
    if (!selectedThumbUrl) return;
    const a = document.createElement("a");
    a.href = selectedThumbUrl;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  });

  // Command palette wiring.
  els.cmdkBackdrop?.addEventListener("click", closeCmdk);
  els.cmdkInput?.addEventListener("input", () => {
    cmdkFiltered = filterCommands(els.cmdkInput.value || "");
    cmdkIndex = 0;
    renderCmdkList();
  });
  document.addEventListener("keydown", (ev) => {
    const k = String(ev.key || "").toLowerCase();
    if ((ev.ctrlKey || ev.metaKey) && k === "k") {
      ev.preventDefault();
      (cmdkOpen ? closeCmdk : openCmdk)();
      return;
    }

    if (!cmdkOpen) return;

    if (ev.key === "Escape") {
      ev.preventDefault();
      closeCmdk();
      return;
    }
    if (!cmdkFiltered.length) return;
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      cmdkIndex = Math.min(cmdkFiltered.length - 1, cmdkIndex + 1);
      renderCmdkList();
      return;
    }
    if (ev.key === "ArrowUp") {
      ev.preventDefault();
      cmdkIndex = Math.max(0, cmdkIndex - 1);
      renderCmdkList();
      return;
    }
    if (ev.key === "Enter") {
      ev.preventDefault();
      execCmdk(cmdkIndex);
      return;
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
    const v = normalizeVideoIdField();
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

async function drawWaveform(url) {
  if (!els.waveCanvas) return;
  const canvas = els.waveCanvas;
  // Match CSS width for crisp rendering
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor((canvas.getAttribute("height") ? Number(canvas.getAttribute("height")) : 64) * dpr));

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "rgba(0,0,0,0.12)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  let buf;
  try {
    const res = await fetch(url);
    buf = await res.arrayBuffer();
  } catch {
    return;
  }

  let audioBuffer;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ac = new AC();
    audioBuffer = await ac.decodeAudioData(buf.slice(0));
    // Close ASAP (Safari can keep it alive otherwise).
    if (typeof ac.close === "function") ac.close().catch(() => {});
  } catch {
    return;
  }

  const data = audioBuffer.getChannelData(0);
  const W = canvas.width;
  const H = canvas.height;
  const mid = H / 2;
  const step = Math.max(1, Math.floor(data.length / W));

  // Background grid
  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  ctx.lineWidth = 1;
  for (let x = 0; x < W; x += Math.floor(44 * dpr)) {
    ctx.beginPath();
    ctx.moveTo(x + 0.5, 0);
    ctx.lineTo(x + 0.5, H);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(34,211,238,0.55)";
  ctx.lineWidth = Math.max(1, Math.floor(1.2 * dpr));
  ctx.beginPath();

  for (let x = 0; x < W; x++) {
    let min = 1.0;
    let max = -1.0;
    const start = x * step;
    const end = Math.min(data.length, start + step);
    for (let i = start; i < end; i++) {
      const v = data[i];
      if (v < min) min = v;
      if (v > max) max = v;
    }
    const y1 = mid + min * (H * 0.38);
    const y2 = mid + max * (H * 0.38);
    ctx.moveTo(x, y1);
    ctx.lineTo(x, y2);
  }

  ctx.stroke();
}
