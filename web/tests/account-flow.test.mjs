import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import * as logic from "../dist/state.mjs";

// Exercise the actual app handlers with a small DOM and SDK boundary. No
// browser session, Firebase request, cloud job, or real credential is involved.
const html = readFileSync(new URL("../dist/index.html", import.meta.url), "utf8");
const source = readFileSync(new URL("../dist/app.js", import.meta.url), "utf8")
  .replace(/^import[\s\S]*?from "\.\/state\.mjs";\n/, "")
  .replace(/\ninit\(\);\s*$/, "\n");

class Element {
  constructor() {
    this.listeners = new Map();
    this.value = "";
    this.open = false;
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  async emit(name) { await this.listeners.get(name)?.({ preventDefault() {} }); }
  setAttribute(name, value) { this[name] = value; }
  removeAttribute(name) { delete this[name]; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  scrollIntoView() {}
  checkValidity() { return true; }
  pause() {}
  load() {}
}

function harness() {
  const nodes = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => [m[1], new Element()]));
  const node = (id) => {
    assert.ok(nodes.has(id), `The actual HTML must contain #${id}`);
    return nodes.get(id);
  };
  const calls = { signIn: 0, link: 0, create: 0, signOut: 0, requests: [] };
  const project = { id: "a".repeat(32), name: "Saved film", seed: 42, hero_color: "#FF763E", accent_color: "#154D58", artifacts: { movie: { updated_at: "2020-01-01T00:00:00Z" } } };
  const quota = { global_render_remaining: 1, user_render_remaining: 1, network_render_remaining: 1, global_job_active: false };
  const job = { id: "b".repeat(32), project_id: project.id, status: "queued", action: "all", created_at: "2026-01-01T00:00:00Z" };
  const existing = { uid: "existing-user", isAnonymous: false, email: "fixture@example.invalid", getIdToken: async () => "fixture-token" };
  const context = vm.createContext({
    ...logic,
    window: { SECOND_NATURE_CONFIG: { apiBaseUrl: "https://api.example.invalid" } },
    document: { getElementById: node, querySelectorAll: () => [], addEventListener() {}, createElement: () => new Element() },
    location: { origin: "https://studio.example.invalid" },
    URL, AbortSignal, console,
    setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {},
    fetch: async (url, options = {}) => {
      calls.requests.push({ url, method: options.method || "GET" });
      let data = url.endsWith("/v1/me") ? { quota } : url.endsWith("/v1/projects") ? { projects: [project] } : { project, jobs: [job] };
      if (options.method === "POST") data = job;
      return { ok: true, status: options.method === "POST" ? 202 : 200, json: async () => data };
    },
  });
  vm.runInContext(source, context);
  context.fixture = { project, quota };
  context.sdkFixture = {
    signInWithEmailAndPassword: async () => { calls.signIn++; return { user: existing }; },
    createUserWithEmailAndPassword: async () => { calls.create++; return { user: existing }; },
    EmailAuthProvider: { credential: (email, password) => ({ email, password }) },
    linkWithCredential: async (user) => { calls.link++; return { user: { ...user, isAnonymous: false } }; },
    signOut: async () => { calls.signOut++; },
  };
  vm.runInContext(`state.user = {uid: "guest-user", isAnonymous: true, getIdToken: async () => "fixture-token"}; state.sdk = sdkFixture; state.auth = {}; state.authReady = true; state.projects = [fixture.project]; state.quota = fixture.quota; state.register = false;`, context);
  node("email").value = "fixture@example.invalid";
  node("password").value = "Fixture-password-123";
  node("auth-dialog").showModal();
  return { context, node, calls, run: (code) => vm.runInContext(code, context) };
}

{
  const h = harness();
  h.run("state.pendingNew = true");
  await h.node("auth-form").emit("submit");
  assert.equal(h.calls.signIn, 0);
  assert.equal(h.run("state.user.uid"), "guest-user");
  assert.equal(h.node("guest-exit-dialog").open, true);
  await h.node("guest-keep").emit("click");
  assert.equal(h.run("state.register"), true);
  assert.equal(h.node("email").value, "fixture@example.invalid");
  assert.equal(h.node("password").value, "Fixture-password-123");
  assert.equal(h.run("state.pendingNew"), true);
  await h.node("auth-form").emit("submit");
  assert.equal(h.calls.link, 1);
  assert.equal(h.calls.signIn, 0);
  assert.equal(h.run("state.user.uid"), "guest-user");
  assert.equal(h.node("project-dialog").open, true);
}
{
  const h = harness();
  h.node("project-name").value = "Private unsaved idea";
  h.node("hero-color").value = "#abcdef";
  await h.node("auth-form").emit("submit");
  await h.node("guest-leave").emit("click");
  assert.equal(h.node("project-name").value, "");
  assert.equal(h.node("hero-color").value, "#FF763E");
  assert.equal(h.node("accent-color").value, "#154D58");
  assert.equal(h.node("seed").value, "42");
  assert.equal(h.calls.signIn, 1);
  assert.equal(h.calls.signOut, 0);
  assert.equal(h.run("state.user.uid"), "existing-user");
}
{
  const h = harness();
  await h.node("auth-form").emit("submit");
  await h.node("guest-exit-dialog").emit("cancel");
  await h.node("guest-leave").emit("click");
  assert.equal(h.calls.signIn, 0);
  assert.equal(h.run("state.user.uid"), "guest-user");
}
{
  const h = harness();
  await h.node("auth-form").emit("submit");
  h.run('state.user = {uid: "another-user", isAnonymous: false}');
  await h.node("guest-leave").emit("click");
  assert.equal(h.calls.signIn, 0);
}
{
  const h = harness();
  h.run("offerRenderAgain(fixture.project)");
  assert.equal(h.node("render-again-dialog").open, true);
  assert.equal(h.calls.requests.length, 0);
  h.run('closeDialog("render-again-dialog")');
  await h.node("render-again-confirm").emit("click");
  assert.equal(h.calls.requests.length, 0);
}
{
  const h = harness();
  h.run("offerRenderAgain(fixture.project)");
  await h.node("render-again-confirm").emit("click");
  assert.equal(h.calls.requests.filter((r) => r.method === "POST").length, 1);
  assert.ok(h.calls.requests.find((r) => r.method === "POST").url.endsWith("/v1/projects/" + "a".repeat(32) + "/jobs"));
  assert.equal(h.node("render-again-dialog").open, false);
}
{
  const h = harness();
  h.run("offerRenderAgain(fixture.project); state.fetchEpoch++");
  await h.node("render-again-confirm").emit("click");
  assert.equal(h.calls.requests.length, 0);
}
{
  const h = harness();
  h.run("offerRenderAgain(fixture.project); state.quota.network_render_remaining = 0");
  await h.node("render-again-confirm").emit("click");
  assert.equal(h.calls.requests.length, 0);
  assert.match(h.node("render-again-error").textContent, /network/);
}
{
  const h = harness();
  h.run("state.pendingNew = true; openNew()");
  assert.equal(h.run("state.pendingNew"), false);
  assert.equal(h.node("project-dialog").open, true);
}
console.log("9 mocked account-preservation and explicit regeneration flows passed.");
