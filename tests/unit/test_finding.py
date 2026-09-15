"""Test per il modello Finding."""
import pytest

from processors.models.finding import (
    Finding,
    make_finding,
    STATUS_OK,
    STATUS_WARN,
    STATUS_FAIL,
    STATUS_INFO,
    STATUS_NA,
)
from processors.audit_processor import make_audit_row


class TestFindingConstruction:

    def test_create_minimal_finding(self):
        f = Finding(
            audit_id="U-01",
            category="Usability",
            element="CWV",
            status="FAIL",
            severity=1,
            result="LCP 4.8s",
        )
        assert f.audit_id == "U-01"
        assert f.status == "FAIL"
        assert f.url == ""
        assert f.notes == ""

    def test_create_full_finding(self):
        f = Finding(
            audit_id="U-01",
            category="Usability",
            element="CWV",
            status="FAIL",
            severity=1,
            result="LCP 4.8s",
            url="https://x.com",
            notes="Nota tecnica",
            source="pagespeed",
            metric="lcp",
            value=4.8,
            threshold="< 2.5s",
            recommendation="Ridurre JS/CSS",
            estimated_effort="medium",
            business_impact="high",
        )
        assert f.source == "pagespeed"
        assert f.metric == "lcp"
        assert f.value == 4.8
        assert f.estimated_effort == "medium"

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Status non valido"):
            Finding(
                audit_id="X", category="c", element="e",
                status="INVALID", severity=0, result="r",
            )

    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError, match="Severity non valida"):
            Finding(
                audit_id="X", category="c", element="e",
                status="OK", severity=99, result="r",
            )


class TestFindingConversions:

    def test_to_audit_dict_keys(self):
        f = make_finding("U-01", "Usability", "Test", "FAIL", 1, "Errore")
        d = f.to_audit_dict()
        expected_keys = {
            "ID Audit", "Categoria", "Elemento Analizzato", "Stato",
            "Severità", "Risultato / Evidenza", "URL / Link Evidenza",
            "Note Tecniche",
        }
        assert set(d.keys()) == expected_keys

    def test_to_audit_dict_values(self):
        f = make_finding("U-01", "Usability", "Test", "FAIL", 1, "Errore", "https://x.com", "nota")
        d = f.to_audit_dict()
        assert d["ID Audit"] == "U-01"
        assert d["Categoria"] == "Usability"
        assert d["Elemento Analizzato"] == "Test"
        assert d["Stato"] == "FAIL"
        assert d["Severità"] == 1
        assert d["Risultato / Evidenza"] == "Errore"
        assert d["URL / Link Evidenza"] == "https://x.com"
        assert d["Note Tecniche"] == "nota"

    def test_to_dict_includes_all_fields(self):
        f = make_finding(
            "U-01", "Usability", "Test", "FAIL", 1, "Errore",
            source="pagespeed", metric="lcp", value=4.8,
        )
        d = f.to_dict()
        assert d["audit_id"] == "U-01"
        assert d["status"] == "FAIL"
        assert d["source"] == "pagespeed"
        assert d["metric"] == "lcp"
        assert d["value"] == 4.8
        assert "url" in d
        assert "notes" in d


class TestFindingStatusHelpers:

    def test_is_fail(self):
        f = make_finding("X", "c", "e", "FAIL", 1, "r")
        assert f.is_fail()
        assert not f.is_warn()
        assert not f.is_ok()

    def test_is_warn(self):
        f = make_finding("X", "c", "e", "WARN", 2, "r")
        assert f.is_warn()
        assert not f.is_fail()

    def test_is_ok(self):
        f = make_finding("X", "c", "e", "OK", 0, "r")
        assert f.is_ok()

    def test_is_info(self):
        f = make_finding("X", "c", "e", "INFO", 0, "r")
        assert f.is_info()

    def test_is_na(self):
        f = make_finding("X", "c", "e", "N/A", 0, "r")
        assert f.is_na()


class TestMakeAuditRowCompatibility:
    """Verifica che make_audit_row sia retrocompatibile."""

    def test_returns_dict(self):
        row = make_audit_row("U-01", "Usability", "Test", "FAIL", 1, "Errore")
        assert isinstance(row, dict)

    def test_dict_has_8_keys(self):
        row = make_audit_row("U-01", "Usability", "Test", "FAIL", 1, "Errore")
        assert len(row) == 8

    def test_dict_values(self):
        row = make_audit_row(
            "U-01", "Usability", "Test", "FAIL", 1, "Errore",
            "https://x.com", "nota",
        )
        assert row["ID Audit"] == "U-01"
        assert row["Stato"] == "FAIL"
        assert row["Severità"] == 1
        assert row["URL / Link Evidenza"] == "https://x.com"

    def test_status_validated(self):
        """make_audit_row ora valida lo status tramite Finding."""
        with pytest.raises(ValueError):
            make_audit_row("X", "c", "e", "INVALID", 0, "r")

    def test_severity_validated(self):
        with pytest.raises(ValueError):
            make_audit_row("X", "c", "e", "OK", 99, "r")