from __future__ import annotations

import math
from typing import List, Dict

def _estimate_audio_duration_seconds(audio_path: str | bytes | None) -> float:
    if audio_path is None:
        return 0.0
    # Use MoviePy to avoid pydub/audioop dependency
    from moviepy.editor import AudioFileClip  # local import to keep module load light

    with AudioFileClip(str(audio_path)) as audio:
        return float(audio.duration)


def allocate_caption_spans(
    text: str,
    total_duration_s: float | None,
    audio_path: str | None = None,
) -> List[Dict[str, float | str]]:
    """Split text into timed caption spans across the given duration.

    If total_duration_s is None, infer it from audio_path.
    We create evenly timed spans by grouping words (4–7 per span).
    """
    if total_duration_s is None:
        if audio_path is None:
            raise ValueError("Must provide total_duration_s or audio_path")
        total_duration_s = _estimate_audio_duration_seconds(audio_path)

    words = [w for w in text.split() if w.strip()]
    if not words:
        return [{"start": 0.0, "end": total_duration_s, "text": ""}]

    # Group words into spans of roughly 5 words, jitter between 4 and 7
    spans_words: List[List[str]] = []
    idx = 0
    while idx < len(words):
        group_size = 5
        # ensure last group consumes remaining words
        remaining = len(words) - idx
        if remaining <= 7:
            group_size = remaining
        spans_words.append(words[idx : idx + group_size])
        idx += group_size

    per_word = total_duration_s / max(1, len(words))
    spans: List[Dict[str, float | str]] = []
    t = 0.0
    for g in spans_words:
        dur = per_word * len(g)
        start = t
        end = min(total_duration_s, start + dur)
        spans.append({"start": start, "end": end, "text": " ".join(g)})
        t = end

    # Ensure last span ends exactly at total_duration_s
    if spans:
        spans[-1]["end"] = total_duration_s

    # Avoid zero-length spans
    for s in spans:
        if math.isclose(s["end"], s["start"], abs_tol=1e-3):
            s["end"] = s["start"] + 0.05

    return spans


def allocate_karaoke_word_spans(
    text: str,
    total_duration_s: float | None = None,
    audio_path: str | None = None,
) -> List[Dict[str, float | int]]:
    """Return per-word timings for karaoke-style highlighting.

    We distribute total duration proportionally to word lengths as a simple proxy.
    This avoids heavyweight forced alignment.
    """
    if total_duration_s is None:
        if audio_path is None:
            raise ValueError("Must provide total_duration_s or audio_path")
        total_duration_s = _estimate_audio_duration_seconds(audio_path)

    tokens = [w for w in text.split() if w.strip()]
    if not tokens:
        return [{"start": 0.0, "end": total_duration_s, "text": "", "index": 0}]

    # Weight by character length so longer words get slightly more time
    weights = [max(1, len(t)) for t in tokens]
    total_w = float(sum(weights))
    spans: List[Dict[str, float | int]] = []
    t = 0.0
    for idx, (tok, w) in enumerate(zip(tokens, weights)):
        dur = total_duration_s * (w / total_w)
        start = t
        end = min(total_duration_s, start + dur)
        spans.append({"start": start, "end": end, "text": tok, "index": idx})
        t = end
    # ensure last word touches end
    spans[-1]["end"] = total_duration_s
    return spans


def whisper_word_timestamps(audio_path: str, language: str = "en", original_text: str | None = None) -> List[Dict[str, float | str]]:
    """Get precise per-word timestamps using faster-whisper (local Whisper).

    Returns a list of {start, end, word} for the entire audio.
    If original_text is provided, we'll try to align the Whisper output to match it.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        # Fallback if Whisper not available - use simple word timing
        return allocate_karaoke_word_spans(original_text or "", total_duration_s=None, audio_path=audio_path)

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, language=language, vad_filter=True, word_timestamps=True)
    words: List[Dict[str, float | str]] = []
    for seg in segments:
        if getattr(seg, "words", None):
            for w in seg.words:
                words.append({"start": float(w.start), "end": float(w.end), "word": w.word})
    
    # If we have original text, try to align Whisper output to it
    if original_text and words:
        words = _align_whisper_to_original(words, original_text)
    
    # Fallback if no words produced
    if not words:
        total = _estimate_audio_duration_seconds(audio_path)
        tokens = ["..."]
        return [{"start": 0.0, "end": total, "word": t} for t in tokens]
    return words


def _align_whisper_to_original(whisper_words: List[Dict[str, float | str]], original_text: str) -> List[Dict[str, float | str]]:
    """Align Whisper transcription to original text for better sync."""
    import re
    
    # Clean and split original text into words
    original_tokens = [w.strip() for w in re.findall(r'\b\w+\b', original_text.lower()) if w.strip()]
    whisper_tokens = [str(w["word"]).strip().lower() for w in whisper_words]
    
    if len(original_tokens) == 0 or len(whisper_tokens) == 0:
        return whisper_words
    
    # Simple alignment: if counts match reasonably, use original words with Whisper timings
    if abs(len(original_tokens) - len(whisper_tokens)) <= 2:
        aligned: List[Dict[str, float | str]] = []
        for i, orig_word in enumerate(original_tokens):
            if i < len(whisper_words):
                aligned.append({
                    "start": whisper_words[i]["start"],
                    "end": whisper_words[i]["end"], 
                    "word": orig_word
                })
            else:
                # Extend last timing proportionally
                if aligned:
                    last_end = float(aligned[-1]["end"])
                    duration = 0.5  # default duration for extra words
                    aligned.append({
                        "start": last_end,
                        "end": last_end + duration,
                        "word": orig_word
                    })
        return aligned
    
    # If alignment is too different, fall back to original Whisper output
    return whisper_words


def words_to_karaoke_spans(words: List[Dict[str, float | str]]) -> List[Dict[str, float | str | int]]:
    spans: List[Dict[str, float | str | int]] = []
    for idx, w in enumerate(words):
        spans.append({
            "start": float(w["start"]),
            "end": float(w["end"]),
            "text": str(w["word"]).strip(),
            "index": idx,
        })
    return spans

