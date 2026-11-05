# 05-Knowledge

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
  `cuda` (Linux x64), `coreml` (macOS); `batch_size` (default 16) is lowered for a small
  GPU, through a patched local install of the tool in `.tool/`. An index stores absolute paths, so it belongs to one
  OS; give each OS its own `db` paths.
- **Agents:** stdio MCP server, registered in Claude Code and in local-model clients.
- **Layout:** documents in `docs/`, index in `.index/`, model cache in `.models/`; the last two
  stay out of Git.
- **Work documents:** a second instance whose documents and index both live on `W:`,
  registered only in the local-model client.
