from __future__ import annotations

import random
from pathlib import Path
from typing import List, Dict, Sequence

# Pillow compatibility shim for MoviePy with Pillow >= 10
try:  # pragma: no cover - tiny runtime shim
    from PIL import Image as _PILImage

    if not hasattr(_PILImage, "ANTIALIAS"):
        try:
            # Pillow 10+ uses Resampling enum
            if hasattr(_PILImage, "Resampling"):
                _PILImage.ANTIALIAS = _PILImage.Resampling.LANCZOS  # type: ignore[attr-defined]
                _PILImage.BICUBIC = _PILImage.Resampling.BICUBIC  # type: ignore[attr-defined]
                _PILImage.BILINEAR = _PILImage.Resampling.BILINEAR  # type: ignore[attr-defined]
            else:
                _PILImage.ANTIALIAS = _PILImage.LANCZOS  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
except Exception:  # noqa: BLE001
    pass

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    CompositeAudioClip,
)
from moviepy.video.fx import all as vfx


def _get_random_background_music(bg_music_dir: Path | str = "assets/background_music") -> Path | None:
    """Select a random background music file from the bg music directory."""
    bg_dir = Path(bg_music_dir)
    if not bg_dir.exists():
        return None
    
    # Find all audio files (mp3, wav, m4a, etc.)
    audio_extensions = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'}
    audio_files = [
        f for f in bg_dir.iterdir() 
        if f.is_file() and f.suffix.lower() in audio_extensions
    ]
    
    if not audio_files:
        return None
    
    return random.choice(audio_files)


def _choose_random_subclip_for_duration(
    video: VideoFileClip, duration: float, start_time: float | None = None
) -> VideoFileClip:
    if video.duration <= 0:
        raise ValueError("Video has zero duration")
    if duration <= 0:
        return video.subclip(0, min(video.duration, 1.0))
    if video.duration >= duration:
        max_start = max(0.0, video.duration - duration)
        if start_time is None:
            start = random.uniform(0.0, max_start) if max_start > 0 else 0.0
        else:
            start = min(max(0.0, start_time), max_start)
        return video.subclip(start, start + duration)
    # If video is shorter than required duration, start from chosen point and loop
    if start_time is None:
        start = 0.0
    else:
        start = min(max(0.0, start_time), max(0.0, video.duration - 0.01))
    base = video.subclip(start, video.duration)
    return vfx.loop(base, duration=duration)


def _render_captions_layers(
    width: int,
    height: int,
    caption_spans: List[Dict[str, float | str]],
) -> List[ImageClip]:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    def _find_font(size: int) -> ImageFont.FreeTypeFont:
        # Prefer Windows Arial if available, then DejaVuSans in PIL package, else default
        candidates = [
            r"C:\\Windows\\Fonts\\TikTok-Sans.ttf",
            r"C:\\Windows\\Fonts\\TikTok-Sans.TTF",
        ]
        for p in candidates:
            try:
                if Path(p).exists():
                    return ImageFont.truetype(p, size=size)
            except Exception:
                pass
        try:
            # Try PIL packaged font
            import PIL

            dejavu = Path(PIL.__file__).parent / "fonts" / "DejaVuSans.ttf"
            if dejavu.exists():
                return ImageFont.truetype(str(dejavu), size=size)
        except Exception:
            pass
        return ImageFont.load_default()

    def _text_image(max_w: int, txt: str) -> Image.Image:
        fontsize = 64
        font = _find_font(fontsize)
        # Wrap text to fit width
        draw = ImageDraw.Draw(Image.new("RGBA", (max_w, 10), (0, 0, 0, 0)))
        words = txt.split()
        lines: list[str] = []
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            bbox = draw.textbbox((0, 0), test, font=font, stroke_width=4)
            if bbox[2] > max_w and line:
                lines.append(line)
                line = w
            else:
                line = test
        if line:
            lines.append(line)

        # Measure final size
        line_heights = []
        max_line_w = 0
        for ln in lines:
            bbox = draw.textbbox((0, 0), ln, font=font, stroke_width=4)
            max_line_w = max(max_line_w, bbox[2])
            line_heights.append(bbox[3])
        total_h = int(sum(line_heights) + (len(lines) - 1) * 8)
        img = Image.new("RGBA", (max_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        y = 0
        for ln, h in zip(lines, line_heights):
            draw.text(
                (int((max_w - max_line_w) / 2), y),
                ln,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=4,
                stroke_fill=(0, 0, 0, 255),
            )
            y += h + 8
        return img

    layers: List[ImageClip] = []
    max_text_width = int(width * 0.9)
    y_pos = int(height * 0.78)
    for span in caption_spans:
        text = str(span.get("text", ""))
        start = float(span["start"])  # type: ignore[arg-type]
        end = float(span["end"])  # type: ignore[arg-type]
        duration = max(0.01, end - start)
        img = _text_image(max_text_width, text)
        clip = (
            ImageClip(np.array(img))
            .set_start(start)
            .set_duration(duration)
            .set_position(("center", y_pos))
        )
        layers.append(clip)
    return layers


def _render_karaoke_overlay(
    width: int,
    height: int,
    word_spans: Sequence[Dict[str, float | str | int]],
) -> List[ImageClip]:
    """Render one word at a time, centered in the frame, large with outline.

    This matches the common TikTok/Shorts style where each word pops in sequence.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    def _find_font(size: int) -> ImageFont.FreeTypeFont:
        candidates = [
            r"C:\\Windows\\Fonts\\arialbd.ttf",
            r"C:\\Windows\\Fonts\\ARIALBD.TTF",
            r"C:\\Windows\\Fonts\\arial.ttf",
            r"C:\\Windows\\Fonts\\ARIAL.TTF",
        ]
        for p in candidates:
            try:
                if Path(p).exists():
                    return ImageFont.truetype(p, size=size)
            except Exception:
                pass
        try:
            import PIL

            dejavu = Path(PIL.__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"
            if dejavu.exists():
                return ImageFont.truetype(str(dejavu), size=size)
        except Exception:
            pass
        return ImageFont.load_default()

    max_w = int(width * 0.85)
    center_y = int(height * 0.5)

    def render_word_img(word: str) -> Image.Image:
        # Start with much smaller font size appropriate for mobile shorts
        size = 40  # Much smaller starting size
        while size >= 24:  # Reduced minimum significantly
            font = _find_font(size)
            tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
            draw = ImageDraw.Draw(tmp)
            bbox = draw.textbbox((0, 0), word, font=font, stroke_width=3)  # Thinner stroke
            w_px = bbox[2]
            h_px = bbox[3]
            if w_px <= max_w:
                img = Image.new("RGBA", (max_w, h_px + 6), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                x = int((max_w - w_px) / 2)
                draw.text(
                    (x, 0),
                    word,
                    font=font,
                    fill=(255, 255, 255, 255),
                    stroke_width=3,  # Much thinner stroke
                    stroke_fill=(0, 0, 0, 255),
                )
                return img
            size -= 3  # Smaller steps
        # Fallback small rendering
        font = _find_font(24)  # Much smaller fallback
        img = Image.new("RGBA", (max_w, 40), (0, 0, 0, 0))  # Smaller height
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), word, font=font, stroke_width=2)
        x = int((max_w - bbox[2]) / 2)
        draw.text((x, 0), word, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
        return img

    layers: List[ImageClip] = []
    for w in word_spans:
        start = float(w["start"])  # type: ignore[arg-type]
        end = float(w["end"])  # type: ignore[arg-type]
        duration = max(0.01, end - start)
        word_text = str(w.get("text", "")).strip()
        img = render_word_img(word_text)
        clip = (
            ImageClip(np.array(img))
            .set_start(start)
            .set_duration(duration)
            .set_position(("center", center_y))
        )
        layers.append(clip)
    return layers


def _ensure_vertical_9_16(
    clip: VideoFileClip, target_height: int = 2160, target_width: int = 1440
) -> VideoFileClip:
    """Crop to 9:16 maintaining highest possible resolution.

    Guarantees dimensions are divisible by 2 and preserves source quality.
    Now supports up to 4K quality (2160x1440) for better output.
    """
    def to_even(x: int) -> int:
        return x if x % 2 == 0 else x - 1

    width, height = clip.size
    target_ratio = 9 / 16  # 0.5625
    current_ratio = width / height
    
    if current_ratio > target_ratio:
        # Video is wider - crop sides to get 9:16
        new_width = int(height * target_ratio)
        new_width = to_even(new_width)
        x1 = int((width - new_width) / 2)
        x2 = x1 + new_width
        cropped = vfx.crop(clip, x1=x1, x2=x2)
        
        # For cropping wider videos, just return the cropped result - no resizing needed!
        return cropped
        
    else:
        # Video is taller - crop top/bottom to get 9:16  
        new_height = int(width / target_ratio)
        new_height = to_even(new_height)
        y1 = int((height - new_height) / 2)
        y2 = y1 + new_height
        cropped = vfx.crop(clip, y1=y1, y2=y2)
        
        # For cropping taller videos, just return the cropped result - no resizing needed!
        return cropped


def _create_split_screen_horizontal(
    clip1: VideoFileClip, 
    clip2: VideoFileClip,
    duration: float,
    chosen_start_time1: float | None = None,
    chosen_start_time2: float | None = None
) -> VideoFileClip:
    """Create a horizontal split screen with two videos (top and bottom halves).
    
    YouTuber style: crop both videos to show the most interesting parts, 
    typically the bottom portion where action happens.
    """
    def to_even(x: int) -> int:
        return x if x % 2 == 0 else x - 1
    
    # Get subclips and crop to 9:16
    sub1 = _choose_random_subclip_for_duration(clip1, duration, start_time=chosen_start_time1)
    sub2 = _choose_random_subclip_for_duration(clip2, duration, start_time=chosen_start_time2)
    
    cropped1 = _ensure_vertical_9_16(sub1)
    cropped2 = _ensure_vertical_9_16(sub2)
    
    # Use dimensions from first video
    width, height = cropped1.size
    half_height = to_even(height // 2)
    
    # Instead of cropping to bottom half and stretching, let's crop to a better section
    # Crop to the lower 3/4 of each video to show more content but still focus on action area
    crop_start1 = int(height * 0.25)  # Start at 25% down
    crop_start2 = int(height * 0.25)  # Start at 25% down
    
    cropped_section1 = vfx.crop(cropped1, y1=crop_start1, y2=height)
    cropped_section2 = vfx.crop(cropped2, y1=crop_start2, y2=height)
    
    # Now resize to fit the half-height sections - less zoom since we're using more of the video
    top_half = cropped_section1.resize((width, half_height)).set_position((0, 0))
    bottom_half = cropped_section2.resize((width, half_height)).set_position((0, half_height))
    
    # Create simple composite
    return CompositeVideoClip([top_half, bottom_half], size=(width, height)).set_duration(duration)


def compose_video_with_tts(
    video_path: Path | str,
    tts_audio_path: Path | str,
    caption_spans: List[Dict[str, float | str]],
    output_path: Path | str,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
    chosen_start_time: float | None = None,
    crf: int = 15,
    video_bitrate: str | None = None,
    karaoke_word_spans: Sequence[Dict[str, float | str | int]] | None = None,
    add_background_music: bool = True,
    bg_music_volume: float = 0.10,
    bg_music_dir: Path | str = "bg music",
    split_screen_enabled: bool = False,
    video_path2: Path | str | None = None,
) -> Path:
    audio = AudioFileClip(str(tts_audio_path))
    duration = float(audio.duration)

    # Store video clips for cleanup later
    source_clips = []
    
    if split_screen_enabled and video_path2:
        # Create split screen with two videos
        video1 = VideoFileClip(str(video_path))
        video2 = VideoFileClip(str(video_path2))
        source_clips.extend([video1, video2])
        
        # Generate random start times for both videos
        start_time1 = chosen_start_time if chosen_start_time is not None else random.uniform(0.0, max(0.0, video1.duration - 1.0))
        start_time2 = random.uniform(0.0, max(0.0, video2.duration - 1.0))
        
        base = _create_split_screen_horizontal(video1, video2, duration, start_time1, start_time2)
        width, height = base.size
    else:
        # Single video mode
        video = VideoFileClip(str(video_path))
        source_clips.append(video)
        
        base = _choose_random_subclip_for_duration(video, duration, start_time=chosen_start_time)
        base = _ensure_vertical_9_16(base)
        width, height = base.size

    if karaoke_word_spans:
        caption_layers = _render_karaoke_overlay(width, height, karaoke_word_spans)
    else:
        caption_layers = _render_captions_layers(width, height, caption_spans)
    # Round duration up to nearest frame to ensure last audio samples are preserved
    fps_out = base.fps or 30
    from math import ceil

    duration = (ceil(duration * fps_out)) / fps_out
    
    # Prepare final audio (TTS + optional background music)
    final_audio = audio
    if add_background_music:
        bg_music_path = _get_random_background_music(bg_music_dir)
        if bg_music_path:
            try:
                bg_music = AudioFileClip(str(bg_music_path))
                # Choose random start time in background music
                if bg_music.duration > duration:
                    max_start = bg_music.duration - duration
                    bg_start = random.uniform(0.0, max_start)
                    bg_music = bg_music.subclip(bg_start, bg_start + duration)
                else:
                    # Loop background music if it's shorter than needed
                    from moviepy.audio.fx import all as afx
                    bg_music = afx.audio_loop(bg_music, duration=duration)
                
                # Reduce background music volume and mix with TTS
                bg_music = bg_music.volumex(bg_music_volume)
                final_audio = CompositeAudioClip([audio, bg_music])
                bg_music.close()
            except Exception:
                # If background music fails to load, just use TTS audio
                pass
    
    final = (
        CompositeVideoClip([base, *caption_layers], size=(width, height))
        .set_audio(final_audio)
        .set_duration(duration)
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Suppress MoviePy's stdout/stderr to prevent harmless logging errors
        import os
        import sys
        from contextlib import redirect_stderr, redirect_stdout
        
        # Create a null device to redirect output
        devnull = open(os.devnull, 'w')
        
        try:
            with redirect_stdout(devnull), redirect_stderr(devnull):
                final.write_videofile(
                    str(out_path),
                    codec="libx264",
                    audio_codec="aac",
                    preset="veryslow",  # Best quality preset (was "slower")
                    threads=6,        # Increased threads for better performance
                    fps=fps_out,
                    audio_fps=48000,  # Higher audio sample rate for better quality
                    bitrate=video_bitrate,
                    ffmpeg_params=[
                        "-crf", str(crf), 
                        "-pix_fmt", "yuv420p", 
                        "-profile:v", "high", 
                        "-level", "5.1",      # Support higher resolutions (was 4.1)
                        "-movflags", "+faststart",  # Optimize for web playback
                        "-bf", "3",           # More B-frames for better compression (was 2)
                        "-g", "48",           # Optimized GOP size for better quality (was 60)
                        "-refs", "5",         # More reference frames for better quality
                        "-me_method", "umh",  # Better motion estimation
                        "-subq", "10",        # Highest subpixel motion estimation
                        "-trellis", "2",      # Rate-distortion optimization
                        "-aq-mode", "2",      # Adaptive quantization
                        "-aq-strength", "1.0", # Adaptive quantization strength
                        "-qmin", "0",         # Allow minimum quantizer for maximum quality
                        "-qmax", "15",        # Limit maximum quantizer to preserve quality
                        "-flags", "+cgop",    # Closed GOP for better seeking
                        "-x264opts", "no-deblock"  # Disable deblocking for sharper output
                    ],
                    verbose=False,    # Reduce verbose output
                    logger=None,      # Disable logging to prevent potential deadlocks
                    write_logfile=False,  # Prevent log file issues
                )
        finally:
            devnull.close()
            
    except Exception as e:
        # If write fails, clean up partial files and re-raise
        if out_path.exists():
            try:
                out_path.unlink()
            except Exception:
                pass
        # Don't re-raise stdout/stderr related errors if video was actually created
        if out_path.exists() and out_path.stat().st_size > 0:
            # Video was created successfully despite the error
            pass
        else:
            raise e
    # Clean up all resources properly
    try:
        audio.close()
    except Exception:
        pass
    try:
        base.close()
    except Exception:
        pass
    # Clean up source video clips
    for clip in source_clips:
        try:
            clip.close()
        except Exception:
            pass
    try:
        if final_audio != audio:
            final_audio.close()
    except Exception:
        pass
    try:
        final.close()
    except Exception:
        pass
    
    # Force garbage collection to free memory
    import gc
    gc.collect()
    
    return out_path



