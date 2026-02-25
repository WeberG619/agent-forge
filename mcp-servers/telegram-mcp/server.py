#!/usr/bin/env python3
"""
Telegram MCP Server
Send and receive Telegram messages, videos, photos, and files from Claude Code.

Tools:
  telegram_status         - Check bot connection status
  telegram_send_message   - Send a text message
  telegram_send_video     - Send a video file or URL
  telegram_send_photo     - Send a photo file or URL
  telegram_send_document  - Send any file/document
  telegram_get_updates    - Get recent incoming messages
  telegram_get_chat_info  - Get info about a chat

Setup:
  1. Create a bot via @BotFather on Telegram
  2. Set TELEGRAM_BOT_TOKEN environment variable (or put in config.json)
  3. Message your bot from your Telegram account to start receiving messages
"""

import asyncio
import json
import mimetypes
import os
import sys
import uuid
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path

# MCP imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    import subprocess

    subprocess.run([sys.executable, "-m", "pip", "install", "mcp", "-q"])
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent


# Configuration
CONFIG_FILE = Path(__file__).parent / "config.json"
BOT_TOKEN = None
ALLOWED_CHAT_IDS = []  # Empty = allow all


def load_config():
    """Load bot token from environment or config file."""
    global BOT_TOKEN, ALLOWED_CHAT_IDS

    # Environment variable takes priority
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    # Fall back to config file
    if not BOT_TOKEN and CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
            BOT_TOKEN = config.get("bot_token", "")
            ALLOWED_CHAT_IDS = config.get("allowed_chat_ids", [])
        except Exception:
            pass

    if not BOT_TOKEN:
        print("[Telegram] WARNING: No bot token configured.", file=sys.stderr)
        print("[Telegram] Set TELEGRAM_BOT_TOKEN env var or create config.json", file=sys.stderr)


def telegram_api(method: str, params: dict = None) -> dict:
    """Call Telegram Bot API with JSON body (for non-file requests)."""
    if not BOT_TOKEN:
        return {"ok": False, "description": "No bot token configured"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    if params:
        data = json.dumps(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "description": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"ok": False, "description": str(e)}


def telegram_api_multipart(method: str, fields: dict, file_field: str, file_path: str) -> dict:
    """Call Telegram Bot API with multipart/form-data for file uploads."""
    if not BOT_TOKEN:
        return {"ok": False, "description": "No bot token configured"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    boundary = f"----FormBoundary{uuid.uuid4().hex}"

    body_parts = []

    # Add text fields
    for key, value in fields.items():
        if value is not None:
            body_parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
            )

    # Add file
    file_path_obj = Path(file_path)
    filename = file_path_obj.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    )

    file_footer = f"\r\n--{boundary}--\r\n"

    try:
        with open(file_path, "rb") as f:
            file_data = f.read()
    except FileNotFoundError:
        return {"ok": False, "description": f"File not found: {file_path}"}
    except PermissionError:
        return {"ok": False, "description": f"Permission denied: {file_path}"}
    except Exception as e:
        return {"ok": False, "description": f"Error reading file: {e}"}

    # Build the full body
    text_part = "".join(body_parts).encode("utf-8")
    body = text_part + file_header.encode("utf-8") + file_data + file_footer.encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "description": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"ok": False, "description": str(e)}


def is_url(s: str) -> bool:
    """Check if a string looks like a URL."""
    return s.startswith("http://") or s.startswith("https://")


def send_media(
    method: str,
    chat_id,
    media_field: str,
    media_source: str,
    caption: str = None,
    parse_mode: str = None,
) -> dict:
    """Send media (video, photo, document, animation) via Telegram.

    Supports both URLs and local file paths.
    """
    if is_url(media_source):
        # Send by URL - use JSON API
        params = {"chat_id": chat_id, media_field: media_source}
        if caption:
            params["caption"] = caption
        if parse_mode:
            params["parse_mode"] = parse_mode
        return telegram_api(method, params)
    else:
        # Send local file - use multipart upload
        fields = {"chat_id": str(chat_id)}
        if caption:
            fields["caption"] = caption
        if parse_mode:
            fields["parse_mode"] = parse_mode
        return telegram_api_multipart(method, fields, media_field, media_source)


def check_chat_allowed(chat_id) -> bool:
    """Check if chat_id is in the allowed list (or if list is empty = allow all)."""
    if not ALLOWED_CHAT_IDS:
        return True
    return str(chat_id) in [str(c) for c in ALLOWED_CHAT_IDS]


# Track last update ID for polling
_last_update_id = 0


server = Server("telegram-mcp")


@server.list_tools()
async def list_tools():
    media_source_schema = {
        "type": "string",
        "description": "Local file path or HTTPS URL to the media",
    }
    caption_schema = {
        "type": "string",
        "description": "Optional caption text (supports Markdown)",
    }
    parse_mode_schema = {
        "type": "string",
        "description": "Parse mode for caption: Markdown or HTML",
        "enum": ["Markdown", "HTML"],
    }
    chat_id_schema = {
        "type": ["string", "integer"],
        "description": "Telegram chat ID (number) or @username",
    }

    return [
        Tool(
            name="telegram_status",
            description="Check Telegram bot connection status and get bot info.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="telegram_send_message",
            description="Send a text message to a Telegram chat. Use chat_id from telegram_get_updates or config.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": chat_id_schema,
                    "text": {
                        "type": "string",
                        "description": "Message text (supports Markdown)",
                    },
                    "parse_mode": {
                        "type": "string",
                        "description": "Parse mode: Markdown or HTML (default: Markdown)",
                        "enum": ["Markdown", "HTML"],
                        "default": "Markdown",
                    },
                },
                "required": ["chat_id", "text"],
            },
        ),
        Tool(
            name="telegram_send_video",
            description="Send a video to a Telegram chat. Supports local file paths and HTTPS URLs. Max 50MB for uploads, 20MB for URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": chat_id_schema,
                    "video": media_source_schema,
                    "caption": caption_schema,
                    "parse_mode": parse_mode_schema,
                },
                "required": ["chat_id", "video"],
            },
        ),
        Tool(
            name="telegram_send_photo",
            description="Send a photo to a Telegram chat. Supports local file paths and HTTPS URLs. Max 10MB, will be compressed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": chat_id_schema,
                    "photo": media_source_schema,
                    "caption": caption_schema,
                    "parse_mode": parse_mode_schema,
                },
                "required": ["chat_id", "photo"],
            },
        ),
        Tool(
            name="telegram_send_document",
            description="Send any file as a document to a Telegram chat. Supports local file paths and HTTPS URLs. Max 50MB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": chat_id_schema,
                    "document": media_source_schema,
                    "caption": caption_schema,
                    "parse_mode": parse_mode_schema,
                },
                "required": ["chat_id", "document"],
            },
        ),
        Tool(
            name="telegram_send_animation",
            description="Send a GIF or MP4 animation (no sound) to a Telegram chat. Supports local file paths and HTTPS URLs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": chat_id_schema,
                    "animation": media_source_schema,
                    "caption": caption_schema,
                    "parse_mode": parse_mode_schema,
                },
                "required": ["chat_id", "animation"],
            },
        ),
        Tool(
            name="telegram_get_updates",
            description="Get recent incoming messages sent to the bot. Returns new messages since last check.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to return (default: 10)",
                        "default": 10,
                    },
                },
            },
        ),
        Tool(
            name="telegram_get_chat_info",
            description="Get information about a Telegram chat (name, type, member count).",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": chat_id_schema,
                },
                "required": ["chat_id"],
            },
        ),
    ]


def _media_response(result: dict, chat_id, media_type: str) -> list:
    """Build a standard response for media send operations."""
    if result.get("ok"):
        msg = result["result"]
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": True,
                        "message_id": msg.get("message_id"),
                        "chat_id": chat_id,
                        "media_type": media_type,
                        "timestamp": datetime.now().isoformat(),
                    },
                    indent=2,
                ),
            )
        ]
    else:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": result.get("description", f"Failed to send {media_type}"),
                    },
                    indent=2,
                ),
            )
        ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    global _last_update_id

    if name == "telegram_status":
        result = telegram_api("getMe")
        if result.get("ok"):
            bot = result["result"]
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "connected",
                            "bot_name": bot.get("first_name", ""),
                            "bot_username": bot.get("username", ""),
                            "bot_id": bot.get("id"),
                            "can_read_messages": not bot.get("is_bot", True) or True,
                            "supported_media": ["video", "photo", "document", "animation"],
                            "instructions": "Send a message to your bot on Telegram to start chatting.",
                        },
                        indent=2,
                    ),
                )
            ]
        else:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "error",
                            "error": result.get("description", "Unknown error"),
                            "instructions": "Check your TELEGRAM_BOT_TOKEN or config.json",
                        },
                        indent=2,
                    ),
                )
            ]

    elif name == "telegram_send_message":
        chat_id = arguments.get("chat_id")
        text = arguments.get("text", "")
        parse_mode = arguments.get("parse_mode", "Markdown")

        if not check_chat_allowed(chat_id):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": f"Chat {chat_id} not in allowed list",
                        },
                        indent=2,
                    ),
                )
            ]

        result = telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            },
        )

        if result.get("ok"):
            msg = result["result"]
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "success": True,
                            "message_id": msg.get("message_id"),
                            "chat_id": chat_id,
                            "timestamp": datetime.now().isoformat(),
                        },
                        indent=2,
                    ),
                )
            ]
        else:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": result.get("description", "Send failed"),
                        },
                        indent=2,
                    ),
                )
            ]

    elif name == "telegram_send_video":
        chat_id = arguments.get("chat_id")
        video = arguments.get("video", "")
        caption = arguments.get("caption")
        parse_mode = arguments.get("parse_mode")

        if not check_chat_allowed(chat_id):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": f"Chat {chat_id} not in allowed list",
                        },
                        indent=2,
                    ),
                )
            ]

        result = send_media("sendVideo", chat_id, "video", video, caption, parse_mode)
        return _media_response(result, chat_id, "video")

    elif name == "telegram_send_photo":
        chat_id = arguments.get("chat_id")
        photo = arguments.get("photo", "")
        caption = arguments.get("caption")
        parse_mode = arguments.get("parse_mode")

        if not check_chat_allowed(chat_id):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": f"Chat {chat_id} not in allowed list",
                        },
                        indent=2,
                    ),
                )
            ]

        result = send_media("sendPhoto", chat_id, "photo", photo, caption, parse_mode)
        return _media_response(result, chat_id, "photo")

    elif name == "telegram_send_document":
        chat_id = arguments.get("chat_id")
        document = arguments.get("document", "")
        caption = arguments.get("caption")
        parse_mode = arguments.get("parse_mode")

        if not check_chat_allowed(chat_id):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": f"Chat {chat_id} not in allowed list",
                        },
                        indent=2,
                    ),
                )
            ]

        result = send_media("sendDocument", chat_id, "document", document, caption, parse_mode)
        return _media_response(result, chat_id, "document")

    elif name == "telegram_send_animation":
        chat_id = arguments.get("chat_id")
        animation = arguments.get("animation", "")
        caption = arguments.get("caption")
        parse_mode = arguments.get("parse_mode")

        if not check_chat_allowed(chat_id):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": f"Chat {chat_id} not in allowed list",
                        },
                        indent=2,
                    ),
                )
            ]

        result = send_media("sendAnimation", chat_id, "animation", animation, caption, parse_mode)
        return _media_response(result, chat_id, "animation")

    elif name == "telegram_get_updates":
        limit = arguments.get("limit", 10)

        params = {"limit": limit, "timeout": 0}
        if _last_update_id > 0:
            params["offset"] = _last_update_id + 1

        result = telegram_api("getUpdates", params)

        if not result.get("ok"):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": result.get("description", "Failed to get updates"),
                        },
                        indent=2,
                    ),
                )
            ]

        updates = result.get("result", [])
        messages = []

        for update in updates:
            _last_update_id = max(_last_update_id, update.get("update_id", 0))
            msg = update.get("message", {})
            if msg:
                messages.append(
                    {
                        "from": msg.get("from", {}).get("first_name", "Unknown"),
                        "from_id": msg.get("from", {}).get("id"),
                        "chat_id": msg.get("chat", {}).get("id"),
                        "chat_type": msg.get("chat", {}).get("type", "private"),
                        "text": msg.get("text", ""),
                        "date": datetime.fromtimestamp(msg.get("date", 0)).isoformat()
                        if msg.get("date")
                        else None,
                    }
                )

        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "count": len(messages),
                        "messages": messages,
                    },
                    indent=2,
                ),
            )
        ]

    elif name == "telegram_get_chat_info":
        chat_id = arguments.get("chat_id")
        result = telegram_api("getChat", {"chat_id": chat_id})

        if result.get("ok"):
            chat = result["result"]
            info = {
                "id": chat.get("id"),
                "type": chat.get("type"),
                "title": chat.get("title", chat.get("first_name", "")),
                "username": chat.get("username", ""),
                "description": chat.get("description", ""),
            }
            # Get member count for groups
            if chat.get("type") in ("group", "supergroup"):
                count_result = telegram_api("getChatMemberCount", {"chat_id": chat_id})
                if count_result.get("ok"):
                    info["member_count"] = count_result["result"]
            return [TextContent(type="text", text=json.dumps(info, indent=2))]
        else:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": result.get("description", "Chat not found"),
                        },
                        indent=2,
                    ),
                )
            ]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    load_config()
    print("[Telegram MCP] Server starting...", file=sys.stderr, flush=True)

    if BOT_TOKEN:
        # Verify token on startup
        result = telegram_api("getMe")
        if result.get("ok"):
            bot = result["result"]
            print(f"[Telegram MCP] Connected as @{bot.get('username', '?')}", file=sys.stderr)
        else:
            print(
                f"[Telegram MCP] Token validation failed: {result.get('description')}",
                file=sys.stderr,
            )
    else:
        print(
            "[Telegram MCP] No token - tools will return errors until configured", file=sys.stderr
        )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
