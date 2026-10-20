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

## Final master delivery

The final 1080p master passed all nine independent media checks in `film/verification.json`: 24.000 seconds, 576 decoded frames at 24 fps, H.264/yuv420p, AAC stereo at 48 kHz, fast-start metadata and an error-free full decode. It is 14,484,028 bytes. The SHA-256 is recorded in `film/delivery.json`.

Measured encoded audio is -15.77 LUFS integrated and -2.24 dB true peak. A finished-render retry reported zero remaining frames and returned without starting Blender.

Before assembly, the cache guard detected that opening the project for the WIP capture had saved a different viewport-state copy. The original Blender backup matched the build manifest's SHA-256 exactly. That exact original was restored, preserving the matching source and all rendered frames; the guard was not bypassed. The separate viewport copy remains an intermediate, outside the delivery package.

## Hosted studio

The Firebase site is `https://second-nature-studio.web.app`. Its public page, configuration, security headers, Firebase guest sign-in and saved palette production have been checked in the browser. A real Cloud Run production is being exercised separately from the unit suites. The deployment receipt distinguishes infrastructure checks from completed render acceptance; do not treat an available API as a completed render.

The cloud suite contains 14 passing tests. The web state suite covers resumed frame counts, malformed progress, project validation, job labels, safe error messages and tightly scoped artifact addresses. The hosted account-switch review also led to epoch guards for pending requests and private playback cleanup. Unchanged production controls now remain mounted during polling.

### Cloud startup correction and recorded QA waiver

The first hosted production stopped before Blender launched: a local-tool fallback path indexed a nonexistent ancestor when the pipeline was installed at `/app`. The fallback now handles shallow container paths, and a regression test covers that layout. The worker image also checks the configured Blender executable, actual headless Blender startup and FFmpeg during its build.

The failed job and its original log remain intact. An explicit one-time operator adjustment restored its single unused render-start charge in the isolated QA fixture's global, account and network counters. The adjustment used a generation-match transaction and left the public limits at 3/2/2. The sanitized receipt is retained in the working QA evidence; this adjustment is not evidence of a successful cloud render.
