/**
 * Chrome extension background service worker.
 */
const BROWSER_SOURCE = 'chrome';
const DEBUG_PREFIX = '[Thunder Dedupe][chrome][bg]';
const IMPORTANT_LOG_MESSAGES = new Set([
  'websocket opened',
  'websocket closed',
  'websocket error',
  'websocket init failed',
  'sendCheckRequest',
  'sendCheckRequest skipped: websocket disconnected',
  'forwardCheckResult failed',
]);
const DEFAULT_CONFIG = {
  WS_PORT: 9876,
  WS_HOST: 'localhost',
  RECONNECT_INTERVAL: 5000,
  HEARTBEAT_INTERVAL: 30000,
};

let CONFIG = { ...DEFAULT_CONFIG };
let ws = null;
let isConnected = false;
let reconnectTimer = null;
let heartbeatTimer = null;

const connectionState = {
  connected: false,
  lastError: null,
  reconnectAttempts: 0,
};

function summarizeValue(value) {
  if (!value) {
    return '';
  }

  return value.length > 120 ? `${value.slice(0, 117)}...` : value;
}

function debugLog(message, details) {
  if (!IMPORTANT_LOG_MESSAGES.has(message)) {
    return;
  }

  if (details === undefined) {
    console.log(DEBUG_PREFIX, message);
    return;
  }

  console.log(DEBUG_PREFIX, message, details);
}

async function loadConfig() {
  try {
    const stored = await chrome.storage.local.get(['wsPort', 'wsHost']);
    CONFIG.WS_PORT = stored.wsPort || DEFAULT_CONFIG.WS_PORT;
    CONFIG.WS_HOST = stored.wsHost || DEFAULT_CONFIG.WS_HOST;
  } catch (error) {
    console.error('[Thunder Dedupe] Failed to load config:', error);
  }
}

function initWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const wsUrl = `ws://${CONFIG.WS_HOST}:${CONFIG.WS_PORT}`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      isConnected = true;
      connectionState.connected = true;
      connectionState.reconnectAttempts = 0;
      startHeartbeat();
      updateIconStatus(true);
      debugLog('websocket opened');

      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    ws.onclose = () => {
      isConnected = false;
      connectionState.connected = false;
      updateIconStatus(false);
      stopHeartbeat();
      scheduleReconnect();
      debugLog('websocket closed', {
        reconnectAttempts: connectionState.reconnectAttempts,
      });
    };

    ws.onerror = (error) => {
      connectionState.lastError = error;
      isConnected = false;
      debugLog('websocket error', error);
    };

    ws.onmessage = (event) => {
      handleMessage(JSON.parse(event.data));
    };
  } catch (error) {
    connectionState.lastError = error;
    debugLog('websocket init failed', error);
    scheduleReconnect();
  }
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (ws && isConnected) {
      ws.send(JSON.stringify({ type: 'heartbeat' }));
    }
  }, CONFIG.HEARTBEAT_INTERVAL);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function scheduleReconnect() {
  if (reconnectTimer) {
    return;
  }

  connectionState.reconnectAttempts += 1;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    initWebSocket();
  }, CONFIG.RECONNECT_INTERVAL);
}

function updateIconStatus(connected) {
  const title = connected ? 'Thunder Dedupe - Connected' : 'Thunder Dedupe - Disconnected';
  chrome.action.setTitle({ title }).catch(() => {});
}

function handleMessage(message) {
  switch (message.type) {
    case 'check_result':
      forwardCheckResult(message.data || message);
      break;
    case 'intercept_decision':
      handleDecision(message.data || message);
      break;
    case 'config_update':
      handleConfigUpdate(message.data || message);
      break;
    default:
      break;
  }
}

function handleConfigUpdate(_data) {}

function forwardCheckResult(data) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs[0]) {
      return;
    }

    chrome.tabs.sendMessage(tabs[0].id, {
      type: 'check_result',
      data,
    }).catch((error) => {
      debugLog('forwardCheckResult failed', error && error.message ? error.message : error);
    });
  });
}

function handleDecision(data) {
  if (data.action === 'allow') {
    resumeDownload(data.downloadId);
  } else if (data.action === 'block') {
    cancelDownload(data.downloadId);
  }
}

function sendCheckRequest(avCode, linkContent, source, options = {}) {
  if (!ws || !isConnected) {
    debugLog('sendCheckRequest skipped: websocket disconnected', {
      intercept: Boolean(options.intercept),
      avCode: avCode || null,
      source,
      linkContent: summarizeValue(linkContent),
    });
    return false;
  }

  debugLog('sendCheckRequest', {
    intercept: Boolean(options.intercept),
    avCode: avCode || null,
    source,
    linkContent: summarizeValue(linkContent),
  });

  ws.send(
    JSON.stringify({
      type: 'check_av',
      data: {
        av_code: avCode,
        link_content: linkContent,
        source,
        intercept: Boolean(options.intercept),
        timestamp: Date.now(),
      },
    })
  );
  return true;
}

function resumeDownload(downloadId) {
  if (downloadId) {
    chrome.downloads.resume(downloadId).catch(() => {});
  }
}

function cancelDownload(downloadId) {
  if (downloadId) {
    chrome.downloads.cancel(downloadId).catch(() => {});
  }
}

chrome.downloads.onCreated.addListener((downloadItem) => {
  const url = downloadItem.url || downloadItem.finalUrl || '';
  if (isConnected && url) {
    sendCheckRequest(null, url, BROWSER_SOURCE, { intercept: false });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'check_link': {
      const success = sendCheckRequest(
        message.avCode,
        message.linkContent,
        message.source || BROWSER_SOURCE,
        { intercept: message.intercept }
      );
      sendResponse({ success, connected: isConnected });
      break;
    }
    case 'get_status':
      sendResponse({
        connected: isConnected,
        reconnectAttempts: connectionState.reconnectAttempts,
      });
      break;
    case 'ping':
      sendResponse({ pong: true });
      break;
    default:
      sendResponse({ ok: false });
      break;
  }

  return true;
});

chrome.runtime.onInstalled.addListener(async () => {
  await loadConfig();
  initWebSocket();
  chrome.storage.local.set({
    enabled: true,
    wsPort: CONFIG.WS_PORT,
  });
});

chrome.runtime.onStartup.addListener(async () => {
  await loadConfig();
  initWebSocket();
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local' && (changes.wsPort || changes.wsHost)) {
    loadConfig().then(() => {
      if (ws) {
        ws.close();
      }
      initWebSocket();
    });
  }
});

loadConfig().then(() => {
  initWebSocket();
});
