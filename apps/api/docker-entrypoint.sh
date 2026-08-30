#!/bin/sh
set -eu

mkdir -p /app/data
chown -R agentgate:agentgate /app/data
exec runuser -u agentgate -- "$@"
