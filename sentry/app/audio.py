"""Offline TTS prompt generation and audio clip catalog for Phase 1–3 HCI & deterrence.

The Jetson plays pre-generated WAV files from `assets/audio/<clip>.wav` via `aplay -q`
when it receives a `{"seq": int, "play": "<clip>"}` UDP packet (`jetson/robot_udp.py`).
Clip names must match `^[a-z0-9_]{1,32}$` (`common/protocol.py`).

Since 2026-10-28 there is NO speaker on the robot (cost): the laptop plays the clips. Use `AudioPromptPlayer(sender=LocalSpeaker())`; the Jetson `play` path above stays
in the code but is unused.

Run offline generation from the repo root:
    python -m sentry.app.audio
"""
import argparse
from array import array
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import wave

from common.protocol import decode_control, encode_play

ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT / "assets" / "audio"

# Required spoken prompts and deterrent clips across Phases 1–3.
# `guard_ready` and `place_camera` both carry the Spec §4.3 deployment message so
# existing controller tests (`guard_ready`, `alarm`) and state-machine prompts match.
PROMPTS = {
    "place_camera": "Guarding position reached. Please place the entrance camera.",
    "guard_ready": "Guarding position reached. Please place the entrance camera.",
    "camera_verified": "Entrance camera verified. Moving to standby.",
    "standby": "Standby mode active. Monitoring entrance.",
    "intruder_detected": "Unregistered entrant detected. Engaging target.",
    "hold_position": "Target stationary. Holding position.",
    "alarm": "Warning. Aggressive movement detected. Evading.",
}

# Earcon header notes (Hz, duration_s) prepended before syllabic speech synthesis
_EARCONS = {
    "place_camera": [(587.33, 0.09), (880.0, 0.12)],
    "guard_ready": [(587.33, 0.09), (880.0, 0.12)],
    "camera_verified": [(523.25, 0.07), (659.25, 0.07), (783.99, 0.11)],
    "standby": [(440.0, 0.08), (554.37, 0.10)],
    "intruder_detected": [(740.0, 0.08), (554.37, 0.08), (740.0, 0.10)],
    "hold_position": [(523.25, 0.09), (523.25, 0.09)],
    "alarm": [(880.0, 0.10), (1320.0, 0.10), (880.0, 0.10), (1320.0, 0.10)],
}

# Formant table (F1, F2, F3 in Hz) by vowel character for deterministic offline synthesis
_VOWEL_FORMANTS = {
    "a": (730.0, 1090.0, 2440.0),
    "e": (530.0, 1840.0, 2480.0),
    "i": (270.0, 2290.0, 3010.0),
    "o": (570.0, 840.0, 2410.0),
    "u": (300.0, 870.0, 2240.0),
    "y": (320.0, 2100.0, 2800.0),
}


@dataclass(frozen=True)
class WavInfo:
    path: Path
    nchannels: int
    sampwidth: int
    framerate: int
    nframes: int
    duration_s: float
    peak: int


def validate_clip_name(clip):
    """Validate `clip` against common.protocol's regex (`^[a-z0-9_]{1,32}$`)."""
    if not isinstance(clip, str):
        raise ValueError("clip name must be a string, got %r" % (clip,))
    decode_control(encode_play(0, clip))
    return clip


def _write_pcm16_mono(path, samples_f32, sample_rate):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = array("h", (int(max(-1.0, min(1.0, x)) * 32767.0) for x in samples_f32))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())
    return path


def _read_and_normalize_wav(src_path, dst_path, sample_rate):
    """Convert any uncompressed WAV written by TTS into 16-bit mono PCM at `sample_rate`."""
    with wave.open(str(src_path), "rb") as wf:
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    if sw == 2:
        arr = array("h")
        arr.frombytes(raw)
        data = [x / 32768.0 for x in arr]
    elif sw == 1:
        data = [(b - 128.0) / 128.0 for b in raw]
    elif sw == 4:
        arr = array("i")
        arr.frombytes(raw)
        data = [x / 2147483648.0 for x in arr]
    else:
        raise ValueError("unsupported sample width: %d" % sw)
    if ch > 1:
        data = [sum(data[i:i + ch]) / float(ch) for i in range(0, len(data), ch)]
    if sr != sample_rate and len(data) > 1:
        new_len = max(1, int(round(len(data) * float(sample_rate) / float(sr))))
        scale = (len(data) - 1) / float(max(1, new_len - 1))
        resampled = []
        for idx in range(new_len):
            pos = idx * scale
            i0 = int(pos)
            i1 = min(len(data) - 1, i0 + 1)
            frac = pos - i0
            resampled.append(data[i0] * (1.0 - frac) + data[i1] * frac)
        data = resampled
    peak = max((abs(x) for x in data), default=0.0)
    if peak > 1e-4:
        inv = 0.85 / peak
        data = [x * inv for x in data]
    return _write_pcm16_mono(dst_path, data, sample_rate)


def _synth_tone(freq_hz, duration_s, sample_rate, amp=0.45):
    n = max(1, int(round(duration_s * sample_rate)))
    fade = min(n // 4, max(1, int(0.012 * sample_rate)))
    out = []
    for i in range(n):
        t = i / float(sample_rate)
        if i < fade:
            env = i / float(fade)
        elif i >= n - fade:
            env = (n - 1 - i) / float(fade)
        else:
            env = 1.0
        sig = (0.75 * math.sin(2.0 * math.pi * freq_hz * t) + 0.25 * math.sin(4.0 * math.pi * freq_hz * t)) * env * amp
        out.append(sig)
    return out


def _synth_speech_formants(text, sample_rate, *, clip_name=None):
    """Deterministic offline formant speech + earcon synthesizer (pure Python stdlib, zero external deps)."""
    samples = []
    for freq, dur in _EARCONS.get(clip_name or "", [(660.0, 0.08)]):
        samples.extend(_synth_tone(freq, dur, sample_rate, amp=0.48))
        samples.extend([0.0] * int(0.025 * sample_rate))

    clauses = [c.strip() for c in re.split(r"[.!?]+", text) if c.strip()]
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "little")
    rng = random.Random(seed)

    for c_idx, clause in enumerate(clauses):
        words = re.findall(r"[a-zA-Z0-9]+", clause.lower())
        for w_idx, word in enumerate(words):
            vowels = [ch for ch in word if ch in _VOWEL_FORMANTS] or ["a"]
            n_syl = max(1, min(3, len(vowels)))
            for s_idx in range(n_syl):
                v_ch = vowels[min(s_idx, len(vowels) - 1)]
                f1, f2, f3 = _VOWEL_FORMANTS[v_ch]
                f3_eff = min(f3, 0.45 * sample_rate)
                dur = 0.075 if n_syl > 1 else 0.095
                n = max(1, int(round(dur * sample_rate)))
                progress = (w_idx + s_idx / float(n_syl)) / max(1.0, float(len(words)))
                f0 = 145.0 - 25.0 * progress + 8.0 * math.sin(2.0 * math.pi * 3.0 * progress)
                has_burst = (s_idx == 0 and word[0] not in _VOWEL_FORMANTS)
                burst_len = min(n // 3, max(1, int(0.018 * sample_rate))) if has_burst else 0
                for i in range(n):
                    t = i / float(sample_rate)
                    glottal = (
                        0.55 * math.sin(2.0 * math.pi * f0 * t)
                        + 0.30 * math.sin(4.0 * math.pi * f0 * t)
                        + 0.15 * math.sin(6.0 * math.pi * f0 * t)
                    )
                    formant_wave = (
                        0.50 * math.sin(2.0 * math.pi * f1 * t)
                        + 0.32 * math.sin(2.0 * math.pi * f2 * t)
                        + 0.12 * math.sin(2.0 * math.pi * f3_eff * t)
                    )
                    consonant = 0.15 * rng.uniform(-1.0, 1.0) if i < burst_len else 0.0
                    env = max(0.0, math.sin(math.pi * i / float(max(1, n - 1)))) ** 0.65
                    samples.append((0.55 * glottal + 0.45 * formant_wave + consonant) * env * 0.42)
            samples.extend([0.0] * int(0.028 * sample_rate))
        if c_idx + 1 < len(clauses):
            samples.extend([0.0] * int(0.09 * sample_rate))

    if not samples:
        samples = [0.0] * int(0.2 * sample_rate)
    peak = max((abs(x) for x in samples), default=0.0)
    if peak > 1e-4:
        inv = 0.85 / peak
        samples = [x * inv for x in samples]
    return samples


def _try_pyttsx3(text, out_path, sample_rate):
    import pyttsx3

    with tempfile.TemporaryDirectory() as tmp:
        raw_wav = Path(tmp) / "tts.wav"
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.save_to_file(text, str(raw_wav))
        engine.runAndWait()
        if not raw_wav.exists() or raw_wav.stat().st_size < 64:
            raise RuntimeError("pyttsx3 did not produce audio output")
        return _read_and_normalize_wav(raw_wav, out_path, sample_rate)


def _try_espeak(text, out_path, sample_rate):
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise FileNotFoundError("neither espeak-ng nor espeak is on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        raw_wav = Path(tmp) / "espeak.wav"
        subprocess.run([exe, "-s", "165", "-w", str(raw_wav), text], check=True, timeout=10)
        if not raw_wav.exists() or raw_wav.stat().st_size < 64:
            raise RuntimeError("espeak did not produce audio output")
        return _read_and_normalize_wav(raw_wav, out_path, sample_rate)


def render_prompt_wav(text, out_path, *, clip_name=None, backend="auto", sample_rate=8000):
    """Render `text` into a 16-bit mono PCM WAV file at `out_path`.

    backend:
      * 'auto': tries pyttsx3 (Windows SAPI / espeak), then espeak-ng/espeak CLI,
                and falls back to deterministic offline formant synthesis.
      * 'pyttsx3': require pyttsx3.
      * 'espeak': require espeak-ng or espeak.
      * 'synth': always use deterministic offline formant synthesis.
    """
    if not text or not isinstance(text, str):
        raise ValueError("prompt text must be a non-empty string")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if clip_name is not None:
        validate_clip_name(clip_name)

    out_path = Path(out_path)
    if backend == "pyttsx3":
        return _try_pyttsx3(text, out_path, sample_rate)
    if backend == "espeak":
        return _try_espeak(text, out_path, sample_rate)
    if backend == "synth":
        samples = _synth_speech_formants(text, sample_rate, clip_name=clip_name)
        return _write_pcm16_mono(out_path, samples, sample_rate)
    if backend != "auto":
        raise ValueError("unknown audio backend: %r" % (backend,))

    for fn in (_try_pyttsx3, _try_espeak):
        try:
            return fn(text, out_path, sample_rate)
        except Exception:
            continue
    samples = _synth_speech_formants(text, sample_rate, clip_name=clip_name)
    return _write_pcm16_mono(out_path, samples, sample_rate)


def verify_wav(path):
    """Inspect a WAV file and verify it is non-empty 16-bit mono PCM suitable for `aplay`."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError("missing WAV file: %s" % path)
    with wave.open(str(path), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        comptype = wf.getcomptype()
        raw = wf.readframes(nframes)
    if comptype != "NONE" or nchannels != 1 or sampwidth != 2:
        raise ValueError("expected uncompressed 16-bit mono PCM WAV in %s" % path)
    if framerate <= 0 or nframes <= 0:
        raise ValueError("empty WAV in %s" % path)
    pcm = array("h")
    pcm.frombytes(raw)
    peak = max((abs(int(x)) for x in pcm), default=0)
    if peak == 0:
        raise ValueError("silent WAV in %s" % path)
    return WavInfo(
        path=path,
        nchannels=nchannels,
        sampwidth=sampwidth,
        framerate=framerate,
        nframes=nframes,
        duration_s=float(nframes) / float(framerate),
        peak=peak,
    )


def generate_all(audio_dir=AUDIO_DIR, *, prompts=None, backend="auto", sample_rate=8000, overwrite=True):
    """Generate and verify all pre-rendered WAV clips in `audio_dir`."""
    audio_dir = Path(audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    catalog = PROMPTS if prompts is None else dict(prompts)
    generated = {}
    for clip, text in sorted(catalog.items()):
        validate_clip_name(clip)
        wav_path = audio_dir / ("%s.wav" % clip)
        if overwrite or not wav_path.exists():
            render_prompt_wav(text, wav_path, clip_name=clip, backend=backend, sample_rate=sample_rate)
        generated[clip] = verify_wav(wav_path)
    return generated


def _default_backend():
    """winsound on Windows (asynchronous), else the first of aplay / afplay / paplay on PATH; the returned callable raises if nothing can play."""
    try:
        import winsound
        return lambda path: winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except ImportError:
        pass
    for exe in ("aplay", "afplay", "paplay"):
        found = shutil.which(exe)
        if found:
            return lambda path, exe=found: subprocess.Popen([exe, path])

    def no_player(path):
        raise RuntimeError("no audio player found (winsound, aplay, afplay, paplay)")
    return no_player


class LocalSpeaker:
    """Sender for AudioPromptPlayer that plays the clip on THIS machine. play(clip) -> True when playback started; False (never raises) for a missing clip or a failing player,
    so an audio problem can never stop the state machine. `backend(path)` is replaceable for tests."""

    def __init__(self, audio_dir=AUDIO_DIR, backend=None):
        self.audio_dir = Path(audio_dir)
        self._backend = backend
        self.played = []

    def play(self, clip):
        validate_clip_name(clip)
        path = self.audio_dir / ("%s.wav" % clip)
        if not path.exists():
            return False
        try:
            if self._backend is None:
                self._backend = _default_backend()
            self._backend(str(path))
        except Exception:
            return False
        self.played.append(clip)
        return True


class AudioPromptPlayer:
    """Validates clip names, checks local WAV assets, and dispatches `play` commands."""

    def __init__(self, sender=None, audio_dir=AUDIO_DIR):
        self.sender = sender
        self.audio_dir = Path(audio_dir)
        self.history = []

    def clip_path(self, clip):
        validate_clip_name(clip)
        return self.audio_dir / ("%s.wav" % clip)

    def play(self, clip):
        path = self.clip_path(clip)
        if not path.exists():
            raise FileNotFoundError("missing audio prompt %s" % path)
        sent = True if self.sender is None else bool(self.sender.play(clip))
        self.history.append(clip)
        return sent


def main():
    ap = argparse.ArgumentParser(description="Generate offline WAV prompts into assets/audio/")
    ap.add_argument("--out-dir", default=str(AUDIO_DIR))
    ap.add_argument("--backend", default="auto", choices=["auto", "pyttsx3", "espeak", "synth"])
    ap.add_argument("--sample-rate", type=int, default=8000)
    args = ap.parse_args()
    infos = generate_all(args.out_dir, backend=args.backend, sample_rate=args.sample_rate, overwrite=True)
    for clip, info in sorted(infos.items()):
        print("%-20s  %5.2f s  %6d B  %s" % (clip, info.duration_s, info.path.stat().st_size, info.path))


if __name__ == "__main__":
    main()
