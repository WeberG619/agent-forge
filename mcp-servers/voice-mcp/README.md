# Voice MCP Server

Text-to-speech and voice input for Claude Code using Microsoft Edge TTS.

## Setup

### Basic (TTS only - no API key needed)

```bash
pip install -r requirements.txt
```

### Full (TTS + voice input)

```bash
pip install mcp edge-tts sounddevice numpy openai
export OPENAI_API_KEY="your-key"  # For Whisper transcription
```

## Tools

| Tool | Description | Requirements |
|------|-------------|-------------|
| `voice_speak` | Speak text aloud | edge-tts |
| `voice_listen` | Record and transcribe voice | sounddevice, numpy, openai |
| `voice_conversation` | Speak then listen | All of the above |

## Voices

| Voice | Style |
|-------|-------|
| `en-US-AndrewNeural` | Professional male (default) |
| `en-US-GuyNeural` | Casual male |
| `en-US-DavisNeural` | Warm male |
| `en-US-JennyNeural` | Professional female |
| `en-US-AriaNeural` | Expressive female |

## Configuration

Add to your `settings.local.json`:

```json
{
  "mcpServers": {
    "voice-mcp": {
      "command": "python3",
      "args": ["/path/to/voice-mcp/server.py"],
      "env": {
        "OPENAI_API_KEY": "sk-..."
      },
      "disabled": false
    }
  }
}
```

## Platform Support

| Platform | TTS | Voice Input |
|----------|-----|-------------|
| WSL (Windows) | Via PowerShell | Via Windows audio |
| macOS | Via afplay | Via microphone |
| Linux | Via mpv/ffplay | Via microphone |

## Notes

- TTS works without any API key (Edge TTS is free)
- Voice input requires OpenAI API key for Whisper transcription
- Audio is cached for faster repeated phrases
- Edge TTS requires internet connectivity
