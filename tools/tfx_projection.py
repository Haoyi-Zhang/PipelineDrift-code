#!/usr/bin/env python3
"""Narrow, provenance-preserving projection of a pinned TFX schema.

Only feature-level presence constraints with min_fraction=1.0 and min_count=1
are projected.  This is not a general TFDV protobuf parser or TFX integration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from drift_contracts.dsl_reference import check_compilation
from drift_contracts.portfolio import build_conflict_analysis, make_optimal_certificate, optimize_portfolio
from drift_contracts.portfolio_dsl import compile_declaration
from drift_contracts.portfolio_verify import verify_optimal, verify_safe

SOURCE_DIR = ROOT / "external" / "tfx-penguin"


def _blocks(text: str, keyword: str) -> list[str]:
    result: list[str] = []
    pattern = re.compile(rf"(?m)^\s*{re.escape(keyword)}\s*\{{")
    for match in pattern.finditer(text):
        start = match.end() - 1
        depth = 0
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    result.append(text[match.start():index + 1])
                    break
        else:
            raise ValueError(f"unterminated {keyword} block")
    return result


def parse_required_features(text: str) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for block in _blocks(text, "feature"):
        name_match = re.search(r'(?m)^\s*name:\s*"([^"]+)"\s*$', block)
        type_match = re.search(r"(?m)^\s*type:\s*([A-Z_]+)\s*$", block)
        presence_blocks = _blocks(block, "presence")
        if not name_match or not type_match or len(presence_blocks) != 1:
            raise ValueError("unsupported feature block in pinned schema")
        presence = presence_blocks[0]
        fraction_match = re.search(r"(?m)^\s*min_fraction:\s*([0-9.]+)\s*$", presence)
        count_match = re.search(r"(?m)^\s*min_count:\s*(\d+)\s*$", presence)
        if not fraction_match or not count_match:
            continue
        min_fraction = float(fraction_match.group(1))
        min_count = int(count_match.group(1))
        if min_fraction == 1.0 and min_count == 1:
            features.append({
                "name": name_match.group(1),
                "type": type_match.group(1),
                "min_fraction": min_fraction,
                "min_count": min_count,
            })
    if not features:
        raise ValueError("no supported required-presence constraints found")
    return features


def build_declaration(features: list[dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    fields = {f"{feature['name']}_present": [False, True] for feature in features}
    atoms = []
    updates = []
    for feature in features:
        field = f"{feature['name']}_present"
        predicate = {"op": "not", "args": [{"field": field}]}
        atoms.append({
            "name": f"ever-missing-{feature['name']}",
            "kind": "seen",
            "predicate": predicate,
            "cost": 1,
            "initial": 0,
        })
        updates.append({
            "name": f"reject-ever-missing-{feature['name']}",
            "kind": "seen",
            "predicate": predicate,
            "initial": 0,
        })
    return {
        "name": "tfx-penguin-required-presence-projection",
        "metadata": {
            "source_repository": source["repository"],
            "source_commit": source["commit"],
            "source_path": source["path"],
            "projection": "only feature presence min_fraction=1.0 and min_count=1; each finite event is a Boolean batch-summary record",
            "non_claim": "not a general TFDV protobuf parser, TFX runtime adapter, or production validation",
        },
        "history_schema": {"fields": fields},
        "future_schema": {"fields": fields},
        "retention_atoms": atoms,
        "monitor_updates": updates,
    }


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output must not already exist: {output}")
    output.mkdir(parents=True)
    schema_path = SOURCE_DIR / "schema.pbtxt"
    source_path = SOURCE_DIR / "SOURCE.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    data = schema_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != source["local_sha256"]:
        raise ValueError("pinned TFX schema digest differs from SOURCE.json")
    features = parse_required_features(data.decode("utf-8"))
    declaration = build_declaration(features, source)
    problem = compile_declaration(declaration)
    language = check_compilation(declaration, problem)
    analysis = build_conflict_analysis(problem)
    result = optimize_portfolio(problem, analysis)
    if not result["feasible"]:
        raise AssertionError("projected required-presence catalogue unexpectedly infeasible")
    mask = int(result["selected_mask"])
    certificate = make_optimal_certificate(problem, analysis, mask)
    certificate_valid = verify_optimal(problem, certificate)
    independently_safe = verify_safe(problem, mask)
    projection_map = {
        "source": source,
        "supported_constraint": "feature presence with min_fraction=1.0 and min_count=1",
        "event_abstraction": "one Boolean field per source feature records whether that feature is present in a finite batch summary",
        "features": [
            {
                **feature,
                "event_field": f"{feature['name']}_present",
                "retention_atom": f"ever-missing-{feature['name']}",
                "monitor_update": f"reject-ever-missing-{feature['name']}",
            }
            for feature in features
        ],
        "excluded_semantics": [
            "general protobuf fields and environments",
            "numeric distribution drift or skew",
            "streaming execution and orchestration",
            "model training, inference, deployment, or production costs",
        ],
    }
    report = {
        "scope": "narrow pinned public-schema projection; not full TFDV or TFX compatibility",
        "source_sha256": digest,
        "source_commit": source["commit"],
        "features_projected": len(features),
        "history_records": len(problem.history_symbols),
        "future_records": len(problem.future_symbols),
        "retention_atoms": len(problem.atoms),
        "monitor_updates": len(problem.updates),
        "language_initial_states_checked": language["initial_states_checked"],
        "language_empty_histories_checked": language["empty_histories_checked"],
        "feasible": result["feasible"],
        "selected_mask": mask,
        "selected_atoms": problem.selected_names(mask),
        "selected_cost": result["cost"],
        "certificate_valid": certificate_valid,
        "independently_safe": independently_safe,
        "status": "pass" if certificate_valid and independently_safe else "fail",
    }
    (output / "projected-declaration.json").write_text(
        json.dumps(declaration, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "projection-map.json").write_text(
        json.dumps(projection_map, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "certificate.json").write_text(
        json.dumps(certificate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "result.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.output)
    except (OSError, ValueError, AssertionError) as exc:
        print(f"TFX schema projection failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "pass" else 3


if __name__ == "__main__":
    raise SystemExit(main())
