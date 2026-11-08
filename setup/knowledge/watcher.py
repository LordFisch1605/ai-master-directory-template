"""Knowledge-base watcher: keeps every mcp-local-rag index in step with its folders.

  python watcher.py            poll forever (every interval_seconds)
  python watcher.py --once     one pass, then exit

Python 3 standard library only; Windows, Linux, macOS. Needs Node (npx) for mcp-local-rag.
Config: instances.<os>.json (os = windows, linux, macos) next to this file if it exists, else
instances.json; per machine, not in Git (see instances.example.json). The per-OS name lets two
systems on one dual-boot machine share this folder with their own paths and devices.

Per instance and pass:
  1. Resolve the roots: "roots" as given, plus every folder named in "discover.dirs" found
     under "discover.under" (e.g. all _raw/ folders).
  2. If any root is missing (volume not mounted, folder moved): skip the instance. A sync
     without a root would delete that root's files from the index.
  3. Snapshot: path, size and mtime of every indexable file not matched by "ignore".
     Unchanged since the last successful sync: nothing to do.
  4. Otherwise take the instance's lock (one writer per index) and run the tool's `sync`;
     record the snapshot only when the sync succeeded.
The tool runs from a local install in .tool/<version>/ (made on first use), patched so that
"batch_size" sets the embedding batch (the tool fixes it at 16, too much for a small GPU) and
"gpu_id" picks the DirectML adapter (it always takes adapter 0, often the integrated GPU), and
"max_tokens" caps chunk length (the tool takes the model's window, 131,072 tokens for
EmbeddingGemma 2, so one long code block became one chunk and needed gigabytes of memory), and
"cpu_threads" caps the CPU threads of the embedding model (and of the caption model, through
Ollama's num_thread). "priority" (normal, low, idle) starts the sync at that OS priority.
Raw folders: JSON/HTML in a _raw/ (or _rohdaten/) with neither a Markdown version in the
sibling _derived/ nor a line in _derived/.skipped is listed in .state/unconverted.txt.
State and log live in .state/<os>/ (not in Git).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OS = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
STATE = HERE / ".state" / OS
INDEXABLE = {".md", ".txt", ".pdf", ".docx"}
CONVERTIBLE = {".json", ".html", ".htm"}
LOCK_STALE_SECONDS = 24 * 3600  # a first sync with PDF captions can take hours
SKIP_DIRS = {".git", "node_modules"}  # never documents, and slow to walk every pass
TOOL = HERE / ".tool"
# (file under node_modules, original text, patched text); each original occurs exactly once
PATCHES = [
    (f, "batchSize: 16,", "batchSize: Number(process.env.RAG_BATCH_SIZE) || 16,")
    for f in ("mcp-local-rag/dist/cli/common.js", "mcp-local-rag/dist/server/index.js")
] + [(
    "mcp-local-rag/dist/embedder/index.js",
    "function resolveEffectiveCap(positionWindow, tokenizerLimit) {",
    "function resolveEffectiveCap(positionWindow, tokenizerLimit) {\n"
    "    if (Number(process.env.RAG_MAX_TOKENS) > 0) return Number(process.env.RAG_MAX_TOKENS);",
), (
    "@huggingface/transformers/dist/transformers.node.mjs",
    "session_options.executionProviders ??= executionProviders;",
    "session_options.executionProviders ??= process.env.RAG_DML_DEVICE_ID ? executionProviders.map("
    "(p) => p === \"dml\" ? { name: \"dml\", deviceId: Number(process.env.RAG_DML_DEVICE_ID) } : p)"
    " : executionProviders;",
), (  # applied after the one above, which leaves this text in place
    "@huggingface/transformers/dist/transformers.node.mjs",
    "session_options.executionProviders ??=",
    "if (Number(process.env.RAG_THREADS) > 0) session_options.intraOpNumThreads ??= Number(process.env.RAG_THREADS);\n"
    "    session_options.executionProviders ??=",
)]
# "priority" in the config -> how the sync process is started (Ollama runs as its own service, so
# captions are limited by thread count only)
PRIORITY = {"normal": {}}
if OS == "windows":
    PRIORITY.update(low={"creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS},
                    idle={"creationflags": subprocess.IDLE_PRIORITY_CLASS})
else:
    PRIORITY.update(low={"preexec_fn": lambda: os.nice(10)}, idle={"preexec_fn": lambda: os.nice(19)})


def log(msg):
    STATE.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    path = STATE / "watcher.log"
    if path.exists() and path.stat().st_size > 1_000_000:
        path.replace(STATE / "watcher.log.1")
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def expand(p):
    return Path(os.path.expandvars(os.path.expanduser(p)))


def glob_regex(pattern):
    """mcp-local-rag IGNORE_PATHS semantics: relative to the root, '/' separators,
    * and ** do not match names starting with '.'."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += r"(?:(?!\.)[^/]*/)*"
            i += 3
        elif pattern.startswith("**", i):
            out += r"(?:(?!\.)[^/]*(?:/(?!\.)[^/]*)*)?"
            i += 2
        elif pattern[i] == "*":
            out += r"(?!\.)[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += r"[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def roots_of(inst):
    roots = [expand(r) for r in inst.get("roots", [])]
    disc = inst.get("discover")
    if disc:
        names = set(disc["dirs"])
        for base in map(expand, disc["under"]):
            if not base.is_dir():
                roots.append(base)  # reported as missing below
                continue
            for dirpath, dirnames, _ in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for d in [d for d in dirnames if d in names]:
                    roots.append(Path(dirpath) / d)
                    dirnames.remove(d)  # a raw folder's own subfolders belong to it
    return sorted(set(roots))


def mangled(name):
    """True for a name whose UTF-8 bytes were read as CP437 on the way here (ö -> ├╢), as
    Windows' tar.exe does with a GNU tar archive. A real umlaut never passes this test."""
    try:
        return name.encode("cp437").decode("utf-8") != name
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False


def snapshot(roots, ignore):
    """Digest and count of the indexable files, and those whose path looks mangled."""
    pats = [glob_regex(p) for p in ignore]
    h = hashlib.sha256()
    count = 0
    bad = []
    for root in roots:
        h.update(f"root:{root}\n".encode())
        for f in sorted(walk(root)):
            if f.suffix.lower() not in INDEXABLE:
                continue
            rel = f.relative_to(root).as_posix()
            if any(p.match(rel) for p in pats):
                continue
            st = f.stat()
            h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
            count += 1
            if any(mangled(part) for part in rel.split("/")):
                bad.append(str(f))
    return h.hexdigest(), count, bad


def acquire(lock):
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < LOCK_STALE_SECONDS:
            return False
        lock.unlink()  # left behind by a crashed run
        return acquire(lock)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def tool(cfg):
    """Command that runs the pinned tool from .tool/<version>/, installing and patching it once."""
    name, version = cfg["package"].rsplit("@", 1)
    modules = TOOL / version / "node_modules"
    entry = modules / name / "dist" / "index.js"
    if not entry.exists():
        log(f"installing {cfg['package']} into {TOOL / version}")
        subprocess.run([shutil.which("npm") or "npm", "install", "--prefix", str(TOOL / version),
                        "--no-save", "--no-audit", "--no-fund", cfg["package"]], check=True,
                       capture_output=True)
    for rel, old, new in PATCHES:
        f = modules / rel
        text = f.read_text(encoding="utf-8")
        if new in text:
            continue
        if text.count(old) != 1:  # a new version changed the code: check the patch by hand
            raise RuntimeError(f"patch does not fit {f}")
        f.write_text(text.replace(old, new), encoding="utf-8")
    return [shutil.which("node") or "node", str(entry)]


def sync(name, inst, cfg, roots):
    db = expand(inst["db"])
    db.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if k not in ("BASE_DIR", "IGNORE_PATHS", "RAG_DEVICE", "RAG_BATCH_SIZE", "RAG_DML_DEVICE_ID",
                         "RAG_MAX_TOKENS", "RAG_THREADS")}
    # folders the snapshot skips must be kept out of the index too, or changes there go unseen
    env["IGNORE_PATHS"] = json.dumps(inst.get("ignore", []) + [f"**/{d}/**" for d in sorted(SKIP_DIRS)])
    env.update({
        "BASE_DIRS": json.dumps([str(r) for r in roots]),
        "DB_PATH": str(db),
        "CACHE_DIR": str(expand(cfg["cache_dir"])),
        "MODEL_NAME": cfg["model"],
        # cpu, or the GPU backend of this OS: dml (Windows), cuda (Linux x64), coreml (macOS)
        "RAG_DEVICE": cfg.get("device", "cpu"),
        "RAG_BATCH_SIZE": str(cfg.get("batch_size", 16)),  # lower it if the GPU runs out of memory
        # longer text is split into pieces of this size before embedding; memory grows with its square
        "RAG_MAX_TOKENS": str(cfg.get("max_tokens", 2048)),
    })
    if "gpu_id" in cfg:  # DirectML adapter index, as in Task Manager's "GPU N"
        env["RAG_DML_DEVICE_ID"] = str(cfg["gpu_id"])
    if cfg.get("cpu_threads"):  # CPU threads the embedding model may use; unset or 0: all
        env["RAG_THREADS"] = str(cfg["cpu_threads"])
    cmd = tool(cfg) + ["sync"]
    if inst.get("visual"):
        cmd += ["--visual", "--visual-quality", inst["visual"]]
    started = time.time()
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       **PRIORITY[cfg.get("priority", "normal")])
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    log(f"{name}: sync exit {r.returncode} after {time.time() - started:.0f}s | " + " | ".join(tail))
    return r.returncode == 0


def unconverted(roots):
    found = []
    for root in roots:
        if root.name not in ("_raw", "_rohdaten"):
            continue
        derived = root.parent / "_derived"
        skip_file = derived / ".skipped"
        skipped = set()
        if skip_file.exists():
            for line in skip_file.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    skipped.add(line.replace("\\", "/"))
        for f in walk(root):
            if f.suffix.lower() in CONVERTIBLE:
                rel = f.relative_to(root).as_posix()
                if rel not in skipped and not (derived / (rel + ".md")).exists():
                    found.append(str(f))
    return found


def run_pass(cfg):
    STATE.mkdir(parents=True, exist_ok=True)
    state_file = STATE / "snapshots.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    open_items = []
    for name, inst in cfg["instances"].items():
        roots = roots_of(inst)
        missing = [str(r) for r in roots if not r.is_dir()]
        if missing:
            if state.get(f"{name}:missing") != missing:
                log(f"{name}: skipped, missing root(s): {', '.join(missing)}")
            state[f"{name}:missing"] = missing
            continue
        state.pop(f"{name}:missing", None)
        if inst.get("captions"):  # figure captions first, so the sync below indexes them
            if str(HERE) not in sys.path:
                sys.path.insert(0, str(HERE))
            import caption
            pats = [glob_regex(p) for p in inst.get("ignore", [])]
            if cfg.get("cpu_threads"):  # the same CPU limit for the caption model
                inst = dict(inst, captions=dict({"num_thread": cfg["cpu_threads"]}, **inst["captions"]))
            caption.run(name, inst, roots, HERE, expand, walk,
                        lambda root, f: any(p.match(f.relative_to(root).as_posix()) for p in pats), log)
            roots = sorted(set(roots + [caption.cache_root(HERE, name, inst, expand)]))
        if inst.get("report_unconverted"):
            open_items += unconverted(roots)
        digest, count, bad = snapshot(roots, inst.get("ignore", []))
        if bad != state.get(f"{name}:mangled", []):
            if bad:  # indexed under the broken name; fix the copy, see AGENTS.md section 3
                log(f"{name}: {len(bad)} file name(s) look mangled (UTF-8 read as CP437): "
                    + ", ".join(bad[:5]))
            state[f"{name}:mangled"] = bad
        if state.get(name) == digest:
            continue
        lock = expand(inst["db"]).with_suffix(".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        if not acquire(lock):
            log(f"{name}: index busy (lock {lock}), next pass")
            continue
        try:
            log(f"{name}: change detected ({count} files in {len(roots)} roots), syncing")
            if sync(name, inst, cfg, roots):
                state[name] = digest
        finally:
            lock.unlink(missing_ok=True)
    state_file.write_text(json.dumps(state, indent=1), encoding="utf-8")
    report = STATE / "unconverted.txt"
    previous = report.read_text(encoding="utf-8") if report.exists() else ""
    current = "".join(f + "\n" for f in sorted(open_items))
    if current != previous:
        report.write_text(current, encoding="utf-8")
        log(f"unconverted JSON/HTML in raw folders: {len(open_items)} (list: {report})")


def main():
    path = HERE / f"instances.{OS}.json"
    if not path.exists():
        path = HERE / "instances.json"
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))  # Windows editors may add a BOM
    once = "--once" in sys.argv
    every = "one pass" if once else "every %ss" % cfg["interval_seconds"]
    log("watcher started (%s, config %s)" % (every, path.name))
    while True:
        try:
            run_pass(cfg)
        except Exception as exc:  # keep watching; the next pass may succeed
            log(f"pass failed: {exc!r}")
        if once:
            return
        time.sleep(cfg["interval_seconds"])


if __name__ == "__main__":
    main()
