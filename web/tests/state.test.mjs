import assert from "node:assert/strict";
import {
  progressView,
  validProject,
  jobLabel,
  safeMessage,
  artifactURL,
} from "../dist/state.mjs";
assert.equal(
  progressView({ progress: { completed: 288, total: 576 } }).percent,
  50,
);
for (const progress of [
  { completed: -1, total: 576 },
  { completed: 600, total: 576 },
  { completed: 1, total: 0 },
  { completed: "bad", total: 576 },
  {},
])
  assert.equal(progressView({ progress }).determinate, false);
assert.equal(
  progressView({ progress: { completed: 0, total: 576 } }).percent,
  0,
);
assert.equal(
  progressView({ progress: { completed: 576, total: 576 } }).percent,
  100,
);
assert.equal(
  progressView({ progress: { completed: 5, total: 566 } }).complete,
  15,
);
assert.equal(
  progressView({ progress: { completed: 5, total: 566 } }).total,
  576,
);
assert.equal(
  progressView({ progress: { completed: 2.5, total: 576 } }).determinate,
  false,
);
assert.equal(
  progressView({ progress: { completed: 1, total: 999 } }).determinate,
  false,
);
assert.equal(jobLabel({ status: "complete", action: "build" }), "Scene ready");
assert.equal(
  jobLabel({ status: "running", stage: "render" }),
  "Rendering the motion",
);
const good = {
  name: "Blue hour",
  seed: 42,
  hero_color: "#5AB8FF",
  accent_color: "#203C5A",
};
assert.ok(validProject(good));
for (const change of [
  { name: " " },
  { seed: -1 },
  { seed: 1.5 },
  { seed: 1000000 },
  { hero_color: "red" },
  { accent_color: "#12" },
])
  assert.equal(validProject({ ...good, ...change }), false);
assert.equal(jobLabel({ status: "failed" }), "Needs attention");
assert.equal(jobLabel({ status: "complete" }), "Film ready");
assert.equal(
  safeMessage({ code: "auth/invalid-credential" }),
  "The email or password did not match. Please try again.",
);
const pid = "a".repeat(32),
  path = `/v1/projects/${pid}/artifacts/movie/content`;
assert.equal(
  artifactURL("/api", path, "https://studio.example", pid, "movie"),
  "https://studio.example/api" + path,
);
assert.equal(
  artifactURL("/api", "/api" + path, "https://studio.example", pid, "movie"),
  "https://studio.example/api" + path,
);
assert.equal(
  artifactURL(
    "https://worker.example",
    path,
    "https://studio.example",
    pid,
    "movie",
  ),
  "https://worker.example" + path,
);
for (const bad of [
  "https://evil.example" + path,
  "//evil.example" + path,
  path + "?token=secret",
  path + "#fragment",
  path.replace(pid, "b".repeat(32)),
  path.replace("/movie/", "/blend/"),
])
  assert.throws(
    () => artifactURL("/api", bad, "https://studio.example", pid, "movie"),
    /invalid export/,
  );
console.log("Hosted state and artifact address tests passed.");
