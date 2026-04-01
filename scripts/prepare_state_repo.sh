#!/usr/bin/env bash

set -euo pipefail

STATE_DIR="${1:-.state}"
STATE_BRANCH="${STATE_BRANCH:-monitor-state}"
REMOTE_URL="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"

if git clone --quiet --depth 1 --branch "${STATE_BRANCH}" "${REMOTE_URL}" "${STATE_DIR}"; then
  exit 0
fi

mkdir -p "${STATE_DIR}"
cd "${STATE_DIR}"

git init -b "${STATE_BRANCH}" >/dev/null
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git remote add origin "${REMOTE_URL}"

mkdir -p state
cat > state/state.json <<'EOF'
{
  "schema_version": 1,
  "updated_at": null,
  "feeds": {},
  "bookings": {}
}
EOF

git add state/state.json
git commit -m "Initialize booking monitor state" >/dev/null
git push --set-upstream origin "${STATE_BRANCH}" >/dev/null
