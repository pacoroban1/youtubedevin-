/* CO-TOMATE Style Automation UI */

const $ = (id) => document.getElementById(id);

// Elements
const els = {
  // Status
  statusDot: $("statusDot"),
  statusText: $("statusText"),
  
  // Tabs
  tabWorkflow: $("tabWorkflow"),
  tabWorkbench: $("tabWorkbench"),
  tabMonitor: $("tabMonitor"),
  tabContentWorkflow: $("tabContentWorkflow"),
  tabContentWorkbench: $("tabContentWorkbench"),
  tabContentMonitor: $("tabContentMonitor"),
  
  // Workflow
  workflowProgress: $("workflowProgress"),
  
  // Workbench
  btnRunNow: $("btnRunNow"),
  btnSchedule: $("btnSchedule"),
  scheduleCard: $("scheduleCard"),
  btnCloseSchedule: $("btnCloseSchedule"),
  scheduleEnabled: $("scheduleEnabled"),
  scheduleHour: $("scheduleHour"),
  btnSaveSchedule: $("btnSaveSchedule"),
  outputCard: $("outputCard"),
  thumbnailImg: $("thumbnailImg"),
  outputTitle: $("outputTitle"),
  outputMeta: $("outputMeta"),
  btnDownloadVideo: $("btnDownloadVideo"),
  btnDownloadThumb: $("btnDownloadThumb"),
  
  // Monitor
  statTotal: $("statTotal"),
  statToday: $("statToday"),
  statSchedule: $("statSchedule"),
  statUptime: $("statUptime"),
};

// Pipeline steps
const STEPS = ["discover", "ingest", "script", "voice", "render", "thumbnail"];

// State
let schedule = {
  enabled: true,
  hour: 6
};
let stats = {
  total: 0,
  today: 0
};

// Load from localStorage
function loadState() {
  try {
    const saved = localStorage.getItem("recapFactory");
    if (saved) {
      const data = JSON.parse(saved);
      schedule = data.schedule || schedule;
      stats = data.stats || stats;
    }
  } catch (e) {
    console.error("Failed to load state:", e);
  }
  updateScheduleUI();
  updateStatsUI();
}

// Save to localStorage
function saveState() {
  try {
    localStorage.setItem("recapFactory", JSON.stringify({ schedule, stats }));
  } catch (e) {
    console.error("Failed to save state:", e);
  }
}

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

// Tab switching
function switchTab(tabName) {
  // Update tab buttons
  document.querySelectorAll(".nav-tab").forEach(tab => {
    tab.classList.remove("active");
  });
  $(`tab${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`)?.classList.add("active");
  
  // Update tab content
  document.querySelectorAll(".tab-content").forEach(content => {
    content.classList.remove("active");
  });
  $(`tabContent${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`)?.classList.add("active");
}

// Update status badge
function setStatus(kind, text) {
  if (els.statusText) els.statusText.textContent = text;
  if (els.statusDot) {
    els.statusDot.className = "status-dot";
    if (kind === "working") els.statusDot.classList.add("working");
    if (kind === "error") els.statusDot.classList.add("error");
  }
}

// Update node status in workflow view
function setNodeStatus(stepName, status) {
  const node = $(`node-${stepName}`);
  if (!node) return;
  
  node.classList.remove("active", "done");
  if (status === "active") node.classList.add("active");
  if (status === "done") node.classList.add("done");
}

// Reset all nodes
function resetNodes() {
  STEPS.forEach(step => {
    const node = $(`node-${step}`);
    if (node) node.classList.remove("active", "done");
  });
  $("node-complete")?.classList.remove("active");
  if (els.workflowProgress) els.workflowProgress.style.width = "0%";
}

// Update workflow progress
function setWorkflowProgress(percent) {
  if (els.workflowProgress) {
    els.workflowProgress.style.width = `${percent}%`;
  }
}

// Update schedule UI
function updateScheduleUI() {
  if (els.scheduleEnabled) els.scheduleEnabled.checked = schedule.enabled;
  if (els.scheduleHour) els.scheduleHour.value = schedule.hour;
  
  // Update trigger node
  const triggerNode = $("node-trigger");
  if (triggerNode) {
    const sub = triggerNode.querySelector(".node__sub");
    if (sub) {
      const hour = schedule.hour;
      const ampm = hour >= 12 ? "PM" : "AM";
      const displayHour = hour % 12 || 12;
      sub.textContent = schedule.enabled ? `Daily ${displayHour}${ampm}` : "Disabled";
    }
  }
  
  // Update monitor stat
  if (els.statSchedule) {
    const hour = schedule.hour;
    const ampm = hour >= 12 ? "PM" : "AM";
    const displayHour = hour % 12 || 12;
    els.statSchedule.textContent = schedule.enabled ? `${displayHour} ${ampm}` : "Off";
  }
}

// Update stats UI
function updateStatsUI() {
  if (els.statTotal) els.statTotal.textContent = stats.total;
  if (els.statToday) els.statToday.textContent = stats.today;
}

// Poll job status
async function pollJobStatus(jobId) {
  const maxAttempts = 300;
  let attempts = 0;
  
  while (attempts < maxAttempts) {
    try {
      const status = await api("GET", `/api/job/${jobId}`);
      
      if (status.job && status.job.current_step) {
        const stepName = status.job.current_step.replace("step_", "");
        const stepIndex = STEPS.indexOf(stepName);
        
        // Mark previous steps as done
        for (let i = 0; i < stepIndex; i++) {
          setNodeStatus(STEPS[i], "done");
        }
        
        // Mark current step as active
        if (stepIndex >= 0) {
          setNodeStatus(stepName, "active");
          setWorkflowProgress(((stepIndex + 0.5) / STEPS.length) * 100);
        }
      }
      
      if (status.job && status.job.status === "completed") {
        return status;
      }
      
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

// Run automation
async function runAutomation() {
  switchTab("workflow");
  setStatus("working", "Running...");
  resetNodes();
  
  try {
    setNodeStatus("discover", "active");
    const startResult = await api("POST", "/api/pipeline/full", { auto_select: true });
    
    if (!startResult.job || !startResult.job.id) {
      throw new Error("Failed to start pipeline");
    }
    
    const result = await pollJobStatus(startResult.job.id);
    
    // Mark all steps as done
    STEPS.forEach(step => setNodeStatus(step, "done"));
    $("node-complete")?.classList.add("active");
    setWorkflowProgress(100);
    
    // Update stats
    stats.total++;
    stats.today++;
    updateStatsUI();
    saveState();
    
    // Show output
    showOutput(result);
    setStatus("ready", "Complete");
    
  } catch (e) {
    console.error("Automation error:", e);
    setStatus("error", "Error");
    alert("Automation failed: " + (e.message || "Unknown error"));
  }
}

// Show output card
function showOutput(result) {
  if (!els.outputCard) return;
  
  els.outputCard.classList.remove("hidden");
  
  if (result && result.job && result.job.result) {
    const r = result.job.result;
    
    if (r.thumbnail_path && els.thumbnailImg) {
      els.thumbnailImg.src = `/outputs/${r.video_id}/thumbnail.png`;
    }
    
    if (els.outputTitle) {
      els.outputTitle.textContent = r.title || "Your Amharic Recap";
    }
    
    if (r.video_id) {
      if (els.outputMeta) els.outputMeta.textContent = `Video ID: ${r.video_id}`;
      if (els.btnDownloadVideo) els.btnDownloadVideo.href = `/outputs/${r.video_id}/final.mp4`;
      if (els.btnDownloadThumb) els.btnDownloadThumb.href = `/outputs/${r.video_id}/thumbnail.png`;
    }
  }
  
  // Switch to workbench to show output
  switchTab("workbench");
}

// Schedule functions
function openSchedule() {
  if (els.scheduleCard) els.scheduleCard.classList.remove("hidden");
}

function closeSchedule() {
  if (els.scheduleCard) els.scheduleCard.classList.add("hidden");
}

function saveSchedule() {
  schedule.enabled = els.scheduleEnabled?.checked ?? true;
  schedule.hour = parseInt(els.scheduleHour?.value ?? "6", 10);
  saveState();
  updateScheduleUI();
  closeSchedule();
}

// Initialize
function init() {
  loadState();
  
  // Tab switching
  els.tabWorkflow?.addEventListener("click", () => switchTab("workflow"));
  els.tabWorkbench?.addEventListener("click", () => switchTab("workbench"));
  els.tabMonitor?.addEventListener("click", () => switchTab("monitor"));
  
  // Run button
  els.btnRunNow?.addEventListener("click", runAutomation);
  
  // Schedule
  els.btnSchedule?.addEventListener("click", openSchedule);
  els.btnCloseSchedule?.addEventListener("click", closeSchedule);
  els.btnSaveSchedule?.addEventListener("click", saveSchedule);
  
  // Check health
  api("GET", "/health").then(() => {
    setStatus("ready", "Ready");
  }).catch(() => {
    setStatus("error", "Offline");
  });
  
  // Check for scheduled run
  checkScheduledRun();
  setInterval(checkScheduledRun, 60000); // Check every minute
}

// Check if we should run based on schedule
function checkScheduledRun() {
  if (!schedule.enabled) return;
  
  const now = new Date();
  const currentHour = now.getHours();
  const currentMinute = now.getMinutes();
  
  // Run if it's the scheduled hour and within the first minute
  if (currentHour === schedule.hour && currentMinute === 0) {
    const lastRun = localStorage.getItem("lastScheduledRun");
    const today = now.toDateString();
    
    if (lastRun !== today) {
      localStorage.setItem("lastScheduledRun", today);
      runAutomation();
    }
  }
}

init();

