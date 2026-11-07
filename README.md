# AI master directory

A folder structure for working with AI agents (built around Claude Code): one place for tasks,
projects, study, skills and a retrieval knowledge base, plus two locked zones — one for work
data that only local models may touch, one for private data no agent may touch.

```
ai-master-directory/
  AGENTS.md  README.md  .gitignore
  .claude/hooks/local-only-guard.py   access rules, registered machine-wide
  01-Tasks/              agent tasks: research, plans, reviews
  02-Projects/
    01-Public/           projects that are or may become public
    02-Private/          all other projects
  03-Uni/                study material and papers
  04-Skills/             Claude Code skills (plugin marketplace)
  05-Knowledge/          vector database for RAG
  90-Work/               VeraCrypt container, mounted as W: — local models only
  91-Private/            sensitive data — no agent
```

Each area holding its own Git repo (tasks, every project, study, skills) is ignored by the root
repo, so the nested repos stay fully independent: own remote, own history, own push.

## Knowledge: skills, MCP, RAG, memory

- **Skills** — repeatable procedures → `04-Skills/`
- **MCP** — reaching outside systems → configured per machine, not stored here
- **RAG** — knowledge someone wrote down, retrieved by semantic search → `05-Knowledge/`
- **Memory** — what the agent learned itself → the agent's own memory

## Setup

1. Clone this repo wherever you keep your work.
2. Set your locked locations in `.claude/hooks/local-only-guard.json`: a drive letter on
   Windows (`"W:"`), a mount point on Linux/macOS (`"~/work-vault"`), and folder names.
3. Register the guard (Python 3, standard library only) in `~/.claude/settings.json`,
   replacing `<path>` with the absolute path of your clone, and `python` with `python3` on
   Linux/macOS:

   ```json
   "hooks": {
     "PreToolUse": [{ "matcher": "*", "hooks": [{ "type": "command",
       "command": "python \"<path>/.claude/hooks/local-only-guard.py\" pre" }] }],
     "SessionStart": [{ "hooks": [{ "type": "command",
       "command": "python \"<path>/.claude/hooks/local-only-guard.py\" session" }] }]
   }
   ```

4. Install VeraCrypt, create a file container `90-Work/Work.hc`, and mount it (as `W:` or at
   `~/work-vault`) only for sessions with a local model. Keep its password in a password
   manager, never in this folder.

## What the guard does not do

- It is a Claude Code hook. Other agents (OpenCode, other clients) do not run it; for them the
  unmounted encrypted volume and their own permission settings are the protection.
- It matches paths written out in a tool call. A path built indirectly, or a recursive search
  from a parent folder, is not caught — `91-Private/` is an ordinary folder, so put anything
  truly sensitive in an encrypted container as well.
- A shell command that merely mentions a locked location is blocked too.
- MCP tool input is matched as text only; do not register an MCP server that indexes the work
  volume in a cloud-model client.
