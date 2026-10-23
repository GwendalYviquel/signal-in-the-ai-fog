#!/usr/bin/env bash
# Runs wrangler with the Cloudflare API token kept in the macOS keychain, never in the repository
# or the shell history. Store the token once (asked hidden, template "Edit Cloudflare Workers"):
#   security add-generic-password -U -a "$USER" -s cloudflare-api-token -w
# Then, from anywhere: scheduler/wrangler.sh deploy   (or any other wrangler command)
set -euo pipefail
cd "$(dirname "$0")"
CLOUDFLARE_API_TOKEN="$(security find-generic-password -a "$USER" -s cloudflare-api-token -w)" \
  || { echo "No Cloudflare token in the keychain: see the top of scheduler/wrangler.sh"; exit 1; }
export CLOUDFLARE_API_TOKEN
exec npx --yes wrangler "$@"
