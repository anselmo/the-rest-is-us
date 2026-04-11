#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${REPO_DIR}/logs"
LOG_FILE="${LOG_DIR}/$(date +%Y-%m-%d).log"
RETRY_DELAY=600

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

notify_failure() {
    osascript -e 'display notification "Pipeline failed after retry. Check logs." with title "The Rest of Us" sound name "Basso"'
}

notify_success() {
    osascript -e 'display notification "Episode ready." with title "The Rest of Us" sound name "Glass"'
}

run_pipeline() {
    cd "$REPO_DIR"
    export PATH="/Users/arodriguesdasilva/Library/Python/3.9/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    make run >> "$LOG_FILE" 2>&1
}

mkdir -p "$LOG_DIR"
log "=== Daily pipeline starting ==="

if run_pipeline; then
    log "=== Pipeline completed successfully ==="
    notify_success
    exit 0
fi

log "!!! First attempt failed, retrying in ${RETRY_DELAY}s ==="
sleep "$RETRY_DELAY"

if run_pipeline; then
    log "=== Pipeline completed on retry ==="
    notify_success
    exit 0
fi

log "!!! Pipeline failed after retry ==="
notify_failure
exit 1
