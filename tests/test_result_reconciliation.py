"""Independent reconciliation of shipped raw finite records and summaries.

This test intentionally derives counts from CSV/JSON records rather than from
manuscript tables or table-rendering code.  It guards against a stale summary
being propagated into the paper after a campaign change.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _bool_cell(value: str) -> bool:
    if value in {"True", "1", "true"}:
        return True
    if value in {"False", "0", "false"}:
        return False
    raise AssertionError(f"unexpected Boolean CSV cell {value!r}")


class ResultReconciliationTests(unittest.TestCase):
    def test_raw_records_reconcile_to_shipped_summaries(self):
        portfolio = json.loads(
            (RESULTS / "portfolio" / "summary.json").read_text(encoding="utf-8"))
        unary = _rows(RESULTS / "portfolio" / "unary-catalogue.csv")
        binary = _rows(RESULTS / "portfolio" / "binary-catalogue.csv")
        mutants = _rows(RESULTS / "portfolio" / "mutation-results.csv")

        self.assertEqual(4_096, len(unary))
        self.assertEqual(16_384, len(binary))
        self.assertEqual(20_480, len(unary) + len(binary))
        # The protocol fixes three unary atoms (8 masks) and two binary atoms
        # (4 masks); derive the total from the raw row counts rather than copy
        # the summary field.
        self.assertEqual(98_304, len(unary) * 8 + len(binary) * 4)
        self.assertEqual(571, len(mutants))
        self.assertEqual(len(unary) + len(binary), portfolio["totals"]["cases"])
        self.assertEqual(
            len(unary) * 8 + len(binary) * 4,
            portfolio["totals"]["portfolio_masks_checked"],
        )
        self.assertEqual(len(mutants), portfolio["examples"]["mutations"])
        self.assertEqual(
            sum(not _bool_cell(row["mutated_catalogue_feasible"]) for row in mutants),
            portfolio["examples"]["mutated_catalogue_infeasible"],
        )
        self.assertEqual(
            sum((not _bool_cell(row["catalogue_infeasibility_verified"])) and
                (not _bool_cell(row["mutated_catalogue_feasible"])) for row in mutants),
            portfolio["examples"]["mutation_infeasibility_verification_failures"],
        )

        random_rows = _rows(RESULTS / "random-differential" / "cases.csv")
        random_summary = json.loads(
            (RESULTS / "random-differential" / "summary.json").read_text(
                encoding="utf-8"))
        self.assertEqual(256, len(random_rows))
        random_masks = sum(int(row["masks_checked"])
                           for row in random_rows)
        self.assertEqual(2_348, random_masks)
        self.assertEqual(len(random_rows), random_summary["problems"])
        self.assertEqual(random_masks, random_summary["portfolio_masks_checked"])

        cost_rows = _rows(RESULTS / "cost-sensitivity" / "variations.csv")
        cost_summary = json.loads(
            (RESULTS / "cost-sensitivity" / "summary.json").read_text(
                encoding="utf-8"))
        self.assertEqual(79, len(cost_rows))
        self.assertEqual(len(cost_rows), cost_summary["perturbations"])
        self.assertEqual(
            sum(_bool_cell(row["mask_changed"]) for row in cost_rows),
            cost_summary["optimal_mask_changes"],
        )
        self.assertEqual(
            sum(_bool_cell(row["numeric_optimum_changed"]) for row in cost_rows),
            cost_summary["numeric_optimum_changes"],
        )

        language = json.loads(
            (RESULTS / "language-check.json").read_text(encoding="utf-8"))
        totals = language["totals"]
        independent_total = sum(
            totals[key] for key in (
                "retention_transition_cells",
                "monitor_transition_cells",
                "monitor_output_cells",
                "initial_states_checked",
                "empty_histories_checked",
            )
        )
        self.assertEqual(1_272, independent_total)

        tfx = json.loads(
            (RESULTS / "tfx-projection" / "result.json").read_text(
                encoding="utf-8"))
        projected = json.loads(
            (RESULTS / "tfx-projection" / "projected-declaration.json").read_text(
                encoding="utf-8"))
        self.assertEqual(
            len(projected["retention_atoms"]), tfx["features_projected"])
        self.assertEqual(
            len(projected["monitor_updates"]), tfx["monitor_updates"])
        self.assertEqual((1 << tfx["features_projected"]) - 1,
                         tfx["selected_mask"])

        # Claim-ledger raw-result paths are executable references rather than
        # prose abbreviations. Wildcards must match at least one file. Paper
        # labels are checked by paper/tools/check_claim_labels.py so this
        # standalone artifact never depends on a sibling paper directory.
        with (ROOT / "claim_evidence_ledger.csv").open(
                newline="", encoding="utf-8") as handle:
            ledger = list(csv.DictReader(handle))
        for claim in ledger:
            for raw in claim["raw_result"].split(";"):
                item = raw.strip()
                if not item:
                    continue
                if any(char in item for char in "*?["):
                    self.assertTrue(list(ROOT.glob(item)),
                                    f"{claim['claim_id']} raw-result glob has no match: {item}")
                else:
                    self.assertTrue((ROOT / item).exists(),
                                    f"{claim['claim_id']} raw-result path is missing: {item}")


if __name__ == "__main__":
    unittest.main()
