/**
 * Content script for Chrome.
 *
 * Intercepts browser copy operations before the real download link reaches the
 * system clipboard, then asks the desktop app to decide whether to allow it.
 */
(function () {
  'use strict';

  const BROWSER_SOURCE = 'chrome';
  const COPY_PLACEHOLDER = '[Thunder Dedupe] Link intercepted. Allow it in the desktop app.';
  const processedLinks = new Set();
  let appConnected = null;

  function injectPageClipboardHook() {
    const script = document.createElement('script');
    script.textContent = `
      (() => {
        if (window.__thunderDedupeClipboardHookInstalled) {
          return;
        }
        window.__thunderDedupeClipboardHookInstalled = true;

        const placeholder = ${JSON.stringify(COPY_PLACEHOLDER)};
        const isDownloadLink = (value) => {
          if (!value || typeof value !== 'string') {
            return false;
          }

          return [
            /^thunder:\\/\\/[A-Za-z0-9+/=]+/,
            /^magnet:\\?xt=urn:btih:[A-Za-z0-9]+/i,
            /^ed2k:\\/\\/\\|file\\|/i
          ].some((pattern) => pattern.test(value));
        };

        const postIntercept = (text) => {
          window.postMessage({
            source: 'thunder-dedupe-page',
            type: 'clipboard-write-intercept',
            text
          }, '*');
        };

        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
          const originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
          navigator.clipboard.writeText = function(text) {
            if (isDownloadLink(text)) {
              postIntercept(text);
              return originalWriteText(placeholder);
            }
            return originalWriteText(text);
          };
        }
      })();
    `;

    (document.documentElement || document.head || document.body).appendChild(script);
    script.remove();
  }

  function refreshStatus() {
    chrome.runtime.sendMessage({ type: 'get_status' }, (response) => {
      if (chrome.runtime.lastError) {
        return;
      }
      appConnected = Boolean(response && response.connected);
    });
  }

  function extractAvCode(text) {
    if (!text) {
      return null;
    }

    const patterns = [
      /[A-Z]{2,6}-\d{3,5}/i,
      /[A-Z]{2,6}\d{3,5}/i,
      /[A-Z]{3,6}-\d{2,4}/i,
    ];

    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        return match[0].toUpperCase().replace(/([A-Z]+)(\d+)/, '$1-$2');
      }
    }

    return null;
  }

  function isDownloadLink(url) {
    if (!url) {
      return false;
    }

    const patterns = [
      /^thunder:\/\/[A-Za-z0-9+/=]+/,
      /^magnet:\?xt=urn:btih:[A-Za-z0-9]+/i,
      /^ed2k:\/\/\|file\|/i,
      /\.(torrent|mp4|mkv|avi|wmv|flv)$/i,
    ];

    return patterns.some((pattern) => pattern.test(url));
  }

  function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = 'thunder-dedupe-notification';
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 15px 20px;
      background: ${type === 'warning' ? '#f39c12' : type === 'error' ? '#e74c3c' : '#27ae60'};
      color: white;
      border-radius: 8px;
      font-size: 14px;
      z-index: 999999;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      transition: opacity 0.3s;
      max-width: 360px;
      line-height: 1.4;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);
    setTimeout(() => {
      notification.style.opacity = '0';
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }

  function checkLink(url, avCode, options = {}) {
    chrome.runtime.sendMessage(
      {
        type: 'check_link',
        linkContent: url,
        avCode: avCode,
        source: BROWSER_SOURCE,
        intercept: Boolean(options.intercept),
      },
      (response) => {
        if (chrome.runtime.lastError) {
          console.warn('[Thunder Dedupe] Send failed:', chrome.runtime.lastError);
          return;
        }

        appConnected = Boolean(response && response.connected);
        if (!appConnected) {
          showNotification('桌面应用未连接，本次复制没有进入放行流程', 'warning');
        }
      }
    );
  }

  function getSelectedText() {
    return (window.getSelection && window.getSelection().toString().trim()) || '';
  }

  function findSelectedAnchor() {
    const selection = window.getSelection && window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      return null;
    }

    let node = selection.anchorNode;
    if (node && node.nodeType === Node.TEXT_NODE) {
      node = node.parentElement;
    }

    if (node && typeof node.closest === 'function') {
      return node.closest('a[href]');
    }

    return null;
  }

  function resolveCopiedLink() {
    const selectedText = getSelectedText();
    if (isDownloadLink(selectedText)) {
      return {
        url: selectedText,
        avCode: extractAvCode(selectedText),
      };
    }

    const selectedAnchor = findSelectedAnchor();
    if (selectedAnchor && isDownloadLink(selectedAnchor.href)) {
      return {
        url: selectedAnchor.href,
        avCode: extractAvCode(selectedAnchor.href) || extractAvCode(selectedAnchor.textContent || ''),
      };
    }

    if (isDownloadLink(window.__thunderDedupePendingLink || '')) {
      const pendingLink = window.__thunderDedupePendingLink;
      return {
        url: pendingLink,
        avCode: extractAvCode(pendingLink),
      };
    }

    return null;
  }

  function interceptClick(event) {
    let target = event.target;
    if (target.tagName !== 'A' && target.closest) {
      target = target.closest('a');
    }

    if (!target || target.tagName !== 'A') {
      return;
    }

    const href = target.href;
    if (!isDownloadLink(href)) {
      return;
    }

    if (processedLinks.has(href)) {
      return;
    }
    processedLinks.add(href);

    const linkText = target.textContent || '';
    const avCode = extractAvCode(href) || extractAvCode(linkText);
    checkLink(href, avCode, { intercept: false });

    if (avCode) {
      showNotification(`检测到番号 ${avCode}，正在检查`, 'info');
    }
  }

  function interceptCopy(event) {
    const copied = resolveCopiedLink();
    if (!copied) {
      return;
    }

    if (appConnected === false) {
      showNotification('桌面应用未连接，本次复制保持原样', 'warning');
      return;
    }

    if (event.clipboardData) {
      event.clipboardData.setData('text/plain', COPY_PLACEHOLDER);
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    event.stopPropagation();

    window.__thunderDedupePendingLink = null;
    checkLink(copied.url, copied.avCode, { intercept: true });
    showNotification('已拦截复制，等待桌面端放行后再交给迅雷', 'warning');
  }

  window.addEventListener('message', (event) => {
    if (event.source !== window) {
      return;
    }

    const data = event.data || {};
    if (data.source !== 'thunder-dedupe-page' || data.type !== 'clipboard-write-intercept') {
      return;
    }

    const text = typeof data.text === 'string' ? data.text : '';
    if (!isDownloadLink(text)) {
      return;
    }

    checkLink(text, extractAvCode(text), { intercept: true });
    showNotification('网页复制按钮已拦截，等待桌面端放行', 'warning');
  });

  document.addEventListener(
    'copy',
    (event) => {
      interceptCopy(event);
    },
    true
  );

  document.addEventListener(
    'contextmenu',
    (event) => {
      let target = event.target;
      if (target.tagName !== 'A' && target.closest) {
        target = target.closest('a');
      }

      if (target && target.tagName === 'A' && isDownloadLink(target.href)) {
        window.__thunderDedupePendingLink = target.href;
      } else {
        window.__thunderDedupePendingLink = null;
      }
    },
    true
  );

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    switch (message.type) {
      case 'check_result':
        handleCheckResult(message.data);
        break;
      case 'intercept_decision':
        handleInterceptDecision(message.data);
        break;
      default:
        break;
    }

    sendResponse({ received: true });
    return true;
  });

  function handleCheckResult(data) {
    if (!data) {
      return;
    }

    const { av_code: avCode, exists, file_path: filePath, error } = data;
    if (error) {
      showNotification(`链接已拦截，等待桌面端放行`, 'warning');
      return;
    }

    if (exists) {
      showNotification(`番号 ${avCode} 已存在：${filePath}`, 'warning');
    } else if (avCode) {
      showNotification(`番号 ${avCode} 未下载，可决定是否放行`, 'info');
    } else {
      showNotification('链接已拦截，等待桌面端放行', 'warning');
    }
  }

  function handleInterceptDecision(data) {
    if (!data) {
      return;
    }

    const { action, av_code: avCode } = data;
    if (action === 'allow') {
      showNotification(`已放行 ${avCode || '当前链接'}`, 'info');
    } else if (action === 'block') {
      showNotification(`已拦截 ${avCode || '当前链接'}`, 'warning');
    }
  }

  document.addEventListener('click', interceptClick, true);
  injectPageClipboardHook();
  refreshStatus();
  setInterval(refreshStatus, 5000);
})();
