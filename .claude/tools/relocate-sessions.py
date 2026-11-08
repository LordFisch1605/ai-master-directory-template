"""Point Claude Code and Claude desktop sessions at folders that have moved.

  python relocate-sessions.py MAP.json          dry run: counts what would change
  python relocate-sessions.py MAP.json --run    backs up, then changes

MAP.json is a list of [old, new] folder pairs. A path that does not start with a drive
letter or "/" is relative to the home folder ("Desktop/old-projects/homepage").

What it changes:
  - the desktop app's session files, saved targets, worktree registry and recent folders
    (every path string under an old folder is rewritten; formatting is kept)
  - ~/.claude.json (per-folder settings and trust), ~/.claude/history.jsonl, settings.json
    and the plugin marketplace files (a marketplace kept in a moved folder)
  - ~/.claude/projects/<folder>: transcript folders are renamed to the new folder's name,
    merged into an existing one where it is already there (a file present in both is kept
    at the new place and reported). Transcripts themselves are not edited.

Quit the Claude desktop app and every Claude Code session first: they rewrite these files
from memory and would undo the change. With --run it refuses while a claude.exe runs.
Backup (small files only; transcript folders are renamed, not rewritten):
~/.claude/relocate-backup-<time>/.
"""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
APP_DATA = HOME / "AppData/Local/Claude-Data"   # Windows desktop app (MSIX)
PROJECTS = HOME / ".claude/projects"


def absolute(p):
    p = p.replace("/", "\\") if sys.platform == "win32" else p
    return p if re.match(r"^[A-Za-z]:|^[\\/]", p) else str(HOME / p)


def encode(path):
    # Claude Code's transcript folder name: every character but letters and digits becomes "-"
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def load_map(file):
    pairs = [(absolute(o), absolute(n)) for o, n in json.loads(Path(file).read_text(encoding="utf-8"))]
    return sorted(pairs, key=lambda p: -len(p[0]))   # longest first: a project before its parent


def text_rules(pairs):
    """Regexes for an old folder as it appears in JSON text: backslashes escaped, or slashes."""
    rules = []
    for old, new in pairs:
        parts = re.split(r"[\\/]", old)
        for sep_re, sep_out in ((r"\\\\", "\\\\"), ("/", "/")):
            pat = sep_re.join(map(re.escape, parts)) + r"(?=\\\\|/|\"|'|\s|$)"
            rules.append((re.compile(pat, re.IGNORECASE), sep_out.join(re.split(r"[\\/]", new))))
    return rules


def rewrite(text, rules):
    n = 0
    for rx, repl in rules:
        text, k = rx.subn(lambda m, r=repl: r, text)
        n += k
    return text, n


def merge_project_keys(text, rules):
    """~/.claude.json keys its per-folder settings by path: where the new folder already has
    an entry, keep that one and drop the old, so the file never holds a key twice."""
    d = json.loads(text)
    projects = d.get("projects", {})
    if not isinstance(projects, dict):
        return text
    renamed = {}
    for key, value in projects.items():
        new = rewrite(json.dumps(key), rules)[0]
        if new != json.dumps(key) and json.loads(new) in projects:
            print(f"       ~/.claude.json: dropped {key} (its new folder has its own entry)")
            continue
        renamed[key] = value
    if len(renamed) == len(projects):
        return text
    d["projects"] = renamed
    return json.dumps(d, indent=2, ensure_ascii=False)


def json_files():
    files = []
    for root in APP_DATA.glob("claude_*"):
        files += [root / f for f in ("ccd-session-presets.json", "git-worktrees.json",
                                     "claude_desktop_config.json") if (root / f).is_file()]
        files += [f for f in (root / "claude-code-sessions").rglob("*.json") if f.is_file()]
    files += [f for f in (HOME / ".claude.json", HOME / ".claude/history.jsonl",
                          HOME / ".claude/settings.json",
                          HOME / ".claude/plugins/known_marketplaces.json",
                          HOME / ".claude/plugins/installed_plugins.json") if f.is_file()]
    return sorted(set(files))


def transcript_moves(pairs):
    moves = []
    if not PROJECTS.is_dir():
        return moves
    enc = [(encode(o).lower(), encode(n)) for o, n in pairs]
    for d in sorted(PROJECTS.iterdir()):
        name = d.name.lower()
        for old, new in enc:
            if name == old or name.startswith(old + "-"):
                moves.append((d, PROJECTS / (new + d.name[len(old):])))
                break
    return moves


def claude_running():
    if sys.platform != "win32":
        # the claude binary itself, not any command line that merely mentions ~/.claude
        out = subprocess.run(["pgrep", "-af", r"(^|/)claude(\.exe)?( |$)"], capture_output=True,
                             text=True).stdout
        return out.splitlines()
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.lower().startswith('"claude')]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    pairs, run = load_map(sys.argv[1]), "--run" in sys.argv
    for old, new in pairs:
        if not Path(new).exists():
            print(f"warning: new folder missing: {new}")
    if run and claude_running():
        sys.exit("Claude is still running (desktop app or a Claude Code session). Quit it first:\n  "
                 + "\n  ".join(claude_running()))
    rules = text_rules(pairs)
    backup = HOME / ".claude" / time.strftime("relocate-backup-%Y%m%d-%H%M%S")

    changed = total = 0
    for f in json_files():
        text = f.read_text(encoding="utf-8")
        if f.name == ".claude.json":
            text = merge_project_keys(text, rules)
        new, n = rewrite(text, rules)
        if not n:
            continue
        if f.suffix == ".json":
            json.loads(new)   # never write a file the app cannot read
        changed += 1
        total += n
        print(f"{n:5}  {f}")
        if run:
            dest = backup / f.relative_to(HOME)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            f.write_text(new, encoding="utf-8", newline="")
    print(f"files: {changed}, paths rewritten: {total}")

    moves = transcript_moves(pairs)
    for src, dst in moves:
        print(f"{'merge' if dst.exists() else 'move '}  {src.name}\n    -> {dst.name}")
        if not run:
            continue
        if not dst.exists():
            src.rename(dst)
            continue
        for item in src.rglob("*"):
            target = dst / item.relative_to(src)
            if item.is_dir():
                target.mkdir(exist_ok=True)
            elif target.exists():
                if target.read_bytes() == item.read_bytes():
                    item.unlink()   # same file at both places (e.g. memories copied earlier)
                else:
                    print(f"    differs, kept both, the new place wins: {target.relative_to(dst)}")
            else:
                item.rename(target)
        if not any(p.is_file() for p in src.rglob("*")):
            shutil.rmtree(src)
        else:
            print(f"    left over (both had it): {src}")
    print(f"transcript folders: {len(moves)}")
    if run:
        (backup / "moves.json").parent.mkdir(parents=True, exist_ok=True)
        (backup / "moves.json").write_text(json.dumps([[str(s), str(d)] for s, d in moves], indent=1),
                                           encoding="utf-8")
        print(f"backup: {backup}")
    else:
        print("dry run; add --run to change (quit Claude first)")


if __name__ == "__main__":
    main()
