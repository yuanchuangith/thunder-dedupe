/**
 * Popup script.
 */
document.addEventListener('DOMContentLoaded', () => {
  const appStatus = document.getElementById('appStatus');
  const appHint = document.getElementById('appHint');
  const interceptStatus = document.getElementById('interceptStatus');
  const interceptHint = document.getElementById('interceptHint');
  const toggleSwitch = document.getElementById('toggleSwitch');
  const testBtn = document.getElementById('testBtn');
  const openSettingsBtn = document.getElementById('openSettingsBtn');

  function setStatus(element, text, state) {
    element.textContent = text;
    element.className = `status-value ${state}`;
  }

  function setHint(element, text, isWarning = false) {
    element.textContent = text;
    element.className = isWarning ? 'status-note warning' : 'status-note';
  }

  function updateConnectionStatus() {
    chrome.runtime.sendMessage({ type: 'get_status' }, (response) => {
      if (chrome.runtime.lastError) {
        setStatus(appStatus, '通信异常', 'disconnected');
        setHint(appHint, '扩展无法读取后台状态，请重新加载扩展后再试。', true);
        return;
      }

      if (response && response.connected) {
        setStatus(appStatus, '已连接', 'connected');
        setHint(appHint, '桌面程序在线，当前可以接收复制拦截和放行请求。');
        testBtn.textContent = '重新检查连接';
      } else {
        setStatus(appStatus, '未连接', 'disconnected');
        setHint(appHint, '请先打开桌面程序，并在主页启动“WS服务”。', true);
        testBtn.textContent = '尝试连接桌面端';
      }

      testBtn.disabled = false;
    });
  }

  function syncToggleUi(enabled) {
    setStatus(interceptStatus, enabled ? '已开启' : '已关闭', enabled ? 'connected' : 'disconnected');
    setHint(
      interceptHint,
      enabled
        ? '浏览器会先拦截复制动作，再交给桌面端决定是否放行。'
        : '扩展前置拦截已关闭，复制链接时可能直接被迅雷读取。'
    );
    toggleSwitch.className = enabled ? 'toggle-switch active' : 'toggle-switch';
    toggleSwitch.setAttribute('aria-checked', String(enabled));
  }

  function loadInterceptStatus() {
    chrome.storage.local.get('enabled', (data) => {
      const enabled = data.enabled !== false;
      syncToggleUi(enabled);
    });
  }

  function toggleIntercept() {
    chrome.storage.local.get('enabled', (data) => {
      const newEnabled = data.enabled === false;
      chrome.storage.local.set({ enabled: newEnabled }, () => {
        syncToggleUi(newEnabled);
      });
    });
  }

  toggleSwitch.addEventListener('click', toggleIntercept);
  toggleSwitch.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggleIntercept();
    }
  });

  testBtn.addEventListener('click', () => {
    testBtn.disabled = true;
    testBtn.textContent = '正在检查...';

    chrome.runtime.sendMessage({ type: 'ping' }, (response) => {
      if (response && response.pong) {
        setStatus(appStatus, '连接正常', 'connected');
        setHint(appHint, '扩展后台可正常响应，正在同步最新桌面连接状态。');
      } else {
        setStatus(appStatus, '通信异常', 'disconnected');
        setHint(appHint, '扩展后台没有正确响应，请重新加载扩展后重试。', true);
      }

      updateConnectionStatus();
    });
  });

  openSettingsBtn.addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
    window.close();
  });

  updateConnectionStatus();
  loadInterceptStatus();
  setInterval(updateConnectionStatus, 5000);
});
