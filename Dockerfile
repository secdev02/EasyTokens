FROM python:3.12-slim

# Install nginx + PHP-FPM
# After install: configure FPM to listen on TCP 9000 and inherit container env vars
RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx php-fpm \
 && rm -rf /var/lib/apt/lists/* \
 && PHP_POOL=$(find /etc/php -name 'www.conf' -path '*/fpm/pool.d/*' | head -1) \
 && sed -i 's|^listen = .*|listen = 127.0.0.1:9000|' "$PHP_POOL" \
 && echo 'clear_env = no' >> "$PHP_POOL"

WORKDIR /app

COPY *.py .
COPY nginx.conf /etc/nginx/nginx.conf
COPY php-enrollment/ /var/www/php-enrollment/
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
 && mkdir -p /data /logs /etc/nginx/conf.d \
 && rm -f /etc/nginx/conf.d/default.conf

# 80   — nginx (domain-based victim traffic)
# 3000 — Python operator UI / direct victim access
# 8080 — PHP enrollment front-end (nginx + PHP-FPM)
EXPOSE 80 3000 8080

ENTRYPOINT ["/entrypoint.sh"]
