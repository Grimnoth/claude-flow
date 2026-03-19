#!/usr/bin/env python3
"""
Approval Insights Analyzer

Reads ~/.claude/approval-logs/approvals.jsonl, detects patterns,
classifies safety, and outputs structured analysis.

Usage:
  python3 analyze.py [--days N] [--json] [--consolidate]

  --days N         Filter to last N days (default: 30)
  --json           Output raw JSON (for skill consumption)
  --consolidate    Analyze existing allowlist for consolidation opportunities
"""

import json
import sys
import os
import re
import argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Safety classification
# ---------------------------------------------------------------------------

DESTRUCTIVE_PATTERNS = [
    r'\brm\s+(-[a-zA-Z]*r|--recursive)',
    r'\brm\s+(-[a-zA-Z]*f|--force)',
    r'\brm\b(?!\s+-[a-zA-Z]*[^rf])',  # bare rm with no safe flags
    r'git\s+push\s+.*(-f\b|--force)',
    r'git\s+reset\s+--hard',
    r'git\s+clean\s+-[a-zA-Z]*f',
    r'git\s+(checkout|restore)\s+\.\s*$',
    r'\bdrop\s+(table|database|index|view)\b',
    r'\btruncate\b',
    r'\bdelete\s+from\b',
    r'\bkill\s+(-9\s+)?',
    r'\bpkill\b',
    r'docker\s+(rm\s+-f|system\s+prune|rmi\s+-f)',
    r'kubectl\s+delete\b',
    r'chmod\s+777',
    r'>\s*/dev/',
    r'\bmkfs\.',
    r'\bdd\s+if=',
    r'git\s+branch\s+-[dD]\b',
]

SAFE_PATTERNS = [
    r'^(cat|head|tail|less|more|wc|file|stat|du|df)\b',
    r'^(ls|find|tree|which|where|type|command)\b',
    r'^git\s+(log|diff|status|branch\s*$|show|remote|tag|fetch|describe|rev-parse|symbolic-ref)\b',
    r'^(grep|rg|ag|ack)\b',
    r'^(echo|printf|date|cal|uptime|whoami|hostname|uname|arch|sw_vers)\b',
    r'^(npm|yarn|pnpm|bun)\s+(test|run|build|start|dev|lint|format|typecheck)\b',
    r'^(cargo|dotnet|go|make|cmake|gradle|mvn)\s+(test|build|check|run|vet|lint|fmt)\b',
    r'^(python3?|node|ruby|perl|deno|bun)\s+\S+\.(py|js|ts|rb|pl)\b',
    r'^(curl|wget|http|httpie)\b',
    r'^(jq|yq|xq|sed\s+-n|awk)\b',
    r'^(docker|podman)\s+(build|images|ps|logs|inspect|compose\s+(up|down|logs|ps))\b',
    r'^(env|printenv|set|id|groups|locale)\b',
    r'^(pwd|basename|dirname|realpath|readlink)\b',
    r'^\./run_tests\.sh\b',
    r'^(open|pbcopy|pbpaste)\b',
    r'^(pip|pip3)\s+(list|show|freeze)\b',
    r'^(brew)\s+(list|info|search)\b',
    r'^(rtk)\b',
]


def classify_safety(command: str) -> str:
    """Returns 'safe', 'moderate', or 'destructive'."""
    if not command:
        return 'moderate'
    cmd_lower = command.lower()
    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd_lower):
            return 'destructive'
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, command):
            return 'safe'
    return 'moderate'


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

def extract_pattern(command: str) -> str:
    """Extract a glob pattern from a specific command."""
    if not command:
        return ''

    # Specific pattern rules (most specific first)
    rules = [
        # ./run_tests.sh with args
        (r'^(\./run_tests\.sh)\s+', r'./run_tests.sh *'),
        # git subcommands
        (r'^(git\s+\w+)\s+', None),  # handled below
        # npm/yarn/pnpm subcommands
        (r'^(npm|yarn|pnpm|bun)\s+(\w+)\s+', None),
        # dotnet subcommands
        (r'^(dotnet)\s+(\w+)\s+', None),
        # cargo subcommands
        (r'^(cargo)\s+(\w+)\s+', None),
        # python/node with script
        (r'^(python3?|node)\s+', None),
        # docker subcommands
        (r'^(docker)\s+(\w+)\s+', None),
        # docker compose subcommands
        (r'^(docker\s+compose)\s+(\w+)\s*', None),
    ]

    # Git: group by subcommand
    m = re.match(r'^(git)\s+(\w+)(.*)$', command)
    if m:
        subcmd = m.group(2)
        rest = m.group(3).strip()
        if rest:
            return f'git {subcmd} *'
        return f'git {subcmd}'

    # Package managers: group by subcommand
    m = re.match(r'^(npm|yarn|pnpm|bun)\s+(\w+)(.*)$', command)
    if m:
        pm, subcmd, rest = m.group(1), m.group(2), m.group(3).strip()
        if rest:
            return f'{pm} {subcmd} *'
        return f'{pm} {subcmd}'

    # Build tools: group by subcommand
    m = re.match(r'^(dotnet|cargo|go|make)\s+(\w+)(.*)$', command)
    if m:
        tool, subcmd, rest = m.group(1), m.group(2), m.group(3).strip()
        if rest:
            return f'{tool} {subcmd} *'
        return f'{tool} {subcmd}'

    # Docker compose
    m = re.match(r'^(docker\s+compose)\s+(\w+)(.*)$', command)
    if m:
        prefix, subcmd, rest = m.group(1), m.group(2), m.group(3).strip()
        if rest:
            return f'{prefix} {subcmd} *'
        return f'{prefix} {subcmd}'

    # Docker subcommands
    m = re.match(r'^(docker)\s+(\w+)(.*)$', command)
    if m:
        tool, subcmd, rest = m.group(1), m.group(2), m.group(3).strip()
        if rest:
            return f'{tool} {subcmd} *'
        return f'{tool} {subcmd}'

    # Python/node scripts
    m = re.match(r'^(python3?|node)\s+(.+)$', command)
    if m:
        return f'{m.group(1)} *'

    # ./run_tests.sh
    m = re.match(r'^(\./run_tests\.sh)(.+)$', command)
    if m:
        return './run_tests.sh *'

    # Generic: first word + *
    m = re.match(r'^(\S+)\s+(.+)$', command)
    if m:
        return f'{m.group(1)} *'

    # Exact command (no args)
    return command


def is_covered_by_allowlist(pattern: str, allowlist: list) -> bool:
    """Check if a Bash(...) pattern is already covered by the allowlist."""
    # Build the full pattern
    full = f'Bash({pattern})'

    for entry in allowlist:
        if entry == full:
            return True
        # Check if an existing broader pattern covers this one
        if entry.startswith('Bash(') and entry.endswith(')'):
            existing = entry[5:-1]
            # Convert glob to regex
            regex = re.escape(existing).replace(r'\*', '.*')
            try:
                if re.match(f'^{regex}$', pattern):
                    return True
            except re.error:
                continue
    return False


def is_tool_call_allowed(tool_name: str, command: str, file_path: str, allowlist: list) -> bool:
    """Check if a specific tool call would be auto-allowed by the allowlist."""
    for entry in allowlist:
        # Exact tool name match (e.g., "Edit")
        if entry == tool_name:
            return True

        # Wildcard tool match (e.g., "mcp__linear__*")
        if '*' in entry and not entry.startswith('Bash(') and not entry.startswith('Read('):
            regex = re.escape(entry).replace(r'\*', '.*')
            try:
                if re.match(f'^{regex}$', tool_name):
                    return True
            except re.error:
                continue

        # Bash(pattern) matching
        if tool_name == 'Bash' and command and entry.startswith('Bash(') and entry.endswith(')'):
            pattern = entry[5:-1]
            regex = re.escape(pattern).replace(r'\*', '.*')
            try:
                if re.match(f'^{regex}$', command):
                    return True
            except re.error:
                continue

        # Read(path) matching
        if tool_name == 'Read' and file_path and entry.startswith('Read(') and entry.endswith(')'):
            pattern = entry[5:-1]
            regex = re.escape(pattern).replace(r'\*\*', '.*').replace(r'\*', '[^/]*')
            try:
                if re.match(f'^{regex}$', file_path):
                    return True
            except re.error:
                continue

    return False


# ---------------------------------------------------------------------------
# Consolidation analysis
# ---------------------------------------------------------------------------

def find_consolidation_opportunities(allowlist: list) -> list:
    """Find groups of allowlist entries that could be replaced by one pattern."""
    # Group Bash entries by their common prefix
    bash_entries = []
    for entry in allowlist:
        if entry.startswith('Bash(') and entry.endswith(')'):
            inner = entry[5:-1]
            bash_entries.append(inner)

    # Group by first word(s)
    groups = defaultdict(list)
    for cmd in bash_entries:
        # Already a wildcard pattern — skip
        if cmd.endswith(' *') or cmd.endswith('*)') or cmd == '*':
            continue
        # Find the stem
        m = re.match(r'^(\./?\w[\w.-]*(?:\s+\w+)?)', cmd)
        if m:
            stem = m.group(1)
            groups[stem].append(cmd)

    opportunities = []
    for stem, entries in groups.items():
        if len(entries) >= 3:  # Only suggest consolidation for 3+ entries
            # Determine the pattern
            consolidated = f'{stem} *'
            # Check safety of the consolidated pattern
            safety = classify_safety(stem + ' anything')
            opportunities.append({
                'stem': stem,
                'current_entries': [f'Bash({e})' for e in entries],
                'consolidated_pattern': f'Bash({consolidated})',
                'count': len(entries),
                'safety': safety,
            })

    return sorted(opportunities, key=lambda x: x['count'], reverse=True)


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    # Handle both with and without milliseconds
    for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S%z'):
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # Fallback: return epoch
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def load_log(log_path: str, days: int, allowlist: list) -> tuple:
    """Load and parse the JSONL log file.

    Returns (prompted, completed) dicts where 'prompted' contains only
    tool calls that were NOT auto-allowed by the allowlist (i.e., ones
    that would have shown a permission prompt to the user).
    """
    all_starts = {}  # id -> entry
    completed = {}   # id -> entry

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    if not os.path.exists(log_path):
        return {}, {}

    with open(log_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = parse_timestamp(entry.get('ts', ''))
            if ts < cutoff:
                continue

            event = entry.get('event', '')
            entry_id = entry.get('id', '')

            # Support both old format (prompted/completed) and new (tool_start/tool_end)
            if event in ('tool_start', 'prompted') and entry_id:
                entry['_ts'] = ts
                all_starts[entry_id] = entry
            elif event in ('tool_end', 'completed') and entry_id:
                entry['_ts'] = ts
                completed[entry_id] = entry

    # Filter: only keep tool calls that were NOT auto-allowed
    prompted = {}
    for entry_id, entry in all_starts.items():
        tool = entry.get('tool', '')
        command = entry.get('command', '')
        file_path = entry.get('path', '')

        if not is_tool_call_allowed(tool, command, file_path, allowlist):
            prompted[entry_id] = entry

    return prompted, completed


def load_allowlist(settings_path: str) -> list:
    """Load the current allowlist from settings.json."""
    try:
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        return settings.get('permissions', {}).get('allow', [])
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return []


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze(prompted: dict, completed: dict, allowlist: list) -> dict:
    """Produce the full analysis."""
    total_prompts = len(prompted)
    approvals = {}
    denials = {}

    for tool_id, entry in prompted.items():
        if tool_id in completed:
            wait = (completed[tool_id]['_ts'] - entry['_ts']).total_seconds()
            approvals[tool_id] = {**entry, 'wait_seconds': max(0, wait)}
        else:
            denials[tool_id] = entry

    total_approvals = len(approvals)
    total_denials = len(denials)
    total_wait = sum(a['wait_seconds'] for a in approvals.values())
    avg_wait = total_wait / total_approvals if total_approvals > 0 else 0

    # Unique sessions
    sessions = set()
    for entry in prompted.values():
        s = entry.get('session', '')
        if s:
            sessions.add(s)

    # Group by tool type
    by_tool = defaultdict(lambda: {'prompts': 0, 'approvals': 0, 'denials': 0, 'wait': 0})
    for entry in approvals.values():
        tool = entry.get('tool', 'unknown')
        by_tool[tool]['prompts'] += 1
        by_tool[tool]['approvals'] += 1
        by_tool[tool]['wait'] += entry['wait_seconds']
    for entry in denials.values():
        tool = entry.get('tool', 'unknown')
        by_tool[tool]['prompts'] += 1
        by_tool[tool]['denials'] += 1

    # Pattern detection (Bash tools only for now)
    pattern_data = defaultdict(lambda: {
        'count': 0, 'total_wait': 0, 'examples': [], 'denied': 0
    })

    for entry in approvals.values():
        if entry.get('tool') != 'Bash':
            continue
        cmd = entry.get('command', '')
        if not cmd:
            continue
        pat = extract_pattern(cmd)
        pattern_data[pat]['count'] += 1
        pattern_data[pat]['total_wait'] += entry['wait_seconds']
        if cmd not in pattern_data[pat]['examples']:
            pattern_data[pat]['examples'].append(cmd)
            if len(pattern_data[pat]['examples']) > 5:
                pattern_data[pat]['examples'] = pattern_data[pat]['examples'][:5]

    for entry in denials.values():
        if entry.get('tool') != 'Bash':
            continue
        cmd = entry.get('command', '')
        if not cmd:
            continue
        pat = extract_pattern(cmd)
        pattern_data[pat]['denied'] += 1

    # Non-Bash tool patterns
    non_bash_patterns = defaultdict(lambda: {'count': 0, 'total_wait': 0, 'denied': 0})
    for entry in approvals.values():
        tool = entry.get('tool', '')
        if tool == 'Bash' or not tool:
            continue
        non_bash_patterns[tool]['count'] += 1
        non_bash_patterns[tool]['total_wait'] += entry['wait_seconds']
    for entry in denials.values():
        tool = entry.get('tool', '')
        if tool == 'Bash' or not tool:
            continue
        non_bash_patterns[tool]['denied'] += 1

    # Build pattern recommendations
    patterns = []
    for pat, data in sorted(pattern_data.items(), key=lambda x: x[1]['count'], reverse=True):
        safety = classify_safety(pat)
        covered = is_covered_by_allowlist(pat, allowlist)
        avg_w = data['total_wait'] / data['count'] if data['count'] > 0 else 0

        rec = 'skip'
        if covered:
            rec = 'already_allowed'
        elif safety == 'safe':
            rec = 'add'
        elif safety == 'moderate':
            rec = 'consider'
        elif safety == 'destructive':
            rec = 'never'

        patterns.append({
            'pattern': pat,
            'settings_entry': f'Bash({pat})',
            'count': data['count'],
            'denied': data['denied'],
            'avg_wait_seconds': round(avg_w, 1),
            'total_wait_seconds': round(data['total_wait'], 1),
            'safety': safety,
            'recommendation': rec,
            'examples': data['examples'],
        })

    # Non-bash patterns
    for tool, data in sorted(non_bash_patterns.items(), key=lambda x: x[1]['count'], reverse=True):
        covered = tool in allowlist
        avg_w = data['total_wait'] / data['count'] if data['count'] > 0 else 0
        patterns.append({
            'pattern': tool,
            'settings_entry': tool,
            'count': data['count'],
            'denied': data['denied'],
            'avg_wait_seconds': round(avg_w, 1),
            'total_wait_seconds': round(data['total_wait'], 1),
            'safety': 'safe',
            'recommendation': 'already_allowed' if covered else 'add',
            'examples': [],
        })

    # Build recommendations
    safe_recs = [p['settings_entry'] for p in patterns
                 if p['recommendation'] == 'add' and p['count'] >= 2]
    moderate_recs = [p for p in patterns if p['recommendation'] == 'consider']
    destructive_recs = [p for p in patterns if p['recommendation'] == 'never']

    # Projected savings
    saved_prompts = sum(p['count'] for p in patterns if p['recommendation'] == 'add' and p['count'] >= 2)
    saved_seconds = sum(p['total_wait_seconds'] for p in patterns if p['recommendation'] == 'add' and p['count'] >= 2)

    # Consolidation opportunities
    consolidation = find_consolidation_opportunities(allowlist)

    # Date range
    all_ts = [e['_ts'] for e in prompted.values()]
    date_start = min(all_ts).isoformat() if all_ts else None
    date_end = max(all_ts).isoformat() if all_ts else None

    return {
        'period': {
            'start': date_start,
            'end': date_end,
        },
        'summary': {
            'total_prompts': total_prompts,
            'total_approvals': total_approvals,
            'total_denials': total_denials,
            'approval_rate': round(total_approvals / total_prompts, 3) if total_prompts > 0 else 0,
            'total_wait_seconds': round(total_wait, 1),
            'total_wait_minutes': round(total_wait / 60, 1),
            'avg_wait_seconds': round(avg_wait, 1),
            'sessions': len(sessions),
        },
        'by_tool': dict(by_tool),
        'patterns': patterns,
        'recommendations': {
            'safe': safe_recs,
            'moderate': [{'pattern': p['settings_entry'], 'count': p['count'],
                         'examples': p['examples']} for p in moderate_recs],
            'destructive': [{'pattern': p['settings_entry'], 'count': p['count'],
                            'reason': 'Potentially destructive command'} for p in destructive_recs],
        },
        'projected_savings': {
            'prompts_saved': saved_prompts,
            'seconds_saved': round(saved_seconds, 1),
            'minutes_saved': round(saved_seconds / 60, 1),
        },
        'consolidation': consolidation,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Approval Insights Analyzer')
    parser.add_argument('--days', type=int, default=30, help='Filter to last N days')
    parser.add_argument('--json', action='store_true', help='Output raw JSON')
    parser.add_argument('--consolidate', action='store_true', help='Only show consolidation opportunities')
    parser.add_argument('--settings-path', default=os.path.expanduser('~/.claude/settings.json'),
                       help='Path to settings.json')
    args = parser.parse_args()

    log_path = os.path.expanduser('~/.claude/approval-logs/approvals.jsonl')
    allowlist = load_allowlist(args.settings_path)

    if args.consolidate:
        opportunities = find_consolidation_opportunities(allowlist)
        result = {'consolidation': opportunities, 'total_allowlist_entries': len(allowlist)}
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if not opportunities:
                print("No consolidation opportunities found.")
            else:
                print(f"Found {len(opportunities)} consolidation opportunities:\n")
                for opp in opportunities:
                    print(f"  {opp['consolidated_pattern']} (replaces {opp['count']} entries, safety: {opp['safety']})")
                    for entry in opp['current_entries']:
                        print(f"    - {entry}")
                    print()
        return

    prompted, completed = load_log(log_path, args.days, allowlist)

    if not prompted:
        print(json.dumps({'error': 'no_data', 'message': 'No approval data found.'}, indent=2))
        sys.exit(0)

    result = analyze(prompted, completed, allowlist)

    if args.json:
        # Remove internal _ts fields
        print(json.dumps(result, indent=2, default=str))
    else:
        # Text summary
        s = result['summary']
        print(f"Approval Insights ({args.days} days)")
        print(f"  Prompts: {s['total_prompts']}  Approved: {s['total_approvals']}  Denied: {s['total_denials']}")
        print(f"  Total wait: {s['total_wait_minutes']} min  Avg: {s['avg_wait_seconds']}s  Sessions: {s['sessions']}")
        print()
        print("Top patterns:")
        for p in result['patterns'][:15]:
            flag = {'safe': '+', 'moderate': '~', 'destructive': '!'}[p['safety']]
            rec = {'add': 'ADD', 'consider': 'CONSIDER', 'never': 'NEVER',
                   'already_allowed': 'OK', 'skip': '-'}[p['recommendation']]
            print(f"  [{flag}] {p['count']:3d}x  {p['avg_wait_seconds']:4.1f}s  {rec:8s}  {p['pattern']}")
        if result['consolidation']:
            print(f"\nConsolidation: {len(result['consolidation'])} opportunities")


if __name__ == '__main__':
    main()
