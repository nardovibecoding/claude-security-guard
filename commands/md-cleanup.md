---
name: md-cleanup
description: |
  Unified context budget auditor — CLAUDE.md, hookify rules, memory files, skills. One command, one report.
  Triggers: "md cleanup", "context budget", "clean md", "audit context", "trim rules", "skill cleaning", "memory maintenance", "claudemd maintenance".
  NOT FOR: editing specific files (just edit), git operations, deploying.
  Produces: 5-phase audit report + token budget table with actionable recommendations.
user-invocable: true
---

# MD Cleanup — Context Budget Auditor

Audits all MD-based context sources in one pass. Replaces claudemd-maintenance, memory-maintenance, and skillcleaning.

## Phase 1: CLAUDE.md Audit

1. Read the project CLAUDE.md (default: `~/telegram-claude-bot/CLAUDE.md`)
2. Read `self_review.md` for failure history
3. Classify each section by header:

| Class | Definition | Action |
|---|---|---|
| INTERNALIZED | Claude does this by default, no failures in self_review | REMOVE |
| REINFORCED | Claude failed at this (in self_review) | TRIM to 1-2 lines |
| CUSTOM | Project-specific, Claude can't know without being told | KEEP |
| HISTORICAL | Past incidents, not actionable rules | MOVE to memory/ |
| REDUNDANT | Duplicate of another rule or feedback memory | MERGE |

4. Cross-reference against `feedback_*.md` files — if a CLAUDE.md rule has identical feedback memory, mark REDUNDANT
5. Present table: action counts, lines saved, estimated token savings (~2.5 tokens/line)

## Phase 2: Hookify Rules Audit

1. Read all `~/.claude/hookify.*.local.md` files
2. For each rule, check:
   - **Duplicate of CLAUDE.md?** → delete hookify (CLAUDE.md is lighter)
   - **Duplicate of feedback memory?** → keep hookify IF it's pattern-matched enforcement, delete if stop `.*`
   - **stop `.*` pattern?** → flag as noise unless it enforces something specific
   - **Duplicate of another hookify rule?** → merge into one
3. Priority: pattern-matched hookify > CLAUDE.md text > feedback memory (passive)
4. Present: rules to delete, merge, keep

## Phase 3: Memory Audit

1. Read `MEMORY.md` index — check line count (healthy < 120, warning 120-180, critical > 180)
2. For each memory file referenced:
   - Verify file paths mentioned still exist
   - Check if project/reference memories are stale (dates > 30 days, features removed)
   - Flag duplicates or overlapping topics
3. Check for feedback memories that should promote to CLAUDE.md rules (score: Durability + Impact + Scope, threshold >= 6/9)
4. Present: stale entries, duplicates, promotion candidates

## Phase 4: Skills Audit

1. Inventory: `du -sh ~/.claude/skills/*/` sorted by size
2. Duplicate detection: overlapping triggers between skills
3. Broken scripts: `py_compile` and `bash -n` on all scripts/
4. Missing deps: AST import walk on Python scripts
5. Upstream updates: compare hash vs GitHub raw for official skills (docx, pdf, pptx, xlsx)
6. SKILL.md quality: must have name, description, triggers, NOT FOR, produces
7. Description budget: max 400 chars per YAML description
8. Present: broken, unused, duplicates, updates available

## Phase 5: Budget Report

Count lines and estimate tokens for all context sources:

```
## Context Budget Report
| Source            | Files | Lines | ~Tokens | % of total |
|-------------------|-------|-------|---------|------------|
| CLAUDE.md         |     1 |       |         |            |
| Hookify rules     |       |       |         |            |
| MEMORY.md index   |     1 |       |         |            |
| Skill YAML total  |       |       |         |            |
| TOTAL             |       |       |         |            |

Thresholds: CLAUDE.md < 150 lines, MEMORY.md < 120 lines, hookify < 25 rules, skill YAML < 15K chars
```

Commands for counting:
```bash
wc -l ~/telegram-claude-bot/CLAUDE.md
cat ~/.claude/hookify.*.local.md | wc -c
wc -l ~/.claude/projects/-Users-bernard/memory/MEMORY.md
for f in $(find ~/.claude/skills -name "SKILL.md"); do awk '/^---/{n++; next} n==1{print}' "$f"; done | wc -c
```

Token estimate: chars / 3.5

## After Report

On user approval, execute recommended changes:
- REMOVE/TRIM/MERGE CLAUDE.md sections
- Delete/merge hookify rules
- Delete/update stale memory files
- Fix broken skills, update from upstream
- Git commit all changes together
- Final: re-run budget report showing before/after
