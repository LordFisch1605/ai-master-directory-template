"""Interactive setup for the AI master directory. Python 3 standard library only.

  python setup/setup.py      (python3 on Linux/macOS; install.ps1 / install.sh install Python first)

Asks before every step and every install; a step you decline is skipped. Safe to run again:
each step checks what is already there. The same steps by hand, for every OS: setup/COMMANDS.md.
No AI agent is required. The directory works for people too; if you use one, which one is yours
to choose. Only for Claude Code does this script register hooks, servers and plugins itself.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OS = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
HOME = Path.home()
SETTINGS = HOME / ".claude" / "settings.json"
AGENT = ROOT / "03-Agent"  # what an agent loads: hooks, skills, MCP server configs
HOOKS = AGENT / "hooks" / "claude-code"
MCP = AGENT / "mcp"
GUARD = HOOKS / "local-only-guard.py"
STAY = HOOKS / "stay-inside.py"
KNOWLEDGE = ROOT / "04-Knowledge"  # created only when the knowledge base is chosen
SKILLS = AGENT / "skills"  # created only when the skills are chosen
SKILLS_REPO = "https://github.com/LordFisch1605/paul-skills-public.git"
SKILLS_PLUGINS = ["paul-base", "paul-dev"]
RAG_PACKAGE = "mcp-local-rag@0.23.1"
NODE_MIN = (26, 12, 1)
EMBED_MODEL = "onnx-community/embeddinggemma-2-ONNX"
# free RAM the knowledge base may take -> (embedding batch_size, PDF caption model)
RAM_TIERS = [("4 GB", 2, "bonsai-2:4b"), ("8 GB", 4, "bonsai-2:9b"), ("16 GB or more", 16, "bonsai-2:9b")]
INTERVALS = [("every 5 minutes", 300), ("every 15 minutes", 900), ("every hour", 3600)]
WRITE_TOOLS = ["sync_start", "ingest_file", "ingest_data", "delete_file"]
PACKAGES = {  # tool -> package name per package manager
    "git": {"winget": "Git.Git", "brew": "git", "apt-get": "git", "dnf": "git", "pacman": "git"},
    "node": {"winget": "OpenJS.NodeJS", "brew": "node", "apt-get": "nodejs npm", "dnf": "nodejs npm",
             "pacman": "nodejs npm"},
    "ollama": {"winget": "Ollama.Ollama", "brew": "ollama"},
    "veracrypt": {"winget": "IDRIX.VeraCrypt", "brew": "--cask macfuse veracrypt"},
}
done, skipped = [], []
state = {"agent": "none", "skills": False, "knowledge": False, "hooks": []}


def ask(question, default=True):
    hint = "[Y/n]" if default else "[y/N]"
    answer = input(f"\n{question} {hint} ").strip().lower()
    return default if not answer else answer.startswith(("y", "j"))


def choose(question, options, default=1):
    print(f"\n{question}")
    for i, option in enumerate(options, 1):
        print(f"  {i}) {option}")
    while True:
        answer = input(f"Choice [{default}]: ").strip() or str(default)
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1


def text(question, default):
    return input(f"\n{question} [{default}]: ").strip() or default


def run(cmd, check=True, **kw):
    print("  > " + " ".join(cmd))
    return subprocess.run(cmd, check=check, **kw)


def claude():
    return state["agent"] == "claude" and shutil.which("claude")


def refresh_path():
    """Windows: a fresh install changes PATH in the registry, not in this process."""
    if OS == "windows":
        import winreg
        parts = []
        for hive, key in [(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")]:
            try:
                with winreg.OpenKey(hive, key) as k:
                    parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
            except OSError:
                pass
        os.environ["PATH"] = ";".join(parts + [os.environ["PATH"]])
    local_bin = str(HOME / ".local" / "bin")  # where the Claude Code installer puts claude
    if local_bin not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + local_bin


def manager():
    if OS == "windows":
        return "winget" if shutil.which("winget") else None
    if OS == "macos":
        return "brew" if shutil.which("brew") else None
    return next((m for m in ("apt-get", "dnf", "pacman") if shutil.which(m)), None)


def install(tool):
    """Install a tool with the OS package manager after asking. True when it is on PATH afterwards."""
    if shutil.which(tool):
        return True
    m = manager()
    package = PACKAGES[tool].get(m) if m else None
    if not package:
        print(f"  No package for {tool} via {m or 'a package manager'} here: install it by hand "
              f"(setup/COMMANDS.md), then run this script again.")
        return False
    if not ask(f"{tool} is missing. Install it with {m}?"):
        return False
    names = package.split()
    cmd = {"winget": ["winget", "install", "-e", "--id"] + names,
           "brew": ["brew", "install"] + names,
           "apt-get": ["sudo", "apt-get", "install", "-y"] + names,
           "dnf": ["sudo", "dnf", "install", "-y"] + names,
           "pacman": ["sudo", "pacman", "-S", "--noconfirm"] + names}[m]
    run(cmd, check=False)
    refresh_path()
    return bool(shutil.which(tool)) or tool == "veracrypt"  # VeraCrypt is not on PATH on Windows/macOS


def load_settings():
    if SETTINGS.exists():
        shutil.copy2(SETTINGS, SETTINGS.with_suffix(".json.bak"))
        return json.loads(SETTINGS.read_text(encoding="utf-8-sig"))
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    return {}


def save_settings(settings):
    SETTINGS.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def add_hook(settings, event, script, arg, matcher):
    command = f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}" {arg}'
    entries = settings.setdefault("hooks", {}).setdefault(event, [])
    if not any(script.name in h.get("command", "") for e in entries for h in e.get("hooks", [])):
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        entries.append(entry)


# ---------------------------------------------------------------- steps

def step_prerequisites():
    refresh_path()
    install("git")
    i = choose("Which AI agent do you use here? (No agent is needed; the directory works without one.)",
               ["Claude Code (this script registers its hooks, servers and plugins)",
                "another agent (Codex, OpenCode, ...; you register things in it yourself, see setup/COMMANDS.md)",
                "none"], default=3)
    state["agent"] = ["claude", "other", "none"][i]
    if state["agent"] == "claude" and not shutil.which("claude"):
        if ask("Claude Code is not installed. Install it with the official installer from claude.ai?", default=False):
            if OS == "windows":
                run(["powershell", "-NoProfile", "-Command", "irm https://claude.ai/install.ps1 | iex"], check=False)
            else:
                run(["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"], check=False)
            refresh_path()
        if not shutil.which("claude"):
            skipped.append("Claude Code registration (claude not found: hooks, servers and plugins not registered)")
    done.append(f"prerequisites (agent: {state['agent']})")


def step_structure():
    for d in ["01-Tasks", "02-Projects/01-Public", "02-Projects/02-Private", "02-Projects/03-External",
              "91-Private"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    if shutil.which("git") and not (ROOT / ".git").exists():
        run(["git", "init", str(ROOT)])
    repo = ROOT / "01-Tasks" / "Tasks"
    if not (repo / ".git").exists():
        for f in ["01-Planning", "02-Research", "03-Reviews", "04-One-Shots", "05-Idea-Design", "06-Trips"]:
            (repo / f).mkdir(parents=True, exist_ok=True)
        agents = repo / "AGENTS.md"
        if not agents.exists():
            agents.write_text("# AGENTS.md — Tasks\n\nRepo for your tasks. Read `../../AGENTS.md` and "
                              "`../../CONVENTIONS.md` first; rules that hold only here go below.\n",
                              encoding="utf-8")
        if shutil.which("git"):
            run(["git", "init", str(repo)])
    done.append("folder structure and tasks repo")


def step_hooks():
    if not claude():
        print("\n  Hooks: 03-Agent/hooks/claude-code/ holds two Claude Code hooks (access guard, stay-inside). "
              "They are not registered; another agent can build its own from them (setup/COMMANDS.md).")
        return
    settings = None
    if ask("Register the access guard (blocks the agent from 91-Private and from editing raw data)?"):
        cfg_path = GUARD.with_suffix(".json")
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if OS == "windows":
            letter = text("Drive letter the private VeraCrypt container is mounted as", "P").rstrip(":").upper()
            cfg["private"] = [f"{letter}:"] + [e for e in cfg["private"] if not re.fullmatch(r"[A-Za-z]:", e)]
        else:
            mount = text("Mount point of the private VeraCrypt container", "~/private-vault")
            cfg["private"] = [mount] + [e for e in cfg["private"] if not e.startswith(("~", "/"))]
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        settings = load_settings()
        add_hook(settings, "PreToolUse", GUARD, "pre", "*")
        add_hook(settings, "SessionStart", GUARD, "session", None)
        state["hooks"].append("access guard")
    if ask(f"Keep the agent inside this directory ({ROOT})? It then cannot install packages system-wide "
           "(winget, brew, apt, npm -g, pip --user ...) and asks you to do it instead; since the hook is "
           "registered for your user, it applies to every Claude Code session on this machine.", default=False):
        i = choose("What should be blocked outside the directory?",
                   ["reading and writing (the agent sees nothing outside, not even docs or config in your home folder)",
                    "writing only (reading outside stays allowed)"])
        mode = ["readwrite", "write"][i]
        cfg_path = STAY.with_suffix(".json")
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["mode"] = mode
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        settings = settings or load_settings()
        add_hook(settings, "PreToolUse", STAY, "pre", "*")
        state["hooks"].append(f"stay-inside ({mode})")
    if settings is not None:
        save_settings(settings)
        done.append("Claude Code hooks: " + ", ".join(state["hooks"]))


def node_ok():
    if not shutil.which("node"):
        return False
    out = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout
    return tuple(int(x) for x in re.findall(r"\d+", out)[:3]) >= NODE_MIN


def step_rag():
    if not ask("Set up the knowledge base (RAG: local vector search over your tasks and projects)?"):
        return skipped.append("knowledge base")
    install("node")
    if not node_ok():
        print(f"  Node {'.'.join(map(str, NODE_MIN))} or newer is needed (setup/COMMANDS.md, 'Node'). "
              "Install it, then run this script again.")
        return skipped.append("knowledge base (Node too old or missing)")
    if ask("Use the recommended models (EmbeddingGemma 2 for search, a local Ollama model for figures in PDFs)?"):
        model = EMBED_MODEL
        _, batch, captions = RAM_TIERS[choose("How much RAM may the knowledge base take at most?",
                                              [t[0] for t in RAM_TIERS], default=2)]
        if not ask(f"Describe figures and scanned pages in PDFs with {captions} (Ollama, ~2-4 GB download, "
                   "slow without a GPU)?", default=False):
            captions = None
    else:
        model = text("Embedding model (Hugging Face ONNX id)", EMBED_MODEL)
        batch = int(text("Embedding batch size (16 for 16 GB free, 4 for 8 GB, 1-2 for 4 GB)", "4"))
        captions = text("Ollama vision model for PDF figures (empty: none)", "") or None
    i = choose("How often should the watcher look for changed files and update the index?",
               [t[0] for t in INTERVALS] + ["other (in seconds)"])
    interval = INTERVALS[i][1] if i < len(INTERVALS) else int(text("Seconds between checks", "300"))
    KNOWLEDGE.mkdir(exist_ok=True)
    for f in (ROOT / "setup" / "knowledge").iterdir():  # watcher, captioner, README, example config
        shutil.copy2(f, KNOWLEDGE / f.name)
    if captions:
        if install("ollama"):
            run(["ollama", "pull", captions], check=False)
        else:
            captions = None
    if captions and run([sys.executable, "-m", "pip", "install", "--user", "pypdfium2"], check=False).returncode:
        print("  pypdfium2 could not be installed; the watcher skips captions until it is (setup/COMMANDS.md).")

    p = lambda *parts: ROOT.joinpath(*parts).as_posix()
    cfg = {"interval_seconds": interval, "package": RAG_PACKAGE, "cache_dir": p("04-Knowledge", ".models"),
           "model": model, "device": "cpu", "batch_size": batch, "max_tokens": 2048, "instances": {
               "knowledge": {"roots": [p("01-Tasks"), p("02-Projects")],
                             "ignore": ["**/_raw/**", "**/_rohdaten/**", "**/_derived/**", "**/dist/**",
                                        "**/build/**", "**/.venv/**", "**/cache/**", "**/.claude/**"],
                             "db": p("04-Knowledge", ".index", "knowledge")},
               "raw": {"discover": {"under": [p("01-Tasks")], "dirs": ["_raw", "_rohdaten", "_derived"]},
                       "db": p("04-Knowledge", ".index", "raw"), "report_unconverted": True}}}
    if captions:
        cfg["instances"]["knowledge"]["captions"] = {"model": captions, "max_edge": 1536}
    cfg_path = KNOWLEDGE / f"instances.{OS}.json"
    if not cfg_path.exists() or ask(f"{cfg_path.name} exists. Overwrite it?", default=False):
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))

    print("  Installing the search tool into 04-Knowledge/.tool/ ...")
    spec = importlib.util.spec_from_file_location("watcher", KNOWLEDGE / "watcher.py")
    watcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watcher)
    server = watcher.tool(cfg)  # [node, entry]: the patched install the watcher uses too

    servers = {}
    out = MCP / "knowledge-servers.json"  # per machine: absolute paths, not in Git
    for name, inst in cfg["instances"].items():
        servers[name] = {"command": server[0], "args": server[1:], "env": {
            "BASE_DIR": ROOT.as_posix(), "DB_PATH": watcher.expand(inst["db"]).as_posix(),
            "CACHE_DIR": watcher.expand(cfg["cache_dir"]).as_posix(), "MODEL_NAME": cfg["model"],
            "RAG_HYBRID_WEIGHT": "0", "RAG_MAX_TOKENS": str(cfg.get("max_tokens", 2048))}}
    MCP.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n", encoding="utf-8")
    if claude():
        settings = load_settings()
        deny = settings.setdefault("permissions", {}).setdefault("deny", [])
        for name, s in servers.items():
            run(["claude", "mcp", "remove", "-s", "user", name], check=False, capture_output=True)
            run(["claude", "mcp", "add", "-s", "user", name]
                + [a for k, v in s["env"].items() for a in ("-e", f"{k}={v}")] + ["--", s["command"]] + s["args"],
                check=False)
            deny += [t for t in (f"mcp__{name}__{w}" for w in WRITE_TOOLS) if t not in deny]
        save_settings(settings)
    elif state["agent"] == "other":
        print(f"  The two search servers (stdio MCP) are in {out}: add them to your agent's MCP config, and "
              f"deny their write tools ({', '.join(WRITE_TOOLS)}) so only the watcher writes the index.")

    if ask("Build the indexes now? The first run takes minutes to hours, depending on how much is there.",
           default=False):
        run([sys.executable, str(KNOWLEDGE / "watcher.py"), "--once"], check=False)
    if ask("Start the watcher at every login, so the indexes stay current?"):
        autostart()
    state["knowledge"] = True
    done.append(f"knowledge base (batch {batch}, captions: {captions or 'off'}, check every {interval}s)")


def autostart():
    script = KNOWLEDGE / "watcher.py"
    path = os.pathsep.join(filter(None, [str(Path(shutil.which("node")).parent), os.environ.get("PATH")]))
    if OS == "windows":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        ps = (f"$a = New-ScheduledTaskAction -Execute '{pythonw}' -Argument '\"{script}\"'; "
              "$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME; "
              "Register-ScheduledTask -TaskName 'Knowledge Watcher' -Action $a -Trigger $t -Force")
        run(["powershell", "-NoProfile", "-Command", ps], check=False)
    elif OS == "linux":
        unit = HOME / ".config" / "systemd" / "user" / "knowledge-watcher.service"
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(f"[Unit]\nDescription=Knowledge watcher\n\n[Service]\nExecStart={sys.executable} {script}\n"
                        f"Environment=PATH={path}\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n")
        run(["systemctl", "--user", "daemon-reload"], check=False)
        run(["systemctl", "--user", "enable", "--now", "knowledge-watcher"], check=False)
    else:
        plist = HOME / "Library" / "LaunchAgents" / "local.knowledge-watcher.plist"
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.knowledge-watcher</string>
  <key>ProgramArguments</key><array><string>{sys.executable}</string><string>{script}</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>{path}</string></dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
""")
        run(["launchctl", "load", "-w", str(plist)], check=False)


def veracrypt_cli():
    return {"windows": r"C:\Program Files\VeraCrypt\VeraCrypt Format.exe",
            "macos": "/Applications/VeraCrypt.app/Contents/MacOS/VeraCrypt"}.get(OS) or shutil.which("veracrypt")


def step_veracrypt():
    if not ask("Install VeraCrypt and create an encrypted container for 91-Private?", default=False):
        return skipped.append("VeraCrypt")
    if OS == "linux" and not shutil.which("veracrypt"):
        print("  VeraCrypt has no package in the usual Linux repositories. Install the package for your "
              "distribution from https://veracrypt.io/en/Downloads.html, then run this script again.")
        return skipped.append("VeraCrypt (install it by hand on Linux)")
    cli = veracrypt_cli()
    if not cli or not Path(cli).exists():
        install("veracrypt")
        if OS == "macos":
            print("  macOS asks you to allow macFUSE's system extension (System Settings > Privacy & Security).")
        cli = veracrypt_cli()
    if not cli or not Path(cli).exists():
        return skipped.append("VeraCrypt (not found after install)")
    container = ROOT / "91-Private" / "Private.hc"
    if container.exists():
        return done.append("VeraCrypt (container already there)")
    size = text("Container size (e.g. 5G, 10G, 50G)", "10G")
    if OS == "windows":
        print(f"  The VeraCrypt wizard opens. Choose: Create an encrypted file container > Standard > "
              f"file {container} > AES > size {size}. Pick the password there; this script never sees it.")
        run([cli], check=False)
    else:
        print("  VeraCrypt asks for the password now; this script never sees it.")
        run([cli, "--text", "--create", str(container), "--size", size, "--volume-type", "normal",
             "--encryption", "AES", "--hash", "sha-512", "--filesystem", "exfat", "--pim", "0",
             "--keyfiles", "", "--random-source", "/dev/urandom"], check=False)
    done.append("VeraCrypt (mount and unmount: setup/COMMANDS.md)")


def step_skills():
    if not ask(f"Clone the skill collection {SKILLS_REPO} into 03-Agent/skills?", default=False):
        return skipped.append("skills")
    SKILLS.mkdir(parents=True, exist_ok=True)
    readme = SKILLS / "README.md"
    if not readme.exists():
        readme.write_text("# skills\n\nSkills, one repo per folder (`../../CONVENTIONS.md`, section 10).\n",
                          encoding="utf-8")
    target = SKILLS / "paul-skills-public"
    if (target / ".git").exists():
        run(["git", "-C", str(target), "pull", "--ff-only"], check=False)
    else:
        run(["git", "clone", SKILLS_REPO, str(target)])
    state["skills"] = True
    if not claude():
        done.append("skills (cloned; each skill is a SKILL.md under plugins/*/skills/, load it the way your "
                    "agent loads skills or instructions)")
        return
    run(["claude", "plugin", "marketplace", "add", str(target)], check=False)
    print("  paul-base adds a SessionStart hook that injects working rules into every session, and a "
          "short reminder to every prompt. Read plugins/paul-base/skills/base-conduct/SKILL.md first.")
    for plugin in SKILLS_PLUGINS:
        if ask(f"Install {plugin} in Claude Code?"):
            run(["claude", "plugin", "install", f"{plugin}@paul-skills-public", "-s", "user"], check=False)
    done.append("skills")


def record():
    """Write what this machine has installed into AGENTS.md, so agents know which folders to expect."""
    agents = ROOT / "AGENTS.md"
    body = agents.read_text(encoding="utf-8")
    yes = lambda b: "installed" if b else "not installed"
    lines = (f"Set up on {date.today().isoformat()}:\n\n"
             f"- `03-Agent/skills/`: {yes(state['skills'] or SKILLS.exists())}\n"
             f"- `04-Knowledge/`: {yes(state['knowledge'] or KNOWLEDGE.exists())}\n"
             f"- Agent registered by setup: {state['agent']}\n"
             f"- Claude Code hooks registered: {', '.join(state['hooks']) or 'none'}\n")
    new = re.sub(r"(<!-- setup:start -->\n).*?(<!-- setup:end -->)", lambda m: m.group(1) + lines + m.group(2),
                 body, flags=re.S)
    agents.write_text(new, encoding="utf-8")


def main():
    print(f"AI master directory setup in {ROOT} ({OS}). Every step asks first.")
    for step in (step_prerequisites, step_structure, step_hooks, step_rag, step_veracrypt, step_skills):
        try:
            step()
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"  failed: {exc}")
            skipped.append(f"{step.__name__[5:]} (failed: {exc})")
    record()
    print("\nDone:    " + ("\n         ".join(done) or "-"))
    print("Skipped: " + ("\n         ".join(skipped) or "-"))
    print("\nWhat is installed is now noted in AGENTS.md. "
          + ("Restart Claude Code so it loads the hooks, servers and plugins. " if claude() else "")
          + "Conventions: CONVENTIONS.md. Single steps: setup/COMMANDS.md.")


if __name__ == "__main__":
    main()
