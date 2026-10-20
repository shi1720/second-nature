"""Production safety regressions. Run: python3 -m unittest discover -s tests -v.

All Blender/FFmpeg calls are replaced by a renderer that creates real PNGs in
temporary directories. These tests never touch the delivered film or invoke a
renderer, and need only Python's standard library.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib


BASE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("second_nature_pipeline", BASE / "pipeline.py")
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def png_bytes(width, height):
    """Build a decodable RGB PNG without relying on the code being tested."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    pixels = (b"\0" + b"\x24\x57\x61" * width) * height
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class PipelineSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="second-nature-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "source").mkdir()
        (self.root / "source/scene.py").write_text("# fixture scene\n")
        (self.root / "source/render.py").write_text("# fixture renderer\n")
        self.out = self.root / "film"
        self.out.mkdir()
        self.config_path = self.root / "project.json"
        self.config = dict(name="Test production", seed=1720,
                           hero_color="#FF763E", accent_color="#154D58",
                           output_dir=str(self.out))
        self.save_config()
        self.root_patch = patch.object(pipeline, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.emit_patch = patch.object(pipeline, "emit")
        self.events = self.emit_patch.start()
        self.addCleanup(self.emit_patch.stop)
        self.blend_revision = b"original"
        self.image = png_bytes(960, 540)

    def save_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def build(self):
        def fake_blender(command, log=None):
            (self.out / "second-nature.blend").write_bytes(
                b"BLENDER" + self.blend_revision + b"\0" * 12000)
        with patch.object(pipeline, "run", side_effect=fake_blender):
            pipeline.build(self.config, "unused-blender")

    def render_frames(self, start=1, end=3):
        def fake_renderer(command, log=None):
            job = json.loads(Path(command[-1]).read_text())
            for frame in job["frames"]:
                (Path(job["output_dir"]) / f"frame_{frame:04d}.png").write_bytes(self.image)
        with patch.object(pipeline, "run", side_effect=fake_renderer) as renderer:
            pipeline.render(self.config, "unused-blender", "preview", start, end)
        return renderer

    def assert_verify_and_assembly_reject(self, pattern):
        with patch.object(pipeline, "run") as subprocess_call:
            with self.assertRaisesRegex(RuntimeError, pattern):
                pipeline.assemble(self.config)
            code = pipeline.main(["verify", "--config", str(self.config_path)])
            self.assertEqual(code, 1)
            errors = [call.kwargs.get("message", "") for call in self.events.call_args_list
                      if call.args and call.args[0] == "error"]
            self.assertTrue(any(re.search(pattern, error) for error in errors), errors)
            subprocess_call.assert_not_called()

    def test_unchanged_frames_resume_without_launching_blender(self):
        self.build()
        self.render_frames()
        before = {p.name: p.read_bytes() for p in (self.out / "frames").glob("*.png")}
        renderer = self.render_frames()
        renderer.assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.out / "frames").glob("*.png")})

    def test_complete_current_sequence_verifies_and_can_reach_assembly(self):
        self.build()
        self.render_frames(end=576)
        self.assertEqual(pipeline.main(["verify", "--config", str(self.config_path)]), 0)
        with patch.object(pipeline.shutil, "which", return_value="unused-ffmpeg"), \
                patch.object(pipeline, "run") as assembler:
            pipeline.assemble(self.config)
        assembler.assert_called_once()
        self.assertEqual(assembler.call_args.args[0][-1], "unused-ffmpeg")

    def test_resume_rerenders_corrupt_frame_only(self):
        self.build()
        self.render_frames()
        first = self.out / "frames/frame_0001.png"
        first_stat = first.stat()
        (self.out / "frames/frame_0002.png").write_bytes(self.image[:-9])
        renderer = self.render_frames()
        renderer.assert_called_once()
        job = json.loads((self.out / "render-job.json").read_text())
        self.assertEqual(job["frames"], [2])
        self.assertEqual(first.stat().st_mtime_ns, first_stat.st_mtime_ns)
        self.assertEqual((self.out / "frames/frame_0002.png").read_bytes(), self.image)

    def test_rebuilt_configuration_cannot_verify_or_assemble_old_frames(self):
        self.build()
        self.render_frames()
        self.config["seed"] += 1
        self.save_config()
        self.build()
        self.assert_verify_and_assembly_reject("stale")

    def test_changed_renderer_cannot_verify_or_assemble_old_frames(self):
        self.build()
        self.render_frames()
        (self.root / "source/render.py").write_text("# revised rendering behavior\n")
        self.assert_verify_and_assembly_reject("stale")

    def test_rebuilt_blend_cannot_verify_or_assemble_old_frames(self):
        self.build()
        self.render_frames()
        self.blend_revision = b"revised asset"
        self.build()
        self.assert_verify_and_assembly_reject("stale")

    def test_modified_saved_blend_is_rejected_before_resume(self):
        self.build()
        self.render_frames()
        with (self.out / "second-nature.blend").open("ab") as stream:
            stream.write(b"manual modification")
        with patch.object(pipeline, "run") as renderer:
            with self.assertRaisesRegex(RuntimeError, "Saved Blender project changed"):
                pipeline.render(self.config, "unused-blender", "preview", 1, 3)
            renderer.assert_not_called()
        self.assert_verify_and_assembly_reject("Saved Blender project changed")

    def test_changed_scene_requires_rebuild(self):
        self.build()
        (self.root / "source/scene.py").write_text("# revised geometry\n")
        with self.assertRaisesRegex(RuntimeError, "Rebuild"):
            pipeline.assert_build(self.config)

    def test_png_integrity_accepts_real_image_and_rejects_damage(self):
        damaged_crc = bytearray(self.image)
        damaged_crc[-13] ^= 1  # CRC of the IDAT chunk, before the IEND chunk.
        cases = {
            "valid": (self.image, (960, 540), True),
            "wrong-size": (self.image, (1920, 1080), False),
            "truncated-header": (self.image[:20], (960, 540), False),
            "truncated-chunk": (self.image[:-18], (960, 540), False),
            "missing-IEND": (self.image[:-12], (960, 540), False),
            "bad-CRC": (bytes(damaged_crc), (960, 540), False),
            "not-PNG": (b"not an image", (960, 540), False),
        }
        for label, (content, size, expected) in cases.items():
            with self.subTest(label=label):
                path = self.root / f"{label}.png"
                path.write_bytes(content)
                self.assertEqual(pipeline.valid_png(path, size), expected)
        self.assertFalse(pipeline.valid_png(self.root / "absent.png", (960, 540)))

    def test_invalid_configuration_fails_cleanly_without_starting_process(self):
        invalid = [[], {"seed": True}, {"seed": -1}, {"seed": 2**31},
                   {"seed": "42"}, {"hero_color": "orange"},
                   {"accent_color": "#12345G"}, {"name": 123},
                   {"name": "x" * 101}, {"output_dir": None}, {"output_dir": []},
                   {"output_dir": "   "}]
        for payload in invalid:
            with self.subTest(payload=payload), patch.object(pipeline, "run") as process:
                self.config_path.write_text(json.dumps(payload))
                self.assertEqual(pipeline.main(["build", "--config", str(self.config_path)]), 1)
                process.assert_not_called()

    def test_invalid_frame_ranges_fail_before_process_start(self):
        for first, last in [(0, 3), (4, 3), (1, 577), (-1, 1)]:
            with self.subTest(first=first, last=last), patch.object(pipeline, "run") as process:
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        pipeline.main(["render", "--config", str(self.config_path),
                                       "--start", str(first), "--end", str(last)])
                self.assertEqual(error.exception.code, 2)
                process.assert_not_called()

    def test_active_project_lock_rejects_concurrent_operations(self):
        with pipeline.lock(self.out):
            with self.assertRaisesRegex(RuntimeError, "Another pipeline operation"):
                with pipeline.lock(self.out):
                    self.fail("Concurrent lock was admitted")
            self.assertTrue((self.out / ".pipeline.lock").is_file())
        self.assertFalse((self.out / ".pipeline.lock").exists())

    def test_lock_is_released_after_failed_operation(self):
        with self.assertRaisesRegex(RuntimeError, "job failed"):
            with pipeline.lock(self.out):
                raise RuntimeError("job failed")
        with pipeline.lock(self.out):
            self.assertTrue((self.out / ".pipeline.lock").is_file())

    def test_corrupted_lock_record_is_recovered(self):
        (self.out / ".pipeline.lock").write_text("not-a-pid")
        with pipeline.lock(self.out):
            self.assertEqual((self.out / ".pipeline.lock").read_text(), str(os.getpid()))


if __name__ == "__main__":
    unittest.main()
