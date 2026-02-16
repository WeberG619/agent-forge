#!/usr/bin/env python3
"""
Voice MCP Server - Voice input/output for Claude Code
======================================================

Capabilities:
- Text-to-speech using Microsoft Edge TTS (free, no API key)
- Voice input via microphone with OpenAI Whisper transcription
- Voice conversation mode (speak + listen)

Voices: Andrew, Guy, Jenny (en-US Neural voices)

Run: python server.py
"""

import asyncio
import json
import sys
import os
import tempfile
import subprocess
import queue
from pathlib import Path
from datetime import datetime

# MCP imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "mcp", "-q"])
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

# Audio imports (optional - TTS works without these)
try:
    import sounddevice as sd
    import numpy as np
    HAS_AUDIO_INPUT = True
except ImportError:
    HAS_AUDIO_INPUT = False
    print("[Voice] sounddevice/numpy not installed - voice input disabled", file=sys.stderr)

try:
    import edge_tts
    HAS_TTS = True
except ImportError:
    HAS_TTS = False
    print("[Voice] edge-tts not installed - TTS disabled", file=sys.stderr)

try:
    import openai
    HAS_WHISPER = bool(os.getenv("OPENAI_API_KEY"))
except ImportError:
    HAS_WHISPER = False

import wave
import io

# Configuration
SAMPLE_RATE = 16000
CHANNELS = 1
DEFAULT_VOICE = "en-US-AndrewNeural"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Audio cache for faster repeated phrases
AUDIO_CACHE_DIR = Path(__file__).parent / "audio_cache"
AUDIO_CACHE_DIR.mkdir(exist_ok=True)


class VoiceProcessor:
    """Handles voice input and output."""

    def __init__(self):
        self.is_listening = False

    def record_audio(self, duration: float = 5.0, silence_threshold: float = 0.02,
                     silence_duration: float = 1.5) -> bytes:
        """Record audio until silence is detected or max duration reached."""
        if not HAS_AUDIO_INPUT:
            return b""

        print("[MIC] Listening...", file=sys.stderr, flush=True)

        frames = []
        silent_chunks = 0
        chunk_duration = 0.1
        chunks_for_silence = int(silence_duration / chunk_duration)
        max_chunks = int(duration / chunk_duration)

        self.is_listening = True

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                               dtype=np.float32, blocksize=int(SAMPLE_RATE * chunk_duration)) as stream:
                for _ in range(max_chunks):
                    if not self.is_listening:
                        break

                    audio_chunk, _ = stream.read(int(SAMPLE_RATE * chunk_duration))
                    frames.append(audio_chunk)

                    volume = np.abs(audio_chunk).mean()
                    if volume < silence_threshold:
                        silent_chunks += 1
                        if silent_chunks >= chunks_for_silence and len(frames) > 10:
                            print("[MIC] Silence detected, stopping", file=sys.stderr, flush=True)
                            break
                    else:
                        silent_chunks = 0

        except Exception as e:
            print(f"[MIC ERROR] {e}", file=sys.stderr, flush=True)
            return b""

        self.is_listening = False

        if not frames:
            return b""

        audio_data = np.concatenate(frames)
        audio_int16 = (audio_data * 32767).astype(np.int16)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_int16.tobytes())

        return wav_buffer.getvalue()

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio using OpenAI Whisper API."""
        if not audio_bytes or not OPENAI_API_KEY:
            return ""

        try:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                temp_path = f.name

            try:
                with open(temp_path, "rb") as audio_file:
                    result = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="text"
                    )
                return result.strip()
            finally:
                os.unlink(temp_path)

        except Exception as e:
            print(f"[TRANSCRIBE ERROR] {e}", file=sys.stderr, flush=True)
            return ""

    async def speak(self, text: str, voice: str = DEFAULT_VOICE) -> bool:
        """Speak text using Edge TTS."""
        if not text or not HAS_TTS:
            return False

        try:
            # Check cache first
            cache_key = hash(f"{voice}:{text}")
            cache_file = AUDIO_CACHE_DIR / f"{cache_key}.mp3"

            if not cache_file.exists():
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(str(cache_file))

            # Play audio - platform-specific
            if sys.platform == "linux" and "microsoft" in os.uname().release.lower():
                # WSL - use PowerShell to play on Windows
                win_path = str(cache_file)
                # Convert WSL path to Windows path
                for drive_letter in "cdefghij":
                    if win_path.startswith(f"/mnt/{drive_letter}/"):
                        win_path = f"{drive_letter.upper()}:\\" + win_path[len(f"/mnt/{drive_letter}/"):].replace("/", "\\")
                        break

                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command",
                     f'Add-Type -AssemblyName PresentationCore; '
                     f'$player = New-Object System.Windows.Media.MediaPlayer; '
                     f'$player.Open("{win_path}"); $player.Play(); '
                     f'Start-Sleep -Milliseconds 100; '
                     f'while($player.Position -lt $player.NaturalDuration.TimeSpan) '
                     f'{{ Start-Sleep -Milliseconds 100 }}'],
                    capture_output=True, timeout=30
                )
            elif sys.platform == "darwin":
                # macOS - use afplay
                subprocess.run(["afplay", str(cache_file)], capture_output=True, timeout=30)
            else:
                # Linux - try mpv, then ffplay, then aplay
                for player in ["mpv --no-video", "ffplay -nodisp -autoexit", "aplay"]:
                    cmd = player.split() + [str(cache_file)]
                    try:
                        subprocess.run(cmd, capture_output=True, timeout=30)
                        break
                    except FileNotFoundError:
                        continue

            return True

        except Exception as e:
            print(f"[SPEAK ERROR] {e}", file=sys.stderr, flush=True)
            return False


# Initialize
voice_processor = VoiceProcessor()
server = Server("voice-mcp")


@server.list_tools()
async def list_tools():
    """List available voice tools."""
    tools = [
        Tool(
            name="voice_speak",
            description="Speak text out loud using natural-sounding voices. Great for summaries, announcements, or responses.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to speak",
                    },
                    "voice": {
                        "type": "string",
                        "description": "Voice to use (default: en-US-AndrewNeural)",
                        "enum": [
                            "en-US-AndrewNeural",
                            "en-US-GuyNeural",
                            "en-US-DavisNeural",
                            "en-US-JennyNeural",
                            "en-US-AriaNeural",
                        ],
                        "default": "en-US-AndrewNeural",
                    },
                },
                "required": ["text"],
            },
        ),
    ]

    if HAS_AUDIO_INPUT and HAS_WHISPER:
        tools.extend([
            Tool(
                name="voice_listen",
                description="Listen for voice input and transcribe it. Returns the transcribed text.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "max_duration": {
                            "type": "number",
                            "description": "Maximum recording duration in seconds (default: 10)",
                            "default": 10,
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Optional text to speak before listening",
                        },
                    },
                },
            ),
            Tool(
                name="voice_conversation",
                description="Speak a prompt, then listen for a voice response and transcribe it.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "What to say before listening",
                        },
                        "max_duration": {
                            "type": "number",
                            "description": "Max listen duration in seconds",
                            "default": 10,
                        },
                    },
                    "required": ["prompt"],
                },
            ),
        ])

    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""

    if name == "voice_speak":
        text = arguments.get("text", "")
        voice = arguments.get("voice", DEFAULT_VOICE)

        if not text:
            return [TextContent(type="text", text="No text provided")]

        if not HAS_TTS:
            return [TextContent(type="text", text="edge-tts not installed. Run: pip install edge-tts")]

        success = await voice_processor.speak(text, voice)

        if success:
            return [TextContent(type="text", text=f"Spoke: {text[:100]}{'...' if len(text) > 100 else ''}")]
        else:
            return [TextContent(type="text", text="Failed to speak - check audio output")]

    elif name == "voice_listen":
        if not HAS_AUDIO_INPUT:
            return [TextContent(type="text", text="Voice input requires: pip install sounddevice numpy")]
        if not HAS_WHISPER:
            return [TextContent(type="text", text="Transcription requires: pip install openai + OPENAI_API_KEY env var")]

        max_duration = arguments.get("max_duration", 10)
        prompt = arguments.get("prompt")

        if prompt:
            await voice_processor.speak(prompt)

        audio_bytes = voice_processor.record_audio(duration=max_duration)

        if not audio_bytes:
            return [TextContent(type="text", text="[No audio captured]")]

        transcription = voice_processor.transcribe(audio_bytes)

        if not transcription:
            return [TextContent(type="text", text="[Could not transcribe audio]")]

        return [TextContent(type="text", text=transcription)]

    elif name == "voice_conversation":
        if not HAS_AUDIO_INPUT or not HAS_WHISPER:
            return [TextContent(type="text", text="Voice conversation requires sounddevice, numpy, openai, and OPENAI_API_KEY")]

        prompt = arguments.get("prompt", "")
        max_duration = arguments.get("max_duration", 10)

        await voice_processor.speak(prompt)

        audio_bytes = voice_processor.record_audio(duration=max_duration)

        if not audio_bytes:
            return [TextContent(type="text", text="[No response heard]")]

        transcription = voice_processor.transcribe(audio_bytes)

        if not transcription:
            return [TextContent(type="text", text="[Could not transcribe response]")]

        return [TextContent(type="text", text=transcription)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    print("Voice MCP Server starting...", file=sys.stderr, flush=True)
    print(f"TTS: {'enabled' if HAS_TTS else 'disabled (pip install edge-tts)'}", file=sys.stderr)
    print(f"Voice input: {'enabled' if HAS_AUDIO_INPUT else 'disabled (pip install sounddevice numpy)'}", file=sys.stderr)
    print(f"Whisper: {'enabled' if HAS_WHISPER else 'disabled (pip install openai + set OPENAI_API_KEY)'}", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
