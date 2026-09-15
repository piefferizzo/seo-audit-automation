"""Test per HtmlMetaRules (H-01, H-02, H-03, H-04, U-03)."""
import pytest

from processors.rules.html_meta_rules import HtmlMetaRules


@pytest.fixture
def base_config():
    return {"thresholds": {}}


@pytest.fixture
def rule(base_config):
    return HtmlMetaRules(base_config)


def make_homepage(**overrides):
    base = {
        "url": "https://esempio.com",
        "title": "Titolo di esempio con lunghezza media",
        "meta_description": "Descrizione di esempio di lunghezza compresa tra 120 e 160 caratteri per testare correttamente il check H-02 del processor SEO.",
        "canonical": "https://esempio.com",
        "headings": {"h1": ["H1 principale"]},
        "viewport": "width=device-width, initial-scale=1",
    }
    base.update(overrides)
    return base


class TestHtmlMetaRulesApplicability:

    def test_not_applicable_without_html(self, rule):
        assert not rule.is_applicable({})

    def test_not_applicable_without_homepage(self, rule):
        assert not rule.is_applicable({"html": {}})

    def test_not_applicable_with_error(self, rule):
        assert not rule.is_applicable({"html": {"homepage": {"error": "timeout"}}})

    def test_applicable_with_homepage(self, rule):
        assert rule.is_applicable({"html": {"homepage": make_homepage()}})


class TestH01MetaTitle:

    def test_title_ok(self, rule):
        data = {"html": {"homepage": make_homepage()}}
        rows = rule.evaluate(data, "esempio.com")
        h01 = [r for r in rows if r["ID Audit"] == "H-01"][0]
        assert h01["Stato"] == "OK"

    def test_title_missing_fail(self, rule):
        data = {"html": {"homepage": make_homepage(title="")}}
        rows = rule.evaluate(data, "esempio.com")
        h01 = [r for r in rows if r["ID Audit"] == "H-01"][0]
        assert h01["Stato"] == "FAIL"

    def test_title_too_short_warn(self, rule):
        data = {"html": {"homepage": make_homepage(title="Corto")}}
        rows = rule.evaluate(data, "esempio.com")
        h01 = [r for r in rows if r["ID Audit"] == "H-01"][0]
        assert h01["Stato"] == "WARN"

    def test_title_too_long_warn(self, rule):
        data = {"html": {"homepage": make_homepage(title="A" * 80)}}
        rows = rule.evaluate(data, "esempio.com")
        h01 = [r for r in rows if r["ID Audit"] == "H-01"][0]
        assert h01["Stato"] == "WARN"


class TestH02MetaDescription:

    def test_desc_ok(self, rule):
        data = {"html": {"homepage": make_homepage()}}
        rows = rule.evaluate(data, "esempio.com")
        h02 = [r for r in rows if r["ID Audit"] == "H-02"][0]
        assert h02["Stato"] == "OK"

    def test_desc_missing_fail(self, rule):
        data = {"html": {"homepage": make_homepage(meta_description="")}}
        rows = rule.evaluate(data, "esempio.com")
        h02 = [r for r in rows if r["ID Audit"] == "H-02"][0]
        assert h02["Stato"] == "FAIL"

    def test_desc_too_short_warn(self, rule):
        data = {"html": {"homepage": make_homepage(meta_description="Troppo corta")}}
        rows = rule.evaluate(data, "esempio.com")
        h02 = [r for r in rows if r["ID Audit"] == "H-02"][0]
        assert h02["Stato"] == "WARN"

    def test_desc_too_long_warn(self, rule):
        data = {"html": {"homepage": make_homepage(meta_description="A" * 200)}}
        rows = rule.evaluate(data, "esempio.com")
        h02 = [r for r in rows if r["ID Audit"] == "H-02"][0]
        assert h02["Stato"] == "WARN"


class TestH03Canonical:

    def test_canonical_ok(self, rule):
        data = {"html": {"homepage": make_homepage()}}
        rows = rule.evaluate(data, "esempio.com")
        h03 = [r for r in rows if r["ID Audit"] == "H-03"][0]
        assert h03["Stato"] == "OK"

    def test_canonical_missing_fail(self, rule):
        data = {"html": {"homepage": make_homepage(canonical="")}}
        rows = rule.evaluate(data, "esempio.com")
        h03 = [r for r in rows if r["ID Audit"] == "H-03"][0]
        assert h03["Stato"] == "FAIL"


class TestH04HeadingH1:

    def test_h1_ok(self, rule):
        data = {"html": {"homepage": make_homepage()}}
        rows = rule.evaluate(data, "esempio.com")
        h04 = [r for r in rows if r["ID Audit"] == "H-04"][0]
        assert h04["Stato"] == "OK"

    def test_h1_missing_fail(self, rule):
        data = {"html": {"homepage": make_homepage(headings={"h1": []})}}
        rows = rule.evaluate(data, "esempio.com")
        h04 = [r for r in rows if r["ID Audit"] == "H-04"][0]
        assert h04["Stato"] == "FAIL"

    def test_h1_multiple_fail(self, rule):
        data = {"html": {"homepage": make_homepage(headings={"h1": ["Uno", "Due"]})}}
        rows = rule.evaluate(data, "esempio.com")
        h04 = [r for r in rows if r["ID Audit"] == "H-04"][0]
        assert h04["Stato"] == "FAIL"


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
        assert ids == {"H-01", "H-02", "H-03", "H-04"}

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
