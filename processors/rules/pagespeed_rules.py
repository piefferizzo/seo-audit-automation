"""
Regole PageSpeed Insights.

Estrae U-01 (Core Web Vitals Mobile) e U-02 (Lighthouse Performance)
da audit_processor.py.

v2.4.0 — prima estrazione di regole in modulo dedicato.
"""
from typing import Dict, Any, List

from processors.rules.base_rule import BaseRule
from processors.models.finding import make_audit_row
from utils.thresholds import classify_threshold


class PageSpeedRules(BaseRule):
    """Regole U-01, U-02 basate su PageSpeed Insights mobile."""

    category = "Usability"
    audit_ids = ["U-01", "U-02"]

    def is_applicable(self, raw_data: Dict[str, Any]) -> bool:
        """Applicabile solo se ci sono dati mobile PageSpeed."""
        pagespeed = raw_data.get("pagespeed", {}) or {}
        mobile = pagespeed.get("mobile", {}) or {}
        return bool(mobile)

    def evaluate(self, raw_data: Dict[str, Any], domain: str) -> List[Dict]:
        """Valuta le regole PageSpeed e ritorna le righe di audit."""
        pagespeed = raw_data.get("pagespeed", {}) or {}
        mobile = pagespeed.get("mobile", {}) or {}
        thresholds = self.config["thresholds"]

        if not mobile:
            return []

        rows = []

        # --- U-01: Core Web Vitals (Mobile) ---
        lcp = mobile.get("lcp", 0)
        fcp = mobile.get("fcp", 0)
        cls = mobile.get("cls", 0)

        stato, sev = classify_threshold(
            lcp,
            thresholds["lcp_critical"],
            thresholds["lcp_warning"],
        )

        rows.append(make_audit_row(
            "U-01", "Usability", "Core Web Vitals (Mobile)", stato, sev,
            f"FCP {fcp:.1f}s, LCP {lcp:.1f}s, CLS {cls:.2f}",
            f"https://pagespeed.web.dev/analysis?url={domain}",
            "Ridurre JS/CSS inutilizzati" if stato == "FAIL" else "",
        ))

        # --- U-02: Lighthouse Performance Score ---
        perf_score = mobile.get("performance_score", 0)
        acc_score = mobile.get("accessibility_score", 0)

        stato, sev = classify_threshold(
            perf_score,
            thresholds["lighthouse_perf_critical"],
            thresholds["lighthouse_perf_warning"],
            higher_is_worse=False,
        )

        rows.append(make_audit_row(
            "U-02", "Usability", "Lighthouse Performance Score", stato, sev,
            f"Performance {perf_score:.0f}/100, Accessibility {acc_score:.0f}/100",
            note="Ottimizzazione necessaria" if stato != "OK" else "",
        ))

        return rows
