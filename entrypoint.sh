#!/bin/sh
set -e

# -----------------------------------------------------------------------
# DemoTokens — unified entrypoint
#
# Process layout inside the container
# ------------------------------------
#   php-fpm        — port 9000 (FastCGI), serves php-enrollment/ pages
#   nginx          — port 80 (domain campaigns) + port 8080 (PHP front-end)
#   python         — port 3000 (PORT), operator UI + victim enrollment
#
# Environment variables
# ----------------------
#   PORT              Python server port (default 3000)
#   PORT_MAX          Upper bound of campaign port range (default 3010)
#   DB_PATH           SQLite path (default /data/demotokens.db)
#   LOG_DIR           Log directory (default /logs)
#   NGINX_CONF        Config file written by nginx_helper (default /etc/nginx/conf.d/demotokens.conf)
#   NGINX_RELOAD_CMD  Command to reload nginx (default: nginx -s reload)
#   PHP_BACKEND_URL   Backend URL embedded in PHP enrollment page (default: empty = same-origin proxy)
#
# Access
# -------
#   Port 80   — nginx (domain-based victim traffic, e.g. campaign1.example.com)
#   Port 3000 — Operator UI / direct victim access (Python)
#   Port 8080 — PHP enrollment front-end (nginx → php-fpm)
# -----------------------------------------------------------------------

PORT="${PORT:-3000}"
export PORT

# Start PHP-FPM as a background daemon
echo "[entrypoint] Starting php-fpm..."
PHP_FPM=$(ls /usr/sbin/php-fpm* 2>/dev/null | head -1)
if [ -z "$PHP_FPM" ]; then
    echo "[entrypoint] WARNING: php-fpm binary not found — PHP enrollment page will not work"
else
    "$PHP_FPM" -D
    echo "[entrypoint] php-fpm started ($PHP_FPM)"
fi

# Start nginx as a background daemon (writes PID to /run/nginx.pid)
echo "[entrypoint] Starting nginx..."
nginx

echo "[entrypoint] nginx started (PID $(cat /run/nginx.pid 2>/dev/null || echo unknown))"

# Hand off to the Python server as the foreground process.
# Container lifetime is tied to Python; nginx and php-fpm are background daemons.
echo "[entrypoint] Starting DemoTokens on port ${PORT}..."
exec python main_server.py

