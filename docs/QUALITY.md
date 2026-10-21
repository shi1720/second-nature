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
| Pipeline regression suite | 15 passing tests covering stale cache rejection, modified scene files, PNG CRC/truncation, invalid settings/ranges, lock recovery, and selective resume. Blender/FFmpeg are mocked in these unit tests. |
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

The public studio is hosted on Firebase with guest and email authentication, password recovery, private project storage and bounded Cloud Run Blender workers. It supports one directed film system with palette and soil-seed variants. It does not provide arbitrary text-to-video, billing or unrestricted cloud rendering. Rendering costs are operator funded; application admission limits are not a hard billing cap. No RenderJuice API call or sponsor endorsement is claimed. Motion is scripted, not a physical simulation. Different GPU backends may produce minor pixel differences.

The 80-second narrated studio demonstration is separate from the 24-second animation. It uses a disclosed stock synthetic voice, captions and actual product screens. The contest film requires no spoken voice. Cloud delivery and the final demonstration have passed their separate checks. The guide is exactly 80 seconds, 1,920 frames and 1080p, with all eight media checks and a full decode passing. Its encoded audio measures -16.44 LUFS and -4.5 dB true peak, with no silence of at least 1.2 seconds at -40 dB. Eight burned-caption samples were inspected; their timings derive from the approved synthesis model, not independent forced alignment. The guide is now public in the app, separate from the original film.

## Final master delivery

The final 1080p master passed all nine independent media checks in `film/verification.json`: 24.000 seconds, 576 decoded frames at 24 fps, H.264/yuv420p, AAC stereo at 48 kHz, fast-start metadata and an error-free full decode. It is 14,484,028 bytes. The SHA-256 is recorded in `film/delivery.json`.

Measured encoded audio is -15.77 LUFS integrated and -2.24 dB true peak. A finished-render retry reported zero remaining frames and returned without starting Blender.

Before assembly, the cache guard detected that opening the project for the WIP capture had saved a different viewport-state copy. The original Blender backup matched the build manifest's SHA-256 exactly. That exact original was restored, preserving the matching source and all rendered frames; the guard was not bypassed. The separate viewport copy remains an intermediate, outside the delivery package.

## Hosted studio

The Firebase site is `https://second-nature-studio.web.app`. Its public page, configuration, security headers, Firebase guest sign-in and saved palette production have been checked in the browser. The real Cloud Run production is now accepted separately from the unit suites. All 576 remote frames were verified and the resulting 24-second 540p film passed all nine independent media checks. The deployment receipt remains infrastructure evidence; the accepted render evidence is in `cloud/qa-report.json`.

The cloud suite contains 21 passing tests. The web state suite covers resumed frame counts, malformed progress, project validation, job labels, safe error messages and tightly scoped artifact addresses. The hosted account-switch review also led to epoch guards for pending requests and private playback cleanup. Unchanged production controls now remain mounted during polling. Nine mocked account-flow scenarios (32 behavior checks) exercise guest preservation, explicit workspace-switch confirmation, stale identity guards and confirmed film regeneration. The state suite has 44 assertions, including unknown and exhausted network capacity. Separate live REST suites passed 13 account/isolation checks and 7 guest-upgrade checks; disposable accounts were deleted and no jobs were started by these checks.

### Cloud startup correction and recorded QA waiver

The first hosted production stopped before Blender launched: a local-tool fallback path indexed a nonexistent ancestor when the pipeline was installed at `/app`. The fallback now handles shallow container paths, and a regression test covers that layout. The worker image also checks the configured Blender executable, actual headless Blender startup and FFmpeg during its build.

The failed job and its original log remain intact. An explicit one-time operator adjustment restored its single unused render-start charge in the isolated QA fixture's global, account and network counters. The adjustment used a generation-match transaction and left the public limits at 3/2/2. The sanitized receipt is retained in the working QA evidence; this adjustment is not evidence of a successful cloud render.

### Live browser and account checks

The hosted frontend passed horizontal-overflow checks at 390, 768, 1280 and 1920 pixels. The heading remains correctly spaced at every breakpoint. A saved guest workspace survived reload, and an additional palette production was saved without dispatching a worker. Content fingerprints now connect HTML, JavaScript modules and styles so an older cached release cannot hide updated controls.

Thirteen live REST checks verified Firebase email/password signup and sign-in, authenticated identity, empty new workspaces, cross-owner project and artifact rejection, token rejection and restricted CORS. The disposable account was deleted. See `cloud/auth-qa-report.json`; these checks created no render jobs.

A real browser download produced the private Blender scene. The complete cloud production is accepted in `cloud/qa-report.json`. Its first 17 restored frames retained their original checksums and generations, all 576 frames were present, and the execution finished successfully and released its global reservation. No pre-rendered local frames were injected into the cloud production. The authenticated browser played the accepted 960 x 540 film to its actual 24-second end with no media error (`web/private-playback-qa.json`). The real Download MP4 button produced 5,992,881 bytes with SHA-256 `5cd337506434399910c4f03e49d0daa196a08f076fc8cd0fb03c9fa13dfac5d9`, matching the delivery manifest (`cloud/movie-download-qa.json`).

Live REST tests have established private ownership rejection. The final real-browser sign-out check also passed: the guest warning appeared, the old production view and private movie source cleared, and the unsaved draft reset. A new guest saw no old productions. This browser evidence is recorded separately from REST access-control tests in `web/signout-qa.json`.

### Delivery utility checks

Four packaging tests verify credential and database exclusion, symlink/cache rejection, changed archive content even when ZIP CRCs are valid, and refusal to package unfinished media. The resulting Python total is 48: 15 pipeline, 4 packaging, 8 local-studio and 21 cloud tests. The package manifest records every shipped file's size and SHA-256; the finished ZIP is read back and checked before replacing an earlier archive.

The optional voice-replacement helper was exercised with an 80-second picture fixture and the approved narration. It produced an 80-second stereo export and rejected the 24-second film without writing an output. The source-only dossier rebuilt successfully without the frame cache, and all four PDF pages were rendered and checked visually.

The authenticated browser's downloaded cloud scene also opened successfully in real Blender with Python autorun disabled. It contains 595 objects, five camera cuts, 110 baked actions and a packed font. Material inspection recovered the configured #5AB8FF drop and #203C5A enamel exactly. This check does not render another frame or modify the downloaded scene. Evidence: `cloud/scene-download-qa.json`.

## Deployed public showcase offload

A separate deployed public API route serves exactly three operator-curated films: the original, the accepted Blue hour study and the studio demonstration. It accepts no user ID, project ID, bucket or arbitrary object path. Private user production routes retain owner authentication and no-store responses. The storage bucket stays private, and its seven-day deletion rule applies to `users/`, not the curated `showcase/` prefix.

The published Hosting release uses direct HTTPS API movie URLs, includes the media origin in CSP, and omits large MP4 copies from Firebase Hosting. All three curated uploads passed remote size/MD5 verification (`cloud/showcase-upload.json`). Thirteen live HTTP checks passed for HEAD, valid and invalid ranges, unknown names, traversal and private-route authentication (`cloud/showcase-http-qa.json`). Six focused automated showcase tests are included in the 21 cloud and 48 total Python tests.

The public original, Blue hour and guide reached their actual 24-second, 24-second and 80-second ends with no media errors. Original playback while signed out and mutual pause between players were also observed (`web/showcase-playback-qa.json`). The final layout has no horizontal overflow at 320, 390, 768, 1280 or 1920 pixels (`web/final-responsive-qa.json`). The public study and guide are complete. External publication and contest submission are now recorded separately below.

The separate [internal rubric review](JUDGING-REVIEW.md) records strengths, risks and presentation advice. Its subjective score is not an official contest result.

## Publication and submission receipts

Recorded on 21 October 2026: the [original film](https://www.youtube.com/watch?v=folQG-XiqTY) and [studio guide](https://www.youtube.com/watch?v=EePedJF-2lA) are public on YouTube, with initial checks reporting No issues found and published English SRT tracks of six and 28 cues. The RenderJuice account and private contest registration are confirmed. The [official Discord post](https://discord.com/channels/1547269486057627728/1562304128657522852) is visible with Official Entry, Procedural & Code and Motion Design tags, plus the poster and authentic Blender WIP. The [Devpost project](https://devpost.com/software/second-nature-jrqu9v) reports Project submitted!, uses the original film as its primary video and contains nine gallery images, the guide and testing links.

The [machine-readable receipt](../submission/receipt.json) links screenshot evidence. This confirms publication and submission, not organizer acceptance, eligibility adjudication or an award. Authorship and AI assistance remain disclosed; no outcome is promised.

The [public YouTube playback check](../submission/youtube-playback-qa.json) played both watch pages to their actual ends at 1920 x 1080 after selecting 1080p, without seeking to the end. The original and guide reported 24.021 and 80.021 seconds respectively, `ended: true` and no media error. These are YouTube transcoded durations; the source masters remain exactly 24 and 80 seconds. Published English captions and the English menu option were observed. This records one tested browser/network, not every device.
