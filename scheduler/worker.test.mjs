// Tests of the Cloudflare scheduler (node --test scheduler/worker.test.mjs). Run by tests/test_scheduler.py.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import worker, { parisClock, request, run, shouldStartEpisode } from "./worker.js";

const ENV = { GITHUB_TOKEN: "t0ken", REPOSITORY: "owner/repo", TEST_CRON: "47 9 22 10 *" };
const toml = readFileSync(new URL("./wrangler.toml", import.meta.url), "utf8");
const CRONS = JSON.parse(toml.match(/^crons = (\[.*\])$/m)[1]);

const expand = (field) => field.split(",").flatMap((part) => {
  const [a, b] = part.split("-").map(Number);
  return b === undefined ? [a] : Array.from({ length: b - a + 1 }, (_, i) => a + i);
});

// Every firing of the crons on a UTC date (they all say weekdays 1-5).
function firings(date) {
  const day = date.getUTCDay();
  if (day === 0 || day === 6) return [];
  return CRONS.flatMap((cron) => {
    const [m, h] = cron.split(" ");
    return expand(h).flatMap((hh) => expand(m).map((mm) =>
      Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), hh, mm)));
  }).sort((x, y) => x - y);
}

test("Paris clock follows daylight saving time", () => {
  assert.deepEqual(parisClock(Date.UTC(2026, 6, 15, 2, 5)), { weekday: "Wed", hhmm: "04:05" });
  assert.deepEqual(parisClock(Date.UTC(2027, 0, 13, 3, 5)), { weekday: "Wed", hhmm: "04:05" });
  assert.deepEqual(parisClock(Date.UTC(2026, 9, 26, 3, 5)), { weekday: "Mon", hhmm: "04:05" }); // day after the change
});

test("every weekday of 2026 and 2027 starts the episode at 4:05 Paris, then retries", () => {
  for (let d = new Date(Date.UTC(2026, 0, 1)); d < new Date(Date.UTC(2028, 0, 1)); d.setUTCDate(d.getUTCDate() + 1)) {
    const starts = firings(d).filter(shouldStartEpisode).map((ms) => parisClock(ms).hhmm);
    const weekday = ![0, 6].includes(d.getUTCDay());
    if (!weekday) { assert.deepEqual(starts, [], d.toISOString()); continue; }
    assert.equal(starts[0], "04:05", d.toISOString());
    assert.ok(starts.length >= 3 && starts.every((t) => t < "07:00"), `${d.toISOString()} ${starts}`);
  }
});

test("the request starts the daily workflow as a scheduled attempt", () => {
  const { url, init, test: isTest } = request("5,35 2,3 * * 1-5", ENV);
  assert.equal(url, "https://api.github.com/repos/owner/repo/actions/workflows/daily-episode.yml/dispatches");
  assert.equal(init.method, "POST");
  assert.equal(init.headers.Authorization, "Bearer t0ken");
  assert.deepEqual(JSON.parse(init.body), { ref: "main", inputs: { dry_run: "false", as_scheduled: "true", scheduled: "true" } });
  assert.equal(isTest, false);
});

test("the test cron only asks for a test notification, at any time", async () => {
  const calls = [];
  const fake = async (url, init) => { calls.push([url, JSON.parse(init.body)]); return { status: 204 }; };
  assert.equal(await run(ENV.TEST_CRON, Date.UTC(2026, 9, 22, 9, 47), ENV, fake), "test notification requested");
  assert.deepEqual(calls, [["https://api.github.com/repos/owner/repo/actions/workflows/watchdog.yml/dispatches",
                            { ref: "main", inputs: { test_notification: "true" } }]]);
});

test("outside the morning window nothing is sent", async () => {
  const fake = async () => assert.fail("GitHub called");
  assert.equal(await run("5,35 2,3 * * 1-5", Date.UTC(2027, 0, 13, 2, 35), ENV, fake), "outside the morning window"); // 3:35 Paris
  assert.equal(await run("5 4 * * 1-5", Date.UTC(2026, 9, 24, 4, 5), ENV, fake), "outside the morning window"); // Saturday
});

test("a refusal from GitHub is an error, so Cloudflare logs it", async () => {
  const fake = async () => ({ status: 403, text: async () => "Resource not accessible by personal access token" });
  await assert.rejects(run("5 4 * * 1-5", Date.UTC(2026, 9, 22, 2, 5), ENV, fake), /GitHub answered 403/);
});

test("the worker has no public endpoint", () => {
  assert.equal(worker.fetch, undefined);
  assert.match(toml, /^workers_dev = false/m);
});
