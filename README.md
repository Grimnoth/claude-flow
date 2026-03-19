# claude-flow

Claude Code workflow optimization tools. Currently: approval pattern tracking and allowlist recommendations.

## What it does

- Logs every tool call via `PreToolUse` and `PostToolUse` hooks
- Filters against your existing allowlist to identify which calls required manual approval
- Groups commands into patterns and classifies safety (safe / moderate / destructive)
- Recommends non-destructive patterns to add to your allowlist
- Measures approval latency so you can quantify the time cost
- Detects bloated allowlist entries that could be consolidated into one pattern

## Install

```bash
bash install.sh
```

Then add the hook entries to `~/.claude/settings.json` (the script prints the exact JSON).

## Usage

| Command | Description |
|---------|-------------|
| `/approvals` | Full report (last 30 days) |
| `/approvals 7d` | Last 7 days |
| `/approvals apply` | Add safe recommendations to settings.json |
| `/approvals consolidate` | Simplify bloated allowlist patterns |

## How it works

**Data collection** (zero tokens, ~10ms overhead per tool call):
- `PreToolUse` hook logs `tool_start` events to `~/.claude/approval-logs/approvals.jsonl`
- `PostToolUse` hook logs `tool_end` events for timing analysis

**Analysis** (`analyze.py`, runs on-demand):
- Pairs start/end events to calculate approval wait times
- Filters out auto-allowed tools by checking against your `settings.json` allowlist
- Groups Bash commands into glob patterns (`docker build .` + `docker build --no-cache .` -> `Bash(docker build *)`)
- Classifies each pattern into safety tiers:
  - **Safe**: read-only, build/test, git read ops — always recommended
  - **Moderate**: git write ops, installs, file creation — recommended with warning
  - **Destructive**: rm, force push, reset --hard — never recommended

**Skill** (`/approvals`):
- Runs `analyze.py` and formats the output as a report
- `apply` mode adds only safe patterns to your allowlist (with preview + confirmation)
- `consolidate` mode finds entries like your 15 `./run_tests.sh "TestName"` patterns and suggests `Bash(./run_tests.sh *)`

## File structure

```
hooks/
  approval-log-request.sh   # PreToolUse hook (logs tool_start)
  approval-log-complete.sh  # PostToolUse hook (logs tool_end)
analysis/
  analyze.py                # Pattern detection + safety classification
skill/
  SKILL.md                  # /approvals skill for Claude Code
tests/
  test-approval-hooks.sh    # Test harness
install.sh                  # Symlink installer
```
