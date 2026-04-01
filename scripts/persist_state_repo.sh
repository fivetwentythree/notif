#!/usr/bin/env bash

set -euo pipefail

STATE_DIR="${1:-.state}"
STATE_BRANCH="${STATE_BRANCH:-monitor-state}"

cd "${STATE_DIR}"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

if [[ -z "$(git status --porcelain -- state)" ]]; then
  exit 0
fi

git add state
git commit -m "Update booking monitor state" >/dev/null
git pull --rebase origin "${STATE_BRANCH}" >/dev/null
git push origin "${STATE_BRANCH}" >/dev/null
