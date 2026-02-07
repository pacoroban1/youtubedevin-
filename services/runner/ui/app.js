/* Simple Automation UI - One Button, Show Progress */

const $ = (id) => document.getElementById(id);

// Elements
const els = {
  statusDot: $("statusDot"),
  statusText: $("statusText"),
  
  startSection: $("startSection"),
  progressSection: $("progressSection"),
  completeSection: $("completeSection"),
  errorSection: $("errorSection"),
  
  btnStart: $("btnStart"),
  btnRestart: $("btnRestart"),
  btnRetry: $("btnRetry"),
  
  progressFill: $("progressFill"),
  progressPercent: $("progressPercent"),
  
  thumbnailImg: $("thumbnailImg"),
  outputTitle: $("outputTitle"),
  outputMeta: $("outputMeta"),
  btnDownloadVideo: $("btnDownloadVideo"),
  btnDownloadThumb: $("btnDownloadThumb"),
  btnCopyTitle: $("btnCopyTitle"),
  
  errorMessage: $("errorMessage"),
};

// Steps in order
const STEPS = ["discover", "ingest", "script", "voice", "render", "thumbnail"];

// Current state
let currentStep = 0;
let jobResult = null;

// API helper
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

// Show/hide sections
function showSection(name) {
  els.startSection.classList.add("hidden");
  els.progressSection.classList.add("hidden");
  els.completeSection.classList.add("hidden");
  els.errorSection.classList.add("hidden");
  
  if (name === "start") els.startSection.classList.remove("hidden");
  if (name === "progress") els.progressSection.classList.remove("hidden");
  if (name === "complete") els.completeSection.classList.remove("hidden");
  if (name === "error") els.errorSection.classList.remove("hidden");
}

// Update status badge
function setStatus(kind, text) {
  els.statusText.textContent = text;
  els.statusDot.className = "status__dot";
  if (kind === "working") els.statusDot.classList.add("working");
  if (kind === "error") els.statusDot.classList.add("error");
}

// Update step status
function setStepStatus(stepName, status) {
  const stepEl = $(`step-${stepName}`);
  const statusEl = $(`status-${stepName}`);
  
  if (!stepEl || !statusEl) return;
  
  stepEl.classList.remove("active", "done");
  statusEl.className = "step__status";
  
  if (status === "active") {
    stepEl.classList.add("active");
    statusEl.classList.add("working");
  } else if (status === "done") {
    stepEl.classList.add("done");
    statusEl.classList.add("done");
  } else if (status === "error") {
    statusEl.classList.add("error");
  }
}

// Update progress bar
function setProgress(percent) {
  els.progressFill.style.width = `${percent}%`;
  els.progressPercent.textContent = `${Math.round(percent)}%`;
}

// Reset all steps
function resetSteps() {
  STEPS.forEach(step => {
    const stepEl = $(`step-${step}`);
    const statusEl = $(`status-${step}`);
    if (stepEl) stepEl.classList.remove("active", "done");
    if (statusEl) statusEl.className = "step__status";
  });
  setProgress(0);
}

// Poll job status
async function pollJobStatus(jobId) {
  const maxAttempts = 300; // 5 minutes max
  let attempts = 0;
  
  while (attempts < maxAttempts) {
    try {
      const status = await api("GET", `/api/job/${jobId}`);
      
      // Update current step
      if (status.job && status.job.current_step) {
        const stepName = status.job.current_step.replace("step_", "");
        const stepIndex = STEPS.indexOf(stepName);
        
        // Mark previous steps as done
        for (let i = 0; i < stepIndex; i++) {
          setStepStatus(STEPS[i], "done");
        }
        
        // Mark current step as active
        if (stepIndex >= 0) {
          setStepStatus(stepName, "active");
          setProgress(((stepIndex + 0.5) / STEPS.length) * 100);
        }
      }
      
      // Check if done
      if (status.job && status.job.status === "completed") {
        return status;
      }
      
      // Check if failed
      if (status.job && status.job.status === "failed") {
        throw new Error(status.job.error || "Pipeline failed");
      }
      
    } catch (e) {
      if (e.message !== "Pipeline failed") {
        console.error("Poll error:", e);
      } else {
        throw e;
      }
    }
    
    await new Promise(r => setTimeout(r, 1000));
    attempts++;
  }
  
  throw new Error("Timeout waiting for job to complete");
}

// Start the automation
async function startAutomation() {
  showSection("progress");
  setStatus("working", "Working...");
  resetSteps();
  currentStep = 0;
  
  try {
    // Start the full pipeline (auto-select video)
    setStepStatus("discover", "active");
    const startResult = await api("POST", "/api/pipeline/full", { auto_select: true });
    
    if (!startResult.job || !startResult.job.id) {
      throw new Error("Failed to start pipeline");
    }
    
    // Poll for completion
    const result = await pollJobStatus(startResult.job.id);
    
    // Mark all steps as done
    STEPS.forEach(step => setStepStatus(step, "done"));
    setProgress(100);
    
    // Show completion
    jobResult = result;
    showComplete(result);
    
  } catch (e) {
    console.error("Automation error:", e);
    showError(e.message || "Something went wrong");
  }
}

// Show completion screen
function showComplete(result) {
  setStatus("ready", "Complete");
  showSection("complete");
  
  // Try to populate output info
  if (result && result.job && result.job.result) {
    const r = result.job.result;
    
    if (r.thumbnail_path) {
      els.thumbnailImg.src = `/outputs/${r.video_id}/thumbnail.png`;
    }
    
    if (r.title) {
      els.outputTitle.textContent = r.title;
    } else {
      els.outputTitle.textContent = "Your Amharic Recap";
    }
    
    if (r.video_id) {
      els.outputMeta.textContent = `Video ID: ${r.video_id}`;
      els.btnDownloadVideo.href = `/outputs/${r.video_id}/final.mp4`;
      els.btnDownloadThumb.href = `/outputs/${r.video_id}/thumbnail.png`;
    }
  }
}

// Show error screen
function showError(message) {
  setStatus("error", "Error");
  showSection("error");
  els.errorMessage.textContent = message;
}

// Reset to start
function resetToStart() {
  showSection("start");
  setStatus("ready", "Ready");
  resetSteps();
  jobResult = null;
}

// Copy title to clipboard
async function copyTitle() {
  const title = els.outputTitle.textContent;
  try {
    await navigator.clipboard.writeText(title);
    els.btnCopyTitle.textContent = "Copied!";
    setTimeout(() => {
      els.btnCopyTitle.textContent = "Copy Title";
    }, 2000);
  } catch {
    alert("Failed to copy. Title: " + title);
  }
}

// Wire up events
function init() {
  els.btnStart?.addEventListener("click", startAutomation);
  els.btnRestart?.addEventListener("click", resetToStart);
  els.btnRetry?.addEventListener("click", startAutomation);
  els.btnCopyTitle?.addEventListener("click", copyTitle);
  
  // Check health on load
  api("GET", "/health").then(() => {
    setStatus("ready", "Ready");
  }).catch(() => {
    setStatus("error", "Offline");
  });
}

init();

