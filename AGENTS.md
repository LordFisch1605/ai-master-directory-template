# AGENTS.md — AI master directory

One directory for AI-assisted work: tasks, projects, and optionally skills and a knowledge base
agents retrieve from. It does not depend on one agent or framework, and people can work in it
by the same rules. Where an area has its own `AGENTS.md`, that file wins inside it.

How folders and files are named, numbered and laid out is in `CONVENTIONS.md`: follow it
whenever you create something here. This file holds the rules that must not be broken.

The rules live in `AGENTS.md` files, which most coding agents read. If you are Claude Code:
never add a `CLAUDE.md` anywhere in this tree, since one `CLAUDE.md` in the start folder or above
switches every `AGENTS.md` off for Claude Code.

## 0. What is installed here

Parts of this directory are optional, so a folder named below may be missing on this machine.
That is expected. Do not create a missing optional area unless the user asks for it. The setup
records here what it installed:

<!-- setup:start -->
Not set up yet: run `setup/install.ps1` (Windows) or `setup/install.sh` (Linux/macOS).
<!-- setup:end -->

## 1. Areas

| Folder | Holds | Own Git repo? |
|---|---|---|
| `01-Tasks/` | Agent tasks: research, plans, reviews — one task, one folder | yes, one level down |
| `02-Projects/01-Public/` | Projects that are or may become public; nothing private in them | one per project |
| `02-Projects/02-Private/` | All other projects, numbered by age | one per project |
| `02-Projects/03-External/` | Third-party repos you run or study (not numbered) | upstream's |
| `03-Agent/` | What an agent loads: `hooks/`, `skills/` (optional), `mcp/` server configs | root repo; each skill collection its own |
| `04-Knowledge/` | Knowledge base for retrieval, a vector database; see its README (optional) | root repo |
| `91-Private/` | Sensitive personal data, ideally a VeraCrypt container — **no agent at all** | never in Git |

## 2. Access rules

These rules hold for every agent, whether or not something enforces them:

- **`91-Private/`** and the mounted private container (`P:`, `~/private-vault`, or what the
  guard config names): never read, list, search or write it, local models included.
- **Raw data** (`_raw/`, `_rohdaten/`, `Quellen/`, anywhere): new files may be added, existing
  ones are never edited or overwritten.
- **Local-only locations** (the guard config's `work` list, empty by default): only for agents
  that run against a local model.

`03-Agent/hooks/claude-code/` enforces them for Claude Code (`local-only-guard.py`, locations in
`local-only-guard.json`) and can keep it inside this directory (`stay-inside.py`); section 0
says which of them are registered. Another agent can build its own hooks or permission rules
from those files. Where nothing enforces the rules, keeping them is on you.

A block is final. Do not look for another route to the same files (a variable, a parent-folder
glob, another tool); tell the user what you needed instead. A hook only matches paths written
out in a call, so keeping to the rules is on you, not on the hook.

## 3. Git

The root is a slim repo: the top-level files, `setup/`, `03-Agent/` (without the skill repos)
and `04-Knowledge/` (without the index). Areas with their own repo, and `91-Private/`, are in
`.gitignore`, so nested repos stay independent and private data never reaches a remote. Commit messages describe the substance.

## 4. Inaccuracies in `.md` files

Do not hunt for them, but act on every one you notice while working: a wrong path, a stale
count or version, a rule two files state differently, a pointer to something that moved.

- **The fix is clear** (one right answer, e.g. the new path of a moved folder): fix it at once,
  in its own commit, and name it to the owner in your handoff.
- **Otherwise:** add a line to `INACCURACIES.md` at the root (date, file, what is off, what you
  saw) and tell the owner. Do not guess a fix.

This is how an imperfect migration gets cleaned up by the agents that come after it. Raw data
(`_raw/` and the like) is never edited, not even to fix it.
