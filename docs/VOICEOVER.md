# Neural narrator and captions

The product demonstration uses a stock synthetic English narrator. It does not
clone Shivam Gupta's voice or present the narrator as Shivam. The film soundtrack
and the demonstration narration are separate assets.

The optional synthesis helper uses the official
[Kokoro library](https://github.com/hexgrad/kokoro) and
[Kokoro-82M model](https://huggingface.co/hexgrad/Kokoro-82M), with the `af_heart`
stock voice. The model is published under Apache-2.0. No paid speech service,
voice reference recording or speech API key is required. The first run downloads
the model, stock voice and English pronunciation resources.

Run from the project folder in a separate environment:

```sh
python3 -m venv .voice-venv
.voice-venv/bin/python -m pip install -r requirements-voice.txt
.voice-venv/bin/python source/synthesize_voiceover.py \
  --text docs/studio-demo-script.txt \
  --output film/studio-demo-narration.wav \
  --target-duration 80 \
  --speed 0.84
```

The speed setting matches the prepared narration; its measured native reading
needs only a modest final tempo adjustment to fit 80 seconds.

Install FFmpeg separately. English pronunciation fallback also uses espeak-ng;
on macOS it can be installed with `brew install espeak-ng`. The first model
download needs internet access. Subsequent synthesis can reuse the local cache.
An optional `--cache-dir /absolute/path/to/cache` chooses the model cache.

The helper writes stereo PCM audio at 48 kHz, normalized toward -16 LUFS, plus:

- `.srt` and `.vtt` captions, grouped into short readable phrases.
- `.words.json` with word timing estimates from the speech model's token durations.
- `.narration.json` with transcript, voice, model, duration and SHA-256 provenance.

The timing estimates account for trimming and the final tempo adjustment. They
are model predictions rather than a separate speech recognition alignment.
Review captions against playback before publication. Modest tempo adjustment
keeps a chosen picture duration; the helper rejects large changes that would
damage the reading's natural pace. Revise the script if it does not fit.

There is no first-person impersonation in the demonstration script. Any future
human recording should be credited separately from synthetic narration.
