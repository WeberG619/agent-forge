#!/usr/bin/env node
/**
 * WhatsApp MCP Server
 *
 * Send and receive WhatsApp messages from Claude Code using Baileys (no browser needed).
 *
 * Tools:
 *   whatsapp_status        - Get connection status
 *   whatsapp_send_message  - Send a text message
 *   whatsapp_get_chats     - Get recent chats
 *   whatsapp_search_contacts - Search contacts
 *
 * Setup:
 *   1. npm install
 *   2. First run will show a QR code in terminal - scan with WhatsApp mobile
 *   3. Auth is saved to .baileys_auth/ for future sessions
 */

const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} = require("@modelcontextprotocol/sdk/types.js");
const makeWASocket = require("@whiskeysockets/baileys").default;
const {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const path = require("path");
const pino = require("pino");

// State
let sock = null;
let isReady = false;
let lastQR = null;
let connectionStatus = "disconnected";
const authFolder = path.join(__dirname, ".baileys_auth");

// Logger (quiet)
const logger = pino({ level: "silent" });

// Initialize WhatsApp connection
async function initWhatsApp() {
  if (sock) return;

  const { state, saveCreds } = await useMultiFileAuthState(authFolder);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    logger,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      lastQR = qr;
      connectionStatus = "awaiting_qr_scan";
      console.error("\n[WhatsApp] QR Code received. Scan with your phone:");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      isReady = false;
      const shouldReconnect =
        lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      console.error(
        "[WhatsApp] Connection closed:",
        lastDisconnect?.error?.message || "unknown"
      );
      connectionStatus = "disconnected";
      if (shouldReconnect) {
        sock = null;
        setTimeout(initWhatsApp, 5000);
      }
    } else if (connection === "open") {
      isReady = true;
      lastQR = null;
      connectionStatus = "connected";
      console.error("[WhatsApp] Connected!");
    }
  });
}

// Tool definitions
const tools = [
  {
    name: "whatsapp_status",
    description:
      "Get WhatsApp connection status. If awaiting_qr_scan, check Claude Code terminal for QR code.",
    inputSchema: {
      type: "object",
      properties: {},
      required: [],
    },
  },
  {
    name: "whatsapp_get_chats",
    description: "Get list of recent chats",
    inputSchema: {
      type: "object",
      properties: {
        limit: {
          type: "number",
          description: "Maximum chats to return (default: 20)",
        },
      },
      required: [],
    },
  },
  {
    name: "whatsapp_send_message",
    description: "Send a text message to a phone number or group",
    inputSchema: {
      type: "object",
      properties: {
        to: {
          type: "string",
          description:
            "Phone number with country code (e.g., 13051234567) or group JID",
        },
        message: {
          type: "string",
          description: "Message text to send",
        },
      },
      required: ["to", "message"],
    },
  },
  {
    name: "whatsapp_search_contacts",
    description: "Search for contacts by name or number",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Search query (name or phone number)",
        },
      },
      required: ["query"],
    },
  },
];

// Format JID
function formatJid(input) {
  if (input.includes("@")) return input;
  const clean = input.replace(/\D/g, "");
  return `${clean}@s.whatsapp.net`;
}

// Tool handlers
async function handleTool(name, args) {
  // Auto-init on first use
  if (!sock) {
    await initWhatsApp();
    await new Promise((r) => setTimeout(r, 2000));
  }

  switch (name) {
    case "whatsapp_status": {
      return {
        status: connectionStatus,
        ready: isReady,
        qrPending: !!lastQR,
        instructions: !isReady
          ? "If status is awaiting_qr_scan, check Claude Code terminal for QR. Open WhatsApp > Settings > Linked Devices > Link a Device > Scan"
          : "Connected and ready",
      };
    }

    case "whatsapp_get_chats": {
      if (!isReady) {
        return { error: "WhatsApp not connected. Call whatsapp_status first." };
      }
      const limit = args.limit || 20;
      const store = sock.store || {};
      const chats = Object.values(store.chats || {}).slice(0, limit);

      if (chats.length === 0) {
        return {
          note: "Chat history loads as messages arrive. Try sending a test message first.",
          connected: true,
          myNumber: sock.user?.id || "unknown",
        };
      }

      return chats.map((c) => ({
        id: c.id,
        name: c.name || c.id,
        unreadCount: c.unreadCount || 0,
      }));
    }

    case "whatsapp_send_message": {
      if (!isReady) {
        return { error: "WhatsApp not connected. Call whatsapp_status first." };
      }
      const jid = formatJid(args.to);
      try {
        const result = await sock.sendMessage(jid, { text: args.message });
        return {
          success: true,
          messageId: result.key.id,
          to: jid,
          timestamp: Date.now(),
        };
      } catch (err) {
        return { error: err.message };
      }
    }

    case "whatsapp_search_contacts": {
      if (!isReady) {
        return { error: "WhatsApp not connected. Call whatsapp_status first." };
      }
      const query = (args.query || "").toLowerCase();
      const contacts = sock.store?.contacts || {};
      const matches = Object.values(contacts)
        .filter(
          (c) =>
            (c.name || "").toLowerCase().includes(query) ||
            (c.id || "").includes(query)
        )
        .slice(0, 20);

      if (matches.length === 0) {
        return {
          note: "Contacts sync after connection. Try whatsapp_get_chats or send a message first.",
          query,
        };
      }

      return matches.map((c) => ({
        id: c.id,
        name: c.name || c.notify || c.id,
        number: c.id?.replace("@s.whatsapp.net", ""),
      }));
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// Create MCP server
const server = new Server(
  {
    name: "whatsapp-mcp",
    version: "2.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Register handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  try {
    const result = await handleTool(name, args || {});
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ error: error.message }),
        },
      ],
      isError: true,
    };
  }
});

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[WhatsApp MCP] Server started (Baileys v2)");
  initWhatsApp();
}

main().catch(console.error);
