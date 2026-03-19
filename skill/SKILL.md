---
name: approvals
version: 1.0.0
description: |
  Analyze tool approval patterns and recommend allowlist additions.
  Tracks permission prompts, approval times, and suggests non-destructive
  commands to add to settings.json. Reduces approval friction safely.
allowed-tools:
  - Bash
  - Read
  - Glob
  - Edit
  - AskUserQuestion
---

# /approvals -- Tool Approval Pattern Analysis

Analyzes which tool calls require manual approval, how long you wait,
and recommends safe commands to add to your allowlist.

## User-invocable
When the user types `/approvals`, run this skill.

## Arguments
- `/approvals` -- full report (last 30 days)
- `/approvals 7d` -- last 7 days
- `/approvals 14d` -- last 14 days
- `/approvals 90d` -- last 90 days
- `/approvals apply` -- apply safe recommendations to settings.json
- `/approvals consolidate` -- simplify bloated allowlist patterns

**Argument validation:** If the argument doesn't match a number followed by `d`, the word `apply`, or the word `consolidate`, show usage and stop.

## Step 1: Check Prerequisites

Check if the log file exists and has data:
```bash
[ -f ~/.claude/approval-logs/approvals.jsonl ] && wc -l < ~/.claude/approval-logs/approvals.jsonl || echo "0"
```

If the file does not exist or has 0 lines, tell the user:

> No approval data collected yet. The PreToolUse and PostToolUse hooks are logging
> all tool calls automatically. Use Claude Code normally for a few sessions, then
> come back and run `/approvals` to see your report.

Then stop.

## Step 2: Route by Mode

### Report Mode (default, or with `Nd` argument)

Parse the day count from the argument (default 30).

Run the analysis:
```bash
python3 ~/.claude/approval-logs/analyze.py --days <N> --json
```

Read the JSON output. If it contains `"error": "no_data"`, show the no-data message from Step 1 and stop.

Format the output as follows:

---

### Approval Insights (last N days)

| Metric | Value |
|--------|-------|
| Total permission prompts | X |
| Approved | X (Y%) |
| Denied | X |
| Estimated time blocked | X.X min |
| Avg wait per approval | X.Xs |
| Sessions tracked | X |

### Top Patterns

Show the top 15 patterns sorted by count descending. Use this table format:

```
   | Pattern                    | Count | Avg Wait | Safety      | Action
---|----------------------------|-------|----------|-------------|--------
 1 | Bash(docker build *)       |    12 |    3.2s  | safe        | ADD
 2 | Bash(cargo test *)         |     8 |    2.1s  | safe        | ADD
 3 | Write                      |     5 |    1.5s  | safe        | ADD
 4 | Bash(rm -rf node_modules)  |     3 |    1.8s  | destructive | NEVER
```

Action key:
- `ADD` = safe, recommend adding to allowlist
- `CONSIDER` = moderate risk, show with explanation
- `NEVER` = destructive, never whitelist
- `OK` = already in allowlist

### Recommendations

**Safe -- add to allowlist:**
Show as ready-to-copy JSON array entries. Only include patterns with count >= 2.
```json
"Bash(docker build *)",
"Bash(cargo test *)",
```

**Moderate -- consider with caution:**
List each with a one-line risk explanation.

**Destructive -- never whitelist:**
Show with warning and explanation of why each is dangerous.

### Consolidation Opportunities

If the analysis found consolidation opportunities, show them:
```
Your allowlist has patterns that could be simplified:

  Bash(./run_tests.sh *) could replace 15 entries:
    - Bash(./run_tests.sh "StalwartSkillTests")
    - Bash(./run_tests.sh "IceSkillsTest")
    - ... (13 more)

Run `/approvals consolidate` to review and apply.
```

### Projected Savings

> If you add the N safe recommendations above:
> - X fewer approval prompts per period
> - ~X.X minutes of approval time saved

---

### Apply Mode (`/approvals apply`)

1. Run: `python3 ~/.claude/approval-logs/analyze.py --days 30 --json`
2. Extract only patterns where `recommendation` is `"add"`
3. If no safe recommendations, tell the user and stop.
4. Read `~/.claude/settings.json`
5. Show the user exactly which entries will be added:
   ```
   Will add to permissions.allow:
     + "Bash(docker build *)"
     + "Bash(cargo test *)"
   ```
6. Ask the user to confirm using AskUserQuestion: "Add these N safe patterns to your allowlist?"
7. If confirmed:
   - Add each entry to the `permissions.allow` array in settings.json
   - Use Edit tool to modify settings.json
   - Show: "Added N patterns. They take effect in new sessions."
8. If declined, stop.

**CRITICAL**: Only add patterns classified as `"safe"`. Never add moderate or destructive.

### Consolidate Mode (`/approvals consolidate`)

1. Run: `python3 ~/.claude/approval-logs/analyze.py --consolidate --json`
2. If no opportunities, tell the user and stop.
3. For each opportunity, show:
   ```
   Replace 15 entries with: Bash(./run_tests.sh *)
   Safety: safe

   Entries to remove:
     - Bash(./run_tests.sh "StalwartSkillTests")
     - Bash(./run_tests.sh "IceSkillsTest")
     - ...
   ```
4. Ask user to confirm each consolidation group via AskUserQuestion
5. If confirmed:
   - Read settings.json
   - Remove the specific entries
   - Add the consolidated pattern
   - Write with Edit tool
   - Show the result

## Important Rules

- NEVER recommend destructive patterns for whitelisting. This is a hard rule.
- Output directly to the conversation -- do not write report files.
- The hook scripts are observational only -- they do not change permission behavior.
- If analyze.py is missing, tell the user the skill needs reinstalling.
- When showing JSON snippets for the allowlist, use the exact `Bash(pattern)` format.
- In apply mode, always show a preview and ask for confirmation before modifying settings.json.
- Treat `Edit` tool permissions as safe (already in the user's allowlist).
- For `Write` and `Read` tools with path-based permissions, recommend specific path patterns.
