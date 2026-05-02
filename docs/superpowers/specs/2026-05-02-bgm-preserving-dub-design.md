# BGM-Preserving Dub Pipeline

**Date:** 2026-05-02
**Status:** Approved (design); pending implementation plan

## Problem

The current dubbing pipeline (`pipeline_vi.py` and `pipeline.py`) replaces the entire original audio track with TTS narration on a silent base. This destroys all non-narration audio — background music, sound effects, ambient — forcing the user to manually layer the original and dubbed audio in CapCut and trim manually. Slow and lossy in quality.

Goal: produce `dubbed_video.mp4` where only the narration is replaced; original BGM and SFX remain audible underneath.

## Approach

Use [Demucs](https://github.com/facebookresearch/demucs) (Meta's source-separation model) to split `original_audio.wav` into `vocals.wav` (original speech) and `no_vocals.wav` (music + SFX + ambient). Mix `no_vocals.wav` as the timeline base; overlay TTS segments at their original timestamps.

**Volume policy:** original BGM stays at 100% — no ducking during narration. The user can still apply manual ducking later if desired.

**Default behavior:** BGM-preserve mode is the new default. Old silent-base behavior available via `--no-bg-music`.

## Architecture

```
Step 2  extract_audio        → original_audio.wav
Step 2.5 separate_vocals NEW → no_vocals.wav  +  vocals.wav (kept for debug)
Step 3-5 (transcribe / translate / TTS — unchanged)
Step 6c merge_with_background → audio_vi_full.wav
        (no_vocals.wav as base, VI segments overlaid at their start times)
Step 7  merge_video           → dubbed_video.mp4
```

## Components

### `src/vocal_separator.py` (new)

Single public function:

```python
def separate_vocals(
    input_wav: str,
    output_dir: str,
    model: str = "htdemucs",
) -> dict[str, str | None]:
    """Run Demucs two-stem separation on input_wav.

    Returns {"vocals": path, "no_vocals": path} on success.
    Returns {"vocals": None, "no_vocals": None} on failure (caller falls back).

    Skips work and returns existing paths if no_vocals.wav already exists in
    output_dir (resume-friendly).
    """
```

Implementation: subprocess invocation of `python -m demucs --two-stems=vocals -o <tmp_out> <input_wav>`. Demucs writes to `<tmp_out>/<model>/<basename>/{vocals,no_vocals}.wav`; the wrapper moves these to `<output_dir>/vocals.wav` and `<output_dir>/no_vocals.wav` and removes the temp tree.

CLI invocation chosen over Python API to keep import-time cost low for users running with `--no-bg-music` (Demucs imports torch, ~3–5 s).

### `src/audio_merger.py` (modified)

Extend `merge_segments` with an optional `background_path`:

```python
def merge_segments(
    segments: list[dict],
    segment_dir: str,
    output_path: str,
    total_duration: float,
    background_path: str | None = None,
) -> str:
```

When `background_path` is provided and the file exists: load it as an `AudioSegment`, pad/truncate to `total_duration * 1000` ms, and use it as the base instead of `AudioSegment.silent(...)`. Overlay logic for TTS segments unchanged.

When `background_path` is `None`: existing silent-base behavior (no behavior change for existing callers / tests).

### `pipeline_vi.py` and `pipeline.py` (modified)

CLI flag added to both:

```
--no-bg-music     Disable vocal separation; merge VI segments on a silent base
                  (legacy behavior).
```

After Step 2, before Step 3:

```python
no_vocals_path = None
if not args.no_bg_music:
    logger.info("STEP 2.5: Separating vocals from original audio (Demucs)")
    sep = separate_vocals(audio_path, work_dir)
    no_vocals_path = sep.get("no_vocals")
    if no_vocals_path is None:
        logger.warning("Vocal separation failed — falling back to silent base")
```

Step 6c becomes:

```python
merge_segments(segments, fit_dir, merged_audio_path, total_duration,
               background_path=no_vocals_path)
```

Both pipelines get the same change. JP pipeline (`pipeline.py`) currently has the same merge-on-silence pattern, so the diff mirrors VI exactly.

### `requirements.txt`

Add `demucs>=4.0.0`. Pulls in `torch`, `torchaudio`, `julius`, `lameenc` etc. (~2 GB on first install). First run downloads `htdemucs` model (~250 MB) into the local torch hub cache.

## Resume behavior

- `vocal_separator.separate_vocals` short-circuits if `<output_dir>/no_vocals.wav` already exists, returning the cached paths. Resuming a partially-run work_dir does not re-run Demucs.
- On `--resume` without `--no-bg-music`: pipeline checks for `<work_dir>/no_vocals.wav`. If present (from a prior phase-2 run or a manual Demucs run), it is used directly. If absent, Demucs runs.
- `--no-bg-music` on resume forces silent-base merge regardless of whether `no_vocals.wav` exists.

## Edge cases

| Case | Handling |
|---|---|
| Demucs not installed | subprocess raises; caught; warn + fallback to silent base |
| Model download fails (no internet) | Demucs subprocess returns non-zero; caught; warn + fallback |
| `no_vocals.wav` shorter than `total_duration` | pad with silence to match (preserves trailing tail of last VI segment) |
| `no_vocals.wav` longer than `total_duration` | truncate (final video length is governed by source video, not BGM) |
| GPU unavailable | Demucs auto-falls-back to CPU; ~30–60 s for 5-min audio; no code change |
| Source audio not 44.1 kHz stereo | `extract_audio` already produces a Demucs-compatible WAV; no special handling needed |

## Out of scope

- Programmatic ducking of BGM during narration windows. (User explicitly opted for 100% BGM volume.)
- Replacing Demucs with a smaller/faster model (Spleeter, MDX). Can be revisited if Demucs proves too slow on user's hardware.
- BGM-preserve mode for `pipeline.py` (Japanese) is wired up identically, but end-to-end validation will only run on the VI pipeline in this iteration.

## Testing

- Unit: `tests/test_audio_merger.py` adds a case for `merge_segments(..., background_path=...)` — verifies background is loaded, padded, and TTS segments are overlaid at correct positions.
- Unit: `tests/test_vocal_separator.py` (new) — mocks subprocess; verifies cache hit short-circuits, success path returns expected dict, failure path returns `None`s.
- Integration: re-run `pipeline_vi.py --resume output/VN/20260502140425_vi --file input/0502_1.mp4` (today's known-good work_dir) with the new code; expect `dubbed_video.mp4` to contain audible original BGM under VI narration.

## Open questions

None. All clarified during brainstorming:
- Volume policy: 100% BGM (no ducking) — confirmed
- Default behavior: BGM-preserve is default; `--no-bg-music` opt-out — confirmed
- Scope: shared module + both pipelines wired now — confirmed
