# 05-Knowledge

The knowledge base agents retrieve from (RAG): documents put here deliberately, chunked,
embedded and stored in a vector database, queried by semantic search when a task needs them.

Suggested setup:

- **Tool:** `mcp-local-rag` (MIT), version pinned — indexer, chunker, hybrid search and MCP
  server in one.
- **Engine:** LanceDB, embedded. Each index is one folder.
- **Embedding:** a multilingual model run in-process (e.g. EmbeddingGemma via Transformers.js),
  no separate model server. Changing the model means a new index folder.
- **Updates:** `sync` re-embeds changed files and drops deleted ones; run by hand or on a
  schedule.
- **Agents:** stdio MCP server, registered in Claude Code and in local-model clients.
- **Layout:** documents in `docs/`, index in `.index/`, model cache in `.models/`; the last two
  stay out of Git.
- **Work documents:** a second instance whose documents and index both live on `W:`,
  registered only in the local-model client.
