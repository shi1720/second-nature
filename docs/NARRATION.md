# SECOND NATURE - optional making-of

The **24-second contest film needs no spoken narration**. Submit the film itself, not this longer explanation, as the official animation. This optional making-of can accompany a portfolio or Devpost mirror.

## Word-for-word voiceover

Approximately 75 seconds at a calm 145–150 words per minute. Read naturally, with a short pause after “Then it stops.”

> I'm Shivam Gupta, the entrant and project lead behind SECOND NATURE.
>
> This is a twenty-four-second Blender film about speed with somewhere to go.
>
> It begins with a dry seed. An amber drop races through gates, follows precision rails, and climbs a vertical loop. Then it stops. For a moment, the whole film waits with it. The drop falls, and the seed becomes a flower.
>
> The idea is simple: speed matters because of what it makes possible.
>
> The production is procedural. Blender Python constructs the geometry, materials, lighting, and animation. The flower opens in staggered layers, and motion is baked into keyframes. The soundtrack is synthesized for this film.
>
> Behind it is a local production studio. A creator can sign in, choose a palette and seed, build the scene, render it, and assemble the finished video. Interrupted rendering can resume from saved frames.
>
> OpenAI Codex assisted with the concept, code, production automation, and documentation. The geometry and audio were generated specifically for this project; the typeface is Space Grotesk.
>
> SECOND NATURE. Make every second grow.

## Making-of edit plan

| Approximate time | Picture | Purpose |
| --- | --- | --- |
| 0–8s | Final flower and closing typography, then seed close-up | Establish creator, title, and visual promise |
| 8–24s | Dry seed → droplet chase → loop → suspended drop → bloom; use actual rendered excerpts | Explain the story before discussing tools |
| 24–30s | Hold the flower briefly, then show a Blender viewport of the full scene | Link the purpose of speed to the construction |
| 30–45s | Labelled illustrative code excerpt, then actual growth animation; full executable source is included separately | Explain the baked motion and staggered petal controls |
| 45–60s | Actual local studio screen captures, including its workbench and process log | Show the supporting production interface and evidence |
| 60–69s | AI, asset, tool and project-lead credit card | Make the process and assistance transparent |
| 69–75s | Final bloom and “MAKE EVERY SECOND GROW.” | Resolve on the film's emotional image |

The prepared edit uses real film excerpts and still captures of the Blender and studio interfaces; it does not claim to be a continuous screen recording. For a custom recut, capture actual UI and logs. Do not display invented timings, simulated cloud dashboards, or an untested “completed” job. Record a fresh variant only when its build and playback have been verified. Match edit points to the recorded voice; the timings above are an edit guide, not a required cadence.

## Film storyboard

| Film interval | Story beat | Motion and visual intent |
| --- | --- | --- |
| 0–2s | Dry seed, isolated | A close view establishes the reason for the journey |
| 2–6s | Drop launches through the gates | A following camera and repeated geometry make acceleration readable |
| 6–11s | Full vertical loop | The camera opens out so the route and moving amber drop remain legible |
| 11–15.25s | Final glide, suspension, fall | Motion slows, holds, and releases into the seed |
| 15.25–24s | Growth and resolve | Stem and leaves emerge; staggered petals open; the camera gives the flower and closing line space |

There is no literal countdown. The contrast between rapid travel and suspended stillness supplies the time pressure and release. Storyboard timings reflect the scripted 576-frame sequence; use the final render as the source of truth.

## Ready-made picture edit

`film/optional-making-of-no-voice.mp4` is a separate 75-second picture edit using the actual film, Blender WIP and studio evidence. Its source-code card is labelled as an illustrative excerpt; the complete executable implementation ships with the project. This longer edit is **not** the official 24-second contest animation.

Record the script above in a quiet room in about 75 seconds, then run:

```sh
.venv/bin/python source/add_voiceover.py --voice /absolute/path/to/your-recording.m4a
```

The helper accepts a 60-90-second recording, applies a modest pitch-preserving tempo adjustment to fit the picture, normalizes the voice, and creates `film/optional-making-of-narrated.mp4`. It preserves your original recording and the silent edit. Listen to the completed narration before sharing it.
