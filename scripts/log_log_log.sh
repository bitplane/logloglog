#!/usr/bin/env bash
set -e

OUTPUT_FILE="logs/log.log.log"
PID_FILE=".log.pid"

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -f    Follow-only: only tail live logs, no historical"
    echo "  -k    Kill running tail process"
    echo "  -h    Show this help"
    echo ""
    echo "Default: Aggregate historical logs then start live tail"
}

kill_existing_tail() {
    if [ -f "$PID_FILE" ]; then
        if kill "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "Killed old process"
        else
            echo "Couldn't kill it. 🤷"
        fi
        rm -f "$PID_FILE"
    fi
}

old_logs() {
    # Ensure logs directory exists
    mkdir -p "$(dirname "$OUTPUT_FILE")"

    # Remove existing file
    rm -f "$OUTPUT_FILE"

    # Source venv and call Python tool for historical logs
    source .venv/bin/activate
    python -m logloglog.tools.stream_logs >> "$OUTPUT_FILE"
}

live_logs() {
    echo "Following logs..."

    # Source venv and call Python tool for live logs in background
    source .venv/bin/activate
    python -m logloglog.tools.stream_logs --follow-only >> "$OUTPUT_FILE" 2>/dev/null &

    # Save the PID
    echo $! > "$PID_FILE"

    echo "PID: $(cat "$PID_FILE")"
    echo "To cancel: make log-stop"
}

# Parse command line options
FOLLOW_ONLY=false
KILL_MODE=false

while getopts "fkh" opt; do
    case $opt in
        f)
            FOLLOW_ONLY=true
            ;;
        k)
            KILL_MODE=true
            ;;
        h)
            show_usage
            exit 0
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            show_usage
            exit 1
            ;;
    esac
done

# Execute based on mode
kill_existing_tail
if [ "$KILL_MODE" = true ]; then
    exit 0
fi

if [ "$FOLLOW_ONLY" = false ]; then
    echo "Creating $OUTPUT_FILE..."
    old_logs
fi

live_logs
echo "🪵🪵🪵: $OUTPUT_FILE"

