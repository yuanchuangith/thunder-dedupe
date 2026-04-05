/**
 * Popup script.
 */
document.addEventListener('DOMContentLoaded', () => {
  const appStatus = document.getElementById('appStatus');
  const interceptStatus = document.getElementById('interceptStatus');
  const toggleSwitch = document.getElementById('toggleSwitch');
  const testBtn = document.getElementById('testBtn');
  const openSettingsBtn = document.getElementById('openSettingsBtn');

  function setStatus(element, text, state) {
    element.textContent = text;
    element.className = `status-value ${state}`;
  }

  function updateConnectionStatus() {
    chrome.runtime.sendMessage({ type: 'get_status' }, (response) => {
      if (chrome.runtime.lastError) {
        setStatus(appStatus, '通信异常', 'disconnected');
        return;
      }

      if (response && response.connected) {
        setStatus(appStatus, '已连接', 'connected');
        testBtn.disabled = false;
        testBtn.textContent = '测试连接';
      } else {
        setStatus(appStatus, '未连接', 'disconnected');
        testBtn.disabled = false;
        testBtn.textContent = '尝试连接';
      }
    });
  }

  function syncToggleUi(enabled) {
    setStatus(interceptStatus, enabled ? '已开启' : '已关闭', enabled ? 'connected' : 'disconnected');
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
    testBtn.textContent = '检测中...';

    chrome.runtime.sendMessage({ type: 'ping' }, (response) => {
      if (response && response.pong) {
        setStatus(appStatus, '连接正常', 'connected');
      } else {
        setStatus(appStatus, '通信异常', 'disconnected');
      }

      testBtn.disabled = false;
      testBtn.textContent = '测试连接';
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
