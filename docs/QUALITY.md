# Production and verification record

SECOND NATURE · Shivam Gupta · 24 seconds · 24 fps · 576 frames.

## What was exercised

| Check | Evidence |
| --- | --- |
| Actual Blender build | Blender 4.5.9 LTS generated 595 scene objects, baked animation, packed typography, and a saved editable project. |
| Native delivery rendering | Cycles on the local Apple M4 Pro Metal device; final profile is 1920 × 1080 with 48 samples and denoising. |
| Real interruption and resume | The active render was terminated with SIGTERM. Its Blender child stopped, the pipeline exited with code 130, and the project lock cleared. SHA-256 checks confirmed all 76 frames recorded before interruption were unchanged. The resumed job found 77 complete frames and began at frame 78. |
| Real studio integration | A request through the authenticated HTTP API built a separate blue-palette project in 8.8 seconds. Seed 42, hero #5AB8FF and accent #203C5A matched the build manifest; the saved Blender hash also matched. |
| User isolation | The build owner could download the scene (HTTP 200). A second local account could not download it or start its jobs (HTTP 404) and could not see its project/history. |
| Pipeline regression suite | 14 passing tests covering stale cache rejection, modified scene files, PNG CRC/truncation, invalid settings/ranges, lock recovery, and selective resume. Blender/FFmpeg are mocked in these unit tests. |
| Studio regression suite | 8 passing HTTP integration tests covering authentication, CSRF, ownership, media paths/ranges, job prerequisites, concurrency, cancellation, and restart state. |
| Real progress parsing | 14 JavaScript assertions exercise the pipeline's actual FRAME_DONE message format and malformed input handling. |
| Motion preview | The full-length look preview was played in Chrome and sampled at the opening, chase, suspension and closing card. Camera boundary frames and growth stages were inspected separately. |
| Delivery validation | source/verify_delivery.py independently counts and decodes the final movie, checks duration, codec, pixel format, stereo audio, frame rate, dimensions and fast-start metadata. The machine-readable final results are in film/verification.json. |

The delivered movie's dimensions, duration, size and SHA-256 are recorded in `film/delivery.json`. The full frame-sequence check is separate from movie decoding: `pipeline.py verify` validates build/cache identity and all 576 PNGs.

## Review and iteration against the rubric

The independent review assessed still frames and source, rather than inventing a complete animation score from images. It identified six concrete issues before the final render:

1. The drop could leave the frame at the top of the loop. The wide camera was reframed with more headroom.
2. A shared camera could interpolate a teleport during the shutter at a cut. Five independent shot cameras now hold their own boundary poses.
3. Decorative ribs extended outside the tapered drop. They were removed.
4. The drop snapped from a stretched travel pose to upright suspension. A 24-frame quaternion and scale blend now eases braking.
5. The flower's bright heart lost detail. Garden lighting and pollen emission were reduced; petal materials and the flower heart were adjusted.
6. Cache verification did not cover every source change. Verification and assembly now share identity checks covering settings, scene source, renderer source, saved Blender file and quality profile.

| Published criterion | Creative response and evidence |
| --- | --- |
| Idea / 30 | The seed appears before the race, so the journey has a visible purpose. The ending converts speed into growth. |
| Animation / 25 | Acceleration, two loop passes, eased braking, suspended stillness, gravity-shaped release and staggered petal whorls provide distinct timing. |
| Visuals / 25 | Teal enamel, champagne rails and an amber hero carry through one shared set. Physical area lights, depth of field and restrained typography provide consistency. |
| Use of Speed / 20 | Repeated gates and a following camera communicate travel; the wide loop makes the route visible; the quiet pause gives acceleration contrast. |

These are internal review observations, not official contest scores or audience-test results.

## Practical scope

The studio is a local creator workstation application. It is not deployed as an internet service and does not include billing, account recovery or cloud workers. Rendering is local; no RenderJuice API call or sponsor endorsement is claimed. The source uses scripted geometric motion, not a physical simulation. Different GPU backends may produce minor pixel differences even with the same production settings.

The optional 75-second making-of picture edit is separate from the 24-second official animation. The supplied narration may be recorded by Shivam; the contest film requires no spoken voice.
