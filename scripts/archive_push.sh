#!/usr/bin/env bash
# archive_push.sh — daily local commit of the brief archive, optional off-box push.
#
# The archive git repo lives INSIDE weather/brief/ (ignored by the parent repo).
# A public commit history makes a silently-edited past brief a visible diff —
# "never quietly fixed" becomes checkable rather than asserted.
#
# Cron (report-only, installed by the orchestrator):
#   47 6 * * * /usr/bin/python3 /home/opc/worldtwin/scripts/build_brief.py >> /var/log/wt-brief.log 2>&1
#   55 6 * * * /home/opc/worldtwin/scripts/archive_push.sh >> /var/log/wt-brief.log 2>&1
# /var/log/wt-brief.log must exist and be owned by opc (sudo touch + chown) — done 2026-09-24
#
# Push happens ONLY if a remote named "archive" exists (owner must mint a deploy
# key first — REVIVAL_V1 §5.6). A failed push never fails the cron.
set -u
BRIEF_DIR=/home/opc/worldtwin/weather/brief
LOCK=/tmp/wt-archive-push.lock

exec 9>"$LOCK" || exit 1
flock -n 9 || { echo "[archive] $(date -u +%FT%TZ) another run holds the lock — skipping"; exit 0; }

[ -d "$BRIEF_DIR" ] || { echo "[archive] $BRIEF_DIR does not exist — nothing to archive"; exit 0; }
cd "$BRIEF_DIR" || exit 1

if [ ! -d .git ]; then
    git init -b main -q || git init -q   # older git: fall back, then normalize
    git symbolic-ref HEAD refs/heads/main 2>/dev/null || true
    echo "[archive] initialised git repo in $BRIEF_DIR"
fi
git config user.name  "Earth Record archive"
git config user.email "archive@worldtwin.duckdns.org"

git add -A
if git diff --cached --quiet; then
    echo "[archive] $(date -u +%FT%TZ) no changes — nothing to commit"
else
    timeout 60 git commit -q -m "brief $(date -u +%F)" \
        && echo "[archive] $(date -u +%FT%TZ) committed brief $(date -u +%F)"
fi

if git remote get-url archive >/dev/null 2>&1; then
    timeout 120 git push --quiet archive main || echo "[archive] push failed (non-fatal)"
else
    echo "[archive] no 'archive' remote configured — local commit only (no off-box copy yet)"
fi
exit 0
