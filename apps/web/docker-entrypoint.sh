#!/bin/sh
set -eu

api_base_url="${AGENTGATE_API_BASE_URL:-}"
sed "s|\${AGENTGATE_API_BASE_URL}|${api_base_url}|g" \
  /usr/share/nginx/html/config.js.template > /usr/share/nginx/html/config.js
exec nginx -g "daemon off;"
