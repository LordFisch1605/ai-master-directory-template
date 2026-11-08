# 04-Knowledge

The knowledge base agents retrieve from (RAG): documents put here deliberately, chunked,
embedded and stored in a vector database, queried by semantic search when a task needs them.

Suggested setup:

- **Tool:** `mcp-local-rag` (MIT), version pinned — indexer, chunker, hybrid search and MCP
  server in one.
- **Engine:** LanceDB, embedded. Each index is one folder.
- **Embedding:** a multilingual model run in-process (e.g. EmbeddingGemma via Transformers.js),
  no separate model server. Changing the model means a new index folder.
- **Updates:** `watcher.py` (Python 3, stdlib only, Windows/Linux/macOS) scans each
  instance's folders every few minutes and runs `sync` only where files changed. It skips an
  instance whose folder is missing (an unmounted volume would otherwise be wiped from the
  index), keeps itself the only writer with a lock file, and lists JSON/HTML in raw folders
  that have no Markdown version yet. Configure it in `instances.json` (copy
  `instances.example.json`), or per OS in `instances.windows.json` / `instances.linux.json` /
  `instances.macos.json`, so a dual-boot machine can share one checkout; run it with
  `python3 watcher.py` at login. `device` picks `cpu` or the GPU backend: `dml` (Windows),
  `cuda` (Linux x64), `coreml` (macOS); `batch_size` (default 16) sets memory use per
  machine (about 16 for 16 GB free, 4 for 8 GB, 1–2 for 4 GB) and
  `max_tokens` (default 2048, the same on every machine sharing an index) caps chunk length;
  `cpu_threads` (default: all) caps the CPU threads of the embedding and caption models and
  `priority` (`normal`, `low`, `idle`) sets the OS priority of the indexing; `gpu_id` picks the DirectML adapter (the tool always takes adapter 0, often the
  integrated GPU), all three through a patched local install of the tool in `.tool/`. An index stores absolute paths, so it belongs to one
  OS; give each OS its own `db` paths.
- **Figures and scans in PDFs:** `caption.py` (needs `pip install pypdfium2` and Ollama),
  run by the watcher for an instance with a `captions` block, sends each page with figures to
  a local vision model, one page at a time and never alongside the embedding model, and
  transcribes scanned pages, which otherwise give no text. Results go to
  `.derived-cache/captions/`, indexed as text; done pages are never redone. Default model
  `bonsai-2:9b` (~3.4 GB; ~12 s per page on a 6 GB GPU, minutes on a CPU); `max_edge` sets
  the render size. Non-local Ollama hosts are refused.
- **Agents:** stdio MCP server, registered in whichever agent you use; its config is in
  `../03-Agent/mcp/knowledge-servers.json`.
- **Layout:** documents in `docs/`, index in `.index/`, model cache in `.models/`; the last two
  stay out of Git.
- **Setup:** `python setup/setup.py` writes the config, registers the servers and the
  autostart; the single steps are in `setup/COMMANDS.md`.
