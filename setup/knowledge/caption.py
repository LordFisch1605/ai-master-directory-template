"""Figure captions for PDFs, one page at a time, by a local vision model via Ollama.

Used by watcher.py for an instance with a "captions" block; replaces the tool's own --visual,
which keeps the embedding model and a captioner in one process and renders figures at up to
16.7 megapixels. Here the embedding model is not loaded while pages are described, each page is
rendered at "max_edge" pixels (set per machine), and the model is unloaded after the pass.

For every PDF under the instance's roots that has pages with figures (images, or enough vector
drawing), each such page goes to the model; the answers land in one Markdown file per PDF in
.derived-cache/captions/<instance>/, named "<file name>-<content hash>.md". That folder is an
extra root of the instance, so the normal sync indexes the captions as text. Progress is kept
per page in a JSON file beside it: an interrupted pass resumes, an unchanged PDF is skipped, a
deleted one loses its captions, and a renamed, moved or copied one (or a cache brought from a
machine with other paths) is recognised by its content and not described again. index.json
remembers size, mtime and hash per path, so only changed files are hashed.

Needs pypdfium2 (pip install pypdfium2); without it this step is skipped and logged.
"""
import base64
import hashlib
import json
import re
import struct
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def safe(text):
    """A name that cannot be encoded (a file name mangled by a copy) must not stop the pass."""
    return str(text).encode("utf-8", "replace").decode("utf-8")
PROMPT = (
    'This is page {page} of the PDF "{name}". Describe its figures: diagrams, charts, tables, '
    "code listings, screenshots, photos, formulas set as images. For each: what it shows, every "
    "label, axis title, value and piece of text inside it (code and tables word for word), and "
    "what it explains. Leave out the running body text of the page. Answer in the language of "
    "the page, in plain Markdown, with no introduction. Only if the page has none of these at "
    "all (just text, a logo or a badge), answer: NONE"
)
SCAN_PROMPT = (
    'This is page {page} of the scanned PDF "{name}". Transcribe all its text in reading order, '
    "keeping headings, lists and tables as Markdown, and describe any figure in one sentence. "
    "Do not summarise or add anything. Answer with the content only."
)
MIN_IMAGE_SHARE = 0.02  # an image smaller than 2 % of the page is a logo or an icon
MIN_PATHS, MIN_PATH_SHARE = 10, 0.05  # vector drawing: enough paths covering enough of the page
SCAN_SHARE, SCAN_MAX_CHARS = 0.8, 20  # one image over most of the page and next to no text
REPEATED = 0.5  # an object at the same place on half the pages or more is a logo, header or frame


def settings(inst):
    c = dict({"model": "bonsai-2:9b", "max_edge": 1536, "url": "http://localhost:11434"},
             **inst["captions"])
    if urllib.parse.urlparse(c["url"]).hostname not in LOCAL_HOSTS:
        raise ValueError(f"captions url must be local, got {c['url']}")  # pages never leave the machine
    return c


def cache_root(here, name, inst, expand):
    """.derived-cache/captions/<name>, or beside the index when the index lives elsewhere
    (the work index on the encrypted volume: its captions must not leave it)."""
    db = expand(inst["db"]).resolve()
    if here.resolve() in db.parents:
        return here / ".derived-cache" / "captions" / name
    return db.parent / f".captions-{name}"


def figure_pages(pdf):
    """[[page index, "figure" | "scan"], ...] for the pages worth sending to the model."""
    import pypdfium2.raw as raw
    seen = []
    for page in pdf:
        w, h = page.get_size()
        objs = []
        for obj in page.get_objects(max_depth=5):
            if obj.type in (raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_PATH):
                l, b, r, t = obj.get_bounds()
                objs.append((obj.type, round(l), round(b), round(r), round(t)))
        text = page.get_textpage()
        chars = len(text.get_text_bounded().strip())
        text.close()
        seen.append((w * h or 1, objs, chars))
    count = {}
    for _, objs, _ in seen:
        for o in set(objs):
            count[o] = count.get(o, 0) + 1
    repeated = {o for o, n in count.items() if len(seen) >= 3 and n >= REPEATED * len(seen)}
    pages = []
    for i, (area, objs, chars) in enumerate(seen):
        image_area, paths, box = 0.0, 0, None
        for o in objs:
            kind, l, b, r, t = o
            if kind == raw.FPDF_PAGEOBJ_IMAGE:
                image_area = max(image_area, (r - l) * (t - b))  # a scan's page image counts, repeated or not
                continue
            if o in repeated:
                continue
            paths += 1
            box = (l, b, r, t) if box is None else (min(box[0], l), min(box[1], b),
                                                    max(box[2], r), max(box[3], t))
        if image_area / area >= SCAN_SHARE and chars <= SCAN_MAX_CHARS:
            pages.append([i, "scan"])
            continue
        if chars <= SCAN_MAX_CHARS and paths >= MIN_PATHS:  # text drawn as vector outlines
            pages.append([i, "scan"])
            continue
        image_area = max([(r - l) * (t - b) for k, l, b, r, t in objs
                          if k == raw.FPDF_PAGEOBJ_IMAGE and (k, l, b, r, t) not in repeated] or [0])
        path_area = (box[2] - box[0]) * (box[3] - box[1]) if box else 0
        if image_area / area >= MIN_IMAGE_SHARE or (paths >= MIN_PATHS and path_area / area >= MIN_PATH_SHARE):
            pages.append([i, "figure"])
    return pages


def png(page, max_edge):
    w, h = page.get_size()
    bitmap = page.render(scale=max_edge / max(w, h), rev_byteorder=True)
    width, height, stride, n = bitmap.width, bitmap.height, bitmap.stride, bitmap.n_channels
    buf = bytes(bitmap.buffer)
    rows = b"".join(b"\0" + buf[y * stride:y * stride + width * n] for y in range(height))
    chunk = lambda kind, data: (struct.pack(">I", len(data)) + kind + data
                                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    color = {3: 2, 4: 6, 1: 0}[n]
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def ask(c, image, prompt, keep_alive="10m"):
    body = {"model": c["model"], "stream": False, "think": False, "keep_alive": keep_alive,
            "options": {"temperature": 0, "num_ctx": 8192},  # page image + a full transcription
            "messages": [{"role": "user", "content": prompt,
                          "images": [base64.b64encode(image).decode()] if image else []}]}
    req = urllib.request.Request(c["url"].rstrip("/") + "/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)["message"]["content"].strip()


def unload(c):
    try:
        req = urllib.request.Request(c["url"].rstrip("/") + "/api/generate",
                                     json.dumps({"model": c["model"], "keep_alive": 0}).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).close()
    except OSError:
        pass


def write_markdown(md, src, c, state):
    modes = {str(p): m for p, m in state["pages"]}
    real = {p: t for p, t in state["captions"].items()
            if t and t.strip().strip(".").upper() != "NONE"}
    if not real:  # no pages, or the model found no figure after all: nothing worth indexing
        md.unlink(missing_ok=True)
        return
    lines = [f"# Figures in {safe(src.name)}", "", f"Source: {safe(src)}", "",
             f"Made by {c['model']} (local) from each page rendered at {c['max_edge']} px: figure "
             "descriptions, and for scanned pages a transcription. Machine-made; check the PDF "
             "before quoting.", ""]
    for page in sorted(real, key=int):
        kind = " (scanned, transcribed)" if modes.get(page) == "scan" else ""
        lines += [f"## Page {int(page) + 1}{kind}", "", real[page], ""]
    md.write_text("\n".join(lines), encoding="utf-8")


def run(name, inst, roots, here, expand, walk, ignored, log):
    """One caption pass over an instance. Returns True when nothing is left to do."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        log(f"{name}: captions skipped, pypdfium2 not installed (pip install pypdfium2)")
        return True
    c = settings(inst)
    setup = [c["model"], c["max_edge"]]
    out = cache_root(here, name, inst, expand)
    out.mkdir(parents=True, exist_ok=True)
    index_file = out / "index.json"  # path -> size, mtime and content hash, to hash only changed files
    index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else {}
    seen_paths, seen, used, done = set(), set(), False, True
    for root in roots:
        if root == out:
            continue
        for f in sorted(walk(root)):
            if f.suffix.lower() != ".pdf" or ignored(root, f):
                continue
            key, st = safe(f), f.stat()
            stamp = [st.st_size, st.st_mtime_ns]
            entry = index.get(key)
            if not entry or entry["stamp"] != stamp:
                entry = index[key] = {"stamp": stamp, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
            seen_paths.add(key)
            tag = entry["sha256"][:16]
            if tag in seen:
                continue  # the same PDF in a second place: described once
            seen.add(tag)
            # files are named by content, so a renamed or moved PDF, or a cache copied from a
            # machine with other paths, is found again and not described a second time
            found = next(out.glob(f"*-{tag}.json"), None)
            base = str(found)[:-5] if found else str(out / f"{re.sub(r'[^A-Za-z0-9._-]', '_', safe(f.stem))[:40]}-{tag}")
            meta, md = Path(base + ".json"), Path(base + ".md")
            state = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
            if state.get("setup") != setup:  # new, or another model or size: describe again
                state = {"sha256": entry["sha256"], "setup": setup, "captions": {}}
            moved, state["source"] = state.get("source") != key, key
            if "pages" in state and all(str(p) in state["captions"] for p, _ in state["pages"]):
                if moved or (state["pages"] and not md.exists()):  # new place: point to it
                    meta.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
                    if state["pages"]:
                        write_markdown(md, f, c, state)
                continue  # done earlier, or unreadable and unchanged: no need to open the PDF
            try:
                pdf = pdfium.PdfDocument(str(f))
                if "pages" not in state:
                    state["pages"] = figure_pages(pdf)
            except Exception as exc:  # an unreadable PDF must not stop the others
                log(f"{name}: captions skipped for {key}: {exc!r}")
                state.update(pages=[], error=repr(exc))  # retried only when the file changes
                meta.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
                continue
            try:
                todo = [[p, m] for p, m in state["pages"] if str(p) not in state["captions"]]
                if todo:
                    log(f"{name}: describing {len(todo)} of {len(state['pages'])} pages in {safe(f.name)}")
                for p, mode in todo:
                    used = True
                    prompt = (SCAN_PROMPT if mode == "scan" else PROMPT).format(page=p + 1, name=safe(f.name))
                    try:
                        text = ask(c, png(pdf[p], c["max_edge"]), prompt)
                    except Exception as exc:  # Ollama down, out of memory: resume next pass
                        log(f"{name}: caption failed on page {p + 1} of {key}: {exc!r}")
                        done = False
                        break
                    state["captions"][str(p)] = text
                    meta.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            finally:
                pdf.close()
            meta.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            if all(str(p) in state["captions"] for p, _ in state["pages"]):
                write_markdown(md, f, c, state)
            if not done:
                break
        if not done:
            break
    if done:  # PDFs that are gone: drop their captions and index entries
        for meta in out.glob("*-*.json"):
            if meta.stem.rsplit("-", 1)[-1] not in seen:
                Path(str(meta)[:-5] + ".md").unlink(missing_ok=True)
                meta.unlink()
        index = {k: v for k, v in index.items() if k in seen_paths}
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    if used:
        unload(c)  # free the memory before the sync loads the embedding model
    return done
