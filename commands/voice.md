---
description: Text-to-speech using Microsoft Edge TTS - speak summaries and announcements
---

# Voice - Text-to-Speech System

You are using the voice system to speak text aloud to the user.

## Primary Method: MCP Server
```
mcp__voice__speak(text="Your text here", voice="andrew")
mcp__voice__speak_summary(summary="Brief summary", voice="andrew")
```

## Available Voices

| Voice | Description | Best For |
|-------|-------------|----------|
| andrew | Natural, warm male | General use, summaries |
| adam | Professional male | Business, formal |
| guy | Clear male | Technical explanations |
| davis | Deep male | Announcements |
| jenny | Natural female | Friendly, conversational |
| aria | Soft female | Instructions |
| amanda | Professional female | Business |
| michelle | Clear female | General use |

## Features

- **IPv4 forced** - Fixes WSL/network connectivity issues
- **5 retries with exponential backoff** - Keeps trying if network hiccups
- **Windows SAPI fallback** - If Edge TTS fails, falls back to local Windows speech
- **Audio caching** - Reuses audio for repeated phrases (instant playback)
- **60-second timeout per attempt** - Won't hang forever
- **Always works** - SAPI fallback ensures voice output even when offline

## When to Speak

Speak summaries after:
- Completing a coding task
- Running tests or builds
- Research/analysis completion
- Multi-step processes
- Natural breakpoints

## What to Include

1. **What was accomplished** - Brief recap
2. **Any issues encountered** - Problems and resolutions
3. **Recommendations** - What to consider or do next
