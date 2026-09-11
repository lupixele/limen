/**
 * Limen — Autonomous Agent Workbench
 * Specification: "Precision Monolith" (P:\Magnanimity\Projects\Harness\FRONTEND_DESIGN_AUDIT.md)
 */

(function () {
  'use strict';

  // Application State
  const state = {
    config: {
      provider_url: 'http://localhost:20128/v1',
      api_key: '',
      active_model: 'antigravity/gemini-3.8-flash-tiered',
      custom_models: ['antigravity/gemini-3.8-flash-tiered'],
      max_steps: 8
    },
    activeSessionId: localStorage.getItem('limen_session_id') || '',
    activeSessionTitle: 'Untitled Run',
    sessions: [],
    openTabIds: [], // array of session IDs open in titlebar tabs
    isStreaming: false,
    abortController: null,
    runStatus: 'idle', // 'idle' | 'running' | 'converged' | 'step-limit' | 'interrupted'
    stepCount: 0,
    userScrolledUp: false,
    artifacts: [], // collected plan_artifacts in current session
    selectedToolForInspect: null,
    telemetryLogs: []
  };

  // DOM Elements Cache
  const el = {
    // Titlebar
    titlebarTabsStrip: document.getElementById('titlebar-tabs-strip'),
    btnNewTab: document.getElementById('btn-new-tab'),
    globalModelSelect: document.getElementById('global-model-select'),
    engineStatusDot: document.getElementById('engine-status-dot'),
    engineStatusLabel: document.getElementById('engine-status-label'),
    btnTitlebarPing: document.getElementById('btn-titlebar-ping'),
    btnToggleInspector: document.getElementById('btn-toggle-inspector'),
    btnOpenSettings: document.getElementById('btn-open-settings'),

    // Rail & Sidebar
    workbenchSidebar: document.getElementById('workbench-sidebar'),
    railBtnSessions: document.getElementById('rail-btn-sessions'),
    railBtnTools: document.getElementById('rail-btn-tools'),
    railBtnTelemetry: document.getElementById('rail-btn-telemetry'),
    railBtnSettings: document.getElementById('rail-btn-settings'),
    sessionCountBadge: document.getElementById('session-count-badge'),
    sidebarSessionList: document.getElementById('sidebar-session-list'),

    // Stream Pane
    paneStream: document.getElementById('pane-stream'),
    streamSessionTitle: document.getElementById('stream-session-title'),
    runStatusChip: document.getElementById('run-status-chip'),
    runStatusLabel: document.getElementById('run-status-label'),
    stepCounterChip: document.getElementById('step-counter-chip'),
    timelineViewport: document.getElementById('timeline-viewport'),
    btnJumpLatest: document.getElementById('btn-jump-latest'),
    idleTerminalCard: document.getElementById('idle-terminal-card'),
    executionStreamList: document.getElementById('execution-stream-list'),

    // Composer
    composerForm: document.getElementById('composer-form'),
    composerInput: document.getElementById('composer-input'),
    composerModelIndicator: document.getElementById('composer-model-indicator'),
    composerStepsIndicator: document.getElementById('composer-steps-indicator'),
    btnSubmitTask: document.getElementById('btn-submit-task'),

    // Inspector Pane
    paneInspector: document.getElementById('pane-inspector'),
    btnCloseInspector: document.getElementById('btn-close-inspector'),
    tabBtnArtifacts: document.getElementById('tab-btn-artifacts'),
    tabBtnTool: document.getElementById('tab-btn-tool'),
    tabBtnTelemetry: document.getElementById('tab-btn-telemetry'),
    artifactsCountPill: document.getElementById('artifacts-count-pill'),
    viewArtifacts: document.getElementById('view-artifacts'),
    viewToolCall: document.getElementById('view-tool-call'),
    viewTelemetry: document.getElementById('view-telemetry'),
    emptyArtifacts: document.getElementById('empty-artifacts'),
    artifactsContentContainer: document.getElementById('artifacts-content-container'),
    emptyToolInspector: document.getElementById('empty-tool-inspector'),
    toolInspectionDetails: document.getElementById('tool-inspection-details'),
    inspectToolName: document.getElementById('inspect-tool-name'),
    inspectToolStatus: document.getElementById('inspect-tool-status'),
    inspectToolStep: document.getElementById('inspect-tool-step'),
    inspectToolArgs: document.getElementById('inspect-tool-args'),
    inspectToolOutput: document.getElementById('inspect-tool-output'),
    btnCopyArgs: document.getElementById('btn-copy-args'),
    btnCopyOutput: document.getElementById('btn-copy-output'),
    telemetryLogScroll: document.getElementById('telemetry-log-scroll'),
    telemetryEmpty: document.getElementById('telemetry-empty'),

    // Settings Modal
    modalSettings: document.getElementById('modal-settings'),
    btnCloseSettings: document.getElementById('btn-close-settings'),
    btnCancelSettings: document.getElementById('btn-cancel-settings'),
    btnSaveSettings: document.getElementById('btn-save-settings'),
    cfgProviderUrl: document.getElementById('cfg-provider-url'),
    cfgApiKey: document.getElementById('cfg-api-key'),
    cfgMaxSteps: document.getElementById('cfg-max-steps'),
    settingsModelsTagList: document.getElementById('settings-models-tag-list'),
    inputAddModel: document.getElementById('input-add-model'),
    btnAddModel: document.getElementById('btn-add-model'),
    btnPingGateway: document.getElementById('btn-ping-gateway'),
    diagnosticLog: document.getElementById('diagnostic-log'),

    // Toast
    toastStack: document.getElementById('toast-stack')
  };

  // ---------------------------------------------------------------------------
  // Utilities & Safe Markdown
  // ---------------------------------------------------------------------------
  function escapeHtml(str) {
    if (typeof str !== 'string') {
      try {
        str = JSON.stringify(str, null, 2);
      } catch (e) {
        str = String(str);
      }
    }
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function safeMarkdown(md) {
    if (!md || typeof md !== 'string') return '';
    let html = escapeHtml(md);

    // Code blocks with ```
    html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      return `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`;
    });

    // Inline code `code`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Bold **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic *text*
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Horizontal rule
    html = html.replace(/^---$/gim, '<hr>');

    // Blockquotes
    html = html.replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>');

    // Unordered lists
    html = html.replace(/^\* (.*$)/gim, '<li>$1</li>');
    html = html.replace(/^- (.*$)/gim, '<li>$1</li>');

    // Ordered lists
    html = html.replace(/^\d+\. (.*$)/gim, '<li>$1</li>');

    // Wrap consecutive <li> in <ul>
    html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
    html = html.replace(/<\/ul>\s*<ul>/g, '');

    // Markdown tables
    html = renderMarkdownTables(html);

    // Paragraph line breaks
    const lines = html.split('\n\n');
    html = lines.map(block => {
      const trimmed = block.trim();
      if (!trimmed) return '';
      if (trimmed.startsWith('<h') || trimmed.startsWith('<pre') ||
          trimmed.startsWith('<ul') || trimmed.startsWith('<table') ||
          trimmed.startsWith('<hr') || trimmed.startsWith('<blockquote')) {
        return trimmed;
      }
      return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
    }).join('');

    return html;
  }

  function renderMarkdownTables(text) {
    const tableRegex = /((?:\|[^\n]+\|\r?\n)+)/g;
    return text.replace(tableRegex, (match) => {
      const lines = match.trim().split('\n').map(l => l.trim()).filter(Boolean);
      if (lines.length < 2) return match;
      if (!lines[1].includes('-')) return match;

      const headerCols = lines[0].split('|').slice(1, -1).map(c => c.trim());
      const rows = lines.slice(2).map(line => {
        return line.split('|').slice(1, -1).map(c => c.trim());
      });

      let tableHtml = '<table><thead><tr>';
      headerCols.forEach(col => { tableHtml += `<th>${col}</th>`; });
      tableHtml += '</tr></thead><tbody>';

      rows.forEach(row => {
        tableHtml += '<tr>';
        row.forEach(cell => { tableHtml += `<td>${cell}</td>`; });
        tableHtml += '</tr>';
      });

      tableHtml += '</tbody></table>';
      return tableHtml;
    });
  }

  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    el.toastStack.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 150);
    }, 2800);
  }

  function formatTimestamp(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  // ---------------------------------------------------------------------------
  // Viewport Scroll Tracker
  // ---------------------------------------------------------------------------
  function checkScrollPosition() {
    const vp = el.timelineViewport;
    const scrollBottom = vp.scrollHeight - vp.scrollTop - vp.clientHeight;
    state.userScrolledUp = scrollBottom > 60;
    if (state.userScrolledUp) {
      el.btnJumpLatest.classList.remove('hidden');
    } else {
      el.btnJumpLatest.classList.add('hidden');
    }
  }

  function scrollToBottom(force = false) {
    if (force || !state.userScrolledUp) {
      el.timelineViewport.scrollTop = el.timelineViewport.scrollHeight;
    }
  }

  el.timelineViewport.addEventListener('scroll', checkScrollPosition);
  el.btnJumpLatest.addEventListener('click', () => {
    state.userScrolledUp = false;
    scrollToBottom(true);
    el.btnJumpLatest.classList.add('hidden');
  });

  // ---------------------------------------------------------------------------
  // Execution State & Run Status Chip
  // ---------------------------------------------------------------------------
  function setRunState(status, message) {
    state.runStatus = status;
    el.runStatusChip.className = `run-status-chip ${status}`;

    const labels = {
      idle: 'Ready',
      running: message || 'Executing...',
      converged: 'Converged',
      'step-limit': 'Step Limit',
      interrupted: message || 'Interrupted'
    };

    el.runStatusLabel.innerText = labels[status] || status;

    if (status === 'running') {
      el.btnSubmitTask.disabled = true;
      el.composerInput.disabled = true;
    } else {
      el.btnSubmitTask.disabled = false;
      el.composerInput.disabled = false;
    }
  }

  function updateStepCounter(step) {
    state.stepCount = step;
    el.stepCounterChip.innerText = `Step: ${step}`;
  }

  // ---------------------------------------------------------------------------
  // Backend Configuration & Engine Diagnostics
  // ---------------------------------------------------------------------------
  async function loadConfig() {
    try {
      const res = await fetch('/api/config');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.config = {
        provider_url: data.provider_url || 'http://localhost:20128/v1',
        api_key: data.api_key || '',
        active_model: data.active_model || 'antigravity/gemini-3.8-flash-tiered',
        custom_models: data.custom_models || ['antigravity/gemini-3.8-flash-tiered'],
        max_steps: data.max_steps || 8
      };
      updateUIWithConfig();
      await checkGatewayHealth();
    } catch (err) {
      console.warn('Could not load config from backend:', err);
      el.engineStatusDot.className = 'engine-dot offline';
      el.engineStatusLabel.innerText = 'Offline';
    }
  }

  function updateUIWithConfig() {
    el.composerModelIndicator.innerText = state.config.active_model || 'No model';
    el.composerStepsIndicator.innerText = state.config.max_steps || 8;

    // Populate model select in titlebar
    el.globalModelSelect.innerHTML = '';
    const models = state.config.custom_models || [];
    if (!models.includes(state.config.active_model) && state.config.active_model) {
      models.unshift(state.config.active_model);
    }
    models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      if (m === state.config.active_model) opt.selected = true;
      el.globalModelSelect.appendChild(opt);
    });

    // Populate settings modal
    el.cfgProviderUrl.value = state.config.provider_url;
    el.cfgApiKey.value = state.config.api_key;
    el.cfgMaxSteps.value = state.config.max_steps;
    renderSettingsModelsList();
  }

  function renderSettingsModelsList() {
    el.settingsModelsTagList.innerHTML = '';
    state.config.custom_models.forEach((m, idx) => {
      const row = document.createElement('div');
      row.className = 'model-tag-row';
      row.innerHTML = `
        <span>${escapeHtml(m)}</span>
        <button type="button" class="btn-del-tag" data-index="${idx}" title="Remove model">✕</button>
      `;
      row.querySelector('.btn-del-tag').addEventListener('click', () => {
        state.config.custom_models.splice(idx, 1);
        renderSettingsModelsList();
      });
      el.settingsModelsTagList.appendChild(row);
    });
  }

  async function checkGatewayHealth() {
    el.engineStatusDot.className = 'engine-dot checking';
    el.engineStatusLabel.innerText = 'Checking';
    try {
      const res = await fetch('/api/test-connection', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        el.engineStatusDot.className = 'engine-dot online';
        el.engineStatusLabel.innerText = 'Online';
      } else {
        el.engineStatusDot.className = 'engine-dot offline';
        el.engineStatusLabel.innerText = 'Offline';
      }
      return data;
    } catch (err) {
      el.engineStatusDot.className = 'engine-dot offline';
      el.engineStatusLabel.innerText = 'Offline';
      return { ok: false, message: err.message };
    }
  }

  // ---------------------------------------------------------------------------
  // Titlebar Tabs & Session Management
  // ---------------------------------------------------------------------------
  async function loadSessions() {
    try {
      const res = await fetch('/api/sessions');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.sessions = await res.json();
      renderSidebarSessions();

      // Open initial tabs
      if (state.sessions.length > 0) {
        state.openTabIds = state.sessions.slice(0, 4).map(s => s.id);
        if (state.activeSessionId && state.sessions.find(s => s.id === state.activeSessionId)) {
          if (!state.openTabIds.includes(state.activeSessionId)) {
            state.openTabIds.unshift(state.activeSessionId);
          }
          await loadSession(state.activeSessionId);
        } else {
          await loadSession(state.sessions[0].id);
        }
      } else {
        startNewSession();
      }
      renderTitlebarTabs();
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  }

  function renderTitlebarTabs() {
    el.titlebarTabsStrip.innerHTML = '';
    state.openTabIds.forEach(sessId => {
      const sess = state.sessions.find(s => s.id === sessId);
      const tab = document.createElement('div');
      tab.className = `titlebar-tab ${sessId === state.activeSessionId ? 'active' : ''}`;
      tab.dataset.sessionId = sessId;
      tab.innerHTML = `
        <span class="tab-title">${escapeHtml(sess ? sess.title : 'Run')}</span>
        <button class="tab-close" title="Close Tab">✕</button>
      `;

      tab.addEventListener('click', (e) => {
        if (e.target.closest('.tab-close')) return;
        if (sessId !== state.activeSessionId) {
          loadSession(sessId);
        }
      });

      tab.querySelector('.tab-close').addEventListener('click', (e) => {
        e.stopPropagation();
        closeTitlebarTab(sessId);
      });

      el.titlebarTabsStrip.appendChild(tab);
    });
  }

  function closeTitlebarTab(sessId) {
    state.openTabIds = state.openTabIds.filter(id => id !== sessId);
    if (state.activeSessionId === sessId) {
      if (state.openTabIds.length > 0) {
        loadSession(state.openTabIds[0]);
      } else {
        startNewSession();
      }
    } else {
      renderTitlebarTabs();
    }
  }

  function renderSidebarSessions() {
    el.sessionCountBadge.innerText = state.sessions.length;
    el.sidebarSessionList.innerHTML = '';

    if (state.sessions.length === 0) {
      el.sidebarSessionList.innerHTML = `
        <div style="padding: 10px; font-size: 11px; color: var(--text-muted); text-align: center;">
          No past runs recorded.
        </div>
      `;
      return;
    }

    state.sessions.forEach(s => {
      const row = document.createElement('div');
      row.className = `session-row ${s.id === state.activeSessionId ? 'active' : ''}`;
      row.innerHTML = `
        <span class="session-row-title">${escapeHtml(s.title || 'Untitled Run')}</span>
        <button class="btn-del-run" title="Delete run">✕</button>
      `;

      row.addEventListener('click', (e) => {
        if (e.target.closest('.btn-del-run')) return;
        if (!state.openTabIds.includes(s.id)) {
          state.openTabIds.push(s.id);
        }
        loadSession(s.id);
      });

      row.querySelector('.btn-del-run').addEventListener('click', async (e) => {
        e.stopPropagation();
        await deleteSession(s.id);
      });

      el.sidebarSessionList.appendChild(row);
    });
  }

  async function loadSession(sessionId) {
    if (state.isStreaming) {
      showToast('Agent is currently running', 'error');
      return;
    }

    try {
      const res = await fetch(`/api/sessions/${sessionId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const session = await res.json();

      state.activeSessionId = session.id;
      state.activeSessionTitle = session.title || 'Untitled Run';
      localStorage.setItem('limen_session_id', session.id);

      el.streamSessionTitle.innerText = state.activeSessionTitle;
      renderSidebarSessions();
      renderTitlebarTabs();

      // Clear stream and artifacts
      el.executionStreamList.innerHTML = '';
      state.artifacts = [];
      updateArtifactsInspector();
      updateStepCounter(0);

      const turns = session.turns || [];
      if (turns.length === 0) {
        el.idleTerminalCard.classList.remove('hidden');
        setRunState('idle');
      } else {
        el.idleTerminalCard.classList.add('hidden');
        turns.forEach(turn => {
          if (turn.role === 'user') {
            renderUserTurnDOM(turn.content, turn.timestamp);
          } else if (turn.role === 'assistant') {
            renderHistoricalAssistantTurnDOM(turn);
          }
        });
        setRunState('idle');
      }

      scrollToBottom(true);
    } catch (err) {
      console.error('Error loading session:', err);
      showToast(`Could not load run: ${err.message}`, 'error');
    }
  }

  function startNewSession() {
    if (state.isStreaming) {
      showToast('Wait for run to complete', 'error');
      return;
    }

    state.activeSessionId = '';
    state.activeSessionTitle = 'New Run';
    localStorage.removeItem('limen_session_id');

    el.streamSessionTitle.innerText = 'New Run';
    el.executionStreamList.innerHTML = '';
    el.idleTerminalCard.classList.remove('hidden');
    state.artifacts = [];
    updateArtifactsInspector();
    updateStepCounter(0);

    renderSidebarSessions();
    renderTitlebarTabs();
    setRunState('idle');
    el.composerInput.focus();
  }

  async function deleteSession(sessionId) {
    try {
      const res = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      state.sessions = state.sessions.filter(s => s.id !== sessionId);
      state.openTabIds = state.openTabIds.filter(id => id !== sessionId);

      if (state.activeSessionId === sessionId) {
        if (state.openTabIds.length > 0) {
          await loadSession(state.openTabIds[0]);
        } else if (state.sessions.length > 0) {
          await loadSession(state.sessions[0].id);
        } else {
          startNewSession();
        }
      } else {
        renderSidebarSessions();
        renderTitlebarTabs();
      }
      showToast('Run deleted', 'info');
    } catch (err) {
      showToast(`Delete failed: ${err.message}`, 'error');
    }
  }

  // ---------------------------------------------------------------------------
  // DOM Rendering: User & Assistant Conversation Turns
  // ---------------------------------------------------------------------------
  function renderUserTurnDOM(content, timestamp) {
    const userBlock = document.createElement('div');
    userBlock.className = 'bubble-user';
    userBlock.innerHTML = `
      <div class="bubble-user-meta">
        <span>TASK INSTRUCTION</span>
        <span>${formatTimestamp(timestamp || Date.now() / 1000)}</span>
      </div>
      <div>${escapeHtml(content)}</div>
    `;
    el.executionStreamList.appendChild(userBlock);
    scrollToBottom();
  }

  function createStreamingTurnDOM() {
    const block = document.createElement('div');
    block.className = 'turn-block streaming';

    const header = document.createElement('div');
    header.className = 'turn-block-header';
    header.innerHTML = `
      <div class="header-identity">
        <span class="header-spinner"></span>
        <span class="header-status-label" id="stream-status-label">Deciding action...</span>
      </div>
      <span class="monospace" style="font-size: 10.5px; color: var(--text-muted);">${formatTimestamp(Date.now() / 1000)}</span>
    `;

    // Reasoning Drawer
    const reasoningDrawer = document.createElement('details');
    reasoningDrawer.className = 'reasoning-drawer hidden';
    reasoningDrawer.open = true;
    reasoningDrawer.innerHTML = `
      <summary class="reasoning-summary">
        <span class="reasoning-dot"></span>
        <span>Reasoning &amp; Strategy</span>
      </summary>
      <div class="reasoning-text"></div>
    `;

    // Tool stack
    const toolStack = document.createElement('div');
    toolStack.className = 'tool-disclosure-stack hidden';

    // Prose output
    const proseOutput = document.createElement('div');
    proseOutput.className = 'turn-prose hidden';

    // Terminal State Banner
    const terminalBanner = document.createElement('div');
    terminalBanner.className = 'terminal-state-banner hidden';

    block.appendChild(header);
    block.appendChild(reasoningDrawer);
    block.appendChild(toolStack);
    block.appendChild(proseOutput);
    block.appendChild(terminalBanner);

    el.executionStreamList.appendChild(block);
    scrollToBottom();

    return {
      root: block,
      statusLabel: header.querySelector('#stream-status-label'),
      reasoningDrawer: reasoningDrawer,
      reasoningText: reasoningDrawer.querySelector('.reasoning-text'),
      toolStack: toolStack,
      proseOutput: proseOutput,
      terminalBanner: terminalBanner,
      toolInvocations: new Map()
    };
  }

  function renderHistoricalAssistantTurnDOM(turnData) {
    const block = document.createElement('div');
    block.className = 'turn-block';

    const header = document.createElement('div');
    header.className = 'turn-block-header';
    header.innerHTML = `
      <div class="header-identity">
        <span>Limen Agent</span>
      </div>
      <span class="monospace" style="font-size: 10.5px; color: var(--text-muted);">${formatTimestamp(turnData.timestamp)}</span>
    `;
    block.appendChild(header);

    // Reasoning
    if (turnData.thoughts && turnData.thoughts.trim()) {
      const drawer = document.createElement('details');
      drawer.className = 'reasoning-drawer';
      drawer.innerHTML = `
        <summary class="reasoning-summary">
          <span class="reasoning-dot"></span>
          <span>Reasoning Process</span>
        </summary>
        <div class="reasoning-text">${escapeHtml(turnData.thoughts)}</div>
      `;
      block.appendChild(drawer);
    }

    // Tools
    if (turnData.tools && turnData.tools.length > 0) {
      const toolStack = document.createElement('div');
      toolStack.className = 'tool-disclosure-stack';
      turnData.tools.forEach((t, idx) => {
        const card = createToolRowElement(t.step || (idx + 1), t.tool_name || 'tool', t.status || 'success', t.args || {}, t.result_summary || '');
        toolStack.appendChild(card);
      });
      block.appendChild(toolStack);
    }

    // Plan artifact table
    if (turnData.plan_artifact && turnData.plan_artifact.columns && turnData.plan_artifact.rows) {
      addArtifactToInspector(turnData.plan_artifact.columns, turnData.plan_artifact.rows);
    }

    // Final prose
    if (turnData.content && turnData.content.trim()) {
      const prose = document.createElement('div');
      prose.className = 'turn-prose';
      prose.innerHTML = safeMarkdown(turnData.content);
      block.appendChild(prose);
    }

    el.executionStreamList.appendChild(block);
  }

  // ---------------------------------------------------------------------------
  // 4-Tier Progressive Tool Row Component (Section 14 Specification)
  // ---------------------------------------------------------------------------
  function createToolRowElement(step, toolName, status, args, summary) {
    const card = document.createElement('div');
    card.className = `tool-row-card ${status}`;

    const argsCompact = typeof args === 'object' ? JSON.stringify(args).slice(0, 65) : String(args);
    const argsJson = typeof args === 'string' ? args : JSON.stringify(args, null, 2);

    let statusBadge = '';
    if (status === 'running') {
      statusBadge = '<span class="status-badge-mini running">running...</span>';
    } else if (status === 'success') {
      statusBadge = '<span class="status-badge-mini success">✓ done</span>';
    } else {
      statusBadge = '<span class="status-badge-mini error">✕ error</span>';
    }

    card.innerHTML = `
      <!-- Tier 1: 24px Summary Row with Hover Icon-to-Chevron Morph (Section 14.2) -->
      <div class="tier1-summary-row" title="Click to expand details">
        <div class="row-left">
          <span class="morph-box">
            <svg class="morph-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline></svg>
            <span class="morph-chevron">›</span>
          </span>
          <span class="tool-name-mono">${escapeHtml(toolName)}</span>
          <span class="tool-arg-preview">${escapeHtml(argsCompact)}</span>
        </div>
        <div class="row-right">
          ${statusBadge}
          <button type="button" class="btn-open-inspector-link" title="Open in Inspector Pane">Inspect ↗</button>
        </div>
      </div>

      <!-- Tier 2: Inline visible result summary bar (visible without click) -->
      ${summary ? `<div class="tier2-result-bar"><span class="result-lead">↳</span>${escapeHtml(summary)}</div>` : ''}

      <!-- Tier 4: Crimson error bar if error occurred -->
      ${status === 'error' ? `<div class="tier4-error-alert"><strong>Failure:</strong> ${escapeHtml(summary || 'Execution error')}</div>` : ''}

      <!-- Tier 3: Expandable quick preview -->
      <div class="tier3-inline-details">
        <pre class="details-pre"><code>${escapeHtml(argsJson)}</code></pre>
      </div>
    `;

    // Click on row expands inline details
    card.querySelector('.tier1-summary-row').addEventListener('click', (e) => {
      if (e.target.closest('.btn-open-inspector-link')) return;
      card.classList.toggle('expanded');
    });

    // Inspect button opens right-hand inspector pane
    card.querySelector('.btn-open-inspector-link').addEventListener('click', (e) => {
      e.stopPropagation();
      openToolInInspector(step, toolName, status, args, summary);
    });

    return card;
  }

  function updateToolRowElement(card, step, toolName, status, args, summary) {
    card.className = `tool-row-card ${status}`;

    const argsCompact = typeof args === 'object' ? JSON.stringify(args).slice(0, 65) : String(args);
    const argsJson = typeof args === 'string' ? args : JSON.stringify(args, null, 2);

    let statusBadge = '';
    if (status === 'running') {
      statusBadge = '<span class="status-badge-mini running">running...</span>';
    } else if (status === 'success') {
      statusBadge = '<span class="status-badge-mini success">✓ done</span>';
    } else {
      statusBadge = '<span class="status-badge-mini error">✕ error</span>';
    }

    card.innerHTML = `
      <div class="tier1-summary-row" title="Click to expand details">
        <div class="row-left">
          <span class="morph-box">
            <svg class="morph-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline></svg>
            <span class="morph-chevron">›</span>
          </span>
          <span class="tool-name-mono">${escapeHtml(toolName)}</span>
          <span class="tool-arg-preview">${escapeHtml(argsCompact)}</span>
        </div>
        <div class="row-right">
          ${statusBadge}
          <button type="button" class="btn-open-inspector-link" title="Open in Inspector Pane">Inspect ↗</button>
        </div>
      </div>

      ${summary ? `<div class="tier2-result-bar"><span class="result-lead">↳</span>${escapeHtml(summary)}</div>` : ''}

      ${status === 'error' ? `<div class="tier4-error-alert"><strong>Failure:</strong> ${escapeHtml(summary || 'Execution error')}</div>` : ''}

      <div class="tier3-inline-details">
        <pre class="details-pre"><code>${escapeHtml(argsJson)}</code></pre>
      </div>
    `;

    card.querySelector('.tier1-summary-row').addEventListener('click', (e) => {
      if (e.target.closest('.btn-open-inspector-link')) return;
      card.classList.toggle('expanded');
    });

    card.querySelector('.btn-open-inspector-link').addEventListener('click', (e) => {
      e.stopPropagation();
      openToolInInspector(step, toolName, status, args, summary);
    });
  }

  // ---------------------------------------------------------------------------
  // Right Inspector Pane Management (Section 16 Specification)
  // ---------------------------------------------------------------------------
  function openToolInInspector(step, toolName, status, args, summary) {
    el.paneInspector.classList.remove('hidden-pane');
    el.btnToggleInspector.classList.add('active');

    // Switch to tool inspector tab
    switchInspectorTab('tool_call');

    el.emptyToolInspector.classList.add('hidden');
    el.toolInspectionDetails.classList.remove('hidden');

    el.inspectToolName.innerText = toolName;
    el.inspectToolStatus.innerText = status;
    el.inspectToolStatus.className = `meta-val status-badge-mini ${status}`;
    el.inspectToolStep.innerText = `Step ${step}`;

    const argsText = typeof args === 'string' ? args : JSON.stringify(args, null, 2);
    el.inspectToolArgs.innerText = argsText;
    el.inspectToolOutput.innerText = summary || 'No output recorded';

    state.selectedToolForInspect = { step, toolName, status, args: argsText, output: summary };
  }

  function addArtifactToInspector(columns, rows) {
    state.artifacts.push({ columns, rows, timestamp: Date.now() / 1000 });
    updateArtifactsInspector();
    // Auto switch to artifacts tab if pane is visible
    switchInspectorTab('artifacts');
  }

  function updateArtifactsInspector() {
    el.artifactsCountPill.innerText = state.artifacts.length;
    if (state.artifacts.length === 0) {
      el.emptyArtifacts.classList.remove('hidden');
      el.artifactsContentContainer.classList.add('hidden');
      el.artifactsContentContainer.innerHTML = '';
      return;
    }

    el.emptyArtifacts.classList.add('hidden');
    el.artifactsContentContainer.classList.remove('hidden');
    el.artifactsContentContainer.innerHTML = '';

    state.artifacts.forEach((art, idx) => {
      const block = document.createElement('div');
      block.className = 'artifact-block';

      let tableHtml = `
        <div class="artifact-block-header">
          <span class="artifact-block-title">Artifact #${idx + 1} (${art.rows.length} rows)</span>
          <span class="monospace" style="color: var(--text-muted); font-size: 10px;">${art.columns.length} columns</span>
        </div>
        <div class="artifact-table-scroll">
          <table class="artifact-table">
            <thead><tr>
      `;

      art.columns.forEach(c => { tableHtml += `<th>${escapeHtml(c)}</th>`; });
      tableHtml += '</tr></thead><tbody>';

      art.rows.forEach(r => {
        tableHtml += '<tr>';
        art.columns.forEach(c => {
          const val = r[c] !== undefined ? r[c] : '';
          tableHtml += `<td>${escapeHtml(typeof val === 'object' ? JSON.stringify(val) : String(val))}</td>`;
        });
        tableHtml += '</tr>';
      });

      tableHtml += '</tbody></table></div>';
      block.innerHTML = tableHtml;
      el.artifactsContentContainer.appendChild(block);
    });
  }

  function logTelemetryEvent(ev) {
    el.telemetryEmpty.classList.add('hidden');
    const entry = document.createElement('div');
    entry.className = `telemetry-entry ${ev.type}`;
    entry.innerText = `[${formatTimestamp(Date.now() / 1000)}] [${ev.type}] ${JSON.stringify(ev)}`;
    el.telemetryLogScroll.appendChild(entry);
    el.telemetryLogScroll.scrollTop = el.telemetryLogScroll.scrollHeight;
  }

  function switchInspectorTab(tabName) {
    [el.tabBtnArtifacts, el.tabBtnTool, el.tabBtnTelemetry].forEach(btn => btn.classList.remove('active'));
    [el.viewArtifacts, el.viewToolCall, el.viewTelemetry].forEach(view => view.classList.remove('active'));

    if (tabName === 'artifacts') {
      el.tabBtnArtifacts.classList.add('active');
      el.viewArtifacts.classList.add('active');
    } else if (tabName === 'tool_call') {
      el.tabBtnTool.classList.add('active');
      el.viewToolCall.classList.add('active');
    } else if (tabName === 'telemetry') {
      el.tabBtnTelemetry.classList.add('active');
      el.viewTelemetry.classList.add('active');
    }
  }

  el.tabBtnArtifacts.addEventListener('click', () => switchInspectorTab('artifacts'));
  el.tabBtnTool.addEventListener('click', () => switchInspectorTab('tool_call'));
  el.tabBtnTelemetry.addEventListener('click', () => switchInspectorTab('telemetry'));

  el.btnToggleInspector.addEventListener('click', () => {
    el.paneInspector.classList.toggle('hidden-pane');
    el.btnToggleInspector.classList.toggle('active', !el.paneInspector.classList.contains('hidden-pane'));
  });

  el.btnCloseInspector.addEventListener('click', () => {
    el.paneInspector.classList.add('hidden-pane');
    el.btnToggleInspector.classList.remove('active');
  });

  el.btnCopyArgs.addEventListener('click', () => {
    if (state.selectedToolForInspect) {
      navigator.clipboard.writeText(state.selectedToolForInspect.args);
      showToast('Arguments copied to clipboard', 'info');
    }
  });

  el.btnCopyOutput.addEventListener('click', () => {
    if (state.selectedToolForInspect) {
      navigator.clipboard.writeText(state.selectedToolForInspect.output);
      showToast('Output copied to clipboard', 'info');
    }
  });

  // ---------------------------------------------------------------------------
  // SSE Streaming Execution Loop
  // ---------------------------------------------------------------------------
  async function executeAgentTask(instruction) {
    if (!instruction || !instruction.trim() || state.isStreaming) return;

    el.idleTerminalCard.classList.add('hidden');
    state.userScrolledUp = false;

    renderUserTurnDOM(instruction, Date.now() / 1000);
    el.composerInput.value = '';
    autoResizeTextarea(el.composerInput);

    const stream = createStreamingTurnDOM();
    state.isStreaming = true;
    setRunState('running', 'Starting loop...');

    const modelToUse = el.globalModelSelect.value || state.config.active_model;
    state.abortController = new AbortController();
    let streamCompletedNormally = false;

    try {
      const response = await fetch('/api/agent/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instruction: instruction.trim(),
          session_id: state.activeSessionId || null,
          model: modelToUse
        }),
        signal: state.abortController.signal
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split('\n\n');
        buffer = chunks.pop();

        for (const block of chunks) {
          const trimmed = block.trim();
          if (!trimmed.startsWith('data:')) continue;
          const jsonStr = trimmed.replace(/^data:\s*/, '');
          try {
            const event = JSON.parse(jsonStr);
            logTelemetryEvent(event);
            handleAgentEvent(event, stream);
            if (event.type === 'done') streamCompletedNormally = true;
          } catch (parseErr) {
            console.warn('Failed to parse SSE JSON chunk:', jsonStr);
          }
        }
      }

      if (buffer.trim().startsWith('data:')) {
        try {
          const event = JSON.parse(buffer.trim().replace(/^data:\s*/, ''));
          logTelemetryEvent(event);
          handleAgentEvent(event, stream);
          if (event.type === 'done') streamCompletedNormally = true;
        } catch (e) {}
      }

      if (!streamCompletedNormally) {
        handleStreamDisconnect(stream, 'Stream disconnected prematurely before done confirmation.');
      }
    } catch (fetchErr) {
      console.error('Fetch stream error:', fetchErr);
      handleStreamDisconnect(stream, fetchErr.name === 'AbortError' ? 'Execution aborted.' : `Transport Error: ${fetchErr.message}`);
    } finally {
      state.isStreaming = false;
      state.abortController = null;
      stream.root.classList.remove('streaming');
      loadSessionsSidebarOnly();
    }
  }

  function handleAgentEvent(ev, stream) {
    if (ev.step) updateStepCounter(ev.step);

    switch (ev.type) {
      case 'tool_call': {
        stream.toolStack.classList.remove('hidden');
        const step = ev.step || 1;
        const toolName = ev.tool_name || 'tool';
        const status = ev.status || 'running';
        const args = ev.args || {};
        const summary = ev.result_summary || '';

        const key = `${step}_${toolName}`;
        if (status === 'running') {
          stream.statusLabel.innerText = `Step ${step}: running ${toolName}...`;
          setRunState('running', `Step ${step}: ${toolName}...`);

          const card = createToolRowElement(step, toolName, status, args, summary);
          stream.toolInvocations.set(key, card);
          stream.toolStack.appendChild(card);
        } else {
          const existingCard = stream.toolInvocations.get(key);
          if (existingCard) {
            updateToolRowElement(existingCard, step, toolName, status, args, summary);
          } else {
            const card = createToolRowElement(step, toolName, status, args, summary);
            stream.toolStack.appendChild(card);
          }
          stream.statusLabel.innerText = `Step ${step}: observed ${toolName}`;
          setRunState('running', `Step ${step}: observed ${toolName}`);
        }
        scrollToBottom();
        break;
      }

      case 'thought': {
        stream.reasoningDrawer.classList.remove('hidden');
        stream.reasoningText.innerText += ev.content;
        scrollToBottom();
        break;
      }

      case 'plan_artifact': {
        if (ev.columns && ev.rows) {
          addArtifactToInspector(ev.columns, ev.rows);
        }
        break;
      }

      case 'final_answer': {
        stream.proseOutput.classList.remove('hidden');
        stream.proseOutput.innerHTML = safeMarkdown(ev.content);
        stream.statusLabel.innerText = ev.converged ? 'Goal reached & converged' : 'Execution incomplete';

        stream.terminalBanner.classList.remove('hidden');
        if (ev.converged) {
          stream.terminalBanner.className = 'terminal-state-banner converged';
          stream.terminalBanner.innerHTML = `
            <span>✓ Goal Reached &amp; Converged</span>
            <span class="monospace" style="font-size: 10px;">Step ${ev.step}</span>
          `;
          setRunState('converged');
        } else {
          stream.terminalBanner.className = 'terminal-state-banner step-limit';
          stream.terminalBanner.innerHTML = `
            <span>⚠ Incomplete — Max Execution Steps Reached</span>
            <span class="monospace" style="font-size: 10px;">Step ${ev.step}</span>
          `;
          setRunState('step-limit');
        }
        scrollToBottom();
        break;
      }

      case 'error': {
        const errorCard = document.createElement('div');
        errorCard.className = 'terminal-state-banner interrupted';
        errorCard.innerHTML = `
          <span>✕ Runtime Error: ${escapeHtml(ev.message)}</span>
          <span class="monospace" style="font-size: 10px;">Step ${ev.step || '?'}</span>
        `;
        stream.root.appendChild(errorCard);
        scrollToBottom();
        break;
      }

      case 'done': {
        if (ev.session_id) {
          state.activeSessionId = ev.session_id;
          localStorage.setItem('limen_session_id', ev.session_id);
        }
        if (!ev.converged && state.runStatus !== 'step-limit') {
          setRunState('step-limit');
        } else if (ev.converged) {
          setRunState('converged');
        }
        break;
      }
    }
  }

  function handleStreamDisconnect(stream, errorMsg) {
    stream.terminalBanner.classList.remove('hidden');
    stream.terminalBanner.className = 'terminal-state-banner interrupted';
    stream.terminalBanner.innerHTML = `
      <span>✕ ${escapeHtml(errorMsg)}</span>
      <span class="monospace" style="font-size: 10px;">Transport Drop</span>
    `;
    setRunState('interrupted', errorMsg);
    scrollToBottom();
  }

  async function loadSessionsSidebarOnly() {
    try {
      const res = await fetch('/api/sessions');
      if (res.ok) {
        state.sessions = await res.json();
        renderSidebarSessions();
        renderTitlebarTabs();
      }
    } catch (e) {}
  }

  // ---------------------------------------------------------------------------
  // Textarea Auto-Resize & Composer Keybindings (Section 15 Specification)
  // ---------------------------------------------------------------------------
  function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
  }

  el.composerInput.addEventListener('input', () => autoResizeTextarea(el.composerInput));

  el.composerInput.addEventListener('keydown', (e) => {
    // Enter without shift submits; Shift+Enter creates newline
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      el.composerForm.dispatchEvent(new Event('submit', { cancelable: true }));
    }
  });

  el.composerForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const task = el.composerInput.value.trim();
    if (task) {
      executeAgentTask(task);
    }
  });

  // Prompt templates from idle terminal card
  document.querySelectorAll('.template-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const p = chip.dataset.prompt;
      if (p) {
        el.composerInput.value = p;
        autoResizeTextarea(el.composerInput);
        el.composerInput.focus();
      }
    });
  });

  // Global Shortcuts: Ctrl+K new tab
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      startNewSession();
    }
  });

  el.btnNewTab.addEventListener('click', startNewSession);

  // Rail View Toggles
  el.railBtnSessions.addEventListener('click', () => {
    el.workbenchSidebar.classList.toggle('collapsed');
  });
  el.railBtnTools.addEventListener('click', () => {
    el.paneInspector.classList.remove('hidden-pane');
    el.btnToggleInspector.classList.add('active');
    switchInspectorTab('tool_call');
  });
  el.railBtnTelemetry.addEventListener('click', () => {
    el.paneInspector.classList.remove('hidden-pane');
    el.btnToggleInspector.classList.add('active');
    switchInspectorTab('telemetry');
  });
  el.railBtnSettings.addEventListener('click', openSettingsModal);

  // ---------------------------------------------------------------------------
  // Settings Modal Controls
  // ---------------------------------------------------------------------------
  function openSettingsModal() {
    el.modalSettings.classList.remove('hidden');
    el.cfgProviderUrl.value = state.config.provider_url;
    el.cfgApiKey.value = state.config.api_key;
    el.cfgMaxSteps.value = state.config.max_steps;
    renderSettingsModelsList();
  }

  function closeSettingsModal() {
    el.modalSettings.classList.add('hidden');
  }

  el.btnOpenSettings.addEventListener('click', openSettingsModal);
  el.btnCloseSettings.addEventListener('click', closeSettingsModal);
  el.btnCancelSettings.addEventListener('click', closeSettingsModal);

  el.btnAddModel.addEventListener('click', () => {
    const val = el.inputAddModel.value.trim();
    if (val && !state.config.custom_models.includes(val)) {
      state.config.custom_models.push(val);
      renderSettingsModelsList();
      el.inputAddModel.value = '';
    }
  });

  el.btnPingGateway.addEventListener('click', async () => {
    el.diagnosticLog.className = 'diagnostic-log';
    el.diagnosticLog.innerText = `Pinging ${el.cfgProviderUrl.value}...`;
    const res = await checkGatewayHealth();
    if (res.ok) {
      el.diagnosticLog.className = 'diagnostic-log success';
      el.diagnosticLog.innerText = `Status 200 OK: ${res.message}\nDiscovered Models:\n${(res.discovered_models || []).slice(0, 6).join(', ')}`;
    } else {
      el.diagnosticLog.className = 'diagnostic-log error';
      el.diagnosticLog.innerText = `Connection Failed: ${res.message}`;
    }
  });

  el.btnSaveSettings.addEventListener('click', async () => {
    const payload = {
      provider_url: el.cfgProviderUrl.value.trim(),
      api_key: el.cfgApiKey.value.trim(),
      max_steps: parseInt(el.cfgMaxSteps.value, 10) || 8,
      custom_models: state.config.custom_models
    };

    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      state.config.provider_url = payload.provider_url;
      state.config.api_key = payload.api_key;
      state.config.max_steps = payload.max_steps;
      updateUIWithConfig();
      closeSettingsModal();
      showToast('Configuration applied', 'success');
      await checkGatewayHealth();
    } catch (err) {
      showToast(`Save failed: ${err.message}`, 'error');
    }
  });

  el.btnTitlebarPing.addEventListener('click', async () => {
    const res = await checkGatewayHealth();
    showToast(res.ok ? 'Gateway is online' : 'Gateway is offline', res.ok ? 'success' : 'error');
  });

  // ---------------------------------------------------------------------------
  // Deterministic Fixtures Harness
  // ---------------------------------------------------------------------------
  window.limenFixtures = {
    loadIdleState: () => {
      startNewSession();
    },

    loadRunningState: () => {
      el.idleTerminalCard.classList.add('hidden');
      el.executionStreamList.innerHTML = '';
      renderUserTurnDOM('Check stock_level against reorder_threshold and calculate deficit unit cost.', Date.now() / 1000 - 10);
      updateStepCounter(2);

      const stream = createStreamingTurnDOM();
      stream.reasoningDrawer.classList.remove('hidden');
      stream.reasoningText.innerText = 'Querying database parameters to check if reorder threshold has been breached.';

      stream.toolStack.classList.remove('hidden');
      stream.toolStack.appendChild(createToolRowElement(1, 'mock_lookup', 'success', { key: 'stock_level' }, '30'));
      stream.toolStack.appendChild(createToolRowElement(1, 'mock_lookup', 'success', { key: 'reorder_threshold' }, '50'));
      stream.toolStack.appendChild(createToolRowElement(2, 'calculator', 'running', { expression: '50 - 30' }, ''));

      setRunState('running', 'Step 2: calculating deficit...');
      scrollToBottom(true);
    },

    loadConvergedSuccessState: () => {
      el.idleTerminalCard.classList.add('hidden');
      el.executionStreamList.innerHTML = '';
      renderUserTurnDOM('Look up unit_cost and item_count in the database, calculate total valuation, and apply 10% discount.', Date.now() / 1000 - 60);
      updateStepCounter(4);

      const stream = createStreamingTurnDOM();
      stream.root.classList.remove('streaming');
      stream.statusLabel.innerText = 'Execution converged';

      stream.reasoningDrawer.classList.remove('hidden');
      stream.reasoningText.innerText = 'Step 1: Extracted unit_cost (150) and item_count (42).\nStep 2: Calculated gross inventory (150 * 42 = 6300).\nStep 3: Applied 10% discount resulting in net valuation of $5,670.';

      stream.toolStack.classList.remove('hidden');
      stream.toolStack.appendChild(createToolRowElement(1, 'mock_lookup', 'success', { key: 'unit_cost' }, '150'));
      stream.toolStack.appendChild(createToolRowElement(1, 'mock_lookup', 'success', { key: 'item_count' }, '42'));
      stream.toolStack.appendChild(createToolRowElement(2, 'calculator', 'success', { expression: '150 * 42' }, '6300'));
      stream.toolStack.appendChild(createToolRowElement(3, 'calculator', 'success', { expression: '6300 * 0.90' }, '5670.0'));

      addArtifactToInspector(
        ['Metric', 'Parameter', 'Computed Value', 'Status'],
        [
          { Metric: 'Unit Cost', Parameter: 'unit_cost', 'Computed Value': '$150.00', Status: 'Verified' },
          { Metric: 'Item Count', Parameter: 'item_count', 'Computed Value': '42 units', Status: 'Verified' },
          { Metric: 'Gross Valuation', Parameter: '150 * 42', 'Computed Value': '$6,300.00', Status: 'Calculated' },
          { Metric: 'Net Valuation', Parameter: '10% Discount', 'Computed Value': '$5,670.00', Status: 'Final' }
        ]
      );

      stream.proseOutput.classList.remove('hidden');
      stream.proseOutput.innerHTML = safeMarkdown(`### Inventory Valuation Summary\nRetrieved database parameters: **42 units** at **$150 unit cost**.\n\n* **Gross Valuation:** $6,300.00\n* **10% Discount:** -$630.00\n* **Final Net Valuation:** **$5,670.00**`);

      stream.terminalBanner.classList.remove('hidden');
      stream.terminalBanner.className = 'terminal-state-banner converged';
      stream.terminalBanner.innerHTML = `
        <span>✓ Goal Reached &amp; Converged</span>
        <span class="monospace" style="font-size: 10px;">Step 4</span>
      `;

      setRunState('converged');
      scrollToBottom(true);
    },

    loadFailureRecoveryState: () => {
      el.idleTerminalCard.classList.add('hidden');
      el.executionStreamList.innerHTML = '';
      renderUserTurnDOM('Look up secret_metric in the database. If retrieved, calculate double its value.', Date.now() / 1000 - 40);
      updateStepCounter(2);

      const stream = createStreamingTurnDOM();
      stream.root.classList.remove('streaming');
      stream.statusLabel.innerText = 'Tool failure observed honestly';

      stream.reasoningDrawer.classList.remove('hidden');
      stream.reasoningText.innerText = 'Lookup for `secret_metric` failed with DatabaseConnectionTimeout. Acknowledging failure without fabricating values.';

      stream.toolStack.classList.remove('hidden');
      stream.toolStack.appendChild(createToolRowElement(1, 'mock_lookup', 'error', { key: 'secret_metric' }, "DatabaseConnectionTimeout: Gateway failed to respond for key 'secret_metric' after 30s."));

      stream.proseOutput.classList.remove('hidden');
      stream.proseOutput.innerHTML = safeMarkdown(`### Execution Report: Database Timeout Observed\n\nThe query for \`secret_metric\` failed due to an external database gateway timeout.\n\nBecause the underlying parameter could not be retrieved, no subsequent arithmetic operations were performed.`);

      stream.terminalBanner.classList.remove('hidden');
      stream.terminalBanner.className = 'terminal-state-banner converged';
      stream.terminalBanner.innerHTML = `
        <span>✓ Handled Honest Tool Failure</span>
        <span class="monospace" style="font-size: 10px;">Step 2</span>
      `;

      setRunState('converged');
      scrollToBottom(true);
    },

    loadNonConvergenceState: () => {
      el.idleTerminalCard.classList.add('hidden');
      el.executionStreamList.innerHTML = '';
      renderUserTurnDOM('Iterate until epsilon < 0.00001 is satisfied.', Date.now() / 1000 - 90);
      updateStepCounter(8);

      const stream = createStreamingTurnDOM();
      stream.root.classList.remove('streaming');
      stream.statusLabel.innerText = 'Max step limit reached';

      stream.reasoningDrawer.classList.remove('hidden');
      stream.reasoningText.innerText = 'Maximum steps (8) reached without reaching mathematical convergence.';

      stream.toolStack.classList.remove('hidden');
      for (let i = 1; i <= 4; i++) {
        stream.toolStack.appendChild(createToolRowElement(i, 'calculator', 'success', { expression: `1.0 / ${i}` }, String(1.0 / i)));
      }

      stream.proseOutput.classList.remove('hidden');
      stream.proseOutput.innerHTML = safeMarkdown(`Agent reached maximum execution steps (8) without reaching a final conclusion.`);

      stream.terminalBanner.classList.remove('hidden');
      stream.terminalBanner.className = 'terminal-state-banner step-limit';
      stream.terminalBanner.innerHTML = `
        <span>⚠ Incomplete — Max Execution Steps Reached</span>
        <span class="monospace" style="font-size: 10px;">Step 8</span>
      `;

      setRunState('step-limit');
      scrollToBottom(true);
    }
  };

  // ---------------------------------------------------------------------------
  // Initialization
  // ---------------------------------------------------------------------------
  async function init() {
    await loadConfig();
    await loadSessions();

    const urlParams = new URLSearchParams(window.location.search);
    const fixture = urlParams.get('fixture');
    if (fixture === 'idle' || urlParams.has('new')) {
      window.limenFixtures.loadIdleState();
    } else if (fixture === 'running') {
      window.limenFixtures.loadRunningState();
    } else if (fixture === 'success') {
      window.limenFixtures.loadConvergedSuccessState();
    } else if (fixture === 'failure') {
      window.limenFixtures.loadFailureRecoveryState();
    } else if (fixture === 'step_limit') {
      window.limenFixtures.loadNonConvergenceState();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
