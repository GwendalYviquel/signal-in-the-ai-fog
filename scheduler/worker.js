// Cloudflare Worker: starts the daily episode on time. Learning (2026-10-21/22): GitHub's own
// schedules dropped the morning's runs or started them hours late; Cloudflare's Cron Triggers fire
// on the minute. The worker only asks GitHub to start the workflow (workflow_dispatch), as the
// "Run workflow" button does; the workflow's own guards decide whether anything is published.
//
// Secrets and settings (wrangler.toml, `wrangler secret put GITHUB_TOKEN`):
// - GITHUB_TOKEN: a fine-grained token for this repository only, with "Actions: read and write";
// - REPOSITORY: owner/name;
// - TEST_CRON: optional, a cron that sends a test notification instead (end-to-end check).

const API = "https://api.github.com";
export const WINDOW = { from: "04:00", to: "07:00" }; // Paris time, weekdays

// Paris weekday and HH:MM of a timestamp (Cloudflare crons run in UTC, Paris changes offset).
export function parisClock(ms) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Paris", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(new Date(ms)).map((p) => [p.type, p.value]));
  return { weekday: parts.weekday, hhmm: `${parts.hour}:${parts.minute}` };
}

// The daily workflow is started on weekday mornings only; before 4:05 it does nothing by itself.
export function shouldStartEpisode(ms) {
  const { weekday, hhmm } = parisClock(ms);
  return !["Sat", "Sun"].includes(weekday) && hhmm >= WINDOW.from && hhmm < WINDOW.to;
}

export function request(cron, env) {
  const test = env.TEST_CRON && cron === env.TEST_CRON;
  const workflow = test ? "watchdog.yml" : "daily-episode.yml";
  const inputs = test
    ? { test_notification: "true" }
    : { dry_run: "false", as_scheduled: "true", scheduled: "true" };
  return {
    url: `${API}/repos/${env.REPOSITORY}/actions/workflows/${workflow}/dispatches`,
    init: {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "signal-in-the-ai-fog-scheduler",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    },
    test,
  };
}

export async function run(cron, ms, env, fetchImpl = fetch) {
  const { url, init, test } = request(cron, env);
  if (!test && !shouldStartEpisode(ms)) return "outside the morning window";
  const response = await fetchImpl(url, init);
  if (response.status !== 204) {
    throw new Error(`GitHub answered ${response.status}: ${(await response.text()).slice(0, 200)}`);
  }
  return test ? "test notification requested" : "daily episode started";
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(run(event.cron, event.scheduledTime, env).then((r) => console.log(`${event.cron}: ${r}`)));
  },
};
