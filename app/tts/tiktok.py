from __future__ import annotations

import base64
import os
import random
import string
from pathlib import Path
from typing import List, Tuple

import asyncio
import requests


# A small curated list of known TikTok voice codes. This list may change over time.
# Each item: (Display Name, Voice Code)
TIKTOK_VOICES: List[Tuple[str, str]] = [
    ("English US Male 1", "en_us_001"),
    ("English US Female 1", "en_us_002"),
    ("Narrator Male", "en_male_narration"),
    ("Narrator Female", "en_female_emotional"),
]


def _random_device_id(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _chunk_text_for_tiktok(text: str, max_chars: int = 200) -> list[str]:
    """Split text into chunks that TikTok TTS can handle, respecting sentence boundaries."""
    import re
    
    # Split on sentence boundaries first
    sentences = re.split(r'[.!?]+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        # If adding this sentence would exceed limit, start new chunk
        if current_chunk and len(current_chunk) + len(sentence) + 2 > max_chars:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += ". " + sentence
            else:
                current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def _basic_mp3_sanity_check(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise RuntimeError("Synthesized output file was not created")
    size = path.stat().st_size
    if size < 256:
        raise RuntimeError(f"Synthesized output file too small ({size} bytes)")

    head = path.read_bytes()[:4]
    if head.startswith(b"ID3"):
        return
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return
    raise RuntimeError("Synthesized output does not look like an MP3 file")


def _get_tiktok_tts_endpoints() -> list[str]:
    configured = (os.getenv("TIKTOK_TTS_ENDPOINTS") or "").strip()
    if configured:
        endpoints = [e.strip() for e in configured.split(",") if e.strip()]
        if endpoints:
            return endpoints

    return [
        "https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/",  # Android-like
        "https://api16-normal-c-alisg.tiktokv.com/media/api/text/speech/invoke/",  # ALI region
        "https://tiktok-tts.weilnet.workers.dev/api/generation",  # Cloudflare worker
        "https://tiktoktts.com/api/generation",  # alt community
    ]


def synthesize_tiktok_tts(text: str, voice: str, out_dir: Path) -> Path:
    """Synthesize speech using TikTok's (unofficial) TTS endpoint.
    
    For longer text, splits into chunks and concatenates the audio.
    Returns path to an MP3 file containing the audio. Raises on failure.
    """
    if not text:
        raise ValueError("Text must not be empty")

    out_dir.mkdir(parents=True, exist_ok=True)
    
    # If text is short enough, use single request
    if len(text) <= 200:
        return _synthesize_single_chunk(text, voice, out_dir)
    
    # Split into chunks and synthesize each
    chunks = _chunk_text_for_tiktok(text)
    audio_files = []
    
    for i, chunk in enumerate(chunks):
        chunk_file = _synthesize_single_chunk(chunk, voice, out_dir, suffix=f"_chunk{i}")
        audio_files.append(chunk_file)
    
    # Concatenate all chunks into final file
    final_path = out_dir / f"tts_{_random_device_id(8)}.mp3"
    _concatenate_audio_files(audio_files, final_path)
    
    # Clean up chunk files
    for f in audio_files:
        try:
            f.unlink()
        except Exception:
            pass
    
    return final_path


def _synthesize_single_chunk(text: str, voice: str, out_dir: Path, suffix: str = "") -> Path:
    """Synthesize a single chunk of text using TikTok TTS."""
    out_mp3 = out_dir / f"tts_{_random_device_id(8)}{suffix}.mp3"

    endpoints = _get_tiktok_tts_endpoints()

    last_error: Exception | None = None
    errors: list[str] = []
    for url in endpoints:
        try:
            if "tiktokv.com" in url:
                params = {
                    "text_speaker": voice,
                    "req_text": text,
                    "speaker_map_type": 0,
                    "aid": 1233,
                    "platform": "android",
                }
                headers = {
                    "User-Agent": "okhttp/3.10.0.1",
                    "Accept": "application/json",
                }
                resp = requests.post(url, params=params, headers=headers, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status_code") != 0:
                    raise RuntimeError(
                        f"TikTok API error: {data.get('status_code')} - {data.get('message')}"
                    )
                v_str = data.get("data", {}).get("v_str")
                if not v_str:
                    raise RuntimeError("TikTok API returned no audio data")
                audio_bytes = base64.b64decode(v_str)
                out_mp3.write_bytes(audio_bytes)
            elif "weilnet.workers.dev" in url:
                payload = {"voice": voice, "text": text}
                resp = requests.post(url, json=payload, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                if "data" not in data:
                    raise RuntimeError(f"TTW worker error: {data}")
                audio_bytes = base64.b64decode(data["data"])
                out_mp3.write_bytes(audio_bytes)
            elif "tiktoktts.com" in url:
                payload = {"voice": voice, "text": text}
                resp = requests.post(url, json=payload, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("success") or not data.get("data"):
                    raise RuntimeError(f"tiktoktts.com error: {data}")
                audio_bytes = base64.b64decode(data["data"])
                out_mp3.write_bytes(audio_bytes)
            else:
                raise RuntimeError("Unsupported endpoint")

            _basic_mp3_sanity_check(out_mp3)
            return out_mp3
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            errors.append(f"{url}: {exc}")
            continue

    details = "; ".join(errors[-4:]) if errors else str(last_error)
    raise RuntimeError(f"Failed to synthesize TTS via TikTok endpoint(s): {details}")


def _concatenate_audio_files(audio_files: list[Path], output_path: Path) -> None:
    """Concatenate multiple MP3 files into one using MoviePy."""
    from moviepy.editor import AudioFileClip, concatenate_audioclips
    
    clips = []
    for f in audio_files:
        clip = AudioFileClip(str(f))
        clips.append(clip)
    
    if not clips:
        raise RuntimeError("No audio clips to concatenate")
    
    final_audio = concatenate_audioclips(clips)
    final_audio.write_audiofile(str(output_path), codec='mp3', verbose=False, logger=None)
    
    # Clean up
    final_audio.close()
    for clip in clips:
        clip.close()


