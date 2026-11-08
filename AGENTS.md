# AGENTS.md — AI master directory

One directory for all AI-assisted work: tasks, projects, study, skills, and the knowledge base
agents retrieve from. Where an area has its own `AGENTS.md`, that file wins inside it.

The rules live in `AGENTS.md` files only, read by every coding tool. Never add a `CLAUDE.md`
anywhere in this tree: for Claude Code, one `CLAUDE.md` in the start folder or above switches
every `AGENTS.md` off.

## 1. Areas

| Folder | Holds | Own Git repo? |
|---|---|---|
| `01-Tasks/` | Agent tasks: research, plans, reviews — one task, one folder | yes |
| `02-Projects/01-Public/` | Projects that are or may become public; nothing private in them | one per project |
| `02-Projects/02-Private/` | All other projects | one per project |
| `03-Uni/` | Study material and papers | yes |
| `04-Skills/` | Claude Code skills, as a plugin marketplace | yes |
| `05-Knowledge/` | Knowledge base for retrieval (vector database), see its README | root repo |
| `90-Work/` | Work data, VeraCrypt container only — **local models only** | never in Git |
| `91-Private/` | Sensitive personal data — **no agent at all** | never in Git |

## 2. Access rules

Enforced by `.claude/hooks/local-only-guard.py`, registered in the user-level
`~/.claude/settings.json`, so it holds in every Claude Code session on the machine.

- **`90-Work/` and drive `W:`** (the mounted VeraCrypt volume): blocked for any session that
  runs against a cloud model. Allowed only when `ANTHROPIC_BASE_URL` points at localhost.
  A cloud session that starts while `W:` is mounted shows a warning.
- **`91-Private/`**: blocked for every agent, local ones included.
- **Raw data** (`_raw/`, `_rohdaten/`, `Quellen/`, anywhere): new files may be added, existing
  ones are never edited or overwritten.

The locked locations are listed in `.claude/hooks/local-only-guard.json` (Windows drive `W:`,
Linux/macOS mount point `~/work-vault`, the folder names). The hook checks file-tool paths,
shell commands and MCP tool input; it works on Windows, Linux and macOS.

A block is final. Do not look for another route to the same files (a variable, a parent-folder
glob, another tool); tell the user what you needed instead. The hook only matches paths written
out in a call, so keeping to the rule is on you, not on the hook. It is a Claude Code hook:
other agents do not run it.

## 3. Git

The root is a slim repo: this file, `README.md`, `.claude/`, `05-Knowledge/`. Areas with their
own repo, and `90-Work/` and `91-Private/`, are in `.gitignore`, so nested repos stay
independent and work data never reaches a remote. Commit messages describe the substance.

## 4. Inaccuracies in `.md` files

Do not hunt for them, but act on every one you notice while working: a wrong path, a stale
count or version, a rule two files state differently, a pointer to something that moved.

- **The fix is clear** (one right answer, e.g. the new path of a moved folder): fix it at once,
  in its own commit, and name it to the owner in your handoff.
- **Otherwise:** add a line to `INACCURACIES.md` at the root (date, file, what is off, what you
  saw) and tell the owner. Do not guess a fix.

This is how an imperfect migration gets cleaned up by the agents that come after it. Raw data
(`_raw/` and the like) is never edited, not even to fix it.
