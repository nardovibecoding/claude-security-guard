#!/bin/bash
# Copyright (c) 2026 Nardo. AGPL-3.0 — see LICENSE
# Deploy hooks from repo to ~/.claude/hooks/
# Handles Mac vs Linux path differences and platform filtering.
#
# Usage:
#   ./hooks/deploy_hooks.sh          # deploy hooks for current platform
#   ./hooks/deploy_hooks.sh --dry    # show what would be deployed

set -euo pipefail
cd "$(dirname "$0")"

DRY_RUN=false
[ "${1:-}" = "--dry" ] && DRY_RUN=true

TARGET="$HOME/.claude/hooks"
mkdir -p "$TARGET"

# Detect platform
if [[ "$(uname)" == "Darwin" ]]; then
    PLATFORM="mac"
else
    PLATFORM="vps"
fi

# Read platform filter from shared JSON (single source of truth)
FILTER_FILE="$(dirname "$0")/platform_filter.json"
if [ -f "$FILTER_FILE" ]; then
    MAC_ONLY=($(python3 -c "import json; print(' '.join(json.load(open('$FILTER_FILE'))['mac_only']))"))
    VPS_ONLY=($(python3 -c "import json; print(' '.join(json.load(open('$FILTER_FILE'))['vps_only']))"))
else
    echo "WARNING: platform_filter.json not found, deploying all hooks"
    MAC_ONLY=()
    VPS_ONLY=()
fi

deployed=0
skipped=0

for hook in *.py; do
    [ "$hook" = "deploy_hooks.sh" ] && continue

    # Platform filter
    skip=false
    if [ "$PLATFORM" = "vps" ] && [ ${#MAC_ONLY[@]} -gt 0 ]; then
        for m in "${MAC_ONLY[@]}"; do
            [ "$hook" = "$m" ] && skip=true && break
        done
    elif [ "$PLATFORM" = "mac" ] && [ ${#VPS_ONLY[@]} -gt 0 ]; then
        for v in "${VPS_ONLY[@]}"; do
            [ "$hook" = "$v" ] && skip=true && break
        done
    fi

    if $skip; then
        echo "SKIP  $hook (${PLATFORM} excluded)"
        skipped=$((skipped + 1))
        continue
    fi

    # Check if target is different
    if [ -f "$TARGET/$hook" ] && diff -q "$hook" "$TARGET/$hook" > /dev/null 2>&1; then
        continue  # identical, skip silently
    fi

    if $DRY_RUN; then
        if [ -f "$TARGET/$hook" ]; then
            echo "UPDATE  $hook"
        else
            echo "NEW     $hook"
        fi
    else
        cp "$hook" "$TARGET/$hook"
        echo "DEPLOY  $hook"
    fi
    deployed=$((deployed + 1))
done

echo "---"
echo "Platform: $PLATFORM | Deployed: $deployed | Skipped: $skipped"
