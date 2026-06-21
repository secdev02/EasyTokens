#!/bin/sh
# Stop both the main DemoTokens panel and the PHP relay

echo "[stop] Stopping php-relay..."
docker compose -f php-relay/docker-compose.yml down

echo "[stop] Stopping demotokens..."
docker compose down

echo "[stop] Done."
