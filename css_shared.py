"""Shared CSS for Dunder Mifflin phishing pages."""

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
