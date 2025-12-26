from __future__ import annotations

import os
import random
import subprocess
import uuid
from pathlib import Path
from typing import List, Dict, Sequence


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


def _get_ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg  # type: ignore

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return "ffmpeg"


def _get_ffprobe_exe() -> str:
    ffmpeg = _get_ffmpeg_exe()
    if ffmpeg.lower().endswith("ffmpeg.exe"):
        return ffmpeg[:-9] + "ffprobe.exe"
    if ffmpeg.lower().endswith("/ffmpeg"):
        return ffmpeg[:-6] + "/ffprobe"
    return "ffprobe"


def _probe_duration_seconds(media_path: Path | str) -> float | None:
    p = Path(media_path)
    if not p.exists():
        return None
    try:
        exe = _get_ffprobe_exe()
        r = subprocess.run(
            [
                exe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(p),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            return None
        s = (r.stdout or "").strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _ass_time(t: float) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100.0))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\\", r"\\")
    s = s.replace("{", r"\{").replace("}", r"\}")
    s = s.replace("\n", r"\N")
    return s


def _write_ass_subtitles(
    ass_path: Path,
    caption_spans: List[Dict[str, float | str]] | None,
    karaoke_word_spans: Sequence[Dict[str, float | str | int]] | None,
    width: int,
    height: int,
) -> bool:
    caption_spans = caption_spans or []
    karaoke_word_spans = karaoke_word_spans or []
    if not caption_spans and not karaoke_word_spans:
        return False

    caption_x = int(width * 0.5)
    caption_y = int(height * 0.78)
    center_x = int(width * 0.5)
    center_y = int(height * 0.5)

    font_size_caption = max(28, int(height * 0.035))
    font_size_karaoke = max(28, int(height * 0.040))

    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,Arial,{font_size_caption},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,0,5,10,10,10,1",
            f"Style: Karaoke,Arial,{font_size_karaoke},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,0,5,10,10,10,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )

    lines: list[str] = [header]
    if karaoke_word_spans:
        for w in karaoke_word_spans:
            start = float(w["start"])  # type: ignore[arg-type]
            end = float(w["end"])  # type: ignore[arg-type]
            txt = _ass_escape_text(str(w.get("text", "")).strip())
            if not txt:
                continue
            tag = rf"{{\an5\pos({center_x},{center_y})\fs{font_size_karaoke}\bord4\shad0}}"
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Karaoke,,0,0,0,,{tag}{txt}")
    else:
        for span in caption_spans:
            start = float(span["start"])  # type: ignore[arg-type]
            end = float(span["end"])  # type: ignore[arg-type]
            txt = _ass_escape_text(str(span.get("text", "")).strip())
            if not txt:
                continue
            tag = rf"{{\an5\pos({caption_x},{caption_y})\fs{font_size_caption}\bord4\shad0}}"
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{tag}{txt}")

    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _ffmpeg_filter_escape_path(p: Path) -> str:
    s = str(p).replace("\\", "/")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    return s


def _compose_video_with_tts_ffmpeg(
    video_path: Path | str,
    tts_audio_path: Path | str,
    caption_spans: List[Dict[str, float | str]],
    output_path: Path | str,
    chosen_start_time: float | None,
    crf: int,
    encode_preset: str,
    video_bitrate: str | None,
    karaoke_word_spans: Sequence[Dict[str, float | str | int]] | None,
    add_background_music: bool,
    bg_music_volume: float,
    bg_music_dir: Path | str,
    bg_music_path: Path | str | None,
    split_screen_enabled: bool,
    video_path2: Path | str | None,
    tail_padding_s: float,
    out_width: int = 1080,
    out_height: int = 1920,
    fps_out: int = 30,
) -> Path:
    video_path = Path(video_path)
    tts_audio_path = Path(tts_audio_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tts_dur = _probe_duration_seconds(tts_audio_path)
    if tts_dur is None:
        raise RuntimeError("Failed to probe TTS audio duration (ffprobe missing?)")
    duration = float(tts_dur) + max(0.0, float(tail_padding_s or 0.0))
    duration = max(0.01, duration)

    if chosen_start_time is not None:
        start_time1 = max(0.0, float(chosen_start_time))
    else:
        v1_dur = _probe_duration_seconds(video_path)
        if v1_dur and v1_dur > 1.0:
            start_time1 = random.uniform(0.0, max(0.0, float(v1_dur) - 1.0))
        else:
            start_time1 = 0.0

    start_time2 = 0.0
    if split_screen_enabled and video_path2:
        v2 = Path(video_path2)
        v2_dur = _probe_duration_seconds(v2)
        if v2_dur and v2_dur > 1.0:
            start_time2 = random.uniform(0.0, max(0.0, float(v2_dur) - 1.0))

    chosen_bg: Path | None = None
    if add_background_music:
        chosen_bg = Path(bg_music_path) if bg_music_path else _get_random_background_music(bg_music_dir)

    ass_path = out_path.parent / f"subs_{uuid.uuid4().hex}.ass"
    has_subs = _write_ass_subtitles(
        ass_path=ass_path,
        caption_spans=caption_spans,
        karaoke_word_spans=karaoke_word_spans,
        width=out_width,
        height=out_height,
    )

    ffmpeg = _get_ffmpeg_exe()

    cmd: list[str] = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]

    cmd += ["-stream_loop", "-1", "-i", str(video_path)]
    idx_video2 = None
    if split_screen_enabled and video_path2:
        idx_video2 = 1
        cmd += ["-stream_loop", "-1", "-i", str(video_path2)]

    idx_tts = 1 if idx_video2 is None else 2
    cmd += ["-i", str(tts_audio_path)]

    idx_bg = None
    if chosen_bg and chosen_bg.exists():
        idx_bg = idx_tts + 1
        cmd += ["-stream_loop", "-1", "-i", str(chosen_bg)]

    def v_chain(input_label: str, start: float) -> str:
        return (
            f"{input_label}trim=start={start}:duration={duration},setpts=PTS-STARTPTS,"
            f"scale={out_width}:{out_height}:force_original_aspect_ratio=increase,"
            f"crop={out_width}:{out_height},fps={fps_out}"
        )

    vf_parts: list[str] = []
    if idx_video2 is not None:
        vf_parts.append(v_chain("[0:v]", start_time1) + "[v1]")
        vf_parts.append(v_chain("[1:v]", start_time2) + "[v2]")
        vf_parts.append("[v1]crop=iw:ih*3/4:0:ih*1/4,scale=%d:%d[top]" % (out_width, out_height // 2))
        vf_parts.append("[v2]crop=iw:ih*3/4:0:ih*1/4,scale=%d:%d[bot]" % (out_width, out_height // 2))
        vf_parts.append("[top][bot]vstack=inputs=2[vbase]")
    else:
        vf_parts.append(v_chain("[0:v]", start_time1) + "[vbase]")

    if float(tail_padding_s or 0.0) > 0:
        vf_parts.append(f"[vbase]tpad=stop_mode=clone:stop_duration={float(tail_padding_s)}[vpad]")
        v_in = "[vpad]"
    else:
        v_in = "[vbase]"

    if has_subs:
        subs_esc = _ffmpeg_filter_escape_path(ass_path)
        vf_parts.append(f"{v_in}subtitles='{subs_esc}'[vout]")
    else:
        vf_parts.append(f"{v_in}null[vout]")

    af_parts: list[str] = []
    tail = max(0.0, float(tail_padding_s or 0.0))
    af_parts.append(f"[{idx_tts}:a]apad=pad_dur={tail},atrim=0:{duration},asetpts=N/SR/TB[atts]")
    if idx_bg is not None:
        af_parts.append(f"[{idx_bg}:a]atrim=0:{duration},asetpts=N/SR/TB,volume={float(bg_music_volume)}[abg]")
        af_parts.append("[atts][abg]amix=inputs=2:duration=longest:dropout_transition=0[aout]")
    else:
        af_parts.append("[atts]anull[aout]")

    filter_complex = ";".join([*vf_parts, *af_parts])

    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", "[vout]", "-map", "[aout]"]
    cmd += ["-c:v", "libx264", "-preset", str(encode_preset or "faster"), "-crf", str(int(crf))]
    if video_bitrate:
        cmd += ["-b:v", str(video_bitrate)]
    cmd += ["-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart"]
    cmd += ["-c:a", "aac", "-b:a", "192k"]

    threads = max(1, min(8, int(os.cpu_count() or 1)))
    cmd += ["-threads", str(threads)]
    cmd += [str(out_path)]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or "ffmpeg failed").strip())
        if not out_path.exists() or out_path.stat().st_size <= 0:
            raise RuntimeError("ffmpeg completed but output file is missing/empty")
        return out_path
    finally:
        if has_subs:
            try:
                ass_path.unlink(missing_ok=True)
            except Exception:
                pass


def _choose_random_subclip_for_duration(
    video: VideoFileClip, duration: float, start_time: float | None = None
) -> VideoFileClip:
    from moviepy.video.fx import all as vfx

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
    from moviepy.editor import ImageClip

    def _find_font(size: int) -> ImageFont.FreeTypeFont:
        # Prefer project/local or system fonts if available, else PIL packaged font, else default
        candidates = [
            r"C:\\Windows\\Fonts\\TikTok-Sans.ttf",
            r"C:\\Windows\\Fonts\\TikTok-Sans.TTF",
            # Common Linux fonts (Ubuntu/Debian)
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
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
    from moviepy.editor import ImageClip

    def _find_font(size: int) -> ImageFont.FreeTypeFont:
        candidates = [
            r"C:\\Windows\\Fonts\\arialbd.ttf",
            r"C:\\Windows\\Fonts\\ARIALBD.TTF",
            r"C:\\Windows\\Fonts\\arial.ttf",
            r"C:\\Windows\\Fonts\\ARIAL.TTF",
            # Common Linux fonts (Ubuntu/Debian)
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
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

    from moviepy.video.fx import all as vfx

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

    from moviepy.editor import CompositeVideoClip
    from moviepy.video.fx import all as vfx
    
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


def _compose_video_with_tts_moviepy(
    video_path: Path | str,
    tts_audio_path: Path | str,
    caption_spans: List[Dict[str, float | str]],
    output_path: Path | str,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
    chosen_start_time: float | None = None,
    crf: int = 15,
    encode_preset: str = "faster",
    video_bitrate: str | None = None,
    karaoke_word_spans: Sequence[Dict[str, float | str | int]] | None = None,
    add_background_music: bool = True,
    bg_music_volume: float = 0.10,
    bg_music_dir: Path | str = "bg music",
    bg_music_path: Path | str | None = None,
    split_screen_enabled: bool = False,
    video_path2: Path | str | None = None,
    tail_padding_s: float = 0.0,
) -> Path:
    # Pillow compatibility shim for MoviePy with Pillow >= 10
    try:  # pragma: no cover - tiny runtime shim
        from PIL import Image as _PILImage

        if not hasattr(_PILImage, "ANTIALIAS"):
            try:
                if hasattr(_PILImage, "Resampling"):
                    _PILImage.ANTIALIAS = _PILImage.Resampling.LANCZOS  # type: ignore[attr-defined]
                    _PILImage.BICUBIC = _PILImage.Resampling.BICUBIC  # type: ignore[attr-defined]
                    _PILImage.BILINEAR = _PILImage.Resampling.BILINEAR  # type: ignore[attr-defined]
                else:
                    _PILImage.ANTIALIAS = _PILImage.LANCZOS  # type: ignore[attr-defined]
            except Exception:
                pass
    except Exception:
        pass

    from moviepy.editor import (
        VideoFileClip,
        AudioFileClip,
        CompositeVideoClip,
        CompositeAudioClip,
    )

    audio = AudioFileClip(str(tts_audio_path))
    duration = float(audio.duration) + max(0.0, float(tail_padding_s))

    source_clips = []

    if split_screen_enabled and video_path2:
        video1 = VideoFileClip(str(video_path))
        video2 = VideoFileClip(str(video_path2))
        source_clips.extend([video1, video2])

        start_time1 = chosen_start_time if chosen_start_time is not None else random.uniform(0.0, max(0.0, video1.duration - 1.0))
        start_time2 = random.uniform(0.0, max(0.0, video2.duration - 1.0))

        base = _create_split_screen_horizontal(video1, video2, duration, start_time1, start_time2)
        width, height = base.size
    else:
        video = VideoFileClip(str(video_path))
        source_clips.append(video)

        base = _choose_random_subclip_for_duration(video, duration, start_time=chosen_start_time)
        base = _ensure_vertical_9_16(base)
        width, height = base.size

    if karaoke_word_spans:
        caption_layers = _render_karaoke_overlay(width, height, karaoke_word_spans)
    else:
        caption_layers = _render_captions_layers(width, height, caption_spans)

    fps_out = base.fps or 30
    duration = (int(duration * fps_out)) / fps_out
    duration = max(0.01, duration)

    final_audio = audio
    if add_background_music:
        chosen_bg = Path(bg_music_path) if bg_music_path else _get_random_background_music(bg_music_dir)
        if chosen_bg:
            try:
                bg_music = AudioFileClip(str(chosen_bg))
                if bg_music.duration > duration:
                    max_start = bg_music.duration - duration
                    bg_start = random.uniform(0.0, max_start)
                    bg_music = bg_music.subclip(bg_start, bg_start + duration)
                else:
                    from moviepy.audio.fx import all as afx

                    bg_music = afx.audio_loop(bg_music, duration=duration)

                bg_music = bg_music.volumex(bg_music_volume)
                final_audio = CompositeAudioClip([audio, bg_music])
                bg_music.close()
            except Exception:
                pass

    try:
        from moviepy.audio.AudioClip import AudioClip

        silence = AudioClip(lambda t: 0.0, duration=duration, fps=44100)
        final_audio = CompositeAudioClip([silence, final_audio]).set_duration(duration)
    except Exception:
        try:
            final_audio = final_audio.set_duration(duration)
        except Exception:
            pass

    final = (
        CompositeVideoClip([base, *caption_layers], size=(width, height))
        .set_audio(final_audio)
        .set_duration(duration)
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from contextlib import redirect_stderr, redirect_stdout

        devnull = open(os.devnull, "w")
        try:
            threads = max(1, min(8, int(os.cpu_count() or 1)))
            with redirect_stdout(devnull), redirect_stderr(devnull):
                final.write_videofile(
                    str(out_path),
                    codec="libx264",
                    audio_codec="aac",
                    preset=str(encode_preset or "faster"),
                    threads=threads,
                    fps=fps_out,
                    bitrate=video_bitrate,
                    ffmpeg_params=[
                        "-crf",
                        str(crf),
                        "-pix_fmt",
                        "yuv420p",
                        "-profile:v",
                        "high",
                        "-movflags",
                        "+faststart",
                    ],
                    verbose=False,
                    logger=None,
                    write_logfile=False,
                )
        finally:
            devnull.close()
    except Exception as e:
        if out_path.exists():
            try:
                out_path.unlink()
            except Exception:
                pass
        if out_path.exists() and out_path.stat().st_size > 0:
            pass
        else:
            raise e
    try:
        audio.close()
    except Exception:
        pass
    try:
        base.close()
    except Exception:
        pass
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
    try:
        import gc

        gc.collect()
    except Exception:
        pass

    return out_path


def compose_video_with_tts(
    video_path: Path | str,
    tts_audio_path: Path | str,
    caption_spans: List[Dict[str, float | str]],
    output_path: Path | str,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
    chosen_start_time: float | None = None,
    crf: int = 15,
    encode_preset: str = "faster",
    video_bitrate: str | None = None,
    karaoke_word_spans: Sequence[Dict[str, float | str | int]] | None = None,
    add_background_music: bool = True,
    bg_music_volume: float = 0.10,
    bg_music_dir: Path | str = "bg music",
    bg_music_path: Path | str | None = None,
    split_screen_enabled: bool = False,
    video_path2: Path | str | None = None,
    tail_padding_s: float = 0.0,
    renderer: str = "ffmpeg",
) -> Path:
    r = (renderer or "").strip().lower()
    if r in ("moviepy", "python"):
        return _compose_video_with_tts_moviepy(
            video_path=video_path,
            tts_audio_path=tts_audio_path,
            caption_spans=caption_spans,
            output_path=output_path,
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
            chosen_start_time=chosen_start_time,
            crf=crf,
            encode_preset=encode_preset,
            video_bitrate=video_bitrate,
            karaoke_word_spans=karaoke_word_spans,
            add_background_music=add_background_music,
            bg_music_volume=bg_music_volume,
            bg_music_dir=bg_music_dir,
            bg_music_path=bg_music_path,
            split_screen_enabled=split_screen_enabled,
            video_path2=video_path2,
            tail_padding_s=tail_padding_s,
        )
    try:
        return _compose_video_with_tts_ffmpeg(
            video_path=video_path,
            tts_audio_path=tts_audio_path,
            caption_spans=caption_spans,
            output_path=output_path,
            chosen_start_time=chosen_start_time,
            crf=crf,
            encode_preset=encode_preset,
            video_bitrate=video_bitrate,
            karaoke_word_spans=karaoke_word_spans,
            add_background_music=add_background_music,
            bg_music_volume=bg_music_volume,
            bg_music_dir=bg_music_dir,
            bg_music_path=bg_music_path,
            split_screen_enabled=split_screen_enabled,
            video_path2=video_path2,
            tail_padding_s=tail_padding_s,
        )
    except Exception:
        return _compose_video_with_tts_moviepy(
            video_path=video_path,
            tts_audio_path=tts_audio_path,
            caption_spans=caption_spans,
            output_path=output_path,
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
            chosen_start_time=chosen_start_time,
            crf=crf,
            encode_preset=encode_preset,
            video_bitrate=video_bitrate,
            karaoke_word_spans=karaoke_word_spans,
            add_background_music=add_background_music,
            bg_music_volume=bg_music_volume,
            bg_music_dir=bg_music_dir,
            bg_music_path=bg_music_path,
            split_screen_enabled=split_screen_enabled,
            video_path2=video_path2,
            tail_padding_s=tail_padding_s,
        )



