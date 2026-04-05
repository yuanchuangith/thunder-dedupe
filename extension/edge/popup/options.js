/**
 * Options script.
 */
document.addEventListener('DOMContentLoaded', () => {
  const wsPortInput = document.getElementById('wsPort');
  const wsHostInput = document.getElementById('wsHost');
  const saveBtn = document.getElementById('saveBtn');
  const resetBtn = document.getElementById('resetBtn');
  const saveStatus = document.getElementById('saveStatus');

  const defaultConfig = {
    wsPort: 9876,
    wsHost: 'localhost',
    enabled: true,
  };

  function setStatus(message = '', state = '') {
    saveStatus.textContent = message;
    saveStatus.className = state ? `save-status ${state}` : 'save-status';
  }

  function loadConfig() {
    chrome.storage.local.get(defaultConfig, (data) => {
      wsPortInput.value = data.wsPort;
      wsHostInput.value = data.wsHost;
      setStatus('当前显示的是已保存配置。');
    });
  }

  function readConfigFromForm() {
    const wsPort = Number.parseInt(wsPortInput.value, 10);
    const wsHost = wsHostInput.value.trim();

    if (!Number.isInteger(wsPort) || wsPort < 1000 || wsPort > 65535) {
      setStatus('端口需要是 1000 到 65535 之间的整数。', 'error');
      wsPortInput.focus();
      return null;
    }

    if (!wsHost) {
      setStatus('桌面应用地址不能为空。', 'error');
      wsHostInput.focus();
      return null;
    }

    return { wsPort, wsHost };
  }

  saveBtn.addEventListener('click', () => {
    const config = readConfigFromForm();
    if (!config) {
      return;
    }

    saveBtn.disabled = true;
    setStatus('正在保存并通知后台重新连接...');

    chrome.storage.local.set(config, () => {
      chrome.runtime.sendMessage({
        type: 'config_update',
        config,
      });

      saveBtn.disabled = false;
      setStatus('设置已保存。重新打开弹窗即可看到最新连接状态。', 'success');
    });
  });

  resetBtn.addEventListener('click', () => {
    chrome.storage.local.set(defaultConfig, () => {
      loadConfig();
      setStatus('已恢复默认设置。', 'success');
    });
  });

  loadConfig();
});
