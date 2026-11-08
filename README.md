# AI master directory

A folder structure for AI-assisted work, and a setup that installs it on a fresh machine: one
place for tasks and projects, what an agent loads (hooks, skills, MCP servers), optionally a
local retrieval knowledge base, and a private zone no agent may touch. It works with any agent,
or with none: the conventions are just as usable by people.

- `CONVENTIONS.md` — how everything here is named, numbered and laid out, with an example of a
  grown directory.
- `AGENTS.md` — the rules every agent reads in every session here, and what this machine has
  installed.
- `setup/` — the install script and the same steps as single commands.

```
AGENTS.md  CONVENTIONS.md  README.md  INACCURACIES.md  .gitignore
setup/                 install.ps1, install.sh, setup.py, COMMANDS.md, knowledge/
01-Tasks/              tasks: research, plans, reviews
02-Projects/           01-Public, 02-Private, 03-External
03-Agent/              hooks/ (Claude Code hooks ship here), skills/, mcp/
91-Private/            sensitive data in a VeraCrypt container — no agent
```

Added by the setup only if you choose them:

```
03-Agent/skills/       a skill collection
04-Knowledge/          local vector search (RAG) over tasks and projects
```

## Install

Get this repo (`git clone`, or *Code > Download ZIP* on GitHub if Git is not installed yet),
then run from its root:

- Windows (PowerShell): `powershell -ExecutionPolicy Bypass -File setup\install.ps1`
- Linux/macOS: `bash setup/install.sh`

The bootstrap installs Python 3 if it is missing and starts `setup/setup.py`, which asks before
each step and each install. It installs only what the directory itself needs (Git, and Node,
Ollama or VeraCrypt for the parts you choose), never an AI agent unless you ask for one:

1. **Prerequisites** — Git, and which agent you use: Claude Code, another one, or none.
2. **Structure** — the area folders and a tasks repo (`01-Tasks/Tasks`).
3. **Hooks** (Claude Code only) — the access guard, and optionally the stay-inside hook, which
   blocks reading and writing (or only writing) outside this directory and all system-wide
   package installs. For other agents the hooks stay as files to build their own from.
4. **Knowledge base** — whether you want it, whether to use the recommended models, how much
   RAM it may take (4, 8 or 16+ GB), and how often the watcher checks for changes. Creates
   `04-Knowledge/`, installs Node (and Ollama for figures in PDFs), writes the MCP server config
   to `03-Agent/mcp/` (and registers it in Claude Code), optionally builds the index and starts
   the watcher at login.
5. **VeraCrypt** — installs it and creates `91-Private/Private.hc`; you set the password in
   VeraCrypt, the script never sees it.
6. **Skills** — clones a public skill collection into `03-Agent/skills/` (and installs it in
   Claude Code).

At the end it notes in `AGENTS.md` what was installed. Re-running is safe; finished steps are
detected. Every step by hand, for every OS: `setup/COMMANDS.md`.

## Four kinds of knowledge an agent uses

Where each lives here:

- **Skills** — procedures it follows → `03-Agent/skills/`
- **MCP servers** — tools it calls to reach other systems → `03-Agent/mcp/`
- **RAG** — documents someone wrote down, found by semantic search → `04-Knowledge/`
- **Memory** — what the agent learned itself → the agent's own memory, outside this directory

## What the hooks do not do

- They are Claude Code hooks. Other agents do not run them; for those, their own permission
  settings and the unmounted encrypted container are the protection.
- They match paths written out in a tool call. A path built indirectly, or a recursive search
  from a parent folder, is not caught — `91-Private/` is an ordinary folder, so keep anything
  truly sensitive inside the encrypted container.
- A shell command that merely mentions a locked location is blocked too.
- MCP tool input is matched as text only; do not index the private container.
- Stay-inside does not stop a program from writing outside on its own, such as a package
  manager's cache in the home folder.
