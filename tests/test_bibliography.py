from __future__ import annotations
import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drift_contracts.bibliography import audit_bibliography, parse_bibtex


class BibliographyTests(unittest.TestCase):
    def _fixture(self, directory: Path, *, duplicate_doi: bool = False,
                 missing_citation: bool = False, bad_cohorts: bool = False):
        entries = []
        ledgers = []
        cites = []
        cohorts = (["TSE calibration"] * 12 + ["Influential/foundational"] * 5 +
                   ["Adjacent venue"] * 5)
        for index, cohort in enumerate(cohorts):
            key = f"k{index}"
            doi = "10.1234/shared" if duplicate_doi and index < 2 else f"10.1234/{index}"
            title = f"Title {index}"
            entries.append(
                f"@article{{{key}, author={{A. Author}}, title={{{title}}}, "
                f"journal={{Journal}}, year={{2020}}, doi={{{doi}}}}}"
            )
            ledgers.append({
                "citation_key": key, "title": title, "year": "2020",
                "primary_locator": f"https://doi.org/{doi}",
                "verification_status": "publisher_metadata_cross_checked",
                "verification_basis": "publisher metadata", "checked_utc": "2026-09-16",
                "notes": "bibliographic metadata only",
            })
            if not (missing_citation and index == len(cohorts) - 1):
                cites.append(key)
        (directory / "refs.bib").write_text("\n".join(entries) + "\n", encoding="utf-8")
        (directory / "paper.tex").write_text("\\cite{" + ",".join(cites) + "}\n", encoding="utf-8")
        with (directory / "ledger.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(ledgers[0]))
            writer.writeheader(); writer.writerows(ledgers)
        if bad_cohorts:
            cohorts[-1] = "TSE calibration"
        rows = []
        for index, cohort in enumerate(cohorts):
            rows.append({"cohort": cohort, "citation_key": f"k{index}",
                         "reading_scope": "metadata and relevant sections checked",
                         "source_locator": f"https://doi.org/10.1234/{index}"})
        with (directory / "calibration.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        return dict(bib_path=directory / "refs.bib", tex_paths=[directory / "paper.tex"],
                    ledger_path=directory / "ledger.csv",
                    calibration_path=directory / "calibration.csv", minimum_cited=22)

    def test_parser_handles_nested_braces_and_multiple_entries(self):
        entries = parse_bibtex(
            "@article{x,author={A and B},title={{A {Nested} Title}},journal={J},year={2026}}\n"
            "@book{y,editor={E},title={Book},publisher={P},year={2020}}\n"
        )
        self.assertEqual(["x", "y"], [entry.key for entry in entries])
        self.assertEqual("{A {Nested} Title}", entries[0].fields["title"])

    def test_consistent_fixture_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            report = audit_bibliography(**self._fixture(Path(temp)))
        self.assertEqual("pass", report["status"])
        self.assertEqual(22, report["unique_cited_entries"])

    def test_missing_citation_is_rejected_as_padding(self):
        with tempfile.TemporaryDirectory() as temp:
            report = audit_bibliography(**self._fixture(Path(temp), missing_citation=True))
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("uncited entries" in error for error in report["errors"]))

    def test_duplicate_doi_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            report = audit_bibliography(**self._fixture(Path(temp), duplicate_doi=True))
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("duplicate DOI" in error for error in report["errors"]))

    def test_calibration_counts_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            report = audit_bibliography(**self._fixture(Path(temp), bad_cohorts=True))
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("cohort counts" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
