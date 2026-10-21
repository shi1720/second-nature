# Testing SECOND NATURE

[Public studio](https://second-nature-studio.web.app) · [Source](https://github.com/shi1720/second-nature)

## Current verification status

The original 1080p film is complete. Independent validation confirms 24 seconds, 576 decoded frames at 24 fps, H.264/yuv420p, AAC stereo at 48 kHz, fast-start metadata and a complete decode without errors. [Film verification JSON](../film/verification.json)

**The full cloud production acceptance has passed.** A live cancellation preserved 17 completed frames; the resumed execution reused those frames and began at frame 18. All 576 remote frames were present, including unchanged generations for the original 17. The assembled Blue hour film passed all nine delivery checks: 24 seconds, 960 x 540, 576 decoded frames at 24 fps, H.264/yuv420p, stereo AAC at 48 kHz, fast start and an error-free full decode. See the [accepted cloud report](../cloud/qa-report.json), [delivery manifest](../film/blue-hour-delivery.json) and [independent movie verification](../film/blue-hour-verification.json).

The authenticated browser played the film to its actual 24-second end with no media error. Its **Download MP4** button produced 5,992,881 bytes matching the accepted SHA-256. The private Blender download also matched cloud build/storage hashes and opened in Blender with autorun disabled. Evidence: [browser playback](../web/private-playback-qa.json), [movie download](../cloud/movie-download-qa.json), [scene download](../cloud/blender-download-qa.json) and [scene inspection](../cloud/scene-download-qa.json). The public study and guide are now deployed. A final browser sign-out check also passed: the guest warning appeared, old productions disappeared, the private movie source cleared and the unsaved draft reset. A new guest had no access to the old productions. See [sign-out evidence](../web/signout-qa.json).

## Quick browser test, without a render

1. Open the public studio. Play the featured original film immediately; it requires no account or render slot. The Blue hour palette study and the 80-second narrated guide are also available farther down the page.
2. Select **Try the studio** and continue as a guest. Create a production with a name, a palette and a soil detail seed.
3. Refresh the page and confirm the saved production remains in the guest workspace.
4. To retain access across devices, choose **Keep workspace** and create an email account with a password of at least 12 characters. The upgrade links the existing guest identity. Keep an unlinked guest signed in; clearing browser data or signing it out can lose access.
5. Review the workbench and available capacity. Saving a project does not start a render.

## Full production test

Use **one** production when capacity is available. Select **Create film** and confirm the workbench progresses from preparation/build to actual frame reports. Cloud previews contain the full 24-second story at 540p. Allow around 80 minutes on the current CPU worker, with variation by scene stage and load. Closing the tab does not cancel the cloud execution.

Return to the same workspace to inspect progress. After completion, play the variant and download its MP4 and Blender scene. Confirm that the chosen palette appears in the variant rather than assuming the featured original is the new result. Generated exports and frame caches have a seven-day lifecycle, so download anything to retain.

Cancellation and resume are useful recovery checks, but each resumed render consumes another daily render start. A test does not need repeated cancelled runs. The app allows one active job globally and three render/all starts globally, two per account and two per client network per UTC day. Resets occur at 00:00 UTC / 05:30 IST. Failed and cancelled starts count. These admission limits reduce operator cost; they are not a monetary billing cap. If capacity is unavailable, watch the existing film and inspect saved configuration instead of creating extra identities.

### Cloud acceptance and final publication gates

- [x] Hosted guest access and project save.
- [x] Actual worker build/render progress, cancellation and execution stop.
- [x] Saved checkpoint integrity and resume from the next unfinished frame.
- [x] All 576 cloud frames present and verified.
- [x] Cloud assembly produces the user's 24-second 540p movie.
- [x] Downloaded movie hash matches its delivery manifest and independent decode passes.
- [x] Authenticated hosted variant playback and MP4/Blender downloads work.
- [x] Separate live REST checks reject unauthenticated and cross-account private requests.
- [x] Final browser sign-out clears the private movie source, old production view and unsaved draft; a new guest sees no old productions. Live REST tests separately establish private endpoint ownership rejection.
- [x] The 80-second narrated product demo passes all eight final media checks and a complete 1,920-frame decode.
- [x] All three curated movies are uploaded with matching remote MD5/size and published through the allowlisted showcase route.
- [x] Thirteen live HTTP checks verify HEAD, valid 206 ranges, invalid 416 ranges, allowlist rejection and private 401 rejection.
- [x] Public original, Blue hour and guide reach their actual 24-second, 24-second and 80-second ends without media errors. Original playback is also confirmed while signed out.
- [x] Eight burned-caption samples and encoded demo audio are reviewed; no silence of at least 1.2 seconds is detected at -40 dB.
- [x] Final page has no horizontal overflow at 320, 390, 768, 1280 and 1920 pixels.

Cloud and app publication acceptance are complete. External publication and submission are also recorded: [public original](https://www.youtube.com/watch?v=folQG-XiqTY), [public guide](https://www.youtube.com/watch?v=EePedJF-2lA), [official Discord entry](https://discord.com/channels/1547269486057627728/1562304128657522852) and [submitted Devpost mirror](https://devpost.com/software/second-nature-jrqu9v). Both YouTube initial checks reported No issues found, with six and 28 published English caption cues. The RenderJuice account and private registration are confirmed in the [submission receipt](../submission/receipt.json). These receipts establish submitted/public status, not organizer acceptance or an award. HTTP Range support is verified. A separate native scrubber check on the app's studio guide used Home then Right and reached 0.8 seconds without error; it is not a seeking test of every player.

The [public YouTube playback check](../submission/youtube-playback-qa.json) played both watch pages to their actual ends at 1920 x 1080 after selecting 1080p, without seeking to the end. The original and guide reported 24.021 and 80.021 seconds respectively, `ended: true` and no media error. These are YouTube transcoded durations; the source masters remain exactly 24 and 80 seconds. Published English captions and the English menu option were observed. This records one tested browser/network, not every device.

## Automated tests

Run from the repository root. Python tests currently total **48**: 15 pipeline, 4 delivery-packaging, 8 local-studio and 21 cloud tests. Hosted state tests contain **44 assertions**; nine mocked account-flow scenarios contain **32 behavior checks**; the local progress parser contains **14 assertions**.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s studio/tests -v
node web/tests/state.test.mjs
node web/tests/account-flow.test.mjs
node studio/tests/test_progress.cjs
```

Cloud API/worker tests need their additional SDK dependencies:

```sh
python3 -m venv cloud/.venv
cloud/.venv/bin/python -m pip install -r cloud/requirements.txt httpx
cloud/.venv/bin/python -m unittest discover -s cloud/tests -v
```

Use a current supported Python, preferably 3.12. Node.js is needed for the JavaScript assertions, not for viewing the deployed studio.

Pipeline tests mock Blender and FFmpeg while checking real PNG fixtures, stale cache rejection, selective resume and locks. Local-studio tests use temporary storage, HTTP requests and isolated fake subprocesses, including shutdown handling. Cloud tests inject storage and execution clients and check quotas, compare-and-swap races, ownership, artifact URLs, checkpoint identity, subprocess progress, the three-object public allowlist, bounded media ranges and staged showcase URLs/checksums. They do not consume cloud render slots and do not replace the live acceptance gate. The account-flow suite executes the actual app handlers in a small fake DOM, checking guest-preserving credential linking, explicit confirmation before switching to an existing account, stale-account guards, draft/private-media reset on identity changes, and confirmed film regeneration after artifact expiry. The quota tests include network capacity; rendering remains disabled until quota is known.

Separate live REST checks passed with disposable accounts: [13 email/password and ownership checks](../cloud/auth-qa-report.json) and [7 anonymous-to-email upgrade checks](../cloud/guest-upgrade-qa-report.json). Upgrade linking preserved the Firebase UID through email sign-in. Both fixtures were deleted, no render jobs were created, and credentials were never stored. With email enumeration protection, the supported linking endpoint is `accounts:signUp` with the existing ID token; the legacy `accounts:update` route returns `OPERATION_NOT_ALLOWED`. The pinned Firebase SDK uses the supported route.

The deployed public media offload serves only the operator's curated `original.mp4`, `blue-hour.mp4` and `studio-demo.mp4` from a private bucket through an allowlisted API route. User exports retain owner authentication and no-store responses. The published Hosting release updates media URLs and CSP and omits the large local MP4 copies. Evidence: [verified curated uploads](../cloud/showcase-upload.json), [13 live media/security HTTP checks](../cloud/showcase-http-qa.json), [final responsive check](../web/final-responsive-qa.json), [demo delivery checks](../film/studio-demo.verification.json) and [demo audio/caption samples](../film/studio-demo-audio-qa.json). [Public browser playback](../web/showcase-playback-qa.json) records all three actual endings, signed-out original playback and observed mutual pause between players.

To independently inspect the shipped film, install FFmpeg/FFprobe and run:

```sh
.venv/bin/python source/verify_delivery.py film/second-nature.mp4
```

`pipeline.py verify --config project.json` additionally requires the retained local frame sequence. A source-only checkout without frame PNGs can validate the movie but cannot certify a missing frame cache.
