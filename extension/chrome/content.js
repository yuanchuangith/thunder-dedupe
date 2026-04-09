/**
 * Content script for Chrome.
 *
 * Intercepts browser copy operations before the real download link reaches the
 * system clipboard, then asks the desktop app to decide whether to allow it.
 */
(function () {
  'use strict';

  const BROWSER_SOURCE = 'chrome';
  const DEBUG_PREFIX = '[Thunder Dedupe][chrome][content]';
  const PAGE_HOOK_PREFIX = '[Thunder Dedupe][chrome][page-hook]';
  const COPY_PLACEHOLDER = '[Thunder Dedupe] Link intercepted. Allow it in the desktop app.';
  const IMPORTANT_LOG_MESSAGES = new Set([
    'content script loaded',
    'copy intercepted',
    'page clipboard api intercepted',
    'send check_link',
    'check_link response',
    'received check_result',
    'received intercept_decision',
    'extension context invalidated before sendMessage',
    'runtime message failed',
    'sendMessage threw',
    'storage.get callback failed',
    'storage.get threw',
  ]);
  const DOWNLOAD_LINK_PATTERNS = [
    /^thunder:\/\/[A-Za-z0-9+/=]+/,
    /^magnet:\?xt=urn:btih:[A-Za-z0-9]+/i,
    /^ed2k:\/\/\|file\|/i,
    /\.(torrent|mp4|mkv|avi|wmv|flv)$/i,
  ];
  const AV_CODE_PATTERNS = [
    /[A-Z]{2,6}-\d{3,5}/i,
    /[A-Z]{2,6}\d{3,5}/i,
    /[A-Z]{3,6}-\d{2,4}/i,
  ];

  const processedLinks = new Set();
  let appConnected = null;
  let interceptEnabled = true;

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

  function isExtensionContextValid() {
    try {
      return typeof chrome !== 'undefined' && Boolean(chrome.runtime && chrome.runtime.id);
    } catch (_error) {
      return false;
    }
  }

  function safeStorageGet(keys, callback) {
    if (!isExtensionContextValid() || !chrome.storage || !chrome.storage.local) {
      debugLog('extension context unavailable for storage.get');
      return false;
    }

    try {
      chrome.storage.local.get(keys, (data) => {
        if (chrome.runtime && chrome.runtime.lastError) {
          debugLog('storage.get callback failed', chrome.runtime.lastError.message);
          return;
        }

        callback(data || {});
      });
      return true;
    } catch (error) {
      debugLog('storage.get threw', error && error.message ? error.message : String(error));
      return false;
    }
  }

  function safeSendRuntimeMessage(message, callback) {
    if (!isExtensionContextValid()) {
      debugLog('extension context invalidated before sendMessage', { type: message.type });
      return false;
    }

    try {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime && chrome.runtime.lastError) {
          debugLog('runtime message failed', {
            type: message.type,
            error: chrome.runtime.lastError.message,
          });
          if (callback) {
            callback(null, chrome.runtime.lastError);
          }
          return;
        }

        if (callback) {
          callback(response, null);
        }
      });
      return true;
    } catch (error) {
      debugLog('sendMessage threw', {
        type: message.type,
        error: error && error.message ? error.message : String(error),
      });
      return false;
    }
  }

  function isDownloadLink(value) {
    if (!value) {
      return false;
    }

    return DOWNLOAD_LINK_PATTERNS.some((pattern) => pattern.test(value));
  }

  function extractAvCode(text) {
    if (!text) {
      return null;
    }

    for (const pattern of AV_CODE_PATTERNS) {
      const match = text.match(pattern);
      if (match) {
        return match[0].toUpperCase().replace(/([A-Z]+)(\d+)/, '$1-$2');
      }
    }

    return null;
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

  function loadInterceptSetting() {
    safeStorageGet('enabled', (data) => {
      interceptEnabled = data.enabled !== false;
      debugLog('intercept setting loaded', { enabled: interceptEnabled });
    });
  }

  function installStorageListener() {
    if (!isExtensionContextValid() || !chrome.storage || !chrome.storage.onChanged) {
      debugLog('extension context unavailable for storage listener');
      return;
    }

    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (areaName !== 'local' || !changes.enabled) {
        return;
      }

      interceptEnabled = changes.enabled.newValue !== false;
      debugLog('intercept setting changed', { enabled: interceptEnabled });
    });
  }

  function injectPageClipboardHook() {
    const installHook = () => {
      const script = document.createElement('script');
      script.textContent = `
        (() => {
          const debugPrefix = ${JSON.stringify(PAGE_HOOK_PREFIX)};
          const placeholder = ${JSON.stringify(COPY_PLACEHOLDER)};

          const log = (message, details) => {
            if (details === undefined) {
              console.log(debugPrefix, message);
              return;
            }

            console.log(debugPrefix, message, details);
          };

          if (window.__thunderDedupeClipboardHookInstalled) {
            return;
          }
          window.__thunderDedupeClipboardHookInstalled = true;

          const isDownloadLink = (value) => {
            if (!value || typeof value !== 'string') {
              return false;
            }

            return [
              /^thunder:\\/\\/[A-Za-z0-9+/=]+/,
              /^magnet:\\?xt=urn:btih:[A-Za-z0-9]+/i,
              /^ed2k:\\/\\/\\|file\\|/i,
              /\\.(torrent|mp4|mkv|avi|wmv|flv)$/i
            ].some((pattern) => pattern.test(value));
          };

          const postIntercept = (text, path) => {
            log('clipboard api intercepted', {
              path,
              preview: typeof text === 'string' ? text.slice(0, 120) : ''
            });

            window.postMessage({
              source: 'thunder-dedupe-page',
              type: 'clipboard-write-intercept',
              text,
              path
            }, '*');
          };

          if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            const originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
            navigator.clipboard.writeText = function(text) {
              if (isDownloadLink(text)) {
                postIntercept(text, 'writeText');
                return originalWriteText(placeholder);
              }
              return originalWriteText(text);
            };
          }

          const readClipboardItems = async (items) => {
            if (!Array.isArray(items)) {
              return null;
            }

            for (const item of items) {
              if (!item || !Array.isArray(item.types) || !item.types.includes('text/plain')) {
                continue;
              }

              try {
                const blob = await item.getType('text/plain');
                const text = await blob.text();
                if (isDownloadLink(text)) {
                  return text;
                }
              } catch (error) {
                log('failed to inspect ClipboardItem', error);
              }
            }

            return null;
          };

          const buildPlaceholderItems = () => {
            if (typeof ClipboardItem !== 'function') {
              return null;
            }

            try {
              return [
                new ClipboardItem({
                  'text/plain': new Blob([placeholder], { type: 'text/plain' })
                })
              ];
            } catch (error) {
              log('failed to build placeholder ClipboardItem', error);
              return null;
            }
          };

          if (navigator.clipboard && typeof navigator.clipboard.write === 'function') {
            const originalWrite = navigator.clipboard.write.bind(navigator.clipboard);
            navigator.clipboard.write = async function(items) {
              const interceptedText = await readClipboardItems(items);
              if (!interceptedText) {
                return originalWrite(items);
              }

              postIntercept(interceptedText, 'write');

              if (typeof navigator.clipboard.writeText === 'function') {
                return navigator.clipboard.writeText(placeholder);
              }

              const placeholderItems = buildPlaceholderItems();
              if (placeholderItems) {
                return originalWrite(placeholderItems);
              }

              return originalWrite(items);
            };
          }
        })();
      `;

      (document.documentElement || document.head || document.body).appendChild(script);
      script.remove();
    };

    if (document.documentElement || document.head || document.body) {
      installHook();
      return;
    }

    document.addEventListener('readystatechange', installHook, { once: true });
  }

  function refreshStatus() {
    safeSendRuntimeMessage({ type: 'get_status' }, (response, error) => {
      if (error) {
        appConnected = false;
        return;
      }

      appConnected = Boolean(response && response.connected);
      debugLog('refreshStatus', { connected: appConnected });
    });
  }

  function checkLink(url, avCode, options = {}) {
    debugLog('send check_link', {
      intercept: Boolean(options.intercept),
      avCode: avCode || null,
      url: summarizeValue(url),
    });

    safeSendRuntimeMessage(
      {
        type: 'check_link',
        linkContent: url,
        avCode,
        source: BROWSER_SOURCE,
        intercept: Boolean(options.intercept),
      },
      (response, error) => {
        if (error) {
          return;
        }

        appConnected = Boolean(response && response.connected);
        debugLog('check_link response', response || null);
        if (!appConnected) {
          showNotification('Desktop app is not connected, this copy stayed unchanged.', 'warning');
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
        path: 'selectedText',
      };
    }

    const selectedAnchor = findSelectedAnchor();
    if (selectedAnchor && isDownloadLink(selectedAnchor.href)) {
      return {
        url: selectedAnchor.href,
        avCode: extractAvCode(selectedAnchor.href) || extractAvCode(selectedAnchor.textContent || ''),
        path: 'selectedAnchor',
      };
    }

    if (isDownloadLink(window.__thunderDedupePendingLink || '')) {
      const pendingLink = window.__thunderDedupePendingLink;
      return {
        url: pendingLink,
        avCode: extractAvCode(pendingLink),
        path: 'contextMenuPendingLink',
      };
    }

    return null;
  }

  function interceptClick(event) {
    let target = event.target;
    if (target && target.tagName !== 'A' && target.closest) {
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
    debugLog('download link clicked', {
      avCode,
      url: summarizeValue(href),
    });
    checkLink(href, avCode, { intercept: false });
  }

  function interceptCopy(event) {
    const copied = resolveCopiedLink();
    if (!copied) {
      const selectedText = getSelectedText();
      const pendingLink = window.__thunderDedupePendingLink || '';
      if (selectedText || pendingLink) {
        debugLog('copy event fired but no downloadable link resolved', {
          selectedText: summarizeValue(selectedText),
          pendingLink: summarizeValue(pendingLink),
        });
      }
      return;
    }

    if (!interceptEnabled) {
      debugLog('copy detected but front interception is disabled', {
        avCode: copied.avCode || null,
        path: copied.path,
      });
      return;
    }

    if (appConnected === false) {
      debugLog('copy detected but desktop app is disconnected', {
        avCode: copied.avCode || null,
        url: summarizeValue(copied.url),
      });
      showNotification('Desktop app is not connected, this copy stayed unchanged.', 'warning');
      return;
    }

    if (event.clipboardData) {
      event.clipboardData.setData('text/plain', COPY_PLACEHOLDER);
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    event.stopPropagation();

    window.__thunderDedupePendingLink = null;
    debugLog('copy intercepted', {
      avCode: copied.avCode || null,
      path: copied.path,
      url: summarizeValue(copied.url),
      connected: appConnected,
    });
    checkLink(copied.url, copied.avCode, { intercept: true });
    showNotification('Copy intercepted. Wait for desktop approval before Thunder reads it.', 'warning');
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

    if (!interceptEnabled) {
      debugLog('page clipboard api detected but front interception is disabled', {
        path: data.path || 'unknown',
        url: summarizeValue(text),
      });
      return;
    }

    debugLog('page clipboard api intercepted', {
      path: data.path || 'unknown',
      avCode: extractAvCode(text),
      url: summarizeValue(text),
    });
    checkLink(text, extractAvCode(text), { intercept: true });
    showNotification('Page clipboard API intercepted. Wait for desktop approval.', 'warning');
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
      if (target && target.tagName !== 'A' && target.closest) {
        target = target.closest('a');
      }

      if (target && target.tagName === 'A' && isDownloadLink(target.href)) {
        window.__thunderDedupePendingLink = target.href;
        debugLog('context menu captured link candidate', {
          url: summarizeValue(target.href),
        });
      } else {
        window.__thunderDedupePendingLink = null;
      }
    },
    true
  );

  if (isExtensionContextValid() && chrome.runtime && chrome.runtime.onMessage) {
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
  } else {
    debugLog('extension context unavailable for runtime message listener');
  }

  function handleCheckResult(data) {
    if (!data) {
      return;
    }

    debugLog('received check_result', data);
    const { av_code: avCode, exists, file_path: filePath, error } = data;
    if (error) {
      showNotification('Link intercepted. Waiting for desktop approval.', 'warning');
      return;
    }

    if (exists) {
      showNotification(`番号： ${avCode} 已存在: ${filePath}`, 'warning');
    } else if (avCode) {
      showNotification(`番号： ${avCode} 没有扫描到已存在文件`, 'info');
    } else {
      showNotification('Link intercepted. Waiting for desktop approval.', 'warning');
    }
  }

  function handleInterceptDecision(data) {
    if (!data) {
      return;
    }

    debugLog('received intercept_decision', data);
    const { action, av_code: avCode } = data;
    if (action === 'allow') {
      showNotification(`Allowed: ${avCode || 'current link'}`, 'info');
    } else if (action === 'block') {
      showNotification(`Blocked: ${avCode || 'current link'}`, 'warning');
    }
  }

  document.addEventListener('click', interceptClick, true);

  debugLog('content script loaded', { url: location.href });
  injectPageClipboardHook();
  loadInterceptSetting();
  installStorageListener();
  refreshStatus();
  setInterval(refreshStatus, 5000);
})();
