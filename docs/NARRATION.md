# Narration and film storyboard

The 24-second film is complete without spoken narration. The separate studio demonstration is 80 seconds and uses the following word-for-word script. Its stock synthetic voice is disclosed in the video credits and provenance. It is not a recording or clone of Shivam.

## Word-for-word studio narration

> Second Nature gives small creative teams a repeatable way to turn one visual idea into a finished film.

> Start with the featured animation. A single drop races through a precision machine, pauses above a waiting seed, and brings it to life.

> Continue as a guest, or create an account to keep your workspace across devices. Name a production, choose the drop and enamel colors, and set a detail seed for consistent soil.

> Save the production, then select Create film. Blender builds and lights the editable scene, renders the complete story in the cloud, and assembles the movie.

> The workbench shows actual frame progress and production logs. Cancel safely if needed, then resume from completed frames instead of starting again.

> Once finished, play the film in your browser and download the video or Blender scene. Download the files you want to keep; cloud exports remain available for seven days.

> Created by Shivam Gupta with AI assistance, Second Nature connects a carefully directed visual story to a repeatable production workflow.

> Make every second grow.

Read at about 129 words per minute. Keep the delivery conversational, with short breaths at sentence boundaries. The prepared narration has no pause reaching 1.2 seconds at the measured silence threshold. The picture edit uses actual film excerpts, app captures and production evidence; elapsed production time is condensed.

The captions, word timings and synthesis provenance are alongside `film/studio-demo-narration.wav`. Technical measurements are in `film/studio-demo-narration.verification.json`. Model-predicted word timings must still be checked against the finished picture edit.

## Film storyboard

| Film interval | Story beat | Motion and visual intent |
| --- | --- | --- |
| 0–2s | Dry seed, isolated | Establish why arrival matters |
| 2–6s | Drop launches through gates | Following camera and repeated geometry show acceleration |
| 6–11s | Full vertical loop | The route and moving drop remain visible |
| 11–15.25s | Glide, suspension, fall | Motion slows, holds and releases into the seed |
| 15.25–24s | Growth and resolve | Stem and leaves emerge, staggered petals open, then closing type |

There is no literal countdown. Fast travel and suspended stillness supply the contrast. Storyboard timings follow the scripted 576-frame sequence; the final movie is the source of truth.

## Optional human recording

The finished synthetic narration requires no recording from the entrant. To replace it, record the studio script in a quiet room in about 80 seconds, then run:

```sh
.venv/bin/python source/add_voiceover.py --voice /absolute/path/to/your-recording.m4a
```

The helper requires the completed 80-second `film/studio-demo.mp4`, preserves both inputs, applies pitch-preserving tempo adjustment and normalizes the replacement voice. It writes `film/studio-demo-human-voice.mp4`. It rejects the 24-second film as an accidental input. Review the burned captions against the replacement recording and regenerate the picture edit with revised timings if they drift; a new speaker will not automatically match the synthetic word timings. Update the picture credits to identify the human narrator before publishing the replacement.
