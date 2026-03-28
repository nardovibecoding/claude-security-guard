#!/bin/bash
# Copyright (c) 2026 Nardo. AGPL-3.0 — see LICENSE
# Git pull + auto-deploy hooks if anything changed.
# Used by cron (VPS) and launchd (Mac) for auto-sync.

cd "$(dirname "$0")/.."  # telegram-claude-bot root

# Capture current HEAD
OLD_HEAD=$(git rev-parse HEAD 2>/dev/null)

# Pull
git pull --ff-only origin main >> /tmp/telegram-bot-sync.log 2>&1
PULL_EXIT=$?

if [ $PULL_EXIT -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pull failed (exit $PULL_EXIT)" >> /tmp/telegram-bot-sync.log
    exit $PULL_EXIT
fi

NEW_HEAD=$(git rev-parse HEAD 2>/dev/null)

# If HEAD changed, check what was modified
if [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
    CHANGED=$(git diff --name-only "$OLD_HEAD" "$NEW_HEAD" 2>/dev/null)

    # Auto-deploy hooks if hooks/ changed
    if echo "$CHANGED" | grep -q "^hooks/"; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Hooks changed, deploying..." >> /tmp/telegram-bot-sync.log
        bash hooks/deploy_hooks.sh >> /tmp/telegram-bot-sync.log 2>&1
    fi

    # Check if source-of-truth files changed → warn about stale templates
    SOT_FILES="llm_client.py config.py start_all.sh bot_base.py sanitizer.py utils.py"
    STALE_WARN=""
    for sot in $SOT_FILES; do
        if echo "$CHANGED" | grep -q "$sot"; then
            STALE_WARN="$STALE_WARN $sot"
        fi
    done
    if [ -n "$STALE_WARN" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] SOURCE-OF-TRUTH CHANGED:$STALE_WARN — check ADMIN_HANDBOOK.md, TERMINAL_MEMORY.md, settings.template.json" >> /tmp/telegram-bot-sync.log
    fi

    # Auto-sync to public repos if publishable files changed (Mac only)
    if [[ "$(uname)" == "Darwin" ]] && echo "$CHANGED" | grep -q "^hooks/"; then
        SYNC_SCRIPT="$(pwd)/scripts/sync_public_repos.py"
        if [ -f "$SYNC_SCRIPT" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Publishable hooks changed, syncing to public repos..." >> /tmp/telegram-bot-sync.log
            python3 "$SYNC_SCRIPT" --sync >> /tmp/telegram-bot-sync.log 2>&1
        fi
    fi
fi
