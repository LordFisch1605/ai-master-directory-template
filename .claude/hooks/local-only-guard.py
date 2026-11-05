"""Local-only guard for Claude Code, registered in the user-level ~/.claude/settings.json.

  pre      PreToolUse: block a tool call that touches a "work" location (unless the session
           runs against a local model), any "private" location (always), or edits an existing
           file in a raw-data folder (always).
  session  SessionStart: warn when a work location is mounted in a cloud-model session.

Locations live in local-only-guard.json next to this file. Each entry is one of:
  "W:"              a Windows drive letter (also matched as /w/ and /mnt/w)
  "~/work-vault"    a path (~ expands to the home folder; on Linux/macOS, the mount point)
  "90-Work"         a folder name, matched anywhere in a path
A session is local only when ANTHROPIC_BASE_URL points at a host in "local_hosts".

Checked: path fields of file tools, shell commands, and the whole input of MCP tools.
Not checked: free text such as questions to the user, and the desktop app's own tools
(mcp__ccd_*: sessions, panes), so briefs for other sessions may name the locations.
A path built indirectly (variables, globbing from a parent folder) is not caught; an encrypted,
unmounted volume is the real protection. Works on Windows, Linux and macOS (Python 3, stdlib).
"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

CONFIG = json.loads((Path(__file__).with_suffix(".json")).read_text(encoding="utf-8"))
DRIVE = re.compile(r"^[A-Za-z]:$")

PATH_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep", "LS"}
PATH_KEYS = ("file_path", "path", "notebook_path", "pattern")
SHELL_TOOLS = {"Bash", "PowerShell"}
APP_MCP = "mcp__ccd_"  # Claude desktop app tools (sessions, panes): no data access


def location_pattern(entry):
    if DRIVE.match(entry):
        d = re.escape(entry[0])
        return (rf"(?<![A-Za-z0-9]){d}:(?=[\\/\"']|$)"   # W:\  W:/  "W:"
                rf"|(?<![\w.:/-])/{d}(?=[/\"'\s]|$)"      # Git Bash /w/...
                rf"|/mnt/{d}(?=[/\"'\s]|$)")              # WSL
    if "/" in entry or "\\" in entry or entry.startswith("~"):
        rel = entry[2:] if entry.startswith("~/") else None
        forms = {entry, os.path.expanduser(entry)}
        if rel:
            forms |= {f"$HOME/{rel}", f"${{HOME}}/{rel}", f"%USERPROFILE%\\{rel}"}
        alts = "|".join(r"[\\/]".join(map(re.escape, re.split(r"[\\/]", f))) for f in forms)
        return rf"(?:{alts})(?=[\\/\"'\s]|$)"
    return rf"(?<![\w-]){re.escape(entry)}(?![\w-])"


def compile_locations(entries):
    return re.compile("|".join(location_pattern(e) for e in entries), re.IGNORECASE)


WORK = compile_locations(CONFIG["work"])
PRIVATE = compile_locations(CONFIG["private"])
RAW = re.compile(r"[\\/](" + "|".join(map(re.escape, CONFIG["raw_dirs"])) + r")[\\/]", re.IGNORECASE)


def is_local():
    host = urlparse(os.environ.get("ANTHROPIC_BASE_URL", "")).hostname or ""
    return host.lower() in CONFIG["local_hosts"]


def block(reason):
    print(f"local-only-guard: {reason}", file=sys.stderr)
    sys.exit(2)


def checked_text(tool, tool_input):
    if tool in PATH_TOOLS:
        return "\n".join(str(tool_input.get(k, "")) for k in PATH_KEYS)
    if tool in SHELL_TOOLS:
        return str(tool_input.get("command", ""))
    if tool.startswith("mcp__") and not tool.startswith(APP_MCP):
        return json.dumps(tool_input, ensure_ascii=False)
    return ""


def pre(event):
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    text = checked_text(tool, tool_input)

    if PRIVATE.search(text):
        block("this location is closed to every agent. Ask the user to handle it.")
    if WORK.search(text) and not is_local():
        block("work locations are for local models only; this session runs against a cloud "
              "model. Do not try another route to the same files.")

    path = str(tool_input.get("file_path", ""))
    if RAW.search(path):
        if tool in {"Edit", "MultiEdit", "NotebookEdit"}:
            block("raw-data folders are write-protected: add new files, never change existing ones.")
        if tool == "Write" and os.path.exists(path):
            block(f"{path} already exists in a raw-data folder; raw files are never overwritten.")


def mounted(entry):
    if DRIVE.match(entry):
        return os.path.exists(entry + "\\")
    if "/" in entry or entry.startswith("~"):
        return os.path.ismount(os.path.expanduser(entry))
    return False


def session(_event):
    up = [e for e in CONFIG["work"] if mounted(e)]
    if up and not is_local():
        msg = (f"Work volume mounted ({', '.join(up)}) while a cloud-model session starts. "
               "Unmount it unless you need it now.")
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
