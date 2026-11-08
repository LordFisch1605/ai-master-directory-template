"""Interactive setup for the AI master directory. Python 3 standard library only.

  python setup/setup.py      (python3 on Linux/macOS; install.ps1 / install.sh install Python first)

Asks before every step and every install; a step you decline is skipped. Safe to run again:
each step checks what is already there. The same steps by hand, for every OS: setup/COMMANDS.md.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OS = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
HOME = Path.home()
SETTINGS = HOME / ".claude" / "settings.json"
GUARD = ROOT / ".claude" / "hooks" / "local-only-guard.py"
KNOWLEDGE = ROOT / "05-Knowledge"
SKILLS_REPO = "https://github.com/LordFisch1605/paul-skills-public.git"
SKILLS_PLUGINS = ["paul-base", "paul-dev"]
RAG_PACKAGE = "mcp-local-rag@0.23.1"
NODE_MIN = (26, 12, 1)
EMBED_MODEL = "onnx-community/embeddinggemma-2-ONNX"
# free RAM the knowledge base may take -> (embedding batch_size, PDF caption model)
RAM_TIERS = [("4 GB", 2, "bonsai-2:4b"), ("8 GB", 4, "bonsai-2:9b"), ("16 GB or more", 16, "bonsai-2:9b")]
WRITE_TOOLS = ["sync_start", "ingest_file", "ingest_data", "delete_file"]
PACKAGES = {  # tool -> package name per package manager
    "git": {"winget": "Git.Git", "brew": "git", "apt-get": "git", "dnf": "git", "pacman": "git"},
    "node": {"winget": "OpenJS.NodeJS", "brew": "node", "apt-get": "nodejs npm", "dnf": "nodejs npm",
             "pacman": "nodejs npm"},
    "ollama": {"winget": "Ollama.Ollama", "brew": "ollama"},
    "veracrypt": {"winget": "IDRIX.VeraCrypt", "brew": "--cask macfuse veracrypt"},
}
done, skipped = [], []


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


# ---------------------------------------------------------------- steps

def step_prerequisites():
    refresh_path()
    install("git")
    if not shutil.which("claude"):
        if ask("Claude Code is missing. Install it with the official installer from claude.ai?"):
            if OS == "windows":
                run(["powershell", "-NoProfile", "-Command", "irm https://claude.ai/install.ps1 | iex"], check=False)
            else:
                run(["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"], check=False)
            refresh_path()
    if shutil.which("claude"):
        done.append("prerequisites")
    else:
        skipped.append("Claude Code (guard, knowledge base and skills are registered in it)")


def step_structure():
    for d in ["01-Tasks", "02-Projects/01-Public", "02-Projects/02-Private", "02-Projects/03-External",
              "03-Uni", "04-Skills", "05-Knowledge", "91-Private"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    if shutil.which("git") and not (ROOT / ".git").exists():
        run(["git", "init", str(ROOT)])
    repos = [("01-Tasks/Tasks", "your tasks", ["01-Planning", "02-Research", "03-Reviews",
                                                "04-One-Shots", "05-Idea-Design", "06-Trips"])]
    if ask("Do you study? Then 03-Uni/Study is created as a repo too.", default=False):
        repos.append(("03-Uni/Study", "your study material", ["01-Courses", "02-Papers", "Quellen"]))
    for rel, what, folders in repos:
        repo = ROOT / rel
        if (repo / ".git").exists():
            continue
        for f in folders:
            (repo / f).mkdir(parents=True, exist_ok=True)
        agents = repo / "AGENTS.md"
        if not agents.exists():
            agents.write_text(f"# AGENTS.md — {repo.name}\n\nRepo for {what}. Read `../../AGENTS.md` and "
                              "`../../CONVENTIONS.md` first; rules that hold only here go below.\n",
                              encoding="utf-8")
        if shutil.which("git"):
            run(["git", "init", str(repo)])
    done.append("folder structure and area repos")


def step_guard():
    if not ask("Register the access guard (blocks agents from 91-Private and edits to raw data) "
               "in ~/.claude/settings.json?"):
        return skipped.append("access guard")
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
    hooks = settings.setdefault("hooks", {})
    for event, arg, matcher in [("PreToolUse", "pre", "*"), ("SessionStart", "session", None)]:
        command = f'"{Path(sys.executable).as_posix()}" "{GUARD.as_posix()}" {arg}'
        entries = hooks.setdefault(event, [])
        if not any("local-only-guard.py" in h.get("command", "") for e in entries for h in e.get("hooks", [])):
            entry = {"hooks": [{"type": "command", "command": command}]}
            if matcher:
                entry["matcher"] = matcher
            entries.append(entry)
    save_settings(settings)
    done.append("access guard")


def node_ok():
    if not shutil.which("node"):
        return False
    out = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout
    return tuple(int(x) for x in re.findall(r"\d+", out)[:3]) >= NODE_MIN


def step_rag():
    if not ask("Set up the knowledge base (RAG: local vector search over your tasks, projects and study)?"):
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
    if captions:
        if install("ollama"):
            run(["ollama", "pull", captions], check=False)
        else:
            captions = None
    if captions and run([sys.executable, "-m", "pip", "install", "--user", "pypdfium2"], check=False).returncode:
        print("  pypdfium2 could not be installed; the watcher skips captions until it is (setup/COMMANDS.md).")

    p = lambda *parts: ROOT.joinpath(*parts).as_posix()
    cfg = {"interval_seconds": 300, "package": RAG_PACKAGE, "cache_dir": p("05-Knowledge", ".models"),
           "model": model, "device": "cpu", "batch_size": batch, "max_tokens": 2048, "instances": {
               "knowledge": {"roots": [p("01-Tasks"), p("02-Projects"), p("03-Uni")],
                             "ignore": ["**/_raw/**", "**/_rohdaten/**", "**/_derived/**", "**/dist/**",
                                        "**/build/**", "**/.venv/**", "**/cache/**", "**/.claude/**"],
                             "db": p("05-Knowledge", ".index", "knowledge")},
               "raw": {"discover": {"under": [p("01-Tasks"), p("03-Uni")], "dirs": ["_raw", "_rohdaten", "_derived"]},
                       "db": p("05-Knowledge", ".index", "raw"), "report_unconverted": True}}}
    if captions:
        cfg["instances"]["knowledge"]["captions"] = {"model": captions, "max_edge": 1536}
    cfg_path = KNOWLEDGE / f"instances.{OS}.json"
    if not cfg_path.exists() or ask(f"{cfg_path.name} exists. Overwrite it?", default=False):
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))

    print("  Installing the search tool into 05-Knowledge/.tool/ ...")
    spec = importlib.util.spec_from_file_location("watcher", KNOWLEDGE / "watcher.py")
    watcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watcher)
    server = watcher.tool(cfg)  # [node, entry]: the patched install the watcher uses too

    if shutil.which("claude"):
        settings = load_settings()
        deny = settings.setdefault("permissions", {}).setdefault("deny", [])
        for name, inst in cfg["instances"].items():
            run(["claude", "mcp", "remove", "-s", "user", name], check=False, capture_output=True)
            env = {"BASE_DIR": ROOT.as_posix(), "DB_PATH": watcher.expand(inst["db"]).as_posix(),
                   "CACHE_DIR": watcher.expand(cfg["cache_dir"]).as_posix(), "MODEL_NAME": cfg["model"],
                   "RAG_HYBRID_WEIGHT": "0", "RAG_MAX_TOKENS": str(cfg.get("max_tokens", 2048))}
            run(["claude", "mcp", "add", "-s", "user", name]
                + [a for k, v in env.items() for a in ("-e", f"{k}={v}")] + ["--"] + server, check=False)
            deny += [t for t in (f"mcp__{name}__{w}" for w in WRITE_TOOLS) if t not in deny]
        save_settings(settings)

    if ask("Build the indexes now? The first run takes minutes to hours, depending on how much is there.",
           default=False):
        run([sys.executable, str(KNOWLEDGE / "watcher.py"), "--once"], check=False)
    if ask("Start the watcher at every login, so the indexes stay current?"):
        autostart()
    done.append(f"knowledge base (batch {batch}, captions: {captions or 'off'})")


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
    if not ask(f"Clone the skill marketplace {SKILLS_REPO} into 04-Skills and install it in Claude Code?"):
        return skipped.append("skills")
    target = ROOT / "04-Skills" / "paul-skills-public"
    if (target / ".git").exists():
        run(["git", "-C", str(target), "pull", "--ff-only"], check=False)
    else:
        run(["git", "clone", SKILLS_REPO, str(target)])
    if not shutil.which("claude"):
        return skipped.append("skills (cloned, not installed: Claude Code is missing)")
    run(["claude", "plugin", "marketplace", "add", str(target)], check=False)
    print("  paul-base adds a SessionStart hook that injects working rules into every session, and a "
          "short reminder to every prompt. Read plugins/paul-base/skills/base-conduct/SKILL.md first.")
    for plugin in SKILLS_PLUGINS:
        if ask(f"Install {plugin}?"):
            run(["claude", "plugin", "install", f"{plugin}@paul-skills-public", "-s", "user"], check=False)
    done.append("skills")


def main():
    print(f"AI master directory setup in {ROOT} ({OS}). Every step asks first.")
    for step in (step_prerequisites, step_structure, step_guard, step_rag, step_veracrypt, step_skills):
        try:
            step()
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"  failed: {exc}")
            skipped.append(f"{step.__name__[5:]} (failed: {exc})")
    print("\nDone:    " + ("\n         ".join(done) or "-"))
    print("Skipped: " + ("\n         ".join(skipped) or "-"))
    print("\nRestart Claude Code so it loads the hooks, servers and plugins. "
          "Conventions: CONVENTIONS.md. Single steps: setup/COMMANDS.md.")


if __name__ == "__main__":
    main()
