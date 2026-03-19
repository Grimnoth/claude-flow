#!/usr/bin/env bash
# Hook: PreToolUse — logs all tool calls for approval analysis.
# Observational only: produces no stdout, does not affect tool execution.
# analyze.py determines which ones required user approval by checking the allowlist.
set -euo pipefail

LOG_DIR="$HOME/.claude/approval-logs"
LOG_FILE="$LOG_DIR/approvals.jsonl"

INPUT=$(cat)

TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')
TOOL_USE_ID=$(printf '%s' "$INPUT" | jq -r '.tool_use_id // empty')

# Bail if missing critical fields
if [ -z "$TOOL_NAME" ] || [ -z "$TOOL_USE_ID" ]; then
  exit 0
fi

SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty')

# For Bash tool, extract command string for pattern matching
COMMAND=""
if [ "$TOOL_NAME" = "Bash" ]; then
  COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
fi

# For file-targeting tools, extract the path
FILE_PATH=""
case "$TOOL_NAME" in
  Write|Read|Edit)
    FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
    ;;
esac

mkdir -p "$LOG_DIR"

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

jq -n -c \
  --arg ts "$TS" \
  --arg event "tool_start" \
  --arg tool "$TOOL_NAME" \
  --arg cmd "$COMMAND" \
  --arg path "$FILE_PATH" \
  --arg session "$SESSION_ID" \
  --arg id "$TOOL_USE_ID" \
  '{ts:$ts,event:$event,tool:$tool,command:$cmd,path:$path,session:$session,id:$id}' \
  >> "$LOG_FILE"

# No stdout — does not affect permission decisions
exit 0
