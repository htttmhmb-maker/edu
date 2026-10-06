"""
generate_video.py — Trivia Shorts (English only)
Timeline (13 s): question 6 s -> countdown 3-2-1 (1 s each, tick) -> answer 4 s.
Single ffmpeg pass: images -> video, audio mixed from assets/.

Optional audio files in ./assets (all optional, auto-detected):
  music.mp3   background music (looped, low volume)
  tick.wav    countdown tick (a synthetic beep is used if missing)
  reveal.wav  sound played when the answer appears
"""
import os
import shutil
import subprocess
import tempfile

from generate_image import render_answer, render_countdown, render_question

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

FPS = 30
QUESTION_SECONDS = 6
COUNTDOWN_STEPS = 3          # 3, 2, 1 — one second each
ANSWER_SECONDS = 4
TOTAL_SECONDS = QUESTION_SECONDS + COUNTDOWN_STEPS + ANSWER_SECONDS

MUSIC_VOLUME = 0.30
SFX_VOLUME = 1.0


def _asset(*names):
    for n in names:
        p = os.path.join(ASSETS_DIR, n)
        if os.path.exists(p):
            return p
    return None


def _run(cmd):
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed:\n{e.stderr[-2000:]}") from e


def _write_concat(items, list_path):
    with open(list_path, "w", encoding="utf-8") as f:
        for img, dur in items:
            f.write(f"file '{img.replace(chr(92), '/')}'\nduration {dur}\n")
        f.write(f"file '{items[-1][0].replace(chr(92), '/')}'\n")  # concat demuxer quirk


def build_trivia_video(question_data, output_path):
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH")

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="trivia_") as tmp:
        q_img = render_question(question_data, os.path.join(tmp, "q.png"))
        c_imgs = [render_countdown(question_data, n, os.path.join(tmp, f"c{n}.png"))
                  for n in range(COUNTDOWN_STEPS, 0, -1)]
        a_img = render_answer(question_data, os.path.join(tmp, "a.png"))

        items = [(q_img, QUESTION_SECONDS)] + [(p, 1) for p in c_imgs] + [(a_img, ANSWER_SECONDS)]
        list_path = os.path.join(tmp, "list.txt")
        _write_concat(items, list_path)

        # ---- inputs ----
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path]
        n_in = 1
        music = _asset("music.mp3", "music.wav", "music.m4a")
        tick = _asset("tick.wav", "tick.mp3")
        reveal = _asset("reveal.wav", "reveal.mp3")

        music_idx = tick_idx = reveal_idx = None
        if music:
            cmd += ["-stream_loop", "-1", "-i", music]
            music_idx, n_in = n_in, n_in + 1
        if tick:
            cmd += ["-i", tick]
        else:
            cmd += ["-f", "lavfi", "-i", "sine=frequency=880:duration=0.15"]
        tick_idx, n_in = n_in, n_in + 1
        if reveal:
            cmd += ["-i", reveal]
            reveal_idx, n_in = n_in, n_in + 1

        # ---- audio graph ----
        fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
        parts, labels = [], []
        tick_chain = f"[{tick_idx}:a]{fmt}"
        if not tick:
            tick_chain += ",afade=t=out:st=0.08:d=0.07"
        tick_chain += f",volume={SFX_VOLUME},asplit={COUNTDOWN_STEPS}" + "".join(
            f"[t{k}]" for k in range(COUNTDOWN_STEPS))
        parts.append(tick_chain)
        for k in range(COUNTDOWN_STEPS):
            ms = int((QUESTION_SECONDS + k) * 1000)
            parts.append(f"[t{k}]adelay={ms}|{ms}[dt{k}]")
            labels.append(f"[dt{k}]")
        if reveal_idx is not None:
            ms = int((QUESTION_SECONDS + COUNTDOWN_STEPS) * 1000)
            parts.append(f"[{reveal_idx}:a]{fmt},volume={SFX_VOLUME},adelay={ms}|{ms}[rv]")
            labels.append("[rv]")
        if music_idx is not None:
            parts.append(
                f"[{music_idx}:a]{fmt},volume={MUSIC_VOLUME},atrim=0:{TOTAL_SECONDS},"
                f"afade=t=in:d=0.5,afade=t=out:st={TOTAL_SECONDS - 1}:d=1[m]")
            labels.append("[m]")
        parts.append(
            "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
            f"apad=whole_dur={TOTAL_SECONDS}[aout]")

        cmd += [
            "-filter_complex", ";".join(parts),
            "-map", "0:v", "-map", "[aout]",
            "-vf", f"fps={FPS},scale=1080:1920,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart", "-t", str(TOTAL_SECONDS),
            output_path,
        ]
        _run(cmd)

    return output_path


if __name__ == "__main__":
    from fetch_trivia import get_random_question
    out = build_trivia_video(get_random_question(), os.path.join(BASE_DIR, "test_trivia.mp4"))
    print("saved", out)
