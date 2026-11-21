#!/usr/bin/env bash
# Vividora backup — consistent snapshot of /srv/studio/data (SQLite taken with the online-backup API, so it is safe while the
# server is running), packed as a dated .tar.gz; keeps the newest KEEP files. Optional: INCLUDE_MEDIA=1 also mirrors media/archive.
#
#   sudo DATA_DIR=/srv/studio/data BACKUP_DIR=/srv/studio/backups KEEP=14 scripts/backup.sh
#   copy the backups folder to another disk / PC regularly (a backup on the same disk does not survive a disk failure)
set -euo pipefail
DATA_DIR="${DATA_DIR:-/srv/studio/data}"
BACKUP_DIR="${BACKUP_DIR:-/srv/studio/backups}"
KEEP="${KEEP:-14}"
[ -d "$DATA_DIR" ] || { echo "DATA_DIR नहीं मिला: $DATA_DIR" >&2; exit 1; }
mkdir -p "$BACKUP_DIR"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
python3 - "$DATA_DIR" "$tmp/data" <<'PY'
import shutil, sqlite3, sys
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
for p in src.rglob("*"):
    rel = p.relative_to(src)
    if p.is_dir():
        (dst / rel).mkdir(parents=True, exist_ok=True)
    elif p.name.endswith(("-wal", "-shm")):
        continue                                   # folded into the snapshot below
    elif p.suffix in (".db", ".sqlite", ".sqlite3"):
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        a = sqlite3.connect(f"file:{p}?mode=ro", uri=True); b = sqlite3.connect(dst / rel)
        a.backup(b); b.close(); a.close()
    else:
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst / rel)
PY
out="$BACKUP_DIR/vividora-data-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -C "$tmp" -czf "$out" data
echo "backup: $out ($(du -h "$out" | cut -f1))"
if [ "${INCLUDE_MEDIA:-0}" = "1" ] && command -v rsync >/dev/null; then
  for d in media archive; do
    [ -d "/srv/studio/$d" ] && rsync -a --delete "/srv/studio/$d/" "$BACKUP_DIR/mirror-$d/" && echo "mirror: $d"
  done
fi
ls -1t "$BACKUP_DIR"/vividora-data-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
