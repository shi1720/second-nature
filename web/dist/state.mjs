export const ACTIVE = new Set(["queued", "running", "cancelling", "starting"]);
export function renderAvailability(quota, ownActive) {
  if (ownActive)
    return {
      canRender: false,
      message:
        "Your production continues in the cloud. You can leave this page and return.",
    };
  if (!quota)
    return {
      canRender: false,
      message: "Checking the shared render capacity.",
    };
  if (quota?.user_render_remaining === 0)
    return {
      canRender: false,
      message:
        "Your daily render allowance is used. It resets at 00:00 UTC. You can still plan productions and download finished work.",
    };
  if (quota?.global_render_remaining === 0)
    return {
      canRender: false,
      message:
        "Today's shared render capacity is used. It resets at 00:00 UTC. Your projects and finished films remain available.",
    };
  if (quota?.network_render_remaining === 0)
    return {
      canRender: false,
      message:
        "This network's daily render allowance is used. It resets at 00:00 UTC. You can still plan productions and download finished work.",
    };
  if (quota?.global_job_active)
    return {
      canRender: false,
      message:
        "Another production is using the shared worker. You can prepare your palette now and return to render when it is free.",
    };
  return {
    canRender: true,
    message: quota
      ? `${quota.global_render_remaining} shared render start${quota.global_render_remaining === 1 ? "" : "s"} available today. A full render can take over an hour.`
      : "Checking the shared render capacity.",
  };
}
export function artifactURL(base, path, origin, projectId, kind) {
  const expected = `/v1/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(kind)}/content`;
  if (typeof path !== "string" || ![expected, "/api" + expected].includes(path))
    throw new Error("The studio returned an invalid export address.");
  return new URL(base.replace(/\/$/, "") + expected, origin).href;
}
export function progressView(job) {
  const progress = job?.progress || {};
  const complete = Number(progress.completed),
    total = Number(progress.total);
  const determinate =
    Number.isFinite(complete) &&
    Number.isFinite(total) &&
    total > 0 &&
    total <= 576 &&
    Number.isInteger(complete) &&
    Number.isInteger(total) &&
    complete >= 0 &&
    complete <= total;
  // The renderer counts this pass. A smaller pass contains only unfinished
  // frames after the saved frame cache has been validated. Include that cache
  // in the full story's progress rather than restarting the bar at zero.
  const completedStory = determinate ? 576 - total + complete : 0;
  return {
    determinate,
    complete: completedStory,
    total: 576,
    percent: determinate ? Math.round((completedStory / 576) * 100) : null,
  };
}
export function jobLabel(job) {
  if (!job) return "Ready to create";
  if (job.status === "complete" && job.action === "build") return "Scene ready";
  if (job.status === "complete" && job.action === "render")
    return "Frames ready";
  if (job.status === "running") {
    const stages = {
      restoring: "Loading saved production",
      build: "Building the world",
      render: "Rendering the motion",
      assemble: "Finishing your film",
      verifying: "Checking the export",
    };
    if (stages[job.stage]) return stages[job.stage];
  }
  const names = {
    queued: "Waiting for a worker",
    starting: "Starting the studio",
    running: "Creating your film",
    cancelling: "Stopping safely",
    cancelled: "Cancelled",
    interrupted: "Ready to resume",
    failed: "Needs attention",
    complete: "Film ready",
    completed: "Film ready",
  };
  return names[job.status] || "Production in progress";
}
export function validProject(value) {
  return (
    typeof value.name === "string" &&
    value.name.trim().length >= 1 &&
    value.name.trim().length <= 80 &&
    Number.isInteger(value.seed) &&
    value.seed >= 0 &&
    value.seed <= 999999 &&
    /^#[0-9a-f]{6}$/i.test(value.hero_color) &&
    /^#[0-9a-f]{6}$/i.test(value.accent_color)
  );
}
export function safeMessage(error) {
  const code = error?.code || "";
  const messages = {
    "auth/invalid-credential":
      "The email or password did not match. Please try again.",
    "auth/email-already-in-use":
      "This email already has a workspace. Sign in instead.",
    "auth/invalid-email": "Enter a valid email address.",
    "auth/weak-password": "Choose a password with at least 12 characters.",
    "auth/too-many-requests":
      "Too many attempts. Please wait a little and try again.",
    "auth/network-request-failed":
      "The connection was interrupted. Please try again.",
    "auth/operation-not-allowed":
      "This sign-in method is temporarily unavailable. Please try another method.",
  };
  return (
    messages[code] ||
    error?.message ||
    "Something interrupted that step. Please try again."
  );
}
