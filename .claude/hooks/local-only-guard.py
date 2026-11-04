"""Local-only guard for Claude Code, registered in ~/.claude/settings.json.

  pre      PreToolUse: block a tool call that touches the Work drive or 90-Work
           (unless the session runs against a local model), anything in 91-Private
           (always), or edits an existing file in a raw-data folder (always).
  session  SessionStart: warn when the Work drive is mounted in a cloud session.

A session counts as local only when ANTHROPIC_BASE_URL points at a host in LOCAL_HOSTS.
This matches paths written out in a tool call; a path built indirectly
(variables, globbing from a parent folder) is not caught. The VeraCrypt container is
the real protection; this hook is the second layer.
"""
import json
import os
import re
import sys
from urllib.parse import urlparse

WORK_DRIVE = "W"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

WORK = re.compile(
    rf"(?<![A-Za-z0-9]){WORK_DRIVE}:(?=[\\/\"']|$)"   # W:\  W:/  "W:"
    rf"|(?<![\w.:/-])/{WORK_DRIVE}(?=[/\"'\s]|$)"     # Git Bash /w/...
    rf"|/mnt/{WORK_DRIVE}(?=[/\"'\s]|$)"              # WSL
    r"|90-Work",
    re.IGNORECASE,
)
PRIVATE = re.compile(r"91-Private", re.IGNORECASE)
RAW = re.compile(r"[\\/](_raw|_rohdaten|Quellen)[\\/]", re.IGNORECASE)

PATH_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep", "LS"}
PATH_KEYS = ("file_path", "path", "notebook_path", "pattern")


def is_local():
    host = urlparse(os.environ.get("ANTHROPIC_BASE_URL", "")).hostname or ""
    return host.lower() in LOCAL_HOSTS


def block(reason):
    print(f"local-only-guard: {reason}", file=sys.stderr)
    sys.exit(2)


def pre(event):
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    if tool in PATH_TOOLS:
        text = "\n".join(str(tool_input.get(k, "")) for k in PATH_KEYS)
    else:
        text = json.dumps(tool_input, ensure_ascii=False)

    if PRIVATE.search(text):
        block("91-Private is closed to every agent. Ask the user to handle it.")
    if WORK.search(text) and not is_local():
        block(f"90-Work and drive {WORK_DRIVE}: are for local models only; this session "
              "runs against a cloud model. Do not try another route to the same files.")

    path = str(tool_input.get("file_path", ""))
    if RAW.search(path):
        if tool in {"Edit", "MultiEdit", "NotebookEdit"}:
            block("raw-data folders (_raw, _rohdaten, Quellen) are write-protected: "
                  "add new files, never change existing ones.")
        if tool == "Write" and os.path.exists(path):
            block(f"{path} already exists in a raw-data folder; raw files are never overwritten.")


def session(_event):
    if os.path.exists(f"{WORK_DRIVE}:\\") and not is_local():
        msg = (f"Work drive {WORK_DRIVE}: is mounted while a cloud-model session starts. "
               "Unmount it in VeraCrypt unless you need it now.")
        print(json.dumps({
            "systemMessage": msg,
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg},
        }))


if __name__ == "__main__":
    mode = sys.argv[1]
    try:
        event = json.load(sys.stdin)
        {"pre": pre, "session": session}[mode](event)
    except SystemExit:
        raise
    except Exception as exc:  # a broken guard must not let a tool call through
        if mode == "pre":
            block(f"guard failed ({exc!r}); call blocked to be safe.")
        raise
