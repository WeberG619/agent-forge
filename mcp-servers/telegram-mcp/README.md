# Telegram MCP Server

Send and receive Telegram messages from Claude Code via the Telegram Bot API.

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token

### 2. Configure

Option A - Environment variable:
```bash
export TELEGRAM_BOT_TOKEN="your-token-here"
```

Option B - Config file:
```bash
cp config.json.example config.json
# Edit config.json with your bot token
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start chatting

Message your bot on Telegram. Claude can then read and reply to your messages.

## Tools

| Tool | Description |
|------|-------------|
| `telegram_status` | Check bot connection and get bot info |
| `telegram_send_message` | Send a text message (supports Markdown) |
| `telegram_get_updates` | Get recent incoming messages |
| `telegram_get_chat_info` | Get info about a chat |

## Configuration

Add to your `settings.local.json`:

```json
{
  "mcpServers": {
    "telegram-mcp": {
      "command": "python3",
      "args": ["/path/to/telegram-mcp/server.py"],
      "env": {
        "TELEGRAM_BOT_TOKEN": "your-token-here"
      },
      "disabled": false
    }
  }
}
```

## Security

- Set `allowed_chat_ids` in config.json to restrict who can interact with the bot
- Never commit your bot token to git
- The bot can only see messages sent directly to it (or in groups where it's a member)

## Notes

- No external dependencies beyond the MCP SDK (uses urllib for API calls)
- Bot token can be set via env var or config file
- Messages are polled (not webhooks), so it works behind firewalls
