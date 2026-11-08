# Setup commands

Every step of `setup.py`, by hand, for more control. Run them from the directory's root.
`<root>` is its absolute path with forward slashes (`C:/Users/you/AI-Master-Directory`,
`/home/you/AI-Master-Directory`). Windows commands are PowerShell; Linux examples use `apt`
(`dnf` and `pacman` take the same package names).

No step needs an AI agent. Steps marked **Claude Code** register something in it; with another
agent, do the equivalent in its own config (its docs say where hooks, permissions, MCP servers
and skills go), and with none, skip them.

## 1. Prerequisites

| Tool | Windows | macOS (Homebrew, brew.sh) | Linux |
|---|---|---|---|
| Python 3 | `winget install -e --id Python.Python.3.13` | `brew install python` | `sudo apt install python3 python3-pip` |
| Git | `winget install -e --id Git.Git` | `brew install git` | `sudo apt install git` |

Open a new terminal after installing, so the new `PATH` is read.

## 2. Folders and area repos

```bash
git init
git init 01-Tasks/Tasks
```

Then give the tasks repo an `AGENTS.md` that points to `../../AGENTS.md` and
`../../CONVENTIONS.md`, and create the task categories (`CONVENTIONS.md`, section 4). PowerShell
runs these lines as they are.

## 3. Hooks (Claude Code)

Both hooks are in `03-Agent/hooks/claude-code/`; their docstrings say exactly what they check,
which is also the specification for building them in another agent.

**Access guard.** Set the private locations in `local-only-guard.json`: `"private"` lists the
drive letter of the mounted container (`"P:"`), the mount point (`"~/private-vault"`) and the
folder name (`"91-Private"`). `"work"` is for local-only locations, empty by default.

**Stay-inside (optional).** Set `"mode"` in `stay-inside.json`: `"readwrite"` blocks reading
and writing outside this directory, `"write"` only writing. Both modes block system-wide
package installs (winget, brew, apt, `npm -g`, `pip --user` …), so you install those yourself.
Paths that should count as inside (e.g. the agent's temp folder) go into `"allow"`.

Merge the hooks you want into `~/.claude/settings.json` (`%USERPROFILE%\.claude\settings.json`
on Windows); `python` is `python3` on Linux/macOS. Leave out the stay-inside entry if you do not
want it:

```json
"hooks": {
  "PreToolUse": [
    { "matcher": "*", "hooks": [{ "type": "command",
      "command": "python \"<root>/03-Agent/hooks/claude-code/local-only-guard.py\" pre" }] },
    { "matcher": "*", "hooks": [{ "type": "command",
      "command": "python \"<root>/03-Agent/hooks/claude-code/stay-inside.py\" pre" }] }
  ],
  "SessionStart": [{ "hooks": [{ "type": "command",
    "command": "python \"<root>/03-Agent/hooks/claude-code/local-only-guard.py\" session" }] }]
}
```

Check it: in a new session, ask the agent to list `91-Private`. It must be blocked.

## 4. Knowledge base (RAG)

### Node 26.12.1 or newer

| Windows | macOS | Linux |
|---|---|---|
| `winget install -e --id OpenJS.NodeJS` | `brew install node` | distribution packages are usually older; use nvm: |

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
nvm install 26
```

Check with `node --version`.

### Folder and config

The scripts ship in `setup/knowledge/`; the knowledge area is created from them:

```bash
cp -r setup/knowledge 04-Knowledge
cp 04-Knowledge/instances.example.json 04-Knowledge/instances.json
```

On Windows: `Copy-Item -Recurse setup\knowledge 04-Knowledge`, then
`Copy-Item 04-Knowledge\instances.example.json 04-Knowledge\instances.json`.
Replace `~/ai-master-directory` with `<root>` in it. `interval_seconds` is how often the watcher
checks for changed files (300 = every 5 minutes; an unchanged pass costs a few seconds of
scanning). Memory per machine:

| RAM it may take | `batch_size` | `captions.model` |
|---|---|---|
| 4 GB | 2 | `bonsai-2:4b`, or remove the `captions` block |
| 8 GB | 4 | `bonsai-2:9b` |
| 16 GB or more | 16 | `bonsai-2:9b` |

`device` stays `cpu` unless you test a GPU backend (`04-Knowledge/README.md`).

### Figure captions (optional)

| | Windows | macOS | Linux |
|---|---|---|---|
| Ollama | `winget install -e --id Ollama.Ollama` | `brew install ollama` | `curl -fsSL https://ollama.com/install.sh \| sh` |

```bash
ollama pull bonsai-2:9b
python -m pip install --user pypdfium2
```

On Linux distributions that refuse `pip install --user`, install `pypdfium2` into a venv and
run the watcher with that venv's Python.

### First build

```bash
python 04-Knowledge/watcher.py --once
```

This installs the patched tool into `04-Knowledge/.tool/0.23.1/` and builds both indexes; the
first run takes minutes to hours.

### Register the search servers

Each instance (`knowledge`, `raw`) is a stdio MCP server: command `node`, argument
`<root>/04-Knowledge/.tool/0.23.1/node_modules/mcp-local-rag/dist/index.js`, and these
environment variables, with that instance's `db` path:

```json
{ "mcpServers": { "knowledge": {
  "command": "node",
  "args": ["<root>/04-Knowledge/.tool/0.23.1/node_modules/mcp-local-rag/dist/index.js"],
  "env": { "BASE_DIR": "<root>", "DB_PATH": "<root>/04-Knowledge/.index/knowledge",
           "CACHE_DIR": "<root>/04-Knowledge/.models",
           "MODEL_NAME": "onnx-community/embeddinggemma-2-ONNX",
           "RAG_HYBRID_WEIGHT": "0", "RAG_MAX_TOKENS": "2048" } } } }
```

Keep it in `03-Agent/mcp/knowledge-servers.json` and add it to your agent's MCP config. Deny the
agent the servers' write tools (`sync_start`, `ingest_file`, `ingest_data`, `delete_file`), so
only the watcher writes the index.

**Claude Code**, once per instance:

```bash
claude mcp add -s user knowledge -e BASE_DIR=<root> -e DB_PATH=<root>/04-Knowledge/.index/knowledge -e CACHE_DIR=<root>/04-Knowledge/.models -e MODEL_NAME=onnx-community/embeddinggemma-2-ONNX -e RAG_HYBRID_WEIGHT=0 -e RAG_MAX_TOKENS=2048 -- node <root>/04-Knowledge/.tool/0.23.1/node_modules/mcp-local-rag/dist/index.js
```

and the deny rules in `~/.claude/settings.json`:

```json
"permissions": { "deny": [
  "mcp__knowledge__sync_start", "mcp__knowledge__ingest_file",
  "mcp__knowledge__ingest_data", "mcp__knowledge__delete_file",
  "mcp__raw__sync_start", "mcp__raw__ingest_file",
  "mcp__raw__ingest_data", "mcp__raw__delete_file"
] }
```

### Autostart of the watcher

- Windows (PowerShell; the path to `pythonw.exe` from `where.exe pythonw`):

  ```powershell
  $a = New-ScheduledTaskAction -Execute "pythonw.exe" -Argument '"<root>\04-Knowledge\watcher.py"'
  $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  Register-ScheduledTask -TaskName "Knowledge Watcher" -Action $a -Trigger $t
  ```

- Linux: `~/.config/systemd/user/knowledge-watcher.service`:

  ```ini
  [Service]
  ExecStart=/usr/bin/python3 <root>/04-Knowledge/watcher.py
  Environment=PATH=<folder of node>:/usr/bin:/bin
  Restart=on-failure

  [Install]
  WantedBy=default.target
  ```

  ```bash
  systemctl --user enable --now knowledge-watcher
  ```

- macOS: `~/Library/LaunchAgents/local.knowledge-watcher.plist` with `ProgramArguments`
  `python3 <root>/04-Knowledge/watcher.py`, `EnvironmentVariables` `PATH` containing the
  folder of `node`, `RunAtLoad` and `KeepAlive` true; then:

  ```bash
  launchctl load -w ~/Library/LaunchAgents/local.knowledge-watcher.plist
  ```

### Exact-term search (optional)

`rg` finds every occurrence of a term the index may miss; `rga` also reads PDFs and `.docx`.

| Windows | macOS | Linux |
|---|---|---|
| `winget install -e --id BurntSushi.ripgrep.MSVC` | `brew install ripgrep ripgrep-all` | `sudo apt install ripgrep` |

`rga` on Windows and Linux: release binaries on its GitHub page (`phiresky/ripgrep-all`), plus
Pandoc and Poppler for `.docx` and PDF.

## 5. VeraCrypt for `91-Private`

### Install

| Windows | macOS | Linux |
|---|---|---|
| `winget install -e --id IDRIX.VeraCrypt` | `brew install --cask macfuse veracrypt` (allow macFUSE in System Settings > Privacy & Security) | package for your distribution from veracrypt.io/en/Downloads.html |

### Create the container

- Windows: open **VeraCrypt Format**, choose *Create an encrypted file container* > *Standard*,
  file `<root>\91-Private\Private.hc`, AES, a size such as 10 GB, your password.
- Linux (on macOS the binary is `/Applications/VeraCrypt.app/Contents/MacOS/VeraCrypt`):

  ```bash
  veracrypt --text --create 91-Private/Private.hc --size 10G --volume-type normal --encryption AES --hash sha-512 --filesystem exfat --pim 0 --keyfiles "" --random-source /dev/urandom
  ```

VeraCrypt asks for the password itself. Keep it in a password manager, never in this tree.

### Mount and unmount

| | Mount | Unmount |
|---|---|---|
| Windows | `& "C:\Program Files\VeraCrypt\VeraCrypt.exe" /q /v "<root>\91-Private\Private.hc" /l P` | `& "C:\Program Files\VeraCrypt\VeraCrypt.exe" /q /d P` |
| Linux/macOS | `mkdir -p ~/private-vault` then `veracrypt --text --mount 91-Private/Private.hc ~/private-vault` | `veracrypt --text --dismount ~/private-vault` |

Use the drive letter and mount point that are in the guard's `"private"` list.

## 6. Skills

```bash
git clone https://github.com/LordFisch1605/paul-skills-public.git 03-Agent/skills/paul-skills-public
```

Each skill is a `SKILL.md` under `plugins/*/skills/`; load them the way your agent loads skills
or instructions.

**Claude Code** installs them as plugins:

```bash
claude plugin marketplace add ./03-Agent/skills/paul-skills-public
claude plugin install paul-base@paul-skills-public -s user
claude plugin install paul-dev@paul-skills-public -s user
```

`paul-base` adds a SessionStart hook that injects its working rules into every session and a
short reminder to every prompt; read `plugins/paul-base/skills/base-conduct/SKILL.md` first.
Restart Claude Code afterwards.
