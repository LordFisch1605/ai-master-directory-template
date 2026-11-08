"""Stay-inside hook for Claude Code (PreToolUse): keeps the agent inside this directory.

  python stay-inside.py pre      registered for PreToolUse with matcher "*"

The directory is the folder three levels above this file (03-Agent/hooks/claude-code/). Settings in stay-inside.json:
  "mode": "readwrite"   block reading and writing outside the directory
          "write"       reading outside stays allowed; writing outside is blocked
  "allow": [...]        extra paths that count as inside (e.g. the agent's temp folder)

What it checks (text only, like local-only-guard.py):
  - file tools (Read, Write, Edit, Glob, Grep, ...): the path they name;
  - shell commands: absolute, home (~) and ../ paths written in the command; in "write" mode only
    when the command also writes (redirection, cp, mv, rm, Set-Content, ...);
  - shell commands that install packages system-wide (winget, brew, apt, npm -g, pip --user,
    ...): always blocked, in both modes. Installing is then the user's job.
Not caught: paths built at run time, programs that write outside on their own (a package
manager's cache in the home folder, a build tool's global store). It is a guard rail for an
agent that follows the rules, not a sandbox.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONFIG = json.loads((HERE / "stay-inside.json").read_text(encoding="utf-8"))
READ_TOOLS = {"Read", "Glob", "Grep", "LS"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PATH_KEYS = ("file_path", "path", "notebook_path")
SHELL_TOOLS = {"Bash", "PowerShell"}
INSTALL = re.compile(
    r"(^|[;&|(]\s*|\s)(winget|choco|scoop|brew|apt|apt-get|dnf|yum|pacman|zypper|snap|flatpak|pipx|"
    r"cargo\s+install|go\s+install|gem\s+install|npm\s+(i|install|add)\b[^;&|]*\s(-g|--global)\b|"
    r"pnpm\s+add\b[^;&|]*\s(-g|--global)\b|pip3?\s+install\b[^;&|]*--user|"
    r"Install-Module|Install-Package)\b", re.IGNORECASE)
WRITES = re.compile(
    r"(>|\b(cp|mv|rm|rmdir|mkdir|touch|tee|ln|chmod|chown|dd|install|rsync|scp|tar|unzip|"
    r"Set-Content|Add-Content|Out-File|New-Item|Remove-Item|Copy-Item|Move-Item|Rename-Item|"
    r"Expand-Archive)\b)", re.IGNORECASE)
PATHS = re.compile(r"""(?:(?<=^)|(?<=[\s'"=(]))([A-Za-z]:[\\/][^\s'";|&)]*|~[\\/]?[^\s'";|&)]*|/[^\s'";|&)]+|\.\.[\\/][^\s'";|&)]*)""")


def inside(p, cwd):
    p = os.path.expanduser(p)
    full = Path(p if os.path.isabs(p) else os.path.join(cwd, p))
    full = Path(os.path.normcase(os.path.abspath(full)))
    for base in [ROOT] + [Path(os.path.expanduser(a)) for a in CONFIG.get("allow", [])]:
        base = Path(os.path.normcase(os.path.abspath(base)))
        if full == base or base in full.parents:
            return True
    return False


def block(reason):
    print(f"stay-inside: {reason} Ask the user to do it, or to add the path to "
          f"03-Agent/hooks/claude-code/stay-inside.json \"allow\".", file=sys.stderr)
    sys.exit(2)


def pre(event):
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    cwd = event.get("cwd") or os.getcwd()
    write_only = CONFIG.get("mode", "readwrite") == "write"

    if tool in READ_TOOLS | WRITE_TOOLS:
        if write_only and tool in READ_TOOLS:
            return
        keys = PATH_KEYS + (("pattern",) if tool == "Glob" else ())  # a Glob pattern may be a path
        for key in keys:
            if tool_input.get(key) and not inside(str(tool_input[key]), cwd):
                block(f"{tool_input[key]} is outside {ROOT}.")
    elif tool in SHELL_TOOLS:
        command = str(tool_input.get("command", ""))
        if INSTALL.search(command):
            block("installing packages system-wide is outside this directory.")
        if not inside(cwd, cwd):
            block(f"the shell runs outside {ROOT}.")
        if write_only and not WRITES.search(command):
            return
        for p in PATHS.findall(command):
            if p.startswith("/") and os.name == "nt" and not re.match(r"/[a-zA-Z]/", p):
                continue  # on Windows a lone /x is usually a command switch, not a path
            if re.match(r"/[a-zA-Z]/", p) and os.name == "nt":
                p = p[1] + ":" + p[2:]  # Git Bash spelling /c/Users -> c:/Users
            if not inside(p, cwd):
                block(f"the command names {p}, which is outside {ROOT}.")


if __name__ == "__main__":
    try:
        pre(json.load(sys.stdin))
    except SystemExit:
        raise
    except Exception as exc:  # a broken hook must not let a tool call through
        block(f"hook failed ({exc!r}); call blocked to be safe.")
