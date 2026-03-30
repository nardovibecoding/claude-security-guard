#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""PostToolUse hook: catch Telegram API misuse patterns.

Catches:
1. Missing RetryAfter / rate-limit handling in send/edit/answer calls
2. Unbounded growth: dicts/lists stored in bot_data/context.chat_data
   without any eviction/maxlen
3. Non-atomic file saves (write directly to target, not write-then-rename)
4. TOCTOU: os.path.exists() or Path.exists() check followed by open()/rename()
   without a lock (race condition)
5. asyncio.gather without return_exceptions=True (one failure kills all)

Commits this prevents: 429a5dc (8), ff1bd59 (9), 6f65919 (11)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# Telegram send/edit calls — check if RetryAfter is handled nearby
_TG_SEND = re.compile(
    r"(send_message|send_photo|send_document|send_audio|edit_message_text|"
    r"answer_callback_query|reply_text|reply_photo)\s*\("
)
_RETRY_HANDLING = re.compile(r"RetryAfter|Flood|retry_after|telegram\.error")

# bot_data / context.chat_data assignment
_BOT_DATA_SET = re.compile(
    r"(bot_data|chat_data|user_data)\s*\[.*\]\s*="
)
_HAS_MAXLEN = re.compile(r"maxlen|max_size|evict|LRU|deque|OrderedDict")

# Non-atomic file save: open(path, 'w') where path is the final file
_DIRECT_WRITE = re.compile(r"""open\s*\(\s*(\w+)\s*,\s*['"]w['"]\s*\)""")
_ATOMIC_WRITE = re.compile(r"\.tmp|tempfile|_tmp|write_then_rename|atomic")

# TOCTOU: exists() check then open/rename without lock
_EXISTS_CHECK = re.compile(r"\.(exists|is_file)\s*\(\s*\)")
_LOCK_NEARBY = re.compile(r"lock|Lock|acquire|FileLock|flock")

# asyncio.gather without return_exceptions
_GATHER_NO_EXC = re.compile(r"asyncio\.gather\s*\([^)]*\)")
_HAS_RETURN_EXC = re.compile(r"return_exceptions\s*=\s*True")


def _scan(content):
    lines = content.splitlines()
    warnings = []

    # Check for Telegram send calls with no RetryAfter handling in the file
    has_tg_send = any(_TG_SEND.search(l) for l in lines)
    has_retry = any(_RETRY_HANDLING.search(l) for l in lines)
    if has_tg_send and not has_retry:
        warnings.append(
            "  No RetryAfter/TelegramError handling found, but Telegram send calls present. "
            "Wrap sends in try/except telegram.error.RetryAfter to survive flood limits."
        )

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # bot_data / chat_data assignment without eviction
        if _BOT_DATA_SET.search(line):
            window = "\n".join(lines[max(0, i-5):min(len(lines), i+5)])
            if not _HAS_MAXLEN.search(window):
                warnings.append(
                    f"  line ~{i}: `{stripped[:80]}` — "
                    "bot_data/chat_data grows unbounded. "
                    "Use collections.deque(maxlen=N) or periodic cleanup."
                )

        # Direct file write (non-atomic)
        if _DIRECT_WRITE.search(line):
            window = "\n".join(lines[max(0, i-3):min(len(lines), i+3)])
            if not _ATOMIC_WRITE.search(window):
                warnings.append(
                    f"  line ~{i}: `{stripped[:80]}` — "
                    "direct open(path, 'w') is non-atomic (crash = corrupt file). "
                    "Write to a .tmp file then os.replace() for atomicity."
                )

        # TOCTOU: exists() check
        if _EXISTS_CHECK.search(line):
            window = "\n".join(lines[max(0, i-2):min(len(lines), i+6)])
            if re.search(r"\bopen\s*\(|\brename\s*\(|\bos\.replace\s*\(", window):
                if not _LOCK_NEARBY.search(window):
                    warnings.append(
                        f"  line ~{i}: `{stripped[:80]}` — "
                        "TOCTOU: exists() check followed by open()/rename() without a lock. "
                        "Another process can create/delete the file between check and use."
                    )

        # asyncio.gather without return_exceptions
        if _GATHER_NO_EXC.search(line) and not _HAS_RETURN_EXC.search(line):
            warnings.append(
                f"  line ~{i}: `{stripped[:80]}` — "
                "asyncio.gather() without return_exceptions=True. "
                "One exception cancels all tasks; use return_exceptions=True and check results."
            )

    return warnings


def check(tool_name, tool_input, _input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    fp = tool_input.get("file_path", "")
    if not fp.endswith(".py"):
        return False
    if "tg_api_guard" in fp:
        return False
    return True


def action(tool_name, tool_input, _input_data):
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    warnings = _scan(content)
    if not warnings:
        return None

    fp = tool_input.get("file_path", "")
    return (
        f"TG API GUARD: Telegram API anti-patterns in `{Path(fp).name}`.\n"
        + "\n".join(warnings[:5])
    )


if __name__ == "__main__":
    run_hook(check, action, "tg_api_guard")
