#!/usr/bin/env bash
# Hook: PostToolUse — logs tool completion with timestamp.
# Used to calculate delta (tool_start → tool_end) for approval timing analysis.
set -euo pipefail

LOG_DIR="$HOME/.claude/approval-logs"
LOG_FILE="$LOG_DIR/approvals.jsonl"

mkdir -p "$LOG_DIR"

INPUT=$(cat)

TOOL_USE_ID=$(printf '%s' "$INPUT" | jq -r '.tool_use_id // empty')

if [ -z "$TOOL_USE_ID" ]; then
  exit 0
fi

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

jq -n -c \
  --arg ts "$TS" \
  --arg event "tool_end" \
  --arg id "$TOOL_USE_ID" \
  '{ts:$ts,event:$event,id:$id}' \
  >> "$LOG_FILE"

exit 0
