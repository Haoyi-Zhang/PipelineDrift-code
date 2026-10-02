"""Deterministic consistency checks for the manuscript bibliography.

The checker deliberately stays offline.  It validates that manuscript citations,
BibTeX metadata, the human verification ledger, and the calibration matrix agree.
It does not claim that syntactic validation replaces checking publisher records.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import datetime as _dt
import re
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BibEntry:
    entry_type: str
    key: str
    fields: dict[str, str]


class BibliographyError(ValueError):
    """Raised for a malformed BibTeX source."""


def _skip_space(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _balanced_end(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    quoted = False
    escaped = False
    for pos in range(start, len(text)):
        char = text[pos]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            continue
        if quoted:
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return pos
    raise BibliographyError("unbalanced BibTeX entry")


def _split_top_level(text: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    brace = 0
    quoted = False
    escaped = False
    for pos, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
        elif not quoted and char == "{":
            brace += 1
        elif not quoted and char == "}":
            brace -= 1
            if brace < 0:
                raise BibliographyError("unbalanced field braces")
        elif not quoted and brace == 0 and char == delimiter:
            parts.append(text[start:pos])
            start = pos + 1
    if quoted or brace:
        raise BibliographyError("unbalanced quoted/braced field")
    parts.append(text[start:])
    return parts


def _unwrap(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and ((value[0] == "{" and value[-1] == "}") or
                            (value[0] == '"' and value[-1] == '"')):
        return value[1:-1].strip()
    return value


def parse_bibtex(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    pos = 0
    while True:
        at = text.find("@", pos)
        if at < 0:
            break
        kind_match = re.match(r"@([A-Za-z]+)\s*([\{(])", text[at:])
        if not kind_match:
            raise BibliographyError(f"malformed entry near byte {at}")
        kind = kind_match.group(1).lower()
        opening = kind_match.group(2)
        closing = "}" if opening == "{" else ")"
        body_start = at + kind_match.end() - 1
        body_end = _balanced_end(text, body_start, opening, closing)
        body = text[body_start + 1:body_end]
        pieces = _split_top_level(body)
        if not pieces or not pieces[0].strip():
            raise BibliographyError("entry without citation key")
        key = pieces[0].strip()
        fields: dict[str, str] = {}
        for piece in pieces[1:]:
            if not piece.strip():
                continue
            if "=" not in piece:
                raise BibliographyError(f"{key}: malformed field {piece!r}")
            name, value = piece.split("=", 1)
            name = name.strip().lower()
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
                raise BibliographyError(f"{key}: malformed field name {name!r}")
            if name in fields:
                raise BibliographyError(f"{key}: duplicate field {name}")
            fields[name] = _unwrap(value)
        entries.append(BibEntry(kind, key, fields))
        pos = body_end + 1
    return entries


def _strip_tex_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        escaped = False
        cut = len(line)
        for pos, char in enumerate(line):
            if char == "%" and not escaped:
                cut = pos
                break
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
        lines.append(line[:cut])
    return "\n".join(lines)


def extract_citations(tex_sources: Iterable[str]) -> list[str]:
    keys: list[str] = []
    for source in tex_sources:
        clean = _strip_tex_comments(source)
        for match in re.finditer(r"\\cite[A-Za-z*]*\s*\{([^}]*)\}", clean):
            keys.extend(part.strip() for part in match.group(1).split(",") if part.strip())
    return keys


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def audit_bibliography(
    *,
    bib_path: Path,
    tex_paths: list[Path],
    ledger_path: Path,
    calibration_path: Path,
    minimum_cited: int = 55,
) -> dict:
    entries = parse_bibtex(bib_path.read_text(encoding="utf-8"))
    citations = extract_citations(path.read_text(encoding="utf-8") for path in tex_paths)
    errors: list[str] = []

    keys = [entry.key for entry in entries]
    key_set = set(keys)
    cited_set = set(citations)
    duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
    if duplicate_keys:
        errors.append(f"duplicate BibTeX keys: {', '.join(duplicate_keys)}")
    missing = sorted(cited_set - key_set)
    uncited = sorted(key_set - cited_set)
    if missing:
        errors.append(f"missing cited entries: {', '.join(missing)}")
    if uncited:
        errors.append(f"uncited entries (possible padding): {', '.join(uncited)}")
    if len(cited_set) < minimum_cited:
        errors.append(f"only {len(cited_set)} unique cited entries; require at least {minimum_cited}")

    allowed_types = {"article", "book", "incollection", "inproceedings", "techreport"}
    doi_to_keys: dict[str, list[str]] = {}
    placeholder_pattern = re.compile(
        r"(?:example\.com|placeholder|\bTODO\b|\bTBD\b|anonymous\.4open\.science|github\.com/(?:owner|user)/repo)",
        re.IGNORECASE,
    )
    current_year = _dt.date.today().year
    for entry in entries:
        fields = entry.fields
        if entry.entry_type not in allowed_types:
            errors.append(f"{entry.key}: unsupported entry type {entry.entry_type}")
        for required in ("title", "year"):
            if not fields.get(required, "").strip():
                errors.append(f"{entry.key}: missing {required}")
        if entry.entry_type == "article":
            for required in ("author", "journal"):
                if not fields.get(required, "").strip():
                    errors.append(f"{entry.key}: missing {required}")
        elif entry.entry_type in {"inproceedings", "incollection"}:
            for required in ("author", "booktitle"):
                if not fields.get(required, "").strip():
                    errors.append(f"{entry.key}: missing {required}")
        elif entry.entry_type == "book":
            if not fields.get("author") and not fields.get("editor"):
                errors.append(f"{entry.key}: missing author/editor")
            if not fields.get("publisher"):
                errors.append(f"{entry.key}: missing publisher")
        elif entry.entry_type == "techreport":
            for required in ("author", "institution"):
                if not fields.get(required, "").strip():
                    errors.append(f"{entry.key}: missing {required}")

        year = fields.get("year", "")
        if not re.fullmatch(r"\d{4}", year):
            errors.append(f"{entry.key}: invalid year {year!r}")
        elif not (1900 <= int(year) <= current_year):
            errors.append(f"{entry.key}: implausible year {year}")
        doi = fields.get("doi", "").strip().lower()
        if doi:
            if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
                errors.append(f"{entry.key}: malformed DOI {doi!r}")
            doi_to_keys.setdefault(doi, []).append(entry.key)
        for field, value in fields.items():
            if placeholder_pattern.search(value):
                errors.append(f"{entry.key}: placeholder in {field}")
    for doi, doi_keys in sorted(doi_to_keys.items()):
        if len(doi_keys) > 1:
            errors.append(f"duplicate DOI {doi}: {', '.join(sorted(doi_keys))}")

    all_tex = "\n".join(path.read_text(encoding="utf-8") for path in tex_paths)
    if placeholder_pattern.search(all_tex):
        errors.append("manuscript contains a placeholder URL or marker")

    ledger = _read_csv(ledger_path)
    ledger_keys = [row.get("citation_key", "").strip() for row in ledger]
    if len(ledger_keys) != len(set(ledger_keys)):
        errors.append("verification ledger contains duplicate citation keys")
    if set(ledger_keys) != key_set:
        errors.append(
            "verification ledger key mismatch: "
            f"missing={sorted(key_set-set(ledger_keys))}, extra={sorted(set(ledger_keys)-key_set)}"
        )
    ledger_by_key = {row.get("citation_key", "").strip(): row for row in ledger}
    allowed_statuses = {
        "publisher_metadata_cross_checked",
        "official_archive_cross_checked",
        "bibliographic_catalog_cross_checked",
    }
    for entry in entries:
        row = ledger_by_key.get(entry.key, {})
        if row.get("title", "").strip() != entry.fields.get("title", "").strip():
            errors.append(f"{entry.key}: ledger title differs from BibTeX")
        if row.get("year", "").strip() != entry.fields.get("year", "").strip():
            errors.append(f"{entry.key}: ledger year differs from BibTeX")
        if row.get("verification_status", "").strip() not in allowed_statuses:
            errors.append(f"{entry.key}: invalid or missing ledger status")
        locator = row.get("primary_locator", "").strip()
        if not locator.startswith("https://"):
            errors.append(f"{entry.key}: ledger locator is not HTTPS")
        doi = entry.fields.get("doi", "").strip().lower()
        if doi and doi not in locator.lower():
            errors.append(f"{entry.key}: ledger locator does not contain BibTeX DOI")
        checked = row.get("checked_utc", "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked):
            errors.append(f"{entry.key}: invalid ledger check date")
        if not row.get("verification_basis", "").strip():
            errors.append(f"{entry.key}: missing ledger verification basis")

    calibration = _read_csv(calibration_path)
    cohort_counts: dict[str, int] = {}
    calibration_keys: list[str] = []
    for row in calibration:
        cohort = row.get("cohort", "").strip()
        cohort_counts[cohort] = cohort_counts.get(cohort, 0) + 1
        key = row.get("citation_key", "").strip()
        calibration_keys.append(key)
        if key not in key_set:
            errors.append(f"calibration cites unknown key {key}")
        if not row.get("reading_scope", "").strip():
            errors.append(f"calibration row {key}: missing reading scope")
        locator = row.get("source_locator", "").strip()
        if not locator.startswith("https://"):
            errors.append(f"calibration row {key}: source locator is not HTTPS")
        entry = next((candidate for candidate in entries if candidate.key == key), None)
        if entry and entry.fields.get("doi") and entry.fields["doi"].lower() not in locator.lower():
            errors.append(f"calibration row {key}: locator does not contain BibTeX DOI")
    if len(calibration_keys) != len(set(calibration_keys)):
        errors.append("calibration matrix repeats a citation key across cohorts")
    expected_cohorts = {
        "TSE calibration": 12,
        "Influential/foundational": 5,
        "Adjacent venue": 5,
    }
    if cohort_counts != expected_cohorts:
        errors.append(f"calibration cohort counts {cohort_counts!r}, expected {expected_cohorts!r}")

    report = {
        "status": "pass" if not errors else "fail",
        "bib_entries": len(entries),
        "unique_cited_entries": len(cited_set),
        "citation_occurrences": len(citations),
        "uncited_entries": uncited,
        "missing_entries": missing,
        "duplicate_dois": {doi: values for doi, values in doi_to_keys.items() if len(values) > 1},
        "verification_ledger_rows": len(ledger),
        "calibration_cohorts": cohort_counts,
        "minimum_cited_required": minimum_cited,
        "checks_are_offline_consistency_checks": True,
        "errors": errors,
    }
    return report
