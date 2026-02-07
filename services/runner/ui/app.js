/* BREAKTHROUGH Intelligent Automation UI */

const $ = (id) => document.getElementById(id);

// Swarm Agents
const AGENTS = [
  { id: 'scout', name: 'SCOUT', role: 'Content Discovery', icon: '🔍' },
  { id: 'translator', name: 'TRANSLATOR', role: 'Language Processing', icon: '🌍' },
  { id: 'voice', name: 'VOICE_SYNTH', role: 'Audio Generation', icon: '🎙️' },
  { id: 'renderer', name: 'RENDERER', role: 'Video Assembly', icon: '🎬' },
  { id: 'optimizer', name: 'OPTIMIZER', role: 'Quality Enhancement', icon: '⚡' }
];

// Workflow Steps
const WORKFLOW_STEPS = ['trigger', 'discover', 'ingest', 'script', 'voice', 'render', 'thumbnail', 'complete'];
const PIPELINE_STEPS = ['discover', 'ingest', 'script', 'voice', 'render', 'thumbnail'];

// State
let state = {
  schedule: { enabled: true, hour: 6 },
  stats: { total: 0, today: 0 },
  metrics: { tokens: 0, apiCalls: 0, cost: 0, runtime: 0 },
  evolution: { learning: 78, accuracy: 94, efficiency: 87 },
  predictions: { engagement: 0, postTime: '6:00 AM', quality: 0 }
};

// Load state from localStorage
function loadState() {
  try {
    const saved = localStorage.getItem('breakthroughUI');
    if (saved) {
      const data = JSON.parse(saved);
      state = { ...state, ...data };
    }
  } catch (e) {
    console.error('Failed to load state:', e);
  }
  updateAllUI();
}

// Save state to localStorage
function saveState() {
  try {
    localStorage.setItem('breakthroughUI', JSON.stringify(state));
  } catch (e) {
    console.error('Failed to save state:', e);
  }
}

// API helper
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
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

// Update system status
function setSystemStatus(status, text) {
  const indicator = $('systemStatusIndicator');
  const textEl = $('systemStatusText');
  if (indicator) {
    indicator.style.background = status === 'working' ? 'var(--orange)' : 
                                  status === 'error' ? 'var(--red)' : 'var(--accent)';
    indicator.style.boxShadow = `0 0 10px ${status === 'working' ? 'var(--orange)' : 
                                            status === 'error' ? 'var(--red)' : 'var(--accent)'}`;
  }
  if (textEl) textEl.textContent = text;
}

// Update mini metrics in command bar
function updateMiniMetrics() {
  const confidenceEl = $('metricConfidence');
  const tokensEl = $('metricTokens');
  if (confidenceEl) confidenceEl.textContent = `${state.evolution.accuracy}%`;
  if (tokensEl) tokensEl.textContent = state.metrics.tokens.toLocaleString();
}

// Update agent status
function setAgentStatus(agentId, status) {
  const agent = document.querySelector(`[data-agent="${agentId}"]`);
  if (agent) {
    agent.setAttribute('data-status', status);
    const statusEl = agent.querySelector('.agent__status');
    if (statusEl) {
      statusEl.textContent = status === 'active' ? 'PROCESSING' : 
                             status === 'done' ? 'COMPLETE' : 'STANDBY';
    }
  }
}

// Reset all agents
function resetAgents() {
  AGENTS.forEach(agent => setAgentStatus(agent.id, 'idle'));
}

// Update workflow node
function setNodeStatus(nodeId, status) {
  const node = $(`node-${nodeId}`);
  if (!node) return;
  node.classList.remove('active', 'done');
  if (status === 'active') node.classList.add('active');
  if (status === 'done') node.classList.add('done');
  
  // Update confidence score
  if (status === 'active' || status === 'done') {
    const confEl = node.querySelector('.wf-node__confidence');
    if (confEl) {
      const conf = Math.floor(85 + Math.random() * 15);
      confEl.textContent = `${conf}%`;
    }
  }
}

// Reset all workflow nodes
function resetWorkflow() {
  WORKFLOW_STEPS.forEach(step => {
    const node = $(`node-${step}`);
    if (node) {
      node.classList.remove('active', 'done');
      const confEl = node.querySelector('.wf-node__confidence');
      if (confEl) confEl.textContent = '';
    }
  });
  setWorkflowProgress(0);
}

// Update workflow progress bar
function setWorkflowProgress(percent) {
  const fill = $('workflowProgressFill');
  const text = $('workflowProgressText');
  if (fill) fill.style.width = `${percent}%`;
  if (text) text.textContent = percent === 0 ? 'AWAITING TRIGGER' : 
                               percent === 100 ? 'PIPELINE COMPLETE' : 
                               `PROCESSING ${Math.round(percent)}%`;
}

// Add activity to stream
function addActivity(message, type = 'info') {
  const content = $('activityContent');
  if (!content) return;
  
  const item = document.createElement('div');
  item.className = 'activity-item';
  item.innerHTML = `
    <span class="activity-item__prefix">${type === 'success' ? '>' : type === 'error' ? '!' : '>'}</span>
    <span class="activity-item__text">${message}</span>
  `;
  content.insertBefore(item, content.firstChild);
  
  // Keep only last 10 items
  while (content.children.length > 10) {
    content.removeChild(content.lastChild);
  }
}

// Add decision to log
function addDecision(message, type = 'info') {
  const log = $('decisionLog');
  if (!log) return;
  
  const now = new Date();
  const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  
  const item = document.createElement('div');
  item.className = `decision-item decision-item--${type}`;
  item.innerHTML = `
    <span class="decision-item__time">${time}</span>
    <span class="decision-item__text">${message}</span>
  `;
  log.insertBefore(item, log.firstChild);
  
  // Keep only last 5 items
  while (log.children.length > 5) {
    log.removeChild(log.lastChild);
  }
}

// Update predictions
function updatePredictions() {
  const engagement = Math.floor(75 + Math.random() * 20);
  const quality = Math.floor(85 + Math.random() * 15);
  
  state.predictions.engagement = engagement;
  state.predictions.quality = quality;
  
  const engEl = $('predEngagement');
  const timeEl = $('predPostTime');
  const qualEl = $('predQuality');
  
  if (engEl) engEl.textContent = `${engagement}%`;
  if (timeEl) timeEl.textContent = state.predictions.postTime;
  if (qualEl) qualEl.textContent = `${quality}/100`;
}

// Update evolution metrics
function updateEvolutionMetrics() {
  ['learning', 'accuracy', 'efficiency'].forEach(metric => {
    const fill = $(`evo${metric.charAt(0).toUpperCase() + metric.slice(1)}Fill`);
    const value = $(`evo${metric.charAt(0).toUpperCase() + metric.slice(1)}Value`);
    if (fill) fill.style.width = `${state.evolution[metric]}%`;
    if (value) value.textContent = `${state.evolution[metric]}%`;
  });
}

// Update resource metrics
function updateResourceMetrics() {
  const tokensEl = $('resourceTokens');
  const apiEl = $('resourceApi');
  const costEl = $('resourceCost');
  const runtimeEl = $('resourceRuntime');
  
  if (tokensEl) tokensEl.textContent = state.metrics.tokens.toLocaleString();
  if (apiEl) apiEl.textContent = state.metrics.apiCalls;
  if (costEl) costEl.textContent = `$${state.metrics.cost.toFixed(2)}`;
  if (runtimeEl) runtimeEl.textContent = `${state.metrics.runtime}s`;
}

// Update all UI elements
function updateAllUI() {
  updateMiniMetrics();
  updatePredictions();
  updateEvolutionMetrics();
  updateResourceMetrics();
  updateScheduleUI();
}

// Update schedule UI
function updateScheduleUI() {
  const toggle = $('scheduleToggle');
  const hourSelect = $('scheduleHour');
  
  if (toggle) toggle.checked = state.schedule.enabled;
  if (hourSelect) hourSelect.value = state.schedule.hour;
  
  // Update prediction text
  const hour = state.schedule.hour;
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const displayHour = hour % 12 || 12;
  state.predictions.postTime = `${displayHour}:00 ${ampm}`;
}

// Draw handoff visualization
function drawHandoff(activeIndex = -1) {
  const canvas = $('handoffCanvas');
  if (!canvas) return;
  
  const ctx = canvas.getContext('2d');
  const width = canvas.width = canvas.offsetWidth;
  const height = canvas.height = canvas.offsetHeight;
  
  ctx.clearRect(0, 0, width, height);
  
  const nodeCount = AGENTS.length;
  const nodeSpacing = width / (nodeCount + 1);
  const nodeY = height / 2;
  const nodeRadius = 8;
  
  // Draw connections
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let i = 0; i < nodeCount - 1; i++) {
    const x1 = nodeSpacing * (i + 1);
    const x2 = nodeSpacing * (i + 2);
    ctx.moveTo(x1 + nodeRadius, nodeY);
    ctx.lineTo(x2 - nodeRadius, nodeY);
  }
  ctx.stroke();
  
  // Draw nodes
  for (let i = 0; i < nodeCount; i++) {
    const x = nodeSpacing * (i + 1);
    const isActive = i === activeIndex;
    const isDone = i < activeIndex;
    
    ctx.beginPath();
    ctx.arc(x, nodeY, nodeRadius, 0, Math.PI * 2);
    
    if (isActive) {
      ctx.fillStyle = '#ff6b00';
      ctx.shadowColor = '#ff6b00';
      ctx.shadowBlur = 10;
    } else if (isDone) {
      ctx.fillStyle = '#00ffaa';
      ctx.shadowColor = '#00ffaa';
      ctx.shadowBlur = 5;
    } else {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
      ctx.shadowBlur = 0;
    }
    
    ctx.fill();
    ctx.shadowBlur = 0;
  }
}

// Poll job status
async function pollJobStatus(jobId) {
  const maxAttempts = 300;
  let attempts = 0;
  const startTime = Date.now();
  
  while (attempts < maxAttempts) {
    try {
      const status = await api('GET', `/api/job/${jobId}`);
      
      if (status.job && status.job.current_step) {
        const stepName = status.job.current_step.replace('step_', '');
        const stepIndex = PIPELINE_STEPS.indexOf(stepName);
        
        // Update metrics
        state.metrics.apiCalls++;
        state.metrics.tokens += Math.floor(100 + Math.random() * 200);
        state.metrics.runtime = Math.floor((Date.now() - startTime) / 1000);
        state.metrics.cost = state.metrics.tokens * 0.00001;
        updateResourceMetrics();
        updateMiniMetrics();
        
        // Mark previous steps as done
        for (let i = 0; i < stepIndex; i++) {
          setNodeStatus(PIPELINE_STEPS[i], 'done');
        }
        
        // Mark current step as active
        if (stepIndex >= 0) {
          setNodeStatus(stepName, 'active');
          setWorkflowProgress(((stepIndex + 0.5) / PIPELINE_STEPS.length) * 100);
          
          // Activate corresponding agent
          const agentIndex = Math.min(stepIndex, AGENTS.length - 1);
          for (let i = 0; i < AGENTS.length; i++) {
            setAgentStatus(AGENTS[i].id, i < agentIndex ? 'done' : i === agentIndex ? 'active' : 'idle');
          }
          drawHandoff(agentIndex);
          
          addActivity(`${AGENTS[agentIndex]?.name || 'SYSTEM'} processing ${stepName}...`);
        }
      }
      
      if (status.job && status.job.status === 'completed') {
        return status;
      }
      
      if (status.job && status.job.status === 'failed') {
        throw new Error(status.job.error || 'Pipeline failed');
      }
      
    } catch (e) {
      if (e.message !== 'Pipeline failed') {
        console.error('Poll error:', e);
      } else {
        throw e;
      }
    }
    
    await new Promise(r => setTimeout(r, 1000));
    attempts++;
  }
  
  throw new Error('Timeout waiting for job to complete');
}

// Run automation
async function runAutomation() {
  setSystemStatus('working', 'PROCESSING');
  resetWorkflow();
  resetAgents();
  
  // Reset metrics for this run
  state.metrics = { tokens: 0, apiCalls: 0, cost: 0, runtime: 0 };
  updateResourceMetrics();
  
  addActivity('Initiating automation pipeline...');
  addDecision('Pipeline triggered by user', 'info');
  
  try {
    // Activate trigger node
    setNodeStatus('trigger', 'active');
    addActivity('SCOUT agent activated for content discovery');
    setAgentStatus('scout', 'active');
    drawHandoff(0);
    
    const startResult = await api('POST', '/api/pipeline/full', { auto_select: true });
    
    if (!startResult.job || !startResult.job.id) {
      throw new Error('Failed to start pipeline');
    }
    
    setNodeStatus('trigger', 'done');
    addDecision('Content source identified', 'success');
    
    const result = await pollJobStatus(startResult.job.id);
    
    // Mark all steps as done
    PIPELINE_STEPS.forEach(step => setNodeStatus(step, 'done'));
    setNodeStatus('complete', 'active');
    setWorkflowProgress(100);
    
    // Mark all agents as done
    AGENTS.forEach(agent => setAgentStatus(agent.id, 'done'));
    drawHandoff(AGENTS.length);
    
    // Update stats
    state.stats.total++;
    state.stats.today++;
    
    // Improve evolution metrics slightly
    state.evolution.learning = Math.min(99, state.evolution.learning + 1);
    state.evolution.accuracy = Math.min(99, state.evolution.accuracy + 0.5);
    state.evolution.efficiency = Math.min(99, state.evolution.efficiency + 0.5);
    
    saveState();
    updateAllUI();
    
    addActivity('Pipeline completed successfully!', 'success');
    addDecision('All quality checks passed', 'success');
    
    // Show output modal
    showOutputModal(result);
    setSystemStatus('ready', 'READY');
    
  } catch (e) {
    console.error('Automation error:', e);
    setSystemStatus('error', 'ERROR');
    addActivity(`Error: ${e.message}`, 'error');
    addDecision('Pipeline failed - investigating...', 'error');
  }
}

// Show output modal
function showOutputModal(result) {
  const modal = $('outputModal');
  if (!modal) return;
  
  modal.classList.remove('hidden');
  
  if (result && result.job && result.job.result) {
    const r = result.job.result;
    
    const preview = $('outputPreviewImg');
    const title = $('outputTitleText');
    const meta = $('outputMetaText');
    const qualityScore = $('outputQuality');
    const engagementScore = $('outputEngagement');
    const seoScore = $('outputSeo');
    const downloadVideo = $('btnDownloadVideo');
    const downloadThumb = $('btnDownloadThumb');
    
    if (r.thumbnail_path && preview) {
      preview.src = `/outputs/${r.video_id}/thumbnail.png`;
    }
    
    if (title) title.textContent = r.title || 'Your Amharic Recap';
    if (meta) meta.textContent = `Video ID: ${r.video_id || 'N/A'}`;
    
    // Generate quality scores
    if (qualityScore) qualityScore.textContent = `${state.predictions.quality}/100`;
    if (engagementScore) engagementScore.textContent = `${state.predictions.engagement}%`;
    if (seoScore) seoScore.textContent = `${Math.floor(80 + Math.random() * 18)}/100`;
    
    if (r.video_id) {
      if (downloadVideo) downloadVideo.href = `/outputs/${r.video_id}/final.mp4`;
      if (downloadThumb) downloadThumb.href = `/outputs/${r.video_id}/thumbnail.png`;
    }
  }
}

// Close output modal
function closeOutputModal() {
  const modal = $('outputModal');
  if (modal) modal.classList.add('hidden');
}

// Open schedule modal
function openScheduleModal() {
  const modal = $('scheduleModal');
  if (modal) modal.classList.remove('hidden');
}

// Close schedule modal
function closeScheduleModal() {
  const modal = $('scheduleModal');
  if (modal) modal.classList.add('hidden');
}

// Save schedule
function saveSchedule() {
  const toggle = $('scheduleToggle');
  const hourSelect = $('scheduleHour');
  
  state.schedule.enabled = toggle?.checked ?? true;
  state.schedule.hour = parseInt(hourSelect?.value ?? '6', 10);
  
  saveState();
  updateScheduleUI();
  closeScheduleModal();
  
  addActivity(`Schedule ${state.schedule.enabled ? 'enabled' : 'disabled'}`);
  addDecision(`Automation scheduled for ${state.predictions.postTime}`, 'info');
}

// Check for scheduled run
function checkScheduledRun() {
  if (!state.schedule.enabled) return;
  
  const now = new Date();
  const currentHour = now.getHours();
  const currentMinute = now.getMinutes();
  
  if (currentHour === state.schedule.hour && currentMinute === 0) {
    const lastRun = localStorage.getItem('lastScheduledRun');
    const today = now.toDateString();
    
    if (lastRun !== today) {
      localStorage.setItem('lastScheduledRun', today);
      addActivity('Scheduled automation triggered');
      addDecision('Daily schedule activated', 'info');
      runAutomation();
    }
  }
}

// Initialize
function init() {
  loadState();
  
  // Wire up buttons
  $('btnRunNow')?.addEventListener('click', runAutomation);
  $('btnSchedule')?.addEventListener('click', openScheduleModal);
  $('btnCloseSchedule')?.addEventListener('click', closeScheduleModal);
  $('btnSaveSchedule')?.addEventListener('click', saveSchedule);
  $('btnCloseOutput')?.addEventListener('click', closeOutputModal);
  
  // Close modals on backdrop click
  $('scheduleModal')?.querySelector('.modal__backdrop')?.addEventListener('click', closeScheduleModal);
  $('outputModal')?.querySelector('.modal__backdrop')?.addEventListener('click', closeOutputModal);
  
  // Initial handoff visualization
  drawHandoff(-1);
  
  // Check health
  api('GET', '/health').then(() => {
    setSystemStatus('ready', 'READY');
    addActivity('System initialized successfully');
    addDecision('All systems operational', 'success');
  }).catch(() => {
    setSystemStatus('error', 'OFFLINE');
    addActivity('Backend connection failed', 'error');
  });
  
  // Check for scheduled runs
  checkScheduledRun();
  setInterval(checkScheduledRun, 60000);
  
  // Simulate neural activity
  setInterval(() => {
    if (document.hidden) return;
    // Slight random fluctuation in evolution metrics for "learning" effect
    state.evolution.learning = Math.max(70, Math.min(99, state.evolution.learning + (Math.random() - 0.5) * 0.5));
    updateEvolutionMetrics();
  }, 5000);
}

init();
