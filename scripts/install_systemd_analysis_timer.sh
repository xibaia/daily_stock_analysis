#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${DSA_ENV_FILE:-$REPO_ROOT/.env}"
SYSTEMD_DIR="${DSA_SYSTEMD_DIR:-/etc/systemd/system}"
SERVICE_FILE="$SYSTEMD_DIR/dsa-analysis.service"
TIMER_FILE="$SYSTEMD_DIR/dsa-analysis.timer"
DEFAULT_TIME="${DSA_SCHEDULE_TIME_DEFAULT:-18:00}"
RENDER_ONLY=false

case "${1:-}" in
    "") ;;
    --render-only) RENDER_ONLY=true ;;
    *) echo "usage: $0 [--render-only]" >&2; exit 2 ;;
esac

read_env_value() {
    key="$1"
    if [ ! -f "$ENV_FILE" ]; then
        return
    fi
    awk -v target="$key" '
        /^[[:space:]]*#/ { next }
        {
            line=$0
            name=line
            sub(/[[:space:]]*=.*/, "", name)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
            if (name != target) next
            sub(/^[^=]*=/, "", line)
            sub(/[[:space:]]+#.*$/, "", line)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
            gsub(/^['\''\"]|['\''\"]$/, "", line)
            value=line
        }
        END { if (value != "") print value }
    ' "$ENV_FILE"
}

RAW_TIMES="$(read_env_value SCHEDULE_TIMES)"
if [ -z "$RAW_TIMES" ]; then
    RAW_TIMES="$(read_env_value SCHEDULE_TIME)"
fi
if [ -z "$RAW_TIMES" ]; then
    RAW_TIMES="$DEFAULT_TIME"
fi

NORMALIZED_TIMES=""
OLD_IFS="$IFS"
IFS=','
set -- $RAW_TIMES
IFS="$OLD_IFS"
for candidate in "$@"; do
    schedule_time="$(printf '%s' "$candidate" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    case "$schedule_time" in
        [0-1][0-9]:[0-5][0-9]|2[0-3]:[0-5][0-9]) ;;
        *)
            echo "invalid schedule time '$schedule_time' in $ENV_FILE; expected HH:MM" >&2
            exit 2
            ;;
    esac
    NORMALIZED_TIMES="$NORMALIZED_TIMES $schedule_time"
done

mkdir -p "$SYSTEMD_DIR"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Daily Stock Analysis one-shot run
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=$REPO_ROOT
ExecStart=$REPO_ROOT/scripts/run_scheduled_analysis_once.sh
TimeoutStartSec=3h
EOF

{
    cat <<EOF
[Unit]
Description=Run Daily Stock Analysis in ephemeral containers

[Timer]
EOF
    for schedule_time in $NORMALIZED_TIMES; do
        printf 'OnCalendar=*-*-* %s:00\n' "$schedule_time"
    done
    cat <<EOF
Persistent=true
Unit=dsa-analysis.service

[Install]
WantedBy=timers.target
EOF
} > "$TIMER_FILE"

if [ "$RENDER_ONLY" = true ]; then
    echo "systemd units rendered in $SYSTEMD_DIR for:$NORMALIZED_TIMES"
    exit 0
fi

systemctl daemon-reload
systemctl enable --now dsa-analysis.timer
echo "dsa-analysis.timer installed for:$NORMALIZED_TIMES"
systemctl list-timers dsa-analysis.timer --no-pager
