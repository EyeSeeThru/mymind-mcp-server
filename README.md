# MyMind MCP Server (Python)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that wraps the [MyMind API](https://api.mymind.com) as stdio-based tools. Works with any MCP-capable AI client — Cursor, Claude Desktop, Claude Code, and more.

## Features

- **Objects** — list, get, create, update, delete, download
- **Search** — keyword and semantic search across your mind
- **Tags** — add, remove, list
- **Spaces** — list, create, get, delete
- **Related** — find semantically related objects

## Requirements

- Python 3.10+
- A MyMind API access key (`kid.secret` format)

## Installation

```bash
# Clone the repo
git clone https://github.com/your-username/mymind-mcp-server.git
cd mymind-mcp-server

# Install dependencies
pip install -r requirements.txt

# Configure your access key
cp .env.example ~/.mymind_mcp_access_key
# Or simply:
echo "YOUR_ACCESS_KEY" > ~/.mymind_mcp_access_key && chmod 600 ~/.mymind_mcp_access_key
```

Your access key is in `kid.secret` format — get it from your MyMind account. The file should contain the raw string (e.g. `abc123.xyz456`).

## Usage

### As a standalone MCP server

```bash
python -m mymind_server.server
```

### MCP Client Configuration

#### Claude Desktop (macOS/Windows)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mymind": {
      "command": "python",
      "args": ["-m", "mymind_server.server"]
    }
  }
}
```

Or with a custom config path:

```json
{
  "mcpServers": {
    "mymind": {
      "command": "python",
      "args": ["-m", "mymind_server.server", "--config", "/path/to/config.yaml"]
    }
  }
}
```

#### Cursor

Add to Cursor settings (JSON):

```json
{
  "mcpServers": {
    "mymind": {
      "command": "python",
      "args": ["-m", "mymind_server.server"]
    }
  }
}
```

#### Claude Code

```bash
claude --acp -- python -m mymind_server.server
```

### Command-Line Options

```
python -m mymind_server.server [--config CONFIG_PATH]
```

- `--config` — Path to a YAML config file (default: `~/.mymind_mcp_access_key`)

### Config File Format

**Default path:** `~/.mymind_mcp_access_key` (plain text, single line)

**YAML config** (`~/.mymind_mcp_config.yaml`):
```yaml
access_key: "your_kid.secret_key_here"
# Optional:
# base_url: "https://api.mymind.com"  # default, for custom deployments
```

## Available Tools

| Tool | Description |
|------|-------------|
| `list_objects` | List objects. Optional: `q` (search query), `limit` |
| `get_object` | Get single object by ID. Optional: `contentAs` |
| `create_object` | Create object. Params: `title`, `content`, `url`, `tags[]`, `spaces[]` |
| `update_object` | Update object title by ID |
| `delete_object` | Delete object by ID |
| `download_object` | Download object content (returns base64) |
| `search` | Search objects by keyword. Params: `query`, `limit` |
| `add_tags` | Add tags to object |
| `remove_tag` | Remove tag from object |
| `list_spaces` | List all spaces |
| `create_space` | Create space by name |
| `get_space` | Get space by ID |
| `delete_space` | Delete space by ID |
| `list_tags` | List all tags |
| `related` | Find related objects by ID |

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run directly
python -m mymind_server.server

# Run tests
python -m pytest
```

## License

MIT
