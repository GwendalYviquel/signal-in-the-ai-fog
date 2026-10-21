"""Cost tracking: Claude usage and ElevenLabs characters for every run, in data/costs.json and COSTS.md."""
import datetime as dt
import json

import pytest

from conftest import TUESDAY, make_episode, reply, submit_block, usage
from podcast import costs, generate, main, tts

from test_main import mocks, repo  # noqa: F401  (temporary repository fixtures)


def test_usage_is_summed_over_every_call_including_corrections(cfg, fake_claude):
    # Research (paused once), then a light correction: three billed calls.
    bad = make_episode(headlines=["one, two", "b c", "d e"])
    fake_claude([reply(stop_reason="pause_turn", usage=usage(10_000, 500, searches=6)),
                 reply(submit_block(bad, "t1"), usage=usage(30_000, 3_000, cache_read=5_000, searches=4)),
                 reply(submit_block(make_episode(), "t2"), usage=usage(4_000, 2_500))])
    total = costs.empty_claude_usage("claude-sonnet-5-5")
    ep = generate.generate_episode(cfg, TUESDAY, [], usage=total)
    assert ep["usage"] is total
    assert total == {"model": "claude-sonnet-5-5", "input_tokens": 44_000, "output_tokens": 6_000,
                     "cache_creation_input_tokens": 0, "cache_read_input_tokens": 5_000,
                     "web_search_requests": 10, "api_calls": 3}


def test_usage_is_kept_when_generation_gives_up(cfg, fake_claude):
    # Claude is paid even when the episode is rejected: the spend must not be lost.
    bad = make_episode(question="What should we do " + "x " * 20)
    fake_claude([reply(submit_block(bad, f"t{i}"), usage=usage(20_000, 2_000)) for i in range(3)])
    total = costs.empty_claude_usage("m")
    with pytest.raises(SystemExit):
        generate.generate_episode(cfg, TUESDAY, [], usage=total)
    assert total["api_calls"] == 3 and total["input_tokens"] == 60_000


def test_response_without_usage_still_counts_the_call():
    total = costs.empty_claude_usage("m")
    costs.add_usage(total, reply())
    assert total["api_calls"] == 1 and total["input_tokens"] == 0


def test_claude_cost_estimate(cfg):
    u = dict(costs.empty_claude_usage("m"), input_tokens=1_000_000, output_tokens=100_000,
             cache_creation_input_tokens=200_000, cache_read_input_tokens=1_000_000, web_search_requests=15)
    # 2.00 + 1.00 + 0.50 + 0.20 + 0.15
    assert costs.claude_usd(u, cfg["costs"]) == pytest.approx(3.85)


def test_prices_belong_to_the_model_in_use(cfg):
    # Changing generation.model without reviewing the prices would make every estimate wrong.
    assert cfg["costs"]["priced_model"] == cfg["generation"]["model"]


def test_record_writes_the_ledger_the_report_and_the_step_summary(cfg, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/podcast")
    ledger, report = tmp_path / "costs.json", tmp_path / "COSTS.md"
    claude = dict(costs.empty_claude_usage("m"), api_calls=2, input_tokens=60_000, output_tokens=5_000,
                  web_search_requests=12)
    for day in (dt.datetime(2026, 10, 20, 2, 5, tzinfo=dt.timezone.utc),
                dt.datetime(2026, 11, 2, 3, 5, tzinfo=dt.timezone.utc)):
        costs.record(cfg, "publish", "ok", claude, 6_200, ledger=ledger, report=report, now=day)
    costs.record(cfg, "voice check", "failed", None, 3, ledger=ledger, report=report,
                 now=dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.timezone.utc))
    runs = json.loads(ledger.read_text())
    assert [r["mode"] for r in runs] == ["publish", "publish", "voice check"]
    assert runs[0]["claude"]["usd"] == pytest.approx(0.29)  # 0.12 + 0.05 + 0.12
    assert runs[0]["run_url"] == "https://github.com/owner/podcast/actions/runs/42"
    text = report.read_text()
    assert "| 2026-11 | 2 | 1 | 65,000 | 12 | $0.29 | 6,203 |" in text
    assert "| 2026-10 | 1 | 1 | 65,000 | 12 | $0.29 | 6,200 |" in text
    assert "[2026-11-02 09:00](https://github.com/owner/podcast/actions/runs/42) | voice check | failed | —" in text
    assert "ElevenLabs 3 characters" in summary.read_text()


def ledger(repo):
    path = repo / "data" / "costs.json"
    return json.loads(path.read_text()) if path.exists() else []


def test_a_published_episode_records_claude_and_both_elevenlabs_uses(repo, mocks):
    main.main()
    [run] = ledger(repo)
    assert run["mode"] == "publish" and run["outcome"] == "ok"
    assert run["claude"]["input_tokens"] == 50_000 and run["claude"]["web_search_requests"] == 12
    assert run["elevenlabs_characters"] > 6 and run["note"].startswith("voice check 6 + episode ")
    assert (repo / "COSTS.md").exists()


def test_dry_run_and_preview_record_claude_only(repo, mocks, monkeypatch):
    for mode in ("DRY_RUN", "PREVIEW"):
        monkeypatch.setenv(mode, "true")
        main.main()
        monkeypatch.delenv(mode)
    assert [(r["mode"], r["elevenlabs_characters"], r["claude"]["api_calls"]) for r in ledger(repo)] == \
        [("dry run", 0, 2), ("preview", 0, 2)]


def test_speech_failing_half_way_still_records_what_was_billed(repo, mocks, monkeypatch):
    def half(parts, cfg, out, billed=None, timeline=None):
        billed[:] = [2_000]
        raise RuntimeError("ElevenLabs 500")
    monkeypatch.setattr(tts, "synthesize", half)
    with pytest.raises(RuntimeError):
        main.main()
    [run] = ledger(repo)
    assert run["outcome"] == "failed" and run["claude"]["api_calls"] == 2
    assert run["elevenlabs_characters"] == 6 + 2_000


def test_a_refused_voice_records_only_the_billed_characters(repo, mocks, monkeypatch):
    monkeypatch.setattr(tts, "voice_check_results", lambda cfg: {"host": "ok", "analyst": "ElevenLabs 402"})
    with pytest.raises(RuntimeError):
        main.main()
    [run] = ledger(repo)
    assert run["claude"] is None and run["elevenlabs_characters"] == 3


def test_nothing_is_recorded_when_nothing_was_spent(repo, mocks, monkeypatch):
    monkeypatch.setattr(main, "current_time", lambda cfg: dt.datetime(2026, 10, 24, 4, 5))  # Saturday
    main.main()
    assert ledger(repo) == []


def test_news_cutoff_is_the_scheduled_time(repo, mocks, monkeypatch, cfg):
    # A manual run "as scheduled" and a late scheduled run both use 4:05 as the news cutoff.
    monkeypatch.setattr(main, "current_time", lambda c: dt.datetime(2026, 10, 20, 23, 40,
                                                                    tzinfo=main.ZoneInfo("Europe/Paris")))
    monkeypatch.setenv("AS_SCHEDULED", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    main.main()
    assert f"{mocks['editorial_now']:%Y-%m-%d %H:%M}" == "2026-10-20 04:05"
    assert "News cutoff: use only news published before 04:05 Paris time today" in \
        generate.build_user_message(cfg, mocks["editorial_now"], [])
