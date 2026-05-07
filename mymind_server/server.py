#!/usr/bin/env python3
"""
MyMind MCP Server
Wraps the MyMind REST API as a stdio MCP server.
Works with any MCP-capable AI client.
"""

import json
import sys
import os
import base64
import hashlib
import hmac
import time
import argparse
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Optional

VERSION = "1.0.0"
BASE_URL = "https://api.mymind.com"
DEFAULT_KEY_PATH = os.path.expanduser("~/.mymind_mcp_access_key")
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.mymind_mcp_config.yaml")


# ─── Credential Loading ────────────────────────────────────────────────────────

def load_access_key_from_file(path: str) -> str:
    """Read access key from a plain text file (single line)."""
    if not os.path.exists(path):
        raise RuntimeError(
            f"Access key not found at {path}.\n"
            "Create it with: echo 'YOUR_KEY' > ~/.mymind_mcp_access_key && chmod 600 ~/.mymind_mcp_access_key\n"
            "Or use --config to specify a YAML config file."
        )
    with open(path, "r") as f:
        key = f.read().strip()
    if not key:
        raise RuntimeError(f"Access key at {path} is empty.")
    return key


def load_access_key_from_env() -> str:
    """Read access key from MYMIND_ACCESS_KEY environment variable."""
    key = os.environ.get("MYMIND_ACCESS_KEY", "")
    if not key:
        raise RuntimeError(
            "MYMIND_ACCESS_KEY environment variable is not set.\n"
            "Set it with: export MYMIND_ACCESS_KEY='your_kid.secret_key'\n"
            "Or create a file at ~/.mymind_mcp_access_key"
        )
    return key


def load_access_key_from_config(path: str) -> str:
    """Read access key and optional base_url from a YAML config file."""
    import yaml
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    access_key = config.get("access_key", "")
    if not access_key:
        raise RuntimeError(f"access_key not found in {path}")
    return access_key


def load_access_key() -> tuple[str, str]:
    """
    Load access key from the first available source:
    1. --key-file argument
    2. MYMIND_ACCESS_KEY env var
    3. ~/.mymind_mcp_access_key file
    4. ~/.mymind_mcp_config.yaml file
    Returns (access_key, base_url).
    """
    key = None
    base_url = BASE_URL

    # 1. Env var
    key = os.environ.get("MYMIND_ACCESS_KEY", "")
    if key:
        return key, base_url

    # 2. Default key file
    if os.path.exists(DEFAULT_KEY_PATH):
        with open(DEFAULT_KEY_PATH, "r") as f:
            key = f.read().strip()
        if key:
            return key, base_url

    # 3. YAML config
    if os.path.exists(DEFAULT_CONFIG_PATH):
        import yaml
        with open(DEFAULT_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        key = config.get("access_key", "")
        base_url = config.get("base_url", BASE_URL)
        if key:
            return key, base_url

    raise RuntimeError(
        "No access key found. Set MYMIND_ACCESS_KEY env var, "
        "create ~/.mymind_mcp_access_key, or use --config."
    )


def split_access_key(key: str) -> tuple[str, str]:
    """
    Split 'kid.secret' format into (kid, secret).
    If no dot found, treat entire key as the secret and use 'default' as kid.
    """
    if "." in key:
        parts = key.split(".", 1)
        return parts[0], parts[1]
    return "default", key


# ─── JWT Signing ─────────────────────────────────────────────────────────────

def sign_token(kid: str, secret_b64: str, path: str, method: str) -> str:
    """Generate a signed JWT bound to request path and method."""
    import json as _json

    secret = base64.b64decode(secret_b64)
    now = int(time.time())
    payload = {
        "path": path,
        "method": method.upper(),
        "iat": now,
        "exp": now + 300,  # 5 minutes
    }
    header = {"alg": "HS256", "typ": "JWT", "kid": kid}

    def _b64(data: dict) -> str:
        return base64.urlsafe_b64encode(_json.dumps(data).encode()).rstrip(b"=").decode()

    header_b64 = _b64(header)
    payload_b64 = _b64(payload)
    message = f"{header_b64}.{payload_b64}"
    sig = hmac.new(secret, message.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{message}.{sig_b64}"


# ─── API Client ───────────────────────────────────────────────────────────────

class MyMindClient:
    def __init__(self, access_key: str, base_url: str = BASE_URL):
        self.access_key = access_key
        self.base_url = base_url
        self.kid, self.secret = split_access_key(access_key)

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Make an authenticated request to the MyMind API."""
        url = self.base_url + path
        if params:
            encoded_params = {k: urllib.parse.quote(str(v), safe="") for k, v in params.items()}
            qs = "&".join(f"{k}={v}" for k, v in encoded_params.items())
            url = f"{url}?{qs}"

        data = json.dumps(body).encode() if body else None
        token = sign_token(self.kid, self.secret, path, method)

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", f"mymind-mcp-server/{VERSION}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read() or b"{}"
            err = json.loads(raw)
            raise RuntimeError(f"MyMind API error {e.code}: {err}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}")

    # Objects
    def list_objects(self, q: Optional[str] = None, limit: int = 100) -> list[dict]:
        params = {"limit": limit}
        if q:
            params["q"] = q
        return self._request("GET", "/objects", params=params)

    def create_object(
        self,
        title: Optional[str] = None,
        content: Optional[str] = None,
        url: Optional[str] = None,
        tags: Optional[list[str]] = None,
        spaces: Optional[list[str]] = None,
    ) -> dict:
        body: dict = {}
        if title:
            body["title"] = title
        if content:
            body["content"] = content
        if url:
            body["url"] = url
        if tags:
            body["tags"] = [{"name": t} for t in tags]
        if spaces:
            body["spaces"] = [{"id": s} for s in spaces]
        return self._request("POST", "/objects", body=body)

    def get_object(self, object_id: str, content_as: Optional[str] = None) -> dict:
        params = {}
        if content_as:
            params["contentAs"] = content_as
        return self._request(
            "GET", f"/objects/{object_id}", params=params if params else None
        )

    def update_object(self, object_id: str, title: Optional[str] = None) -> dict:
        body = {}
        if title is not None:
            body["title"] = title
        return self._request("PATCH", f"/objects/{object_id}", body=body)

    def delete_object(self, object_id: str) -> dict:
        return self._request("DELETE", f"/objects/{object_id}")

    def download_object(self, object_id: str) -> dict:
        """Download object content. Returns dict with url, content_type, data (base64)."""
        path = f"/objects/{object_id}/download"
        url = self.base_url + path
        token = sign_token(self.kid, self.secret, path, "GET")
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("User-Agent", f"mymind-mcp-server/{VERSION}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                content_type = resp.headers.get("Content-Type", "application/octet-stream")
                data_b64 = base64.b64encode(raw).decode()
                return {"content_type": content_type, "data": data_b64}
        except urllib.error.HTTPError as e:
            raw = e.read() or b"{}"
            err = json.loads(raw)
            raise RuntimeError(f"MyMind API error {e.code}: {err}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}")

    def search(self, query: str, limit: int = 20) -> list[dict]:
        return self._request("GET", "/search", params={"q": query, "limit": limit})

    def add_tags(self, object_id: str, tags: list[str]) -> dict:
        body = [{"name": t} for t in tags]
        return self._request("POST", f"/objects/{object_id}/tags", body=body)

    def remove_tag(self, object_id: str, tag: str) -> dict:
        return self._request("DELETE", f"/objects/{object_id}/tags/{tag}")

    # Spaces
    def list_spaces(self) -> list[dict]:
        return self._request("GET", "/spaces")

    def create_space(self, name: str) -> dict:
        return self._request("POST", "/spaces", body={"name": name})

    def get_space(self, space_id: str) -> dict:
        return self._request("GET", f"/spaces/{space_id}")

    def delete_space(self, space_id: str) -> dict:
        return self._request("DELETE", f"/spaces/{space_id}")

    # Tags
    def list_tags(self) -> list[dict]:
        return self._request("GET", "/tags")

    # Related
    def related(self, object_id: str, limit: int = 20) -> list[dict]:
        return self._request(
            "GET", f"/objects/{object_id}/related", params={"limit": limit}
        )


# ─── MCP Protocol ─────────────────────────────────────────────────────────────

def tool_to_response(tool_name: str, result: Any) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": None,
        "result": {
            "tool": tool_name,
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        },
    }


def error_to_response(error_msg: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": error_msg},
    }


def handle_request(client: MyMindClient, method: str, params: dict) -> dict:
    """Route a method call to the appropriate client method."""
    try:
        if method == "list_objects":
            return tool_to_response(
                "list_objects",
                client.list_objects(q=params.get("q"), limit=params.get("limit", 100)),
            )

        elif method == "create_object":
            return tool_to_response(
                "create_object",
                client.create_object(
                    title=params.get("title"),
                    content=params.get("content"),
                    url=params.get("url"),
                    tags=params.get("tags"),
                    spaces=params.get("spaces"),
                ),
            )

        elif method == "get_object":
            return tool_to_response(
                "get_object",
                client.get_object(params["id"], content_as=params.get("contentAs")),
            )

        elif method == "update_object":
            return tool_to_response(
                "update_object",
                client.update_object(params["id"], title=params.get("title")),
            )

        elif method == "delete_object":
            return tool_to_response(
                "delete_object", client.delete_object(params["id"])
            )

        elif method == "download_object":
            return tool_to_response(
                "download_object", client.download_object(params["id"])
            )

        elif method == "search":
            return tool_to_response(
                "search",
                client.search(params["query"], limit=params.get("limit", 20)),
            )

        elif method == "add_tags":
            return tool_to_response(
                "add_tags",
                client.add_tags(params["id"], params["tags"]),
            )

        elif method == "remove_tag":
            return tool_to_response(
                "remove_tag",
                client.remove_tag(params["id"], params["tag"]),
            )

        elif method == "list_spaces":
            return tool_to_response("list_spaces", client.list_spaces())

        elif method == "create_space":
            return tool_to_response(
                "create_space", client.create_space(params["name"])
            )

        elif method == "get_space":
            return tool_to_response(
                "get_space", client.get_space(params["id"])
            )

        elif method == "delete_space":
            return tool_to_response(
                "delete_space", client.delete_space(params["id"])
            )

        elif method == "list_tags":
            return tool_to_response("list_tags", client.list_tags())

        elif method == "related":
            return tool_to_response(
                "related",
                client.related(params["id"], limit=params.get("limit", 20)),
            )

        else:
            return error_to_response(f"Unknown tool: {method}")

    except Exception as e:
        return error_to_response(str(e))


# ─── Stdio Transport ───────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_objects",
        "description": "List objects from MyMind. Pass q=search query, limit=max results (default 100).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
        },
    },
    {
        "name": "create_object",
        "description": "Create a new object (URL, note, or content) in MyMind.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "url": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "spaces": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "get_object",
        "description": "Get a single object by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "contentAs": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "update_object",
        "description": "Update an object's title.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "delete_object",
        "description": "Delete an object by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "download_object",
        "description": "Download object content. Returns base64-encoded data.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "search",
        "description": "Search MyMind objects by keyword or query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_tags",
        "description": "Add tags to an object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id", "tags"],
        },
    },
    {
        "name": "remove_tag",
        "description": "Remove a tag from an object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "tag": {"type": "string"},
            },
            "required": ["id", "tag"],
        },
    },
    {
        "name": "list_spaces",
        "description": "List all spaces.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_space",
        "description": "Create a new space.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "get_space",
        "description": "Get a space by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "delete_space",
        "description": "Delete a space by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "list_tags",
        "description": "List all tags in your mind.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "related",
        "description": "Find objects semantically related to an object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["id"],
        },
    },
]


def main():
    parser = argparse.ArgumentParser(description="MyMind MCP Server")
    parser.add_argument("--config", help="Path to YAML config file")
    parser.add_argument("--key-file", help="Path to plain text access key file")
    args = parser.parse_args()

    # Load credentials
    try:
        if args.config:
            access_key = load_access_key_from_config(args.config)
            base_url = BASE_URL
        elif args.key_file:
            access_key = load_access_key_from_file(args.key_file)
            base_url = BASE_URL
        else:
            access_key, base_url = load_access_key()
    except RuntimeError as e:
        sys.stderr.write(f"FATAL: {e}\n")
        sys.exit(1)

    client = MyMindClient(access_key, base_url)

    # Send capabilities on startup
    capabilities = {
        "jsonrpc": "2.0",
        "id": None,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mymind", "version": VERSION},
        },
    }
    print(json.dumps(capabilities), flush=True)

    # Read requests from stdin
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method", "")
        params = req.get("params", {}) or {}

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mymind", "version": VERSION},
                },
            }
            print(json.dumps(resp), flush=True)

        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "result": {"tools": TOOLS},
            }
            print(json.dumps(resp), flush=True)

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {}) or {}
            resp = handle_request(client, tool_name, tool_args)
            resp["id"] = req.get("id")
            print(json.dumps(resp), flush=True)

        else:
            resp = error_to_response(f"Unsupported method: {method}")
            resp["id"] = req.get("id")
            print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
