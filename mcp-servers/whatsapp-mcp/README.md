# WhatsApp MCP Server

Send and receive WhatsApp messages from Claude Code using [Baileys](https://github.com/WhiskeySockets/Baileys) (no browser required).

## Setup

```bash
cd mcp-servers/whatsapp-mcp
npm install
```

## First Run

On first launch, a QR code will appear in the Claude Code terminal. Scan it with your phone:

1. Open WhatsApp on your phone
2. Go to **Settings > Linked Devices > Link a Device**
3. Scan the QR code

Authentication is saved to `.baileys_auth/` for future sessions.

## Tools

| Tool | Description |
|------|-------------|
| `whatsapp_status` | Check connection status |
| `whatsapp_send_message` | Send a text message |
| `whatsapp_get_chats` | List recent chats |
| `whatsapp_search_contacts` | Search contacts by name or number |

## Configuration

Add to your `settings.local.json`:

```json
{
  "mcpServers": {
    "whatsapp-mcp": {
      "command": "node",
      "args": ["/path/to/whatsapp-mcp/server.js"],
      "disabled": false
    }
  }
}
```

## Notes

- Requires Node.js 18+
- Uses Baileys library (no Chromium/Puppeteer needed)
- Auth persists across sessions
- If disconnected, will auto-reconnect (unless logged out from phone)
