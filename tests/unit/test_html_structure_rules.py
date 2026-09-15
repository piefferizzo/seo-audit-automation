"""Test per HTMLStructureRules (H-05, H-06, H-07, H-08)."""
import pytest

from processors.rules.html_structure_rules import HTMLStructureRules


@pytest.fixture
def base_config():
    return {"thresholds": {}}


@pytest.fixture
def rule(base_config):
    return HTMLStructureRules(base_config)


def make_homepage(**overrides):
    base = {
        "url": "https://esempio.com",
        "images": [],
        "structured_data": [{"@type": "Organization"}],
        "og_tags": {"title": "x"},
        "hreflang": [],
        "lang": "it",
    }
    base.update(overrides)
    return base


class TestHTMLStructureRulesApplicability:

    def test_not_applicable_without_html(self, rule):
        assert not rule.is_applicable({})

    def test_not_applicable_without_homepage(self, rule):
        assert not rule.is_applicable({"html": {}})

    def test_not_applicable_with_error(self, rule):
        assert not rule.is_applicable({"html": {"homepage": {"error": "timeout"}}})

    def test_applicable_with_homepage(self, rule):
        assert rule.is_applicable({"html": {"homepage": make_homepage()}})


class TestH05ImagesAlt:

    def test_no_images_ok(self, rule):
        data = {"html": {"homepage": make_homepage(images=[])}}
        rows = rule.evaluate(data, "esempio.com")
        h05 = [r for r in rows if r["ID Audit"] == "H-05"][0]
        assert h05["Stato"] == "OK"

    def test_all_with_alt_ok(self, rule):
        imgs = [{"src": "a.jpg", "alt": "ok"}, {"src": "b.jpg", "alt": "ok"}]
        data = {"html": {"homepage": make_homepage(images=imgs)}}
        rows = rule.evaluate(data, "esempio.com")
        h05 = [r for r in rows if r["ID Audit"] == "H-05"][0]
        assert h05["Stato"] == "OK"

    def test_some_without_alt_fail(self, rule):
        imgs = [{"src": "a.jpg", "alt": "ok"}, {"src": "b.jpg", "alt": ""},
                {"src": "c.jpg", "alt": ""}]
        data = {"html": {"homepage": make_homepage(images=imgs)}}
        rows = rule.evaluate(data, "esempio.com")
        h05 = [r for r in rows if r["ID Audit"] == "H-05"][0]
        assert h05["Stato"] == "FAIL"
        assert h05["Severità"] == 1


class TestH06StructuredData:

    def test_structured_data_ok(self, rule):
        data = {"html": {"homepage": make_homepage(structured_data=[{"@type": "Org"}])}}
        rows = rule.evaluate(data, "esempio.com")
        h06 = [r for r in rows if r["ID Audit"] == "H-06"][0]
        assert h06["Stato"] == "OK"

    def test_no_structured_data_fail(self, rule):
        data = {"html": {"homepage": make_homepage(structured_data=[])}}
        rows = rule.evaluate(data, "esempio.com")
        h06 = [r for r in rows if r["ID Audit"] == "H-06"][0]
        assert h06["Stato"] == "FAIL"


class TestH07OpenGraph:

    def test_og_ok(self, rule):
        data = {"html": {"homepage": make_homepage(og_tags={"title": "x"})}}
        rows = rule.evaluate(data, "esempio.com")
        h07 = [r for r in rows if r["ID Audit"] == "H-07"][0]
        assert h07["Stato"] == "OK"

    def test_no_og_warn(self, rule):
        data = {"html": {"homepage": make_homepage(og_tags={})}}
        rows = rule.evaluate(data, "esempio.com")
        h07 = [r for r in rows if r["ID Audit"] == "H-07"][0]
        assert h07["Stato"] == "WARN"


class TestH08Hreflang:

    def test_hreflang_present_ok(self, rule):
        hl = [{"lang": "it", "href": "https://esempio.com"},
              {"lang": "en", "href": "https://esempio.com/en"}]
        data = {"html": {"homepage": make_homepage(hreflang=hl)}}
        rows = rule.evaluate(data, "esempio.com")
        h08 = [r for r in rows if r["ID Audit"] == "H-08"][0]
        assert h08["Stato"] == "OK"

    def test_monolingual_na(self, rule):
        data = {"html": {"homepage": make_homepage(hreflang=[], lang="it")}}
        rows = rule.evaluate(data, "esempio.com")
        h08 = [r for r in rows if r["ID Audit"] == "H-08"][0]
        assert h08["Stato"] == "N/A"

    def test_missing_hreflang_on_multilang_warn(self, rule):
        data = {"html": {"homepage": make_homepage(hreflang=[], lang="de")}}
        rows = rule.evaluate(data, "esempio.com")
        h08 = [r for r in rows if r["ID Audit"] == "H-08"][0]
        assert h08["Stato"] == "WARN"


class TestFullRuleOutput:

    def test_evaluate_returns_4_rows(self, rule):
        data = {"html": {"homepage": make_homepage()}}
        rows = rule.evaluate(data, "esempio.com")
        assert len(rows) == 4

    def test_evaluate_empty_when_not_applicable(self, rule):
        assert rule.evaluate({}, "esempio.com") == []

    def test_rows_have_expected_ids(self, rule):
        data = {"html": {"homepage": make_homepage()}}
        rows = rule.evaluate(data, "esempio.com")
        ids = {r["ID Audit"] for r in rows}
        assert ids == {"H-05", "H-06", "H-07", "H-08"}

    def test_rows_have_all_8_keys(self, rule):
        data = {"html": {"homepage": make_homepage()}}
        rows = rule.evaluate(data, "esempio.com")
        expected_keys = {
            "ID Audit", "Categoria", "Elemento Analizzato", "Stato",
            "Severità", "Risultato / Evidenza", "URL / Link Evidenza",
            "Note Tecniche",
        }
        for r in rows:
            assert set(r.keys()) == expected_keys
