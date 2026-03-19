#!/usr/bin/env bash
# claude-flow installer
# Creates symlinks in ~/.claude/ so Claude Code discovers the hooks and skill.
# Does NOT modify settings.json — add hook entries manually or via /approvals.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "Installing claude-flow from $REPO_DIR"

# Check dependencies
for cmd in jq python3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is required but not found. Install it first."
    exit 1
  fi
done

# Create directories
mkdir -p "$CLAUDE_DIR/hooks"
mkdir -p "$CLAUDE_DIR/approval-logs"
mkdir -p "$CLAUDE_DIR/skills/approvals"

# Create symlinks (force-overwrite if they exist)
ln -sf "$REPO_DIR/hooks/approval-log-request.sh" "$CLAUDE_DIR/hooks/approval-log-request.sh"
ln -sf "$REPO_DIR/hooks/approval-log-complete.sh" "$CLAUDE_DIR/hooks/approval-log-complete.sh"
ln -sf "$REPO_DIR/analysis/analyze.py" "$CLAUDE_DIR/approval-logs/analyze.py"
ln -sf "$REPO_DIR/skill/SKILL.md" "$CLAUDE_DIR/skills/approvals/SKILL.md"

echo ""
echo "Symlinks created:"
echo "  ~/.claude/hooks/approval-log-request.sh -> $REPO_DIR/hooks/"
echo "  ~/.claude/hooks/approval-log-complete.sh -> $REPO_DIR/hooks/"
echo "  ~/.claude/approval-logs/analyze.py -> $REPO_DIR/analysis/"
echo "  ~/.claude/skills/approvals/SKILL.md -> $REPO_DIR/skill/"
echo ""
echo "Next: Add these hook entries to ~/.claude/settings.json if not already present:"
echo ""
cat << 'HOOKS'
"PreToolUse": [
  ... (your existing PreToolUse entries) ...,
  {
    "hooks": [{
      "type": "command",
      "command": "REPO_DIR/hooks/approval-log-request.sh",
      "timeout": 2
    }]
  }
],
"PostToolUse": [{
  "hooks": [{
    "type": "command",
    "command": "REPO_DIR/hooks/approval-log-complete.sh",
    "timeout": 2
  }]
}]
HOOKS
echo ""
echo "(Replace REPO_DIR with: $REPO_DIR)"
echo ""
echo "Done. Restart Claude Code sessions to activate."
