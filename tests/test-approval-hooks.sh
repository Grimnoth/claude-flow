#!/usr/bin/env bash
# Test harness for approval-insights hooks and analyze.py
set -euo pipefail

PASS=0
FAIL=0
TOTAL=0

# Use temp dir for isolated testing
TEST_HOME=$(mktemp -d)
LOG_DIR="$TEST_HOME/.claude/approval-logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/approvals.jsonl"

HOOKS_DIR="$HOME/.claude/hooks"

pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); echo "  FAIL: $1"; }

# -------------------------------------------------------------------
echo "=== Hook: approval-log-request.sh (PreToolUse) ==="
# -------------------------------------------------------------------

# Test 1: Logs a tool_start event for Bash tool
STDOUT=$(echo '{"tool_name":"Bash","tool_input":{"command":"docker build .","description":"Build image"},"tool_use_id":"toolu_test1","session_id":"sess_test1"}' \
  | HOME="$TEST_HOME" bash "$HOOKS_DIR/approval-log-request.sh" 2>/dev/null) || true
if [ -z "$STDOUT" ] && [ -f "$LOG_FILE" ] && grep -q '"toolu_test1"' "$LOG_FILE" && grep -q '"tool_start"' "$LOG_FILE"; then
  pass "Logs tool_start event for Bash tool (no stdout)"
else
  fail "Logs tool_start event for Bash tool"
  [ -n "$STDOUT" ] && echo "    Unexpected stdout: $STDOUT"
fi

# Test 2: Extracts command field for Bash tools
if grep -q '"command":"docker build ."' "$LOG_FILE" 2>/dev/null; then
  pass "Extracts command field for Bash tool"
else
  fail "Extracts command field for Bash tool"
fi

# Test 3: Handles non-Bash tool and extracts file_path
echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.txt","content":"hi"},"tool_use_id":"toolu_test2","session_id":"sess_test1"}' \
  | HOME="$TEST_HOME" bash "$HOOKS_DIR/approval-log-request.sh" 2>/dev/null || true
if grep -q '"toolu_test2"' "$LOG_FILE" && grep -q '"tool":"Write"' "$LOG_FILE" && grep -q '"path":"/tmp/test.txt"' "$LOG_FILE"; then
  pass "Logs non-Bash tool (Write) with file_path"
else
  fail "Logs non-Bash tool (Write) with file_path"
fi

# Test 4: Empty tool_name exits cleanly with no log entry
BEFORE=$(wc -l < "$LOG_FILE")
echo '{"tool_name":"","tool_input":{},"tool_use_id":"","session_id":""}' \
  | HOME="$TEST_HOME" bash "$HOOKS_DIR/approval-log-request.sh" 2>/dev/null || true
AFTER=$(wc -l < "$LOG_FILE")
if [ "$BEFORE" = "$AFTER" ]; then
  pass "Empty tool_name produces no log entry"
else
  fail "Empty tool_name produced a log entry"
fi

# Test 5: Missing tool_use_id exits cleanly
BEFORE=$(wc -l < "$LOG_FILE")
echo '{"tool_name":"Bash","tool_input":{"command":"ls"},"tool_use_id":"","session_id":"sess_x"}' \
  | HOME="$TEST_HOME" bash "$HOOKS_DIR/approval-log-request.sh" 2>/dev/null || true
AFTER=$(wc -l < "$LOG_FILE")
if [ "$BEFORE" = "$AFTER" ]; then
  pass "Empty tool_use_id produces no log entry"
else
  fail "Empty tool_use_id produced a log entry"
fi

# -------------------------------------------------------------------
echo ""
echo "=== Hook: approval-log-complete.sh (PostToolUse) ==="
# -------------------------------------------------------------------

# Test 6: Logs tool_end for any ID present in log
echo '{"tool_name":"Bash","tool_input":{"command":"docker build ."},"tool_use_id":"toolu_test1","session_id":"sess_test1"}' \
  | HOME="$TEST_HOME" bash "$HOOKS_DIR/approval-log-complete.sh" 2>/dev/null || true
if grep -q '"tool_end"' "$LOG_FILE" && grep -c '"toolu_test1"' "$LOG_FILE" | grep -q '2'; then
  pass "Logs tool_end for existing tool_use_id"
else
  fail "Logs tool_end for existing tool_use_id"
fi

# Test 7: Also logs tool_end for new IDs (logs all completions now)
echo '{"tool_name":"Bash","tool_input":{"command":"ls"},"tool_use_id":"toolu_new_id","session_id":"sess_test1"}' \
  | HOME="$TEST_HOME" bash "$HOOKS_DIR/approval-log-complete.sh" 2>/dev/null || true
if grep -q '"toolu_new_id"' "$LOG_FILE"; then
  pass "Logs tool_end for all tool_use_ids"
else
  fail "Should log tool_end for all tool_use_ids"
fi

# Test 8: Handles missing log file gracefully
EMPTY_HOME=$(mktemp -d)
STDOUT=$(echo '{"tool_name":"Bash","tool_input":{"command":"ls"},"tool_use_id":"toolu_x","session_id":"sess_x"}' \
  | HOME="$EMPTY_HOME" bash "$HOOKS_DIR/approval-log-complete.sh" 2>/dev/null) || true
EXIT_CODE=$?
if [ "$EXIT_CODE" -eq 0 ] && [ -z "$STDOUT" ]; then
  pass "Handles missing log file gracefully"
else
  fail "Missing log file should exit 0 with no output"
fi
rm -rf "$EMPTY_HOME"

# -------------------------------------------------------------------
echo ""
echo "=== analyze.py ==="
# -------------------------------------------------------------------

# Create synthetic test data using new event format
# Note: docker build and cargo test are NOT in the real allowlist, so they should be "prompted"
# git status IS in the allowlist, so it should be filtered out
cat > "$LOG_FILE" << 'JSONL'
{"ts":"2026-03-19T10:00:00Z","event":"tool_start","tool":"Bash","command":"docker build .","path":"","session":"sess_1","id":"toolu_a1"}
{"ts":"2026-03-19T10:00:05Z","event":"tool_end","id":"toolu_a1"}
{"ts":"2026-03-19T10:01:00Z","event":"tool_start","tool":"Bash","command":"docker build --no-cache .","path":"","session":"sess_1","id":"toolu_a2"}
{"ts":"2026-03-19T10:01:03Z","event":"tool_end","id":"toolu_a2"}
{"ts":"2026-03-19T10:02:00Z","event":"tool_start","tool":"Bash","command":"cargo test","path":"","session":"sess_1","id":"toolu_a3"}
{"ts":"2026-03-19T10:02:04Z","event":"tool_end","id":"toolu_a3"}
{"ts":"2026-03-19T10:03:00Z","event":"tool_start","tool":"Bash","command":"cargo test -- --nocapture","path":"","session":"sess_1","id":"toolu_a4"}
{"ts":"2026-03-19T10:03:06Z","event":"tool_end","id":"toolu_a4"}
{"ts":"2026-03-19T10:04:00Z","event":"tool_start","tool":"Bash","command":"rm -rf /tmp/junk","path":"","session":"sess_1","id":"toolu_a5"}
{"ts":"2026-03-19T10:04:02Z","event":"tool_end","id":"toolu_a5"}
{"ts":"2026-03-19T10:05:00Z","event":"tool_start","tool":"Bash","command":"git push --force origin main","path":"","session":"sess_1","id":"toolu_a6"}
{"ts":"2026-03-19T10:06:00Z","event":"tool_start","tool":"Write","command":"","path":"/tmp/out.txt","session":"sess_1","id":"toolu_a7"}
{"ts":"2026-03-19T10:06:02Z","event":"tool_end","id":"toolu_a7"}
{"ts":"2026-03-19T10:07:00Z","event":"tool_start","tool":"Bash","command":"git status","path":"","session":"sess_1","id":"toolu_a8"}
{"ts":"2026-03-19T10:07:01Z","event":"tool_end","id":"toolu_a8"}
{"ts":"2026-03-19T10:08:00Z","event":"tool_start","tool":"Edit","command":"","path":"/tmp/foo.txt","session":"sess_1","id":"toolu_a9"}
{"ts":"2026-03-19T10:08:01Z","event":"tool_end","id":"toolu_a9"}
JSONL

# Test 9: analyze.py runs without errors
ANALYZE_OUT=$(HOME="$TEST_HOME" python3 "$HOME/.claude/approval-logs/analyze.py" --days 30 --json --settings-path "$HOME/.claude/settings.json" 2>&1) || true
if echo "$ANALYZE_OUT" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
  pass "analyze.py produces valid JSON"
else
  fail "analyze.py output is not valid JSON"
  echo "    Output: $(echo "$ANALYZE_OUT" | head -5)"
fi

# Test 10: Filters out auto-allowed tools (git status is in allowlist, Edit is in allowlist)
# Should have: docker build x2, cargo test x2, rm -rf x1, git push --force x1, Write x1 = 7
# Should NOT have: git status (allowed), Edit (allowed)
TOTAL_PROMPTS=$(echo "$ANALYZE_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['summary']['total_prompts'])" 2>/dev/null) || TOTAL_PROMPTS=0
if [ "$TOTAL_PROMPTS" = "7" ]; then
  pass "Filters out auto-allowed tools, counts 7 prompted events"
else
  fail "Expected 7 prompts (filtering auto-allowed), got $TOTAL_PROMPTS"
fi

# Test 11: Detects denial (toolu_a6 has no completion)
TOTAL_DENIALS=$(echo "$ANALYZE_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['summary']['total_denials'])" 2>/dev/null) || TOTAL_DENIALS=0
if [ "$TOTAL_DENIALS" = "1" ]; then
  pass "Detects 1 denial (force push with no completion)"
else
  fail "Expected 1 denial, got $TOTAL_DENIALS"
fi

# Test 12: Classifies rm -rf as destructive
DESTRUCTIVE=$(echo "$ANALYZE_OUT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
destructive = [p for p in d['patterns'] if p['safety']=='destructive']
print(len(destructive))
" 2>/dev/null) || DESTRUCTIVE=0
if [ "$DESTRUCTIVE" -ge 1 ]; then
  pass "Classifies destructive commands correctly"
else
  fail "Should find at least 1 destructive pattern"
fi

# Test 13: Classifies docker build and cargo test as safe
SAFE=$(echo "$ANALYZE_OUT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
safe = [p for p in d['patterns'] if p['safety']=='safe' and ('docker' in p.get('pattern','') or 'cargo' in p.get('pattern',''))]
print(len(safe))
" 2>/dev/null) || SAFE=0
if [ "$SAFE" -ge 2 ]; then
  pass "Classifies docker build + cargo test as safe"
else
  fail "Expected at least 2 safe patterns (docker build, cargo test), got $SAFE"
fi

# Test 14: Consolidation detection on real settings.json
CONSOL_OUT=$(python3 "$HOME/.claude/approval-logs/analyze.py" --consolidate --json --settings-path "$HOME/.claude/settings.json" 2>&1) || true
CONSOL_COUNT=$(echo "$CONSOL_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('consolidation',[])))" 2>/dev/null) || CONSOL_COUNT=0
if [ "$CONSOL_COUNT" -ge 1 ]; then
  pass "Finds consolidation opportunities in real settings.json ($CONSOL_COUNT found)"
else
  fail "Expected at least 1 consolidation opportunity"
fi

# Test 15: Allowlist filtering works (git status should NOT appear in patterns)
GIT_STATUS=$(echo "$ANALYZE_OUT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
matches = [p for p in d['patterns'] if 'git status' in p.get('pattern','')]
print(len(matches))
" 2>/dev/null) || GIT_STATUS=0
if [ "$GIT_STATUS" = "0" ]; then
  pass "Allowlist filtering: git status excluded from prompted"
else
  fail "git status should be filtered out (it's in the allowlist)"
fi

# -------------------------------------------------------------------
echo ""
echo "=== JSONL format validation ==="
# -------------------------------------------------------------------

# Test 16: Every line in the log is valid JSON
BAD_LINES=0
while IFS= read -r line; do
  echo "$line" | python3 -c "import sys,json; json.loads(sys.stdin.read())" 2>/dev/null || BAD_LINES=$((BAD_LINES + 1))
done < "$LOG_FILE"
if [ "$BAD_LINES" -eq 0 ]; then
  pass "All log lines are valid JSON"
else
  fail "$BAD_LINES lines are not valid JSON"
fi

# -------------------------------------------------------------------
# Cleanup
# -------------------------------------------------------------------
rm -rf "$TEST_HOME"

echo ""
echo "=== Results: $PASS passed, $FAIL failed (out of $TOTAL) ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
