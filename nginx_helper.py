#!/usr/bin/env python3
"""
nginx_helper — auto-generate and reload nginx reverse-proxy config for DemoTokens campaigns.

When a campaign with a domain is created, deleted, or cleared this module rewrites
NGINX_CONF and reloads nginx.  The file contains one server block per domain campaign.

Environment variables
---------------------
  NGINX_CONF        Path to write the generated config (default /etc/nginx/conf.d/demotokens.conf)
  NGINX_RELOAD_CMD  Shell command to reload nginx (default: nginx -s reload)

Set NGINX_CONF to an empty string or leave NGINX_RELOAD_CMD blank to disable automation.
"""

import os
import re
import subprocess

import db

NGINX_CONF       = os.environ.get("NGINX_CONF",       "/etc/nginx/conf.d/demotokens.conf")
NGINX_RELOAD_CMD = os.environ.get("NGINX_RELOAD_CMD", "nginx -s reload")
_DEFAULT_PORT    = int(os.environ.get("PORT", 3000))

# Strict allow-list: valid hostname characters only (prevents config injection)
_DOMAIN_RE = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
                        r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')


def is_valid_domain(domain):
    """Return True if domain contains only safe hostname characters."""
    if not domain or len(domain) > 253:
        return False
    return bool(_DOMAIN_RE.match(domain))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_conf(domain_campaigns):
    """Return nginx config text for a list of campaigns that each have a domain."""
    lines = [
        "# DemoTokens — auto-generated nginx reverse-proxy config",
        "# DO NOT EDIT — this file is overwritten on every campaign change",
        "",
    ]
    for dc in domain_campaigns:
        domain = (dc.get("domain") or "").strip()
        if not is_valid_domain(domain):
            continue
        port = int(dc.get("port") or _DEFAULT_PORT)
        lines += [
            "server {",
            "    listen 80;",
            "    server_name " + domain + ";",
            "    location / {",
            "        proxy_pass         http://127.0.0.1:" + str(port) + ";",
            "        proxy_set_header   Host              $host;",
            "        proxy_set_header   X-Real-IP         $remote_addr;",
            "        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;",
            "        proxy_read_timeout 120s;",
            "    }",
            "}",
            "",
        ]
    return "\n".join(lines)


def _reload_nginx():
    """Run NGINX_RELOAD_CMD, log the outcome.  Never raises."""
    if not NGINX_RELOAD_CMD:
        return
    try:
        result = subprocess.run(
            NGINX_RELOAD_CMD.split(),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print("[NGINX] reload failed (exit %d): %s" % (result.returncode, result.stderr.strip()))
        else:
            print("[NGINX] reloaded OK")
    except FileNotFoundError:
        print("[NGINX] nginx binary not found — skipping reload (set NGINX_RELOAD_CMD='' to suppress)")
    except subprocess.TimeoutExpired:
        print("[NGINX] reload timed out")
    except Exception as exc:
        print("[NGINX] reload error: " + str(exc))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync():
    """Regenerate NGINX_CONF from the current campaign list and reload nginx.

    Called after any campaign create / delete / clear.
    Silently skips if NGINX_CONF is empty (opt-out).
    """
    if not NGINX_CONF:
        return

    campaigns        = db.list_device_codes()
    domain_campaigns = [dc for dc in campaigns if is_valid_domain((dc.get("domain") or "").strip())]

    if not domain_campaigns:
        # No domain campaigns — remove the file so nginx doesn't serve stale blocks
        if os.path.exists(NGINX_CONF):
            try:
                os.remove(NGINX_CONF)
                print("[NGINX] removed config (no domain campaigns remain)")
                _reload_nginx()
            except Exception as exc:
                print("[NGINX] failed to remove config: " + str(exc))
        return

    conf_text = _build_conf(domain_campaigns)
    try:
        conf_dir = os.path.dirname(NGINX_CONF)
        if conf_dir:
            os.makedirs(conf_dir, exist_ok=True)
        with open(NGINX_CONF, "w") as f:
            f.write(conf_text)
        print("[NGINX] wrote config — %d server block(s) → %s" % (len(domain_campaigns), NGINX_CONF))
        _reload_nginx()
    except PermissionError:
        print("[NGINX] permission denied writing %s — run as root or set NGINX_CONF to a writable path" % NGINX_CONF)
    except Exception as exc:
        print("[NGINX] failed to write config: " + str(exc))
