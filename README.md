# AI master directory

A folder structure for working with AI agents (built around Claude Code), and a setup that
installs it on a fresh machine: one place for tasks, projects, study, skills and a local
retrieval knowledge base, plus a private zone no agent may touch.

- `CONVENTIONS.md` — how everything here is named, numbered and laid out, with an example of a
  grown directory. Agents follow it when they create something; so can you.
- `AGENTS.md` — the rules every agent reads in every session here.
- `setup/` — the install script and the same steps as single commands.

```
AGENTS.md  CONVENTIONS.md  README.md  INACCURACIES.md  .gitignore
.claude/hooks/         access guard, registered machine-wide
setup/                 install.ps1, install.sh, setup.py, COMMANDS.md
01-Tasks/              agent tasks: research, plans, reviews
02-Projects/           01-Public, 02-Private, 03-External
03-Uni/                study material and papers
04-Skills/             skills (plugin marketplaces)
05-Knowledge/          local vector search (RAG) over all of the above
91-Private/            sensitive data in a VeraCrypt container — no agent
```

## Install

Get this repo (`git clone`, or *Code > Download ZIP* on GitHub if Git is not installed yet),
then run from its root:

- Windows (PowerShell): `powershell -ExecutionPolicy Bypass -File setup\install.ps1`
- Linux/macOS: `bash setup/install.sh`

The bootstrap installs Python 3 if it is missing and starts `setup/setup.py`, which asks before
each step and each install:

1. **Prerequisites** — Git and Claude Code, if missing.
2. **Structure** — the area folders, a tasks repo (`01-Tasks/Tasks`), a study repo if you study.
3. **Access guard** — where your private container is mounted; registers the guard hook in
   `~/.claude/settings.json` (a backup is kept as `settings.json.bak`).
4. **Knowledge base** — whether you want it, whether to use the recommended models, and how
   much RAM it may take (4, 8 or 16+ GB). Installs Node (and Ollama for figures in PDFs),
   writes the config, registers the search servers in Claude Code, optionally builds the index
   and starts the watcher at login.
5. **VeraCrypt** — installs it and creates `91-Private/Private.hc`; you set the password in
   VeraCrypt, the script never sees it.
6. **Skills** — clones a public skill marketplace into `04-Skills/` and installs its plugins.

Re-running is safe; finished steps are detected. Every step by hand, for every OS:
`setup/COMMANDS.md`.

## Knowledge: skills, MCP, RAG, memory

- **Skills** — repeatable procedures → `04-Skills/`
- **MCP** — reaching outside systems → configured per machine, not stored here
- **RAG** — knowledge someone wrote down, retrieved by semantic search → `05-Knowledge/`
- **Memory** — what the agent learned itself → the agent's own memory

## What the guard does not do

- It is a Claude Code hook. Other agents (OpenCode, other clients) do not run it; for them the
  unmounted encrypted container and their own permission settings are the protection.
- It matches paths written out in a tool call. A path built indirectly, or a recursive search
  from a parent folder, is not caught — `91-Private/` is an ordinary folder, so keep anything
  truly sensitive inside the encrypted container.
- A shell command that merely mentions a locked location is blocked too.
- MCP tool input is matched as text only; do not index the private container.
