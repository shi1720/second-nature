# SECOND NATURE / Production studio

A local creator workstation for **SECOND NATURE**, a 24-second procedural Blender film by Shivam Gupta. Choose a seed and palette, generate a scene, render its motion, and assemble a playable film with visible process logs. No cloud keys, package installation, or paid service is required by the studio.

## Start

From the `second-nature` folder:

```sh
python3 studio/server.py
```

Open **http://127.0.0.1:8765**. Create a local account with an email-shaped identifier and a password of at least 12 characters. The email is never sent anywhere. There is no default password or password recovery. Use a unique local password.

Python 3.10 or later is required. Blender and FFmpeg requirements are documented in the parent project README. The studio runs the parent `pipeline.py` using the same Python interpreter as the server.

1. Select **New production** and choose its name, seed, colors, and Preview or Final profile.
2. Select **01 Build** to generate the Blender scene.
3. Select **02 Render** to render frames. Rendering requires a successful scene build.
4. Select **03 Assemble** to encode the frame sequence. The pipeline validates frame completeness.
5. Select **Play** to review the MP4 or **↓ .blend** to download the scene.

Both profiles cover the full 24 seconds / 576 frames. Preview uses 960×540; Final uses 1920×1080. Final is more expensive to render on local hardware. The server does not invent a percentage or completion time: the log comes from the subprocess, and the activity bar uses `FRAME_DONE` events from the renderer as completed frames / (completed + remaining frames). Malformed or partial reports are ignored; output without valid counts stays indeterminate.

The featured film loads from `../film/second-nature.mp4` when that file exists. Look-development images load from `../stills/`. The decorative orbital artwork shown before assets exist is clearly marked **Awaiting render** and is not represented as a Blender result.

## Pipeline integration

Each production gets a new `../projects/<uuid>/` directory with a persisted `config.json`:

```json
{
  "name": "Second Nature — My cut",
  "seed": 42,
  "hero_color": "#ed785b",
  "accent_color": "#3d9893",
  "profile": "preview",
  "output_dir": "/absolute/path/to/second-nature/projects/<uuid>"
}
```

The studio starts only these fixed commands (arguments never pass through a shell):

```sh
python3 pipeline.py build --config /path/to/config.json
python3 pipeline.py render --config /path/to/config.json --profile preview
python3 pipeline.py assemble --config /path/to/config.json
```

Expected outputs are `second-nature.blend`, `frames/*.png`, and `second-nature.mp4` in the configured output directory. User input cannot override the output path. Creating another production is the supported way to change configuration; existing configurations remain reproducible.

One job can run at a time across all local accounts. Cancel terminates the job's process group, then forces shutdown if necessary after five seconds. Closing the browser leaves the server and its job running. Stopping the server with Ctrl+C, SIGTERM, or SIGHUP (including a terminal hangup on supported systems) stops job admission, cancels owned jobs, and gives worker cleanup an eight-second window before forcing remaining owned processes to stop. Unresolved jobs are recorded as interrupted. An uncatchable termination such as SIGKILL cannot run cleanup. Restarting the server marks previously unfinished jobs **interrupted**; it does not claim they completed or automatically resume them. Build/render/assemble can then be rerun as appropriate. The production pipeline owns render resumability and frame validation.

## Security and operating limits

This is a **local workstation tool**, not an internet SaaS or a hardened multi-tenant service. It deliberately binds only to `127.0.0.1`. Do not expose it with a tunnel, reverse proxy, public bind address, or shared-host deployment. Run one server instance per studio data directory. It has no email verification, password reset, MFA, billing, remote workers, or account administration.

Passwords are salted and hashed with PBKDF2-HMAC-SHA256 (310,000 iterations). Sessions have random tokens, are stored as token hashes, expire after 12 hours, and use HttpOnly / SameSite=Strict cookies. State-changing requests require a session-bound CSRF token. Host and Origin checks reject cross-site requests and DNS rebinding hosts. HTTP cookies are intentionally not Secure because the service is loopback HTTP only. Login attempts are limited locally. Project/job access is checked by account; media access uses a path allowlist and resolved-path containment. Video byte ranges support seeking. Browser output uses text nodes rather than rendering production names or process output as HTML.

Authentication state and logs are in `studio/.data/studio.sqlite3`; this directory is ignored by Git. Files remain on the local filesystem and can be accessed by the computer's owner. Back up both `.data/` and `../projects/` to preserve accounts and production history. To completely reset this local studio, stop the server and move `.data/` somewhere safe; this removes local accounts/history from the next run, while project files remain on disk.

## Test

```sh
python3 -m unittest discover -s studio/tests -v
```

Tests use an isolated temporary directory and a fake pipeline; they do not launch Blender or touch real productions. They cover authentication, CSRF, project isolation, output-path injection, traversal, range playback, job prerequisites, job concurrency, cancellation, persisted interruption status, and real server CLI shutdown for SIGINT/SIGTERM/SIGHUP. Shutdown tests launch only isolated fake pipelines and verify process cleanup and persisted terminal status, including forced termination of a process that ignores SIGTERM.

The browser progress parser also has a small optional Node.js test (no packages required):

```sh
node studio/tests/test_progress.cjs
```

It checks resumed batches, malformed/partial JSON, invalid counts, legacy frame logs, and completion. Node.js is needed only for this parser test; running the studio itself requires only Python.
