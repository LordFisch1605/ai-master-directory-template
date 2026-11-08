# 03-Agent

What an AI agent loads to work here, kept in one place and independent of which agent you use:

- `hooks/` — hooks that enforce the rules in `../AGENTS.md`. `hooks/claude-code/` holds the
  Claude Code versions (access guard, stay-inside); for another agent, build the same from them
  in its own hook or permission system and put it in `hooks/<agent>/`.
- `skills/` — skill collections, one repo per folder (only if chosen in setup).
- `mcp/` — MCP server configs, e.g. the knowledge base's search servers that the setup writes.

Skills are procedures an agent follows, MCP servers are tools it calls; the knowledge it
retrieves lives in `../04-Knowledge/`, and what it learns itself in the agent's own memory.
