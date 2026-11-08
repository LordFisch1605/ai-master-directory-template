# Setup commands

Every step of `setup.py`, by hand, for more control. Run them from the directory's root.
`<root>` is its absolute path with forward slashes (`C:/Users/you/AI-Master-Directory`,
`/home/you/AI-Master-Directory`). Windows commands are PowerShell; Linux examples use `apt`
(`dnf` and `pacman` take the same package names).

## 1. Prerequisites

| Tool | Windows | macOS (Homebrew, brew.sh) | Linux |
|---|---|---|---|
| Python 3 | `winget install -e --id Python.Python.3.13` | `brew install python` | `sudo apt install python3 python3-pip` |
| Git | `winget install -e --id Git.Git` | `brew install git` | `sudo apt install git` |
| Claude Code | `irm https://claude.ai/install.ps1 \| iex` | `curl -fsSL https://claude.ai/install.sh \| bash` | same as macOS |

Open a new terminal after installing, so the new `PATH` is read.

## 2. Folders and area repos

```bash
git init
git init 01-Tasks/Tasks
```

Then give the tasks repo an `AGENTS.md` that points to `../../AGENTS.md` and
`../../CONVENTIONS.md`, and create the task categories (`CONVENTIONS.md`, section 4). PowerShell
runs these lines as they are.

## 3. Access guard

1. Set the private locations in `.claude/hooks/local-only-guard.json`: `"private"` lists the
   drive letter of the mounted container (`"P:"`), the mount point (`"~/private-vault"`) and
   the folder name (`"91-Private"`). `"work"` is for local-only locations, empty by default.
2. Merge this into `~/.claude/settings.json` (`%USERPROFILE%\.claude\settings.json` on
   Windows); `python` is `python3` on Linux/macOS:

   ```json
   "hooks": {
     "PreToolUse": [{ "matcher": "*", "hooks": [{ "type": "command",
       "command": "python \"<root>/.claude/hooks/local-only-guard.py\" pre" }] }],
     "SessionStart": [{ "hooks": [{ "type": "command",
       "command": "python \"<root>/.claude/hooks/local-only-guard.py\" session" }] }]
   }
   ```

3. Check it: in a new Claude Code session, ask the agent to list `91-Private`. It must be blocked.

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
Replace `~/ai-master-directory` with `<root>` in it. Memory per machine:

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

### Register in Claude Code

Once per instance (`knowledge`, `raw`), with that instance's `db` path:

```bash
claude mcp add -s user knowledge -e BASE_DIR=<root> -e DB_PATH=<root>/04-Knowledge/.index/knowledge -e CACHE_DIR=<root>/04-Knowledge/.models -e MODEL_NAME=onnx-community/embeddinggemma-2-ONNX -e RAG_HYBRID_WEIGHT=0 -e RAG_MAX_TOKENS=2048 -- node <root>/04-Knowledge/.tool/0.23.1/node_modules/mcp-local-rag/dist/index.js
```

Then keep agents from writing to the index; add to `~/.claude/settings.json`:

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
git clone https://github.com/LordFisch1605/paul-skills-public.git 03-Skills/paul-skills-public
claude plugin marketplace add ./03-Skills/paul-skills-public
claude plugin install paul-base@paul-skills-public -s user
claude plugin install paul-dev@paul-skills-public -s user
```

`paul-base` adds a SessionStart hook that injects its working rules into every session and a
short reminder to every prompt; read `plugins/paul-base/skills/base-conduct/SKILL.md` first.
Restart Claude Code afterwards.
