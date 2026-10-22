"""Two-step generation (generation.dossier): a research dossier checked quote by quote, then the
episode written from it alone. Learning (2026-10-22): the first HR preview stated figures its sources
did not contain; the fact-check removed 15 of them and the episode ended too short."""
import json

from conftest import TUESDAY, make_episode, reply, submit_block
from engine import dossier, factcheck, generate
from types import SimpleNamespace

PAGE = "Le plafond mensuel de la Sécurité sociale s’élève à 4 005 euros en 2026, selon l'arrêté publié. " * 30


def dossier_block(items, id_="toolu_d"):
    return SimpleNamespace(type="tool_use", name="submit_dossier", id=id_, input={"items": items, "agenda": []})


def item(url, quote, title="Plafond"):
    return {"title": title, "theme": "Paie", "context": "C.", "sources": [{"title": "S", "url": url}],
            "facts": [{"statement": "PMSS 2026", "quote": quote, "url": url}]}


def test_a_fact_stays_only_if_its_quote_is_on_its_page(monkeypatch):
    pages = {"https://ok": PAGE, "https://paywall": None}
    monkeypatch.setattr(factcheck, "fetch", lambda url, cache, n: pages[url])
    d = {"items": [item("https://ok", "s'élève à 4005 euros"),     # not copied: "4 005" on the page
                   item("https://ok", "s'élève à 4 100 euros"),    # not what the page says
                   item("https://paywall", "anything")]}           # page not readable: kept, unread
    out = dossier.verify(d, 1000, {})
    assert [len(i["facts"]) for i in out["items"]] == [0, 0, 1]
    assert out["items"][2]["facts"][0]["status"] == "unread"
    assert out["checked"] == {"verified": 0, "unread": 1, "dropped": 2}
    assert [f["quote"] for f in out["dropped"]] == ["s'élève à 4005 euros", "s'élève à 4 100 euros"]


def test_a_quote_copied_from_the_page_is_verified_across_apostrophes_and_case(monkeypatch):
    monkeypatch.setattr(factcheck, "fetch", lambda url, cache, n: PAGE)
    out = dossier.verify({"items": [item("https://ok", "plafond mensuel de la sécurité sociale s'élève à 4 005 euros")]},
                         1000, {})
    assert out["checked"] == {"verified": 1, "unread": 0, "dropped": 0}


def dossier_cfg(cfg):
    cfg["generation"]["dossier"] = True
    cfg["factcheck"]["enabled"] = False
    return cfg


def test_research_then_writing_without_web_search_and_the_dossier_is_saved(cfg, fake_claude, monkeypatch, tmp_path):
    monkeypatch.setattr(factcheck, "fetch", lambda url, cache, n: PAGE)
    ep = make_episode()
    urls = sorted(s["url"] for s in generate.collect_sources(ep))
    items = [item(u, "s'élève à 4 005 euros en 2026", title=u) for u in urls]
    client = fake_claude([reply(dossier_block(items)), reply(submit_block(ep))])
    path = tmp_path / "dossiers" / "2026-10-20.json"
    out = generate.generate_episode(dossier_cfg(cfg), TUESDAY, [], dossier_path=path)
    research, writing = client.calls
    assert {t["name"] for t in research["tools"]} == {"web_search", "submit_dossier"}
    assert [t["name"] for t in writing["tools"]] == ["submit_episode"]  # no web search when writing
    assert "<dossier>" in writing["messages"][0]["content"] and "Step 2 of 2" in writing["messages"][0]["content"]
    assert json.loads(path.read_text())["checked"]["verified"] == len(urls) and out["dossier"]["dropped"] == 0
    # A second run the same day writes again from the saved dossier, without paying the research.
    client = fake_claude([reply(submit_block(ep))])
    generate.generate_episode(dossier_cfg(cfg), TUESDAY, [], dossier_path=path)
    assert len(client.calls) == 1 and "<dossier>" in client.calls[0]["messages"][0]["content"]


def test_a_source_outside_the_dossier_is_refused(cfg, fake_claude, monkeypatch):
    monkeypatch.setattr(factcheck, "fetch", lambda url, cache, n: PAGE)
    ep = make_episode()
    urls = sorted(s["url"] for s in generate.collect_sources(ep))
    client = fake_claude([reply(dossier_block([item(u, "4 005 euros", title=u) for u in urls[1:]])),
                          reply(submit_block(ep, "toolu_w1")), reply(submit_block(ep, "toolu_w2")),
                          reply(submit_block(ep, "toolu_w3"))])
    try:
        generate.generate_episode(dossier_cfg(cfg), TUESDAY, [])
    except SystemExit:
        pass
    feedback = client.calls[2]["messages"][-1]["content"][0]
    assert "Sources not in the research dossier" in feedback["content"] and urls[0] in feedback["content"]


def test_a_pdf_is_unread_not_parsed_as_a_page(monkeypatch):
    class R:
        status_code, text, headers = 200, "%PDF-1.7 " + "stream " * 400, {"content-type": "application/pdf"}
    monkeypatch.setattr(factcheck.requests, "get", lambda *a, **k: R())
    assert factcheck.fetch("https://x/texte.pdf", {}, 1000) is None
