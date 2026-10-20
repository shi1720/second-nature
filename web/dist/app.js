import {
  ACTIVE,
  progressView,
  jobLabel,
  validProject,
  safeMessage,
  artifactURL,
  renderAvailability,
} from "./state.mjs";
const $ = (id) => document.getElementById(id),
  config = window.SECOND_NATURE_CONFIG || {},
  apiBase = (config.apiBaseUrl || "/api").replace(/\/$/, "");
const state = {
  auth: null,
  sdk: null,
  user: null,
  projects: [],
  jobs: new Map(),
  selectedJob: null,
  quota: null,
  register: false,
  poll: null,
  refreshing: false,
  authReady: false,
  pendingNew: false,
  pendingGuestExit: null,
  pendingRenderAgain: null,
  blobUrl: null,
  fetchEpoch: 0,
};
let toastTimer;
let projectListKey = null;
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 6500);
}
function el(tag, attrs = {}, text) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else n.setAttribute(k, v);
  }
  if (text !== undefined) n.textContent = text;
  return n;
}
function busy(button, value) {
  button.disabled = value;
  button.setAttribute("aria-busy", String(value));
}
function openDialog(id) {
  const dialog = $(id);
  if (!dialog.open) dialog.showModal();
}
function closeDialog(id) {
  $(id).close();
  if (id === "guest-exit-dialog") state.pendingGuestExit = null;
  if (id === "render-again-dialog") state.pendingRenderAgain = null;
  if (id === "player-dialog") {
    const player = $("variant-player");
    player.pause();
    player.removeAttribute("src");
    player.load();
    if (state.blobUrl) {
      URL.revokeObjectURL(state.blobUrl);
      state.blobUrl = null;
    }
  }
}
function requireReady() {
  if (!state.authReady)
    throw new Error(
      "The workspace connection is not ready. Please try again in a moment.",
    );
}
async function api(path, options = {}) {
  if (!state.user)
    throw new Error("Sign in or continue as a guest to use your workspace.");
  const user = state.user,
    epoch = state.fetchEpoch;
  const current = () =>
    state.fetchEpoch === epoch && state.user?.uid === user.uid;
  const token = await user.getIdToken();
  if (!current())
    throw new Error("The workspace changed. Please try that step again.");
  const response = await fetch(apiBase + path, {
    ...options,
    headers: {
      Authorization: "Bearer " + token,
      "Content-Type": "application/json",
      ...options.headers,
    },
    signal: options.signal || AbortSignal.timeout(25000),
  });
  let data = null;
  if (response.status !== 204) {
    try {
      data = await response.json();
    } catch {
      if (response.ok)
        throw new Error(
          "The studio returned an unreadable response. Please try again.",
        );
    }
  }
  if (!current())
    throw new Error("The workspace changed. Please try that step again.");
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : detail?.message ||
          data?.error ||
          data?.message ||
          "The studio could not complete that step. Please try again.",
    );
  }
  return data;
}
async function guest() {
  requireReady();
  if (state.user) return state.user;
  const result = await state.sdk.signInAnonymously(state.auth);
  state.user = result.user;
  updateAccount();
  return result.user;
}
function openNew() {
  if (!state.user) {
    state.pendingNew = true;
    openDialog("auth-dialog");
    return;
  }
  state.pendingNew = false;
  $("project-error").textContent = "";
  openDialog("project-dialog");
}
function offerGuestExit(kind) {
  if (!state.user?.isAnonymous) return;
  state.pendingGuestExit = { kind, uid: state.user.uid };
  const switching = kind === "signin";
  $("guest-exit-title").textContent = switching
    ? "Switch workspaces?"
    : "Before you leave.";
  $("guest-exit-note").textContent = switching
    ? "Signing in opens a different workspace and removes access to your guest productions. To keep this guest work, create an account with an email that does not already have a workspace."
    : "Guest work is linked to this browser session. Signing out removes your access. Create an account to keep your productions across devices.";
  $("guest-keep").textContent = switching
    ? "Keep this guest workspace"
    : "Keep my workspace";
  $("guest-leave").textContent = switching
    ? "Switch to the existing workspace"
    : "Sign out without keeping access";
  openDialog("guest-exit-dialog");
}
function authMode(register) {
  state.register = register;
  $("auth-title").textContent = register
    ? "Your space to create."
    : "Welcome back.";
  $("auth-note").textContent = register
    ? state.user?.isAnonymous
      ? "Keep this guest workspace and access it across devices."
      : "Start a workspace for your next perspective."
    : "Save your work and pick up where you left off.";
  $("auth-submit").textContent = register ? "Create workspace" : "Sign in";
  $("auth-switch").textContent = register
    ? "Already have a workspace? Sign in"
    : "New here? Create a workspace";
  $("password").autocomplete = register ? "new-password" : "current-password";
  $("password-reset").hidden = register;
  $("auth-error").textContent = "";
}
function updateAccount() {
  const user = state.user;
  $("auth-open").hidden = !!user && !user.isAnonymous;
  $("auth-open").textContent = user?.isAnonymous
    ? "Keep workspace ↗"
    : "Sign in ↗";
  $("signout").hidden = !user;
  $("account-label").hidden = !user;
  $("account-label").textContent = user
    ? user.isAnonymous
      ? "Guest workspace"
      : user.email || "Your workspace"
    : "";
}
function latestFor(project) {
  return state.jobs.get(project.id)?.[0] || null;
}
function showJob(job) {
  state.selectedJob = job || null;
  const p = progressView(job);
  $("job-summary").textContent = job
    ? `${job.project_name || state.projects.find((x) => x.id === job.project_id)?.name || "Production"} / ${jobLabel(job)}`
    : "Ready when you are.";
  $("job-progress").hidden = !job;
  if (p.determinate) $("job-progress").value = p.complete;
  else $("job-progress").removeAttribute("value");
  $("job-progress").max = p.total;
  $("job-progress-label").textContent = job
    ? job.error ||
      (job.status === "complete" || job.status === "completed"
        ? "Your film is ready to watch and download."
        : p.determinate
          ? `${p.complete} of ${p.total} frames / ${p.percent}%`
          : "Building the scene, preparing the worker, or assembling your export.")
    : "Your actual build, render and export progress will appear here.";
  $("job-log").textContent = job
    ? Array.isArray(job.log)
      ? job.log.join("\n")
      : job.log || "The worker is preparing your production."
    : "Create a production to begin.";
  $("cancel-job").hidden =
    !job || !ACTIVE.has(job.status) || job.status === "cancelling";
}
function action(label, handler, kind = "secondary", disabled = false) {
  const button = el(
    "button",
    { class: "button " + kind, type: "button" },
    label,
  );
  button.disabled = disabled;
  button.addEventListener("click", async () => {
    busy(button, true);
    try {
      await handler();
    } catch (error) {
      toast(safeMessage(error));
    } finally {
      busy(button, false);
    }
  });
  return button;
}
function renderProjects() {
  const activeJob = [...state.jobs.values()]
    .flat()
    .find((j) => ACTIVE.has(j.status));
  const availability = renderAvailability(state.quota, Boolean(activeJob));
  $("capacity-note").hidden = !state.user;
  $("capacity-note").textContent = availability.message;
  // Polling updates frame counts frequently. Keep unchanged production controls
  // mounted so keyboard focus and pointer clicks survive those updates.
  const nextKey = JSON.stringify({
    uid: state.user?.uid,
    availability,
    projects: state.projects.map((p) => [
      p.id,
      p.name,
      p.seed,
      p.hero_color,
      p.accent_color,
      p.artifacts,
    ]),
    jobs: [...state.jobs.entries()].map(([id, jobs]) => [
      id,
      jobs.map((j) => [j.id, j.status, j.stage, j.action]),
    ]),
  });
  if (nextKey === projectListKey) return;
  projectListKey = nextKey;
  const list = $("project-list");
  list.replaceChildren();
  $("project-count").textContent = state.user
    ? `${state.projects.length} production${state.projects.length === 1 ? "" : "s"}`
    : "Your own color of motion";
  if (!state.projects.length) {
    const box = el("div", { class: "empty" });
    box.append(
      el("span", { class: "empty-symbol", "aria-hidden": "true" }, "◈"),
      el(
        "h3",
        {},
        state.user
          ? "A new perspective starts here."
          : "Your next film starts here.",
      ),
      el("p", {}, "Choose a palette. Plant a seed. Make the story your own."),
    );
    box.append(
      action(
        state.user ? "Create a production" : "Try the studio",
        async () => {
          await guest();
          openNew();
        },
      ),
    );
    if (!state.user)
      box.append(
        el(
          "p",
          { class: "fine" },
          "No account needed to explore. Guest work stays linked to this browser.",
        ),
      );
    list.append(box);
    return;
  }
  for (const project of state.projects) {
    const row = el("article", { class: "project-row" }),
      swatch = el("span", { class: "project-swatch", "aria-hidden": "true" });
    swatch.style.background = project.accent_color;
    const drop = el("i");
    drop.style.background = project.hero_color;
    swatch.append(drop);
    const details = el("div"),
      name = el("div", { class: "project-name" }, project.name),
      job = latestFor(project);
    if (job)
      name.append(
        el("span", { class: "project-status " + job.status }, jobLabel(job)),
      );
    details.append(
      name,
      el(
        "div",
        { class: "project-meta" },
        `SEED ${project.seed} / FULL STORY / 540p`,
      ),
    );
    const actions = el("div", { class: "project-actions" });
    const artifacts = project.artifacts || {};
    if (artifacts.movie)
      actions.append(action("Play film", () => play(project), "primary"));
    const resume =
      job && ["failed", "cancelled", "interrupted"].includes(job.status);
    if (!artifacts.movie)
      actions.append(
        action(
          resume ? "Resume production" : "Create film",
          () => startJob(project, resume ? job : null),
          "primary",
          !availability.canRender,
        ),
      );
    if (job) {
      const detailButton = el(
        "button",
        { class: "text-button", type: "button" },
        "View progress",
      );
      detailButton.addEventListener("click", () => {
        showJob(job);
        $("workbench").scrollIntoView({ behavior: "smooth" });
      });
      actions.append(detailButton);
    }
    if (artifacts.movie)
      actions.append(action("Download MP4", () => download(project, "movie")));
    if (artifacts.movie)
      actions.append(
        action(
          "Create film again",
          () => offerRenderAgain(project),
          "secondary",
          !availability.canRender,
        ),
      );
    if (artifacts.blend)
      actions.append(
        action("Blender scene ↓", () => download(project, "blend")),
      );
    row.append(swatch, details, actions);
    list.append(row);
  }
}
async function refresh() {
  const epoch = state.fetchEpoch;
  if (!state.user || state.refreshing === epoch) return;
  state.refreshing = epoch;
  const userId = state.user.uid;
  try {
    const [data, account] = await Promise.all([
      api("/v1/projects"),
      api("/v1/me"),
    ]);
    const projects = data.projects || [];
    const results = await Promise.allSettled(
      projects.map((p) => api("/v1/projects/" + encodeURIComponent(p.id))),
    );
    if (epoch !== state.fetchEpoch || state.user?.uid !== userId) return;
    state.projects = projects;
    state.quota = account.quota || null;
    results.forEach((r, i) => {
      if (r.status === "fulfilled") {
        state.jobs.set(
          projects[i].id,
          (r.value.jobs || []).sort((a, b) =>
            String(b.created_at).localeCompare(String(a.created_at)),
          ),
        );
        if (r.value.project) state.projects[i] = r.value.project;
      }
    });
    renderProjects();
    const all = [...state.jobs.values()]
      .flat()
      .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    const selected =
      all.find((j) => j.id === state.selectedJob?.id) ||
      all.find((j) => ACTIVE.has(j.status)) ||
      all[0];
    showJob(selected);
    $("connection").textContent = "Studio connected";
  } catch (error) {
    if (epoch === state.fetchEpoch) {
      $("connection").textContent = "Reconnecting";
      if (!state.projects.length) {
        projectListKey = null;
        const box = el("div", { class: "error-state" }, safeMessage(error));
        box.append(action("Try again", () => refresh()));
        $("project-list").replaceChildren(box);
      }
    }
  } finally {
    if (state.refreshing === epoch) state.refreshing = false;
  }
}
async function startJob(project, resumeJob) {
  const job = await api(
    resumeJob
      ? `/v1/jobs/${encodeURIComponent(resumeJob.id)}/resume`
      : `/v1/projects/${encodeURIComponent(project.id)}/jobs`,
    {
      method: "POST",
      body: JSON.stringify({ action: "all", profile: "preview" }),
    },
  );
  showJob(job);
  toast(
    resumeJob
      ? "Resuming from saved production files."
      : "Your production is starting. You can leave this page and return later.",
  );
  $("workbench").scrollIntoView({ behavior: "smooth" });
  await refresh();
}
function offerRenderAgain(project) {
  if (!state.user) throw new Error("Sign in to use this production.");
  state.pendingRenderAgain = {
    projectId: project.id,
    uid: state.user.uid,
    epoch: state.fetchEpoch,
  };
  $("render-again-name").textContent = project.name;
  $("render-again-error").textContent = "";
  openDialog("render-again-dialog");
}
async function artifactBlob(project, kind) {
  const user = state.user,
    epoch = state.fetchEpoch;
  if (!user) throw new Error("Sign in to download this production.");
  const current = () =>
    state.fetchEpoch === epoch && state.user?.uid === user.uid;
  const data = await api(
    `/v1/projects/${encodeURIComponent(project.id)}/artifacts/${kind}`,
  );
  const url = artifactURL(apiBase, data.url, location.origin, project.id, kind);
  const token = await user.getIdToken();
  if (!current())
    throw new Error("The workspace changed. Please try that step again.");
  const response = await fetch(url, {
    headers: { Authorization: "Bearer " + token },
    signal: AbortSignal.timeout(180000),
  });
  if (!current())
    throw new Error("The workspace changed. Please try that step again.");
  if (!response.ok)
    throw new Error("The export could not be downloaded. Please try again.");
  const blob = await response.blob();
  if (!current())
    throw new Error("The workspace changed. Please try that step again.");
  return {
    blob,
    filename:
      data.filename ||
      `second-nature.${kind === "movie" ? "mp4" : kind === "blend" ? "blend" : "json"}`,
  };
}
async function play(project) {
  toast("Opening your rendered film.");
  const result = await artifactBlob(project, "movie");
  if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
  state.blobUrl = URL.createObjectURL(result.blob);
  $("variant-player").src = state.blobUrl;
  $("player-title").textContent = project.name;
  $("player-note").textContent = "24 seconds / 540p / Rendered in Blender";
  openDialog("player-dialog");
  try {
    await $("variant-player").play();
  } catch {}
}
async function download(project, kind) {
  toast("Preparing your download.");
  const result = await artifactBlob(project, kind),
    url = URL.createObjectURL(result.blob),
    link = el("a", { href: url, download: result.filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  toast("Your download is ready.");
}
document
  .querySelectorAll("[data-close]")
  .forEach((button) =>
    button.addEventListener("click", () => closeDialog(button.dataset.close)),
  );
$("player-dialog").addEventListener("cancel", () => {
  const v = $("variant-player");
  v.pause();
  if (state.blobUrl) {
    URL.revokeObjectURL(state.blobUrl);
    state.blobUrl = null;
  }
});
$("guest-exit-dialog").addEventListener("cancel", () => {
  state.pendingGuestExit = null;
});
$("render-again-dialog").addEventListener("cancel", () => {
  state.pendingRenderAgain = null;
});
$("render-again-confirm").addEventListener("click", async () => {
  const pending = state.pendingRenderAgain;
  const button = $("render-again-confirm");
  busy(button, true);
  $("render-again-error").textContent = "";
  try {
    if (
      !pending ||
      pending.uid !== state.user?.uid ||
      pending.epoch !== state.fetchEpoch
    )
      throw new Error("The workspace changed. Open this production again.");
    const project = state.projects.find((item) => item.id === pending.projectId);
    if (!project) throw new Error("This production is no longer available.");
    const active = [...state.jobs.values()].flat().some((job) => ACTIVE.has(job.status));
    const availability = renderAvailability(state.quota, active);
    if (!availability.canRender) throw new Error(availability.message);
    await startJob(project, null);
    closeDialog("render-again-dialog");
  } catch (error) {
    $("render-again-error").textContent = safeMessage(error);
  } finally {
    busy(button, false);
  }
});
$("auth-open").addEventListener("click", () => {
  authMode(!!state.user?.isAnonymous);
  openDialog("auth-dialog");
});
$("auth-switch").addEventListener("click", () => authMode(!state.register));
$("new-project").addEventListener("click", openNew);
$("credits-open").addEventListener("click", () => openDialog("credits-dialog"));
$("watch-film").addEventListener("click", async () => {
  const film = $("featured-film");
  film.scrollIntoView({ behavior: "smooth", block: "center" });
  try {
    await film.play();
  } catch {
    toast("Press Play on the film to begin.");
  }
});
const filmPlayers = ["featured-film", "palette-study", "variant-player"].map($);
for (const player of filmPlayers)
  player.addEventListener("play", () => {
    for (const other of filmPlayers)
      if (other !== player) other.pause();
  });
for (const id of ["guest-start", "guest-auth"])
  $(id).addEventListener("click", async () => {
    const b = $(id);
    busy(b, true);
    try {
      await guest();
      closeDialog("auth-dialog");
      openNew();
    } catch (error) {
      toast(safeMessage(error));
    } finally {
      busy(b, false);
    }
  });
async function signOut() {
  try {
    await state.sdk.signOut(state.auth);
    closeDialog("guest-exit-dialog");
    toast("You have signed out.");
  } catch (error) {
    toast(safeMessage(error));
  }
}
$("signout").addEventListener("click", () => {
  if (state.user?.isAnonymous) offerGuestExit("signout");
  else signOut();
});
$("guest-leave").addEventListener("click", async () => {
  const pending = state.pendingGuestExit;
  if (!pending || pending.uid !== state.user?.uid || !state.user.isAnonymous) {
    closeDialog("guest-exit-dialog");
    return;
  }
  if (pending.kind === "signin") {
    closeDialog("guest-exit-dialog");
    await submitAuth({ confirmedGuestUid: pending.uid });
  } else await signOut();
});
$("guest-keep").addEventListener("click", () => {
  const switching = state.pendingGuestExit?.kind === "signin";
  closeDialog("guest-exit-dialog");
  authMode(true);
  if (switching)
    $("auth-note").textContent = "Keep this guest work with an email that does not already have a workspace.";
  openDialog("auth-dialog");
});
$("password-reset").addEventListener("click", async () => {
  const button = $("password-reset");
  busy(button, true);
  try {
    requireReady();
    if (!$("email").checkValidity())
      throw new Error("Enter your workspace email above first.");
    await state.sdk.sendPasswordResetEmail(
      state.auth,
      $("email").value.trim(),
      { url: location.origin },
    );
    toast("If this workspace exists, a password recovery email is on its way.");
  } catch (error) {
    $("auth-error").textContent = safeMessage(error);
  } finally {
    busy(button, false);
  }
});
async function submitAuth({ confirmedGuestUid = null } = {}) {
  const button = $("auth-submit");
  $("auth-error").textContent = "";
  try {
    requireReady();
    if (
      confirmedGuestUid &&
      (state.user?.uid !== confirmedGuestUid || !state.user.isAnonymous || state.register)
    )
      throw new Error("The workspace changed. Please try that step again.");
    if (!state.register && state.user?.isAnonymous && !confirmedGuestUid) {
      offerGuestExit("signin");
      return;
    }
    busy(button, true);
    const email = $("email").value.trim(),
      password = $("password").value;
    const previousUid = state.user?.uid;
    let credential;
    if (state.register) {
      if (state.user?.isAnonymous) {
        credential = await state.sdk.linkWithCredential(
          state.user,
          state.sdk.EmailAuthProvider.credential(email, password),
        );
      } else
        credential = await state.sdk.createUserWithEmailAndPassword(
          state.auth,
          email,
          password,
        );
    } else
      credential = await state.sdk.signInWithEmailAndPassword(
        state.auth,
        email,
        password,
      );
    if (previousUid !== credential.user.uid) resetProductionDraft();
    state.user = credential.user;
    updateAccount();
    $("password").value = "";
    closeDialog("auth-dialog");
    toast(state.register ? "Your workspace is ready." : "Welcome back.");
    if (state.pendingNew) {
      state.pendingNew = false;
      openNew();
    }
  } catch (error) {
    $("auth-error").textContent = safeMessage(error);
  } finally {
    busy(button, false);
  }
}
$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitAuth();
});
$("project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("project-submit");
  busy(button, true);
  $("project-error").textContent = "";
  try {
    const value = {
      name: $("project-name").value.trim(),
      seed: Number($("seed").value),
      hero_color: $("hero-color").value.toUpperCase(),
      accent_color: $("accent-color").value.toUpperCase(),
      profile: "preview",
    };
    if (!validProject(value))
      throw new Error(
        "Choose a name, valid colors, and a whole seed from 0 to 999999.",
      );
    await api("/v1/projects", { method: "POST", body: JSON.stringify(value) });
    closeDialog("project-dialog");
    $("project-name").value = "";
    toast("Production saved. Select Create film to begin.");
    await refresh();
    $("productions").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    $("project-error").textContent = safeMessage(error);
  } finally {
    busy(button, false);
  }
});
function resetProductionDraft() {
  $("project-name").value = "";
  $("seed").value = "42";
  $("hero-color").value = "#FF763E";
  $("accent-color").value = "#154D58";
  $("project-error").textContent = "";
  colorLabels();
  document.querySelectorAll("[data-palette]").forEach((button) => {
    const selected = button.dataset.palette === "#FF763E,#154D58";
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}
function colorLabels() {
  $("hero-hex").textContent = $("hero-color").value.toUpperCase();
  $("accent-hex").textContent = $("accent-color").value.toUpperCase();
}
document.querySelectorAll("[data-palette]").forEach((button) =>
  button.addEventListener("click", () => {
    const [hero, accent] = button.dataset.palette.split(",");
    $("hero-color").value = hero;
    $("accent-color").value = accent;
    colorLabels();
    document.querySelectorAll("[data-palette]").forEach((b) => {
      b.classList.toggle("selected", b === button);
      b.setAttribute("aria-pressed", String(b === button));
    });
  }),
);
for (const id of ["hero-color", "accent-color"])
  $(id).addEventListener("input", () => {
    colorLabels();
    document.querySelectorAll("[data-palette]").forEach((b) => {
      b.classList.remove("selected");
      b.setAttribute("aria-pressed", "false");
    });
  });
$("shuffle-seed").addEventListener("click", () => {
  $("seed").value = crypto.getRandomValues(new Uint32Array(1))[0] % 1000000;
});
$("cancel-job").addEventListener("click", async () => {
  const b = $("cancel-job");
  if (!state.selectedJob) return;
  busy(b, true);
  try {
    await api(`/v1/jobs/${encodeURIComponent(state.selectedJob.id)}/cancel`, {
      method: "POST",
      body: "{}",
    });
    toast("Stopping the worker. Saved frames can be resumed.");
    await refresh();
  } catch (error) {
    toast(safeMessage(error));
  } finally {
    busy(b, false);
  }
});
document.querySelectorAll(".nav-link").forEach((link) =>
  link.addEventListener("click", () => {
    document
      .querySelectorAll(".nav-link")
      .forEach((n) => n.classList.toggle("active", n === link));
  }),
);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
async function init() {
  try {
    if (!config.firebaseConfig)
      throw new Error(
        "The studio is being connected. The original film is available to watch now.",
      );
    const [app, sdk] = await Promise.all([
      import("https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js"),
      import("https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js"),
    ]);
    state.sdk = sdk;
    state.auth = sdk.getAuth(app.initializeApp(config.firebaseConfig));
    await sdk.setPersistence(state.auth, sdk.browserLocalPersistence);
    state.authReady = true;
    sdk.onAuthStateChanged(state.auth, async (user) => {
      const epoch = ++state.fetchEpoch;
      state.user = user;
      if (!user) resetProductionDraft();
      state.projects = [];
      state.quota = null;
      state.jobs.clear();
      state.selectedJob = null;
      closeDialog("player-dialog");
      closeDialog("guest-exit-dialog");
      closeDialog("render-again-dialog");
      updateAccount();
      renderProjects();
      showJob(null);
      clearInterval(state.poll);
      if (user) {
        await refresh();
        if (epoch !== state.fetchEpoch) return;
        state.poll = setInterval(() => {
          if (!document.hidden) refresh();
        }, 7000);
      } else $("connection").textContent = "Studio ready";
    });
  } catch (error) {
    $("connection").textContent = "Film available";
    $("job-progress-label").textContent = safeMessage(error);
  }
}
init();
