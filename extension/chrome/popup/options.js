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
      setStatus('已读取当前配置。修改后点击“保存并重连”即可生效。');
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
      setStatus('桌面程序地址不能为空。', 'error');
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
    setStatus('正在保存设置，并通知扩展后台重新连接桌面程序...');

    chrome.storage.local.set(config, () => {
      chrome.runtime.sendMessage({
        type: 'config_update',
        config,
      });

      saveBtn.disabled = false;
      setStatus('设置已保存。回到弹窗后点击“检查桌面连接”即可确认结果。', 'success');
    });
  });

  resetBtn.addEventListener('click', () => {
    chrome.storage.local.set(defaultConfig, () => {
      loadConfig();
      setStatus('已恢复默认连接参数。', 'success');
    });
  });

  loadConfig();
});
