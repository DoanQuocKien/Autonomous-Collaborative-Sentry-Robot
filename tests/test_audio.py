"""T0 unit tests for sentry/app/audio.py and pre-generated WAV assets in assets/audio/."""
import pytest

from jetson.robot_udp import play_clip
from sentry.app.audio import (
    AUDIO_DIR,
    PROMPTS,
    AudioPromptPlayer,
    generate_all,
    render_prompt_wav,
    validate_clip_name,
    verify_wav,
)


def test_prompt_catalog_respects_spec_text_and_protocol_clip_regex():
    assert PROMPTS["place_camera"] == "Guarding position reached. Please place the entrance camera."
    assert PROMPTS["guard_ready"] == "Guarding position reached. Please place the entrance camera."
    for clip, text in PROMPTS.items():
        assert validate_clip_name(clip) == clip
        assert len(text) > 5
    for bad in ("../escape", "UPPER", "with space", "", 42):
        with pytest.raises(ValueError):
            validate_clip_name(bad)


def test_synth_backend_generates_valid_pcm16_mono_wavs(tmp_path):
    infos = generate_all(tmp_path, backend="synth", sample_rate=8000)
    assert set(infos) == set(PROMPTS)
    for clip, info in infos.items():
        assert info.path == tmp_path / ("%s.wav" % clip)
        assert info.nchannels == 1 and info.sampwidth == 2 and info.framerate == 8000
        assert info.duration_s > 0.3 and info.peak > 1000


def test_committed_assets_audio_wavs_exist_and_work_with_jetson_play_clip():
    assert AUDIO_DIR.exists(), "assets/audio/ must contain pre-generated WAV prompts"
    for clip in PROMPTS:
        wav_path = AUDIO_DIR / ("%s.wav" % clip)
        info = verify_wav(wav_path)
        assert info.nchannels == 1 and info.sampwidth == 2
        assert 400 < wav_path.stat().st_size < 250_000

    # Verify compatibility with jetson/robot_udp.py play_clip
    started = []

    class DummyProc:
        def poll(self):
            return 0

    players = []
    err = play_clip(str(AUDIO_DIR), "place_camera", players, popen=lambda cmd: started.append(cmd) or DummyProc())
    assert err is None
    assert started == [["aplay", "-q", str(AUDIO_DIR / "place_camera.wav")]]


def test_audio_prompt_player_dispatches_to_sender_and_tracks_history(tmp_path):
    render_prompt_wav("Guarding position reached.", tmp_path / "place_camera.wav", clip_name="place_camera", backend="synth")

    class StubSender:
        def __init__(self):
            self.played = []

        def play(self, clip):
            self.played.append(clip)
            return True

    tx = StubSender()
    player = AudioPromptPlayer(sender=tx, audio_dir=tmp_path)
    assert player.play("place_camera")
    assert tx.played == ["place_camera"]
    assert player.history == ["place_camera"]
    with pytest.raises(FileNotFoundError):
        player.play("missing_clip")


def test_local_speaker_plays_on_this_machine_and_never_raises(tmp_path):
    from sentry.app.audio import AudioPromptPlayer, LocalSpeaker
    (tmp_path / "place_camera.wav").write_bytes(b"RIFF")
    played = []
    sp = LocalSpeaker(tmp_path, backend=played.append)
    assert sp.play("place_camera") is True and played == [str(tmp_path / "place_camera.wav")] and sp.played == ["place_camera"]
    assert sp.play("absent") is False                                   # a missing clip is False, not an exception

    def broken(path):
        raise OSError("no sound card")
    assert LocalSpeaker(tmp_path, backend=broken).play("place_camera") is False
    assert AudioPromptPlayer(sender=LocalSpeaker(tmp_path, backend=played.append), audio_dir=tmp_path).play("place_camera") is True
    with pytest.raises(ValueError):
        sp.play("../evil")
