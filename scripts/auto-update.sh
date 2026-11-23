#!/usr/bin/env bash
# Vividora auto-update — pulls new code from GitHub and restarts, safely.
#
#   scripts/auto-update.sh          run from cron every hour; only acts inside the night window (India time)
#   scripts/auto-update.sh --now    update right now (still skips while a render is running)
#   scripts/auto-update.sh --check  only say whether an update is waiting
#
# It never interrupts work and never leaves the server broken:
#   * nothing happens while a job is queued/running or an ffmpeg is alive in the worker;
#   * local edits to tracked files are never overwritten (it stops and says so);
#   * containers are rebuilt only when server code changed (the web UI is a bind mount);
#   * after the restart /api/health must answer — otherwise it goes back to the previous commit and rebuilds that.
#
# Cron (no sudo needed):   crontab -e   →   7 * * * * /srv/studio/vividora/scripts/auto-update.sh >> $HOME/vividora-update.log 2>&1
set -u
{   # the whole script is one block, so bash has read all of it before 'git merge' may replace this file
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${UPDATE_BRANCH:-main}"
HOURS="${UPDATE_HOURS:-2 3 4}"                       # allowed hours, Asia/Kolkata
HEALTH_URL="${UPDATE_HEALTH_URL:-http://127.0.0.1:8000/api/health}"
COMPOSE=(docker compose ${UPDATE_COMPOSE_ARGS:---profile tunnel})
MODE="${1:-}"
say() { echo "[$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M')] $*"; }

cd "$DIR" || { say "repo folder not found: $DIR"; exit 1; }
exec 9>"$DIR/.auto-update.lock"
flock -n 9 || { say "another update is already running — skipped"; exit 0; }

if [ "$MODE" != "--now" ] && [ "$MODE" != "--check" ]; then
  hour=$((10#$(TZ=Asia/Kolkata date +%H)))
  case " $HOURS " in *" $hour "*) ;; *) exit 0 ;; esac
fi

git fetch --quiet origin "$BRANCH" || { say "could not reach GitHub — will try again later"; exit 0; }
PREV="$(git rev-parse HEAD)"; NEW="$(git rev-parse "origin/$BRANCH")"
if [ "$PREV" = "$NEW" ]; then [ -n "$MODE" ] && say "already up to date ($(git rev-parse --short HEAD))"; exit 0; fi
COUNT="$(git rev-list --count "$PREV..$NEW")"
if [ "$MODE" != "--now" ] && [ "$(cat "$DIR/.auto-update.failed" 2>/dev/null)" = "$NEW" ]; then exit 0; fi   # that version already failed here — wait for a newer one
if [ "$MODE" = "--check" ]; then say "$COUNT update(s) waiting:"; git log --oneline "$PREV..$NEW" | head -20; exit 0; fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  say "local changes in tracked files — not updating (see: git status). Nothing was touched."; exit 1
fi
if ! git merge-base --is-ancestor "$PREV" "$NEW"; then
  say "this server has commits GitHub does not have — not updating automatically"; exit 1
fi

busy() {
  local n
  n="$("${COMPOSE[@]}" exec -T api python -c "from vividora import db; print(db.conn().execute(\"SELECT COUNT(*) FROM jobs WHERE status IN ('running','queued')\").fetchone()[0])" 2>/dev/null | tr -dc '0-9')"
  [ -n "$n" ] && [ "$n" -gt 0 ] && return 0
  "${COMPOSE[@]}" top worker 2>/dev/null | grep -q ffmpeg && return 0
  return 1
}
if busy; then say "a render is running or queued — update postponed ($COUNT waiting)"; exit 0; fi

healthy() {
  for _ in $(seq 1 "${UPDATE_HEALTH_TRIES:-40}"); do
    curl -fsS -m 5 "$HEALTH_URL" >/dev/null 2>&1 && return 0
    sleep "${UPDATE_HEALTH_SLEEP:-3}"
  done
  return 1
}

say "updating $(git rev-parse --short "$PREV") → $(git rev-parse --short "$NEW") ($COUNT commit(s))"
git merge --quiet --ff-only "origin/$BRANCH" || { say "git could not fast-forward — nothing changed"; exit 1; }
if git diff --name-only "$PREV" "$NEW" | grep -qvE '^(web/|docs/|site/|agents/|README)'; then
  say "server code changed — rebuilding containers"
  if "${COMPOSE[@]}" up -d --build >/dev/null 2>&1 && healthy; then
    say "updated and healthy ✔"
  else
    say "new version did not come up healthy — going back to $(git rev-parse --short "$PREV")"
    git reset --quiet --hard "$PREV"
    echo "$NEW" > "$DIR/.auto-update.failed"
    if "${COMPOSE[@]}" up -d --build >/dev/null 2>&1 && healthy; then say "rolled back, the old version is running again"; else say "ROLLBACK ALSO FAILED — check: docker compose ps / logs"; fi
    exit 1
  fi
else
  say "only the web UI / docs changed — no restart needed ✔ (browsers pick it up on reload)"
fi
"${COMPOSE[@]}" exec -T api true >/dev/null 2>&1 && docker image prune -f >/dev/null 2>&1   # old images from earlier builds
exit 0
}
