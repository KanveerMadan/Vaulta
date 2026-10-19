#!/usr/bin/env bash
# No Vercel, Render or Firebase default host may be visible to users after launch (go-live, domain rules).
#   scripts/check-default-domains.sh [dist-dir]       the built app (default frontend/dist) and the code that writes
#                                                     emails and Telegram messages
#   scripts/check-default-domains.sh --live URL       the live site: its HTML and every script and stylesheet it loads
# Matches hostnames (name.vercel.app); the Firebase SDK's own error text mentions "firebaseapp.com" bare, which is fine.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
HOSTS='[a-z0-9-]+\.(vercel\.app|onrender\.com|firebaseapp\.com)'

if [ "${1:-}" = "--live" ]; then
  url="${2:?usage: --live https://vaulta.in}"
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  curl -fsSL "$url/" -o "$tmp/index.html"
  for p in /robots.txt /sitemap.xml /.well-known/security.txt; do curl -fsSL "$url$p" -o "$tmp/$(basename $p)" || true; done
  grep -oE '(src|href)="/[^"]+\.(js|css)"' "$tmp/index.html" | cut -d'"' -f2 | while read -r p; do
    curl -fsSL "$url$p" -o "$tmp/$(basename "$p")"
  done
  # scripts the app loads later (code-split chunks)
  grep -ohE '"?assets/[A-Za-z0-9._-]+\.js' "$tmp"/*.js 2>/dev/null | tr -d '"' | sort -u | while read -r p; do
    curl -fsSL "$url/$p" -o "$tmp/$(basename "$p")" || true
  done
  targets=("$tmp")
else
  targets=("${1:-frontend/dist}" backend/app/services/report_email.py backend/app/services/alerts.py
           backend/app/services/telegram_bot.py backend/app/api/routes/unsubscribe.py)
  [ -d "${targets[0]}" ] || { echo "no build at ${targets[0]} (npm run build first)"; exit 1; }
fi

if grep -rEo "$HOSTS" "${targets[@]}" | sort -u; then
  echo "FOUND default hosts above: users would see them"; exit 1
fi
echo "CLEAN: no vercel.app / onrender.com / firebaseapp.com hosts"
