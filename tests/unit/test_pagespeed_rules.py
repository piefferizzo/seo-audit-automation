"""Test per PageSpeedRules."""
import pytest

from processors.rules.pagespeed_rules import PageSpeedRules


@pytest.fixture
def base_config():
    return {
        "thresholds": {
            "lcp_warning": 2.5,
            "lcp_critical": 4.0,
            "fcp_warning": 1.8,
            "fcp_critical": 3.0,
            "cls_warning": 0.1,
            "cls_critical": 0.25,
            "lighthouse_perf_warning": 70,
            "lighthouse_perf_critical": 50,
            "lighthouse_acc_warning": 70,
            "lighthouse_acc_critical": 50,
        }
    }


@pytest.fixture
def rule(base_config):
    return PageSpeedRules(base_config)


class TestPageSpeedRulesApplicability:

    def test_not_applicable_without_data(self, rule):
        assert not rule.is_applicable({})

    def test_not_applicable_with_empty_pagespeed(self, rule):
        assert not rule.is_applicable({"pagespeed": {}})

    def test_not_applicable_without_mobile(self, rule):
        assert not rule.is_applicable({"pagespeed": {"desktop": {"lcp": 2.0}}})

    def test_applicable_with_mobile_data(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 2.0}}}
        assert rule.is_applicable(data)


class TestU01CoreWebVitals:

    def test_u01_fail_when_lcp_critical(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 4.8, "fcp": 1.1, "cls": 0.05}}}
        rows = rule.evaluate(data, "esempio.com")
        u01 = [r for r in rows if r["ID Audit"] == "U-01"][0]
        assert u01["Stato"] == "FAIL"
        assert u01["Severità"] == 1

    def test_u01_warn_when_lcp_above_warning(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 3.0, "fcp": 1.1, "cls": 0.05}}}
        rows = rule.evaluate(data, "esempio.com")
        u01 = [r for r in rows if r["ID Audit"] == "U-01"][0]
        assert u01["Stato"] == "WARN"
        assert u01["Severità"] == 2

    def test_u01_ok_when_lcp_good(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 2.0, "fcp": 1.5, "cls": 0.05}}}
        rows = rule.evaluate(data, "esempio.com")
        u01 = [r for r in rows if r["ID Audit"] == "U-01"][0]
        assert u01["Stato"] == "OK"
        assert u01["Severità"] == 0

    def test_u01_result_format(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 4.8, "fcp": 1.1, "cls": 0.05}}}
        rows = rule.evaluate(data, "esempio.com")
        u01 = [r for r in rows if r["ID Audit"] == "U-01"][0]
        assert "FCP 1.1s" in u01["Risultato / Evidenza"]
        assert "LCP 4.8s" in u01["Risultato / Evidenza"]
        assert "CLS 0.05" in u01["Risultato / Evidenza"]

    def test_u01_url_points_to_pagespeed(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 4.8}}}
        rows = rule.evaluate(data, "esempio.com")
        u01 = [r for r in rows if r["ID Audit"] == "U-01"][0]
        assert "pagespeed.web.dev" in u01["URL / Link Evidenza"]
        assert "esempio.com" in u01["URL / Link Evidenza"]

    def test_u01_note_present_only_on_fail(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 4.8, "fcp": 1.0, "cls": 0.0}}}
        rows = rule.evaluate(data, "esempio.com")
        u01 = [r for r in rows if r["ID Audit"] == "U-01"][0]
        assert u01["Note Tecniche"] != ""

        data_ok = {"pagespeed": {"mobile": {"lcp": 1.5, "fcp": 1.0, "cls": 0.0}}}
        rows_ok = rule.evaluate(data_ok, "esempio.com")
        u01_ok = [r for r in rows_ok if r["ID Audit"] == "U-01"][0]
        assert u01_ok["Note Tecniche"] == ""


class TestU02LighthousePerformance:

    def test_u02_fail_when_perf_critical(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 2.0, "performance_score": 40, "accessibility_score": 90}}}
        rows = rule.evaluate(data, "esempio.com")
        u02 = [r for r in rows if r["ID Audit"] == "U-02"][0]
        assert u02["Stato"] == "FAIL"
        assert u02["Severità"] == 1

    def test_u02_warn_when_perf_below_warning(self, rule):
        data = {"pagespeed": {"mobile": {"performance_score": 65, "accessibility_score": 90}}}
        rows = rule.evaluate(data, "esempio.com")
        u02 = [r for r in rows if r["ID Audit"] == "U-02"][0]
        assert u02["Stato"] == "WARN"

    def test_u02_ok_when_perf_good(self, rule):
        data = {"pagespeed": {"mobile": {"performance_score": 85, "accessibility_score": 95}}}
        rows = rule.evaluate(data, "esempio.com")
        u02 = [r for r in rows if r["ID Audit"] == "U-02"][0]
        assert u02["Stato"] == "OK"

    def test_u02_result_format(self, rule):
        data = {"pagespeed": {"mobile": {"performance_score": 71, "accessibility_score": 93}}}
        rows = rule.evaluate(data, "esempio.com")
        u02 = [r for r in rows if r["ID Audit"] == "U-02"][0]
        assert "Performance 71/100" in u02["Risultato / Evidenza"]
        assert "Accessibility 93/100" in u02["Risultato / Evidenza"]

    def test_u02_note_present_only_when_not_ok(self, rule):
        data_fail = {"pagespeed": {"mobile": {"performance_score": 40, "accessibility_score": 90}}}
        rows_fail = rule.evaluate(data_fail, "esempio.com")
        u02_fail = [r for r in rows_fail if r["ID Audit"] == "U-02"][0]
        assert u02_fail["Note Tecniche"] == "Ottimizzazione necessaria"


class TestFullRuleOutput:

    def test_evaluate_returns_two_rows(self, rule):
        data = {"pagespeed": {"mobile": {
            "lcp": 2.0, "fcp": 1.0, "cls": 0.05,
            "performance_score": 80, "accessibility_score": 90,
        }}}
        rows = rule.evaluate(data, "esempio.com")
        assert len(rows) == 2

    def test_evaluate_empty_when_not_applicable(self, rule):
        rows = rule.evaluate({}, "esempio.com")
        assert rows == []

    def test_rows_have_audit_ids(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 2.0, "performance_score": 80, "accessibility_score": 90}}}
        rows = rule.evaluate(data, "esempio.com")
        ids = {r["ID Audit"] for r in rows}
        assert ids == {"U-01", "U-02"}

    def test_rows_have_all_8_keys(self, rule):
        data = {"pagespeed": {"mobile": {"lcp": 2.0, "performance_score": 80, "accessibility_score": 90}}}
        rows = rule.evaluate(data, "esempio.com")
        expected_keys = {
            "ID Audit", "Categoria", "Elemento Analizzato", "Stato",
            "Severità", "Risultato / Evidenza", "URL / Link Evidenza",
            "Note Tecniche",
        }
        for r in rows:
            assert set(r.keys()) == expected_keys
