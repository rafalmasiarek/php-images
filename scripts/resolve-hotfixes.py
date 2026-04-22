#!/usr/bin/env python3

"""
resolve-hotfixes.py

Resolve hotfix scripts from:
- a Trivy JSON report
- one or more hotfix manifest directories

Supported manifest file names inside each --search-dir:
- index.yaml
- index.yml
- index.json

Supported hotfix manifest schema:

hotfixes:
  - id: upgrade-imagemagick
    file: apk-upgrade-imagemagick.sh
    match:
      cves:
        - CVE-2026-30883
        - CVE-2026-30929
      packages:
        - imagemagick
        - imagemagick<7.1.2-r3
        - openssl>=3.5.1-r0,<3.5.2-r0

  - id: pin-libxml2-2.13.8-r0
    file: pin-libxml2-2.13.8-r0.sh

A hotfix entry without "match" is treated as manual-only and can be selected with:
- --extra-hotfix <id>
- --extra-hotfixes <id1,id2,...>

Design notes:
- Search directory order defines precedence.
  If the same hotfix id appears multiple times, the later search dir wins.
- Matching semantics are OR:
  A hotfix matches if any of the following is true:
  - a listed CVE is present in Trivy
  - a listed package constraint matches a package in Trivy
  - the hotfix id is explicitly requested via extra-hotfix
- Version comparison is implemented in pure Python.
  It is designed for common Alpine/apk-like versions such as:
    1.2.3-r0
    1.2.3-r10
    8.5.5
    3.5.1-r1
  It is intentionally deterministic and dependency-free.
  If you need exact apk-tools version ordering parity for all exotic cases,
  replace compare_versions() with an apk-native comparator.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# PyYAML is not part of the Python standard library.
# We keep the dependency optional at import time so the script can still
# work with index.json manifests without PyYAML installed.
try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")
PACKAGE_EXPR_RE = re.compile(
    r"""
    ^
    (?P<name>[A-Za-z0-9._+-]+)
    (?P<constraints>
        (?:
            \s*(?:==|>=|<=|>|<)\s*[^,\s]+
            (?:\s*,\s*(?:==|>=|<=|>|<)\s*[^,\s]+)*
        )?
    )
    $
    """,
    re.VERBOSE,
)

COMPARATOR_RE = re.compile(r"^\s*(==|>=|<=|>|<)\s*([^\s,]+)\s*$")
MANIFEST_FILENAMES = ("index.yaml", "index.yml", "index.json")


class ResolverError(Exception):
    """Base resolver error."""


class ValidationError(ResolverError):
    """Manifest or input validation error."""


class UnknownExtraHotfixError(ResolverError):
    """Raised when an explicitly requested hotfix id does not exist."""


@dataclass(frozen=True)
class PackageOccurrence:
    name: str
    installed_version: str
    fixed_version: Optional[str]
    vulnerability_id: Optional[str]
    target: Optional[str]
    pkg_path: Optional[str]


@dataclass
class TrivyData:
    vulnerabilities: List[Dict[str, Any]] = field(default_factory=list)
    unique_cves: Set[str] = field(default_factory=set)
    package_occurrences: List[PackageOccurrence] = field(default_factory=list)
    packages_by_name: Dict[str, List[PackageOccurrence]] = field(default_factory=dict)


@dataclass(frozen=True)
class PackageConstraint:
    name: str
    constraints: Tuple[Tuple[str, str], ...]


@dataclass
class HotfixEntry:
    hotfix_id: str
    file_name: str
    manifest_path: Path
    source_dir: Path
    search_dir_index: int
    match_cves: List[str] = field(default_factory=list)
    match_packages_raw: List[str] = field(default_factory=list)
    match_packages: List[PackageConstraint] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def file_path(self) -> Path:
        return (self.source_dir / self.file_name).resolve()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.hotfix_id,
            "file": self.file_name,
            "manifest_path": str(self.manifest_path),
            "source_dir": str(self.source_dir),
            "search_dir_index": self.search_dir_index,
            "match": {
                "cves": list(self.match_cves),
                "packages": list(self.match_packages_raw),
            },
        }


@dataclass
class OverrideRecord:
    hotfix_id: str
    replaced_manifest_path: str
    replacement_manifest_path: str
    replaced_search_dir_index: int
    replacement_search_dir_index: int


@dataclass
class SelectedHotfix:
    entry: HotfixEntry
    reasons: List[str] = field(default_factory=list)

    def add_reason(self, reason: str) -> None:
        if reason not in self.reasons:
            self.reasons.append(reason)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve hotfix scripts from Trivy and hotfix manifests."
    )
    parser.add_argument(
        "--trivy",
        required=True,
        help="Path to Trivy JSON report.",
    )
    parser.add_argument(
        "--search-dir",
        action="append",
        required=True,
        dest="search_dirs",
        help="A hotfix search directory. Can be provided multiple times. Later directories override earlier ones by hotfix id.",
    )
    parser.add_argument(
        "--extra-hotfixes",
        default="",
        help="Comma-separated hotfix ids to force-select.",
    )
    parser.add_argument(
        "--extra-hotfix",
        action="append",
        default=[],
        help="A single hotfix id to force-select. Can be provided multiple times.",
    )
    parser.add_argument(
        "--output",
        help="Write final JSON report to this file.",
    )
    parser.add_argument(
        "--copy-to",
        help="Copy selected hotfix files into this directory.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate inputs and manifests, resolve overrides, then exit without matching or copying.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print the final JSON report to stdout.",
    )
    parser.add_argument(
        "--fail-on-missing-manifest",
        action="store_true",
        help="Fail if a search dir exists but contains no supported manifest file.",
    )
    parser.add_argument(
        "--fail-on-unknown-extra-hotfix",
        action="store_true",
        help="Fail if a manually requested hotfix id does not exist.",
    )
    parser.add_argument(
        "--fail-on-unmatched-cves",
        action="store_true",
        help="Fail if any CVE from Trivy did not contribute to any selected hotfix.",
    )
    parser.add_argument(
        "--fail-on-invalid-package-constraint",
        action="store_true",
        help="Fail on invalid package constraint syntax in manifest entries. Without this flag, invalid constraints still fail because manifests must remain deterministic.",
    )
    parser.add_argument(
        "--strict-search-dir",
        action="store_true",
        help="Fail if any --search-dir does not exist or is not a directory.",
    )
    parser.add_argument(
        "--clean-copy-dir",
        action="store_true",
        help="Remove existing files in --copy-to before copying selected hotfixes.",
    )
    parser.add_argument(
        "--selection-manifest-name",
        default="selection.json",
        help="File name to write inside --copy-to with selection metadata. Default: selection.json",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-error logs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logs.",
    )
    return parser


def log(msg: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


def verbose_log(msg: str, *, verbose: bool = False, quiet: bool = False) -> None:
    if verbose and not quiet:
        print(msg, file=sys.stderr)


def load_json_file(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise ValidationError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in file {path}: {exc}") from exc


def load_yaml_file(path: Path) -> Any:
    if yaml is None:
        raise ValidationError(
            f"Cannot read YAML manifest {path}: PyYAML is not installed. "
            f"Install it or use index.json manifests."
        )
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise ValidationError(f"YAML file not found: {path}") from exc
    except Exception as exc:
        raise ValidationError(f"Invalid YAML in file {path}: {exc}") from exc


def load_manifest_file(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json_file(path)
    if suffix in (".yaml", ".yml"):
        return load_yaml_file(path)
    raise ValidationError(f"Unsupported manifest file type: {path}")


def find_manifest_file(search_dir: Path) -> Optional[Path]:
    for name in MANIFEST_FILENAMES:
        candidate = search_dir / name
        if candidate.is_file():
            return candidate
    return None


def ensure_safe_relative_file(source_dir: Path, relative_file: str) -> Path:
    # A hotfix file must stay inside its source_dir.
    # This prevents path traversal via manifest-controlled file names.
    candidate = (source_dir / relative_file).resolve()
    try:
        candidate.relative_to(source_dir.resolve())
    except ValueError as exc:
        raise ValidationError(
            f"Hotfix file path escapes search directory: file={relative_file!r}, dir={source_dir}"
        ) from exc
    return candidate


def normalize_string(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Expected string value, got: {type(value).__name__}")
    value = value.strip()
    if not value:
        raise ValidationError("String value must not be empty.")
    return value


def parse_package_constraint(expr: str) -> PackageConstraint:
    expr = normalize_string(expr)
    match = PACKAGE_EXPR_RE.match(expr)
    if not match:
        raise ValidationError(f"Invalid package constraint syntax: {expr!r}")

    name = match.group("name")
    constraints_blob = match.group("constraints") or ""
    constraints: List[Tuple[str, str]] = []

    if constraints_blob:
        # Example:
        #   ">=3.5.1-r0,<3.5.2-r0"
        #   "==2.13.9-r1"
        for raw_part in constraints_blob.split(","):
            raw_part = raw_part.strip()
            if not raw_part:
                raise ValidationError(f"Invalid empty package constraint fragment in {expr!r}")
            cm = COMPARATOR_RE.match(raw_part)
            if not cm:
                raise ValidationError(
                    f"Invalid comparator fragment {raw_part!r} in package constraint {expr!r}"
                )
            op, version = cm.groups()
            constraints.append((op, version))

    return PackageConstraint(name=name, constraints=tuple(constraints))


def validate_cve(cve: str) -> str:
    cve = normalize_string(cve)
    if not CVE_RE.match(cve):
        raise ValidationError(f"Invalid CVE format: {cve!r}")
    return cve


def parse_hotfix_entry(
    item: Dict[str, Any],
    *,
    manifest_path: Path,
    source_dir: Path,
    search_dir_index: int,
) -> HotfixEntry:
    if not isinstance(item, dict):
        raise ValidationError(
            f"Each hotfix entry must be a mapping/object in {manifest_path}, got: {type(item).__name__}"
        )

    hotfix_id = normalize_string(item.get("id"))
    file_name = normalize_string(item.get("file"))
    file_path = ensure_safe_relative_file(source_dir, file_name)

    if not file_path.is_file():
        raise ValidationError(
            f"Hotfix file declared in manifest does not exist: id={hotfix_id!r}, file={file_name!r}, manifest={manifest_path}"
        )

    match_obj = item.get("match", {})
    if match_obj is None:
        match_obj = {}
    if not isinstance(match_obj, dict):
        raise ValidationError(
            f"'match' must be a mapping/object for hotfix {hotfix_id!r} in {manifest_path}"
        )

    raw_cves = match_obj.get("cves", []) or []
    if not isinstance(raw_cves, list):
        raise ValidationError(
            f"'match.cves' must be a list for hotfix {hotfix_id!r} in {manifest_path}"
        )

    raw_packages = match_obj.get("packages", []) or []
    if not isinstance(raw_packages, list):
        raise ValidationError(
            f"'match.packages' must be a list for hotfix {hotfix_id!r} in {manifest_path}"
        )

    match_cves = [validate_cve(cve) for cve in raw_cves]
    match_packages_raw = [normalize_string(p) for p in raw_packages]
    match_packages = [parse_package_constraint(p) for p in match_packages_raw]

    return HotfixEntry(
        hotfix_id=hotfix_id,
        file_name=file_name,
        manifest_path=manifest_path,
        source_dir=source_dir,
        search_dir_index=search_dir_index,
        match_cves=match_cves,
        match_packages_raw=match_packages_raw,
        match_packages=match_packages,
        raw=item,
    )


def load_manifest_entries(
    search_dir: Path,
    *,
    search_dir_index: int,
    fail_on_missing_manifest: bool,
    strict_search_dir: bool,
    verbose: bool,
    quiet: bool,
) -> Tuple[List[HotfixEntry], Optional[Path]]:
    if strict_search_dir and not search_dir.is_dir():
        raise ValidationError(f"Search dir does not exist or is not a directory: {search_dir}")

    if not search_dir.exists():
        verbose_log(
            f"[resolver] search dir does not exist, skipping: {search_dir}",
            verbose=verbose,
            quiet=quiet,
        )
        return [], None

    if not search_dir.is_dir():
        raise ValidationError(f"Search dir is not a directory: {search_dir}")

    manifest_path = find_manifest_file(search_dir)
    if manifest_path is None:
        if fail_on_missing_manifest:
            raise ValidationError(
                f"No supported manifest found in search dir {search_dir}. "
                f"Expected one of: {', '.join(MANIFEST_FILENAMES)}"
            )
        verbose_log(
            f"[resolver] no manifest found in search dir, skipping: {search_dir}",
            verbose=verbose,
            quiet=quiet,
        )
        return [], None

    data = load_manifest_file(manifest_path)
    if data is None:
        data = {}

    if not isinstance(data, dict):
        raise ValidationError(f"Manifest root must be an object/mapping in {manifest_path}")

    hotfixes = data.get("hotfixes", [])
    if hotfixes is None:
        hotfixes = []
    if not isinstance(hotfixes, list):
        raise ValidationError(f"'hotfixes' must be a list in manifest {manifest_path}")

    entries: List[HotfixEntry] = []
    seen_ids_in_manifest: Set[str] = set()

    for item in hotfixes:
        entry = parse_hotfix_entry(
            item,
            manifest_path=manifest_path,
            source_dir=search_dir,
            search_dir_index=search_dir_index,
        )
        if entry.hotfix_id in seen_ids_in_manifest:
            raise ValidationError(
                f"Duplicate hotfix id {entry.hotfix_id!r} in manifest {manifest_path}"
            )
        seen_ids_in_manifest.add(entry.hotfix_id)
        entries.append(entry)

    verbose_log(
        f"[resolver] loaded manifest {manifest_path} with {len(entries)} hotfixes",
        verbose=verbose,
        quiet=quiet,
    )
    return entries, manifest_path


def load_all_hotfix_entries(
    search_dirs: List[Path],
    *,
    fail_on_missing_manifest: bool,
    strict_search_dir: bool,
    verbose: bool,
    quiet: bool,
) -> Tuple[Dict[str, HotfixEntry], List[OverrideRecord], List[str], List[str]]:
    resolved: Dict[str, HotfixEntry] = {}
    overrides: List[OverrideRecord] = []
    loaded_manifest_paths: List[str] = []
    skipped_dirs: List[str] = []

    for idx, search_dir in enumerate(search_dirs):
        entries, manifest_path = load_manifest_entries(
            search_dir,
            search_dir_index=idx,
            fail_on_missing_manifest=fail_on_missing_manifest,
            strict_search_dir=strict_search_dir,
            verbose=verbose,
            quiet=quiet,
        )

        if manifest_path is None:
            skipped_dirs.append(str(search_dir))
            continue

        loaded_manifest_paths.append(str(manifest_path))

        for entry in entries:
            if entry.hotfix_id in resolved:
                prev = resolved[entry.hotfix_id]
                overrides.append(
                    OverrideRecord(
                        hotfix_id=entry.hotfix_id,
                        replaced_manifest_path=str(prev.manifest_path),
                        replacement_manifest_path=str(entry.manifest_path),
                        replaced_search_dir_index=prev.search_dir_index,
                        replacement_search_dir_index=entry.search_dir_index,
                    )
                )
                verbose_log(
                    f"[resolver] override hotfix id={entry.hotfix_id} "
                    f"from {prev.manifest_path} to {entry.manifest_path}",
                    verbose=verbose,
                    quiet=quiet,
                )
            resolved[entry.hotfix_id] = entry

    return resolved, overrides, loaded_manifest_paths, skipped_dirs


def load_trivy_report(path: Path) -> TrivyData:
    data = load_json_file(path)
    if not isinstance(data, dict):
        raise ValidationError(f"Trivy report root must be a JSON object: {path}")

    results = data.get("Results", [])
    if results is None:
        results = []
    if not isinstance(results, list):
        raise ValidationError(f"Trivy report 'Results' must be a list: {path}")

    trivy = TrivyData()

    for result in results:
        if not isinstance(result, dict):
            continue

        target = result.get("Target")
        vulnerabilities = result.get("Vulnerabilities", []) or []
        if not isinstance(vulnerabilities, list):
            continue

        for vuln in vulnerabilities:
            if not isinstance(vuln, dict):
                continue

            trivy.vulnerabilities.append(vuln)

            cve = vuln.get("VulnerabilityID")
            if isinstance(cve, str) and cve.strip():
                trivy.unique_cves.add(cve.strip())

            pkg_name = vuln.get("PkgName")
            installed_version = vuln.get("InstalledVersion")
            fixed_version = vuln.get("FixedVersion")
            pkg_path = vuln.get("PkgPath")

            if isinstance(pkg_name, str) and pkg_name.strip():
                occurrence = PackageOccurrence(
                    name=pkg_name.strip(),
                    installed_version=str(installed_version).strip() if installed_version else "",
                    fixed_version=str(fixed_version).strip() if fixed_version else None,
                    vulnerability_id=cve.strip() if isinstance(cve, str) and cve.strip() else None,
                    target=target.strip() if isinstance(target, str) and target.strip() else None,
                    pkg_path=str(pkg_path).strip() if pkg_path else None,
                )
                trivy.package_occurrences.append(occurrence)
                trivy.packages_by_name.setdefault(occurrence.name, []).append(occurrence)

    return trivy


def split_version_revision(version: str) -> Tuple[str, int]:
    """
    Split Alpine-like versions:
      1.2.3-r0 -> ("1.2.3", 0)
      1.2.3    -> ("1.2.3", -1)

    Revision defaults to -1 when absent so:
      1.2.3-r0 > 1.2.3
    """
    version = version.strip()
    m = re.match(r"^(.*?)-r(\d+)$", version)
    if not m:
        return version, -1
    base, rev = m.groups()
    return base, int(rev)


def tokenize_version_base(base: str) -> List[Any]:
    """
    A pragmatic tokenizer for version strings.
    It preserves separators as ordering boundaries by splitting into numeric
    and alphabetic chunks and ignoring separator characters.
    Examples:
      "1.2.3"     -> [1, 2, 3]
      "8.5.5RC1"  -> [8, 5, 5, "rc", 1]
      "1.0_p2"    -> [1, 0, "p", 2]
    """
    tokens: List[Any] = []
    for part in re.findall(r"[0-9]+|[A-Za-z]+", base):
        if part.isdigit():
            tokens.append(int(part))
        else:
            tokens.append(part.lower())
    return tokens


def compare_scalar_tokens(left: Any, right: Any) -> int:
    """
    Compare one token pair.

    Rules:
    - int vs int: numeric compare
    - str vs str: lexical compare, case-insensitive due to preprocessing
    - int > str to keep numeric suffixes ahead of alpha labels in common cases

    This is not a byte-for-byte reimplementation of apk version ordering.
    It is deterministic and good for the version shapes typically found in
    Alpine package reports and Docker image metadata.
    """
    if isinstance(left, int) and isinstance(right, int):
        return (left > right) - (left < right)
    if isinstance(left, str) and isinstance(right, str):
        return (left > right) - (left < right)
    if isinstance(left, int) and isinstance(right, str):
        return 1
    if isinstance(left, str) and isinstance(right, int):
        return -1
    return 0


def compare_versions(left: str, right: str) -> int:
    """
    Compare Alpine-like package versions.

    Returns:
      -1 if left < right
       0 if left == right
       1 if left > right
    """
    left_base, left_rev = split_version_revision(left)
    right_base, right_rev = split_version_revision(right)

    left_tokens = tokenize_version_base(left_base)
    right_tokens = tokenize_version_base(right_base)

    max_len = max(len(left_tokens), len(right_tokens))
    for i in range(max_len):
        if i >= len(left_tokens):
            # Missing trailing token sorts before existing trailing token.
            return -1
        if i >= len(right_tokens):
            return 1

        cmp_result = compare_scalar_tokens(left_tokens[i], right_tokens[i])
        if cmp_result != 0:
            return cmp_result

    return (left_rev > right_rev) - (left_rev < right_rev)


def version_satisfies(installed_version: str, constraints: Iterable[Tuple[str, str]]) -> bool:
    for op, expected in constraints:
        cmp_result = compare_versions(installed_version, expected)
        if op == "==":
            if cmp_result != 0:
                return False
        elif op == ">":
            if cmp_result <= 0:
                return False
        elif op == ">=":
            if cmp_result < 0:
                return False
        elif op == "<":
            if cmp_result >= 0:
                return False
        elif op == "<=":
            if cmp_result > 0:
                return False
        else:
            raise ValidationError(f"Unsupported comparator operator: {op}")
    return True


def normalize_extra_hotfixes(extra_hotfixes_csv: str, extra_hotfix_list: List[str]) -> List[str]:
    requested: List[str] = []
    if extra_hotfixes_csv.strip():
        for item in extra_hotfixes_csv.split(","):
            item = item.strip()
            if item:
                requested.append(item)
    for item in extra_hotfix_list:
        item = item.strip()
        if item:
            requested.append(item)

    seen: Set[str] = set()
    deduped: List[str] = []
    for item in requested:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def match_hotfix_by_cves(entry: HotfixEntry, trivy: TrivyData) -> List[str]:
    reasons: List[str] = []
    if not entry.match_cves:
        return reasons

    for cve in entry.match_cves:
        if cve in trivy.unique_cves:
            reasons.append(f"cve:{cve}")
    return reasons


def match_hotfix_by_packages(entry: HotfixEntry, trivy: TrivyData) -> List[str]:
    reasons: List[str] = []
    if not entry.match_packages:
        return reasons

    for package_constraint in entry.match_packages:
        occurrences = trivy.packages_by_name.get(package_constraint.name, [])
        if not occurrences:
            continue

        if not package_constraint.constraints:
            # Match on package presence alone.
            for occ in occurrences:
                version = occ.installed_version or "unknown"
                reason = f"package:{occ.name}@{version}"
                if reason not in reasons:
                    reasons.append(reason)
            continue

        for occ in occurrences:
            installed_version = occ.installed_version
            # If Trivy does not expose an installed version, a versioned rule
            # cannot match safely.
            if not installed_version:
                continue
            if version_satisfies(installed_version, package_constraint.constraints):
                reason = f"package:{occ.name}@{installed_version}"
                if reason not in reasons:
                    reasons.append(reason)

    return reasons


def resolve_selected_hotfixes(
    hotfixes_by_id: Dict[str, HotfixEntry],
    trivy: TrivyData,
    requested_extra_hotfixes: List[str],
    *,
    fail_on_unknown_extra_hotfix: bool,
) -> Dict[str, SelectedHotfix]:
    selected: Dict[str, SelectedHotfix] = {}

    # Manual selection first so manual-only entries get into the result set
    # even if they have no automatic match rules.
    for hotfix_id in requested_extra_hotfixes:
        entry = hotfixes_by_id.get(hotfix_id)
        if entry is None:
            if fail_on_unknown_extra_hotfix:
                raise UnknownExtraHotfixError(f"Unknown extra hotfix id: {hotfix_id}")
            continue
        selected.setdefault(hotfix_id, SelectedHotfix(entry=entry)).add_reason(f"manual:{hotfix_id}")

    for hotfix_id, entry in hotfixes_by_id.items():
        cve_reasons = match_hotfix_by_cves(entry, trivy)
        pkg_reasons = match_hotfix_by_packages(entry, trivy)

        if cve_reasons or pkg_reasons:
            item = selected.setdefault(hotfix_id, SelectedHotfix(entry=entry))
            for reason in cve_reasons + pkg_reasons:
                item.add_reason(reason)

    return selected


def compute_unmatched_cves(
    trivy: TrivyData,
    selected: Dict[str, SelectedHotfix],
) -> List[str]:
    matched_cves: Set[str] = set()

    for selected_item in selected.values():
        for reason in selected_item.reasons:
            if reason.startswith("cve:"):
                matched_cves.add(reason.split(":", 1)[1])

    # A package-based match may cover CVEs implicitly, but there is no fully safe
    # one-to-one mapping without adopting explicit "coverage" metadata in the manifest.
    # Therefore this report defines "matched CVE" conservatively:
    # a CVE is counted as matched only if it triggered a cve:<id> reason.
    #
    # This behavior keeps reporting honest and deterministic. If you later want
    # package-based hotfixes to mark CVEs as covered, add an explicit "covers.cves"
    # section to the manifest and extend this function.
    return sorted(cve for cve in trivy.unique_cves if cve not in matched_cves)


def compute_unmatched_packages(
    trivy: TrivyData,
    selected: Dict[str, SelectedHotfix],
) -> List[str]:
    matched_packages: Set[str] = set()
    all_packages: Set[str] = set(trivy.packages_by_name.keys())

    for selected_item in selected.values():
        for reason in selected_item.reasons:
            if reason.startswith("package:"):
                payload = reason.split(":", 1)[1]
                pkg_name = payload.split("@", 1)[0]
                matched_packages.add(pkg_name)

    return sorted(all_packages - matched_packages)


def copy_selected_hotfixes(
    selected: Dict[str, SelectedHotfix],
    copy_to: Path,
    *,
    clean_copy_dir: bool,
    selection_manifest_name: str,
    report_data: Dict[str, Any],
) -> List[str]:
    copied_files: List[str] = []

    if copy_to.exists() and clean_copy_dir:
        for child in copy_to.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)

    copy_to.mkdir(parents=True, exist_ok=True)

    # Stable copy order helps debugging and makes CI diffs predictable.
    ordered_entries = sorted(
        selected.values(),
        key=lambda item: (
            item.entry.search_dir_index,
            item.entry.hotfix_id,
            item.entry.file_name,
        ),
    )

    for selected_item in ordered_entries:
        src = selected_item.entry.file_path
        dst = copy_to / src.name
        shutil.copy2(src, dst)
        # Enforce executability because these files are expected to be runnable shell scripts.
        current_mode = dst.stat().st_mode
        dst.chmod(current_mode | 0o111)
        copied_files.append(str(dst))

    selection_manifest_path = copy_to / selection_manifest_name
    with selection_manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(report_data, fh, indent=2, sort_keys=True)
        fh.write("\n")

    copied_files.append(str(selection_manifest_path))
    return copied_files


def build_report(
    *,
    trivy_path: Path,
    search_dirs: List[Path],
    loaded_manifest_paths: List[str],
    skipped_dirs: List[str],
    trivy: TrivyData,
    hotfixes_by_id: Dict[str, HotfixEntry],
    overrides: List[OverrideRecord],
    selected: Dict[str, SelectedHotfix],
    requested_extra_hotfixes: List[str],
) -> Dict[str, Any]:
    ordered_selected = sorted(
        selected.values(),
        key=lambda item: (
            item.entry.search_dir_index,
            item.entry.hotfix_id,
            item.entry.file_name,
        ),
    )

    selected_hotfix_ids = [item.entry.hotfix_id for item in ordered_selected]
    selected_files = [str(item.entry.file_path) for item in ordered_selected]
    matched_by = {
        item.entry.hotfix_id: sorted(item.reasons)
        for item in ordered_selected
    }

    unmatched_cves = compute_unmatched_cves(trivy, selected)
    unmatched_packages = compute_unmatched_packages(trivy, selected)

    return {
        "trivy_report": str(trivy_path),
        "search_dirs": [str(p) for p in search_dirs],
        "loaded_manifests": loaded_manifest_paths,
        "skipped_search_dirs": skipped_dirs,
        "requested_extra_hotfixes": requested_extra_hotfixes,
        "selected_hotfix_ids": selected_hotfix_ids,
        "selected_files": selected_files,
        "matched_by": matched_by,
        "unmatched_cves": unmatched_cves,
        "unmatched_packages": unmatched_packages,
        "overrides": [
            {
                "hotfix_id": item.hotfix_id,
                "replaced_manifest_path": item.replaced_manifest_path,
                "replacement_manifest_path": item.replacement_manifest_path,
                "replaced_search_dir_index": item.replaced_search_dir_index,
                "replacement_search_dir_index": item.replacement_search_dir_index,
            }
            for item in overrides
        ],
        "stats": {
            "trivy_vulnerability_records": len(trivy.vulnerabilities),
            "trivy_unique_cves": len(trivy.unique_cves),
            "trivy_package_occurrences": len(trivy.package_occurrences),
            "trivy_unique_packages": len(trivy.packages_by_name),
            "resolved_hotfix_definitions": len(hotfixes_by_id),
            "selected_hotfixes": len(selected_hotfix_ids),
            "overridden_hotfix_definitions": len(overrides),
        },
        "resolved_hotfixes": {
            hotfix_id: entry.to_dict()
            for hotfix_id, entry in sorted(hotfixes_by_id.items(), key=lambda kv: kv[0])
        },
    }


def write_output_json(report: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")


def print_summary(report: Dict[str, Any], *, quiet: bool) -> None:
    if quiet:
        return

    stats = report["stats"]
    log(
        "[resolver] loaded manifests: "
        f"{len(report['loaded_manifests'])}, "
        f"resolved hotfix definitions: {stats['resolved_hotfix_definitions']}, "
        f"selected hotfixes: {stats['selected_hotfixes']}",
        quiet=quiet,
    )
    log(
        "[resolver] trivy: "
        f"{stats['trivy_vulnerability_records']} vulnerability records, "
        f"{stats['trivy_unique_cves']} unique CVEs, "
        f"{stats['trivy_unique_packages']} unique packages",
        quiet=quiet,
    )

    if report["selected_hotfix_ids"]:
        log(
            "[resolver] selected hotfix ids: " + ", ".join(report["selected_hotfix_ids"]),
            quiet=quiet,
        )
    else:
        log("[resolver] selected hotfix ids: none", quiet=quiet)

    if report["unmatched_cves"]:
        log(
            "[resolver] unmatched CVEs: " + ", ".join(report["unmatched_cves"]),
            quiet=quiet,
        )
    else:
        log("[resolver] unmatched CVEs: none", quiet=quiet)


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    quiet = bool(args.quiet)
    verbose = bool(args.verbose)

    try:
        trivy_path = Path(args.trivy).resolve()
        search_dirs = [Path(p).resolve() for p in args.search_dirs]

        requested_extra_hotfixes = normalize_extra_hotfixes(
            args.extra_hotfixes,
            args.extra_hotfix,
        )

        hotfixes_by_id, overrides, loaded_manifest_paths, skipped_dirs = load_all_hotfix_entries(
            search_dirs,
            fail_on_missing_manifest=bool(args.fail_on_missing_manifest),
            strict_search_dir=bool(args.strict_search_dir),
            verbose=verbose,
            quiet=quiet,
        )

        trivy = load_trivy_report(trivy_path)

        if args.validate_only:
            report = build_report(
                trivy_path=trivy_path,
                search_dirs=search_dirs,
                loaded_manifest_paths=loaded_manifest_paths,
                skipped_dirs=skipped_dirs,
                trivy=trivy,
                hotfixes_by_id=hotfixes_by_id,
                overrides=overrides,
                selected={},
                requested_extra_hotfixes=requested_extra_hotfixes,
            )

            if args.output:
                write_output_json(report, Path(args.output).resolve())
            if args.print_json:
                print(json.dumps(report, indent=2, sort_keys=True))
            print_summary(report, quiet=quiet)
            return 0

        selected = resolve_selected_hotfixes(
            hotfixes_by_id,
            trivy,
            requested_extra_hotfixes,
            fail_on_unknown_extra_hotfix=bool(args.fail_on_unknown_extra_hotfix),
        )

        report = build_report(
            trivy_path=trivy_path,
            search_dirs=search_dirs,
            loaded_manifest_paths=loaded_manifest_paths,
            skipped_dirs=skipped_dirs,
            trivy=trivy,
            hotfixes_by_id=hotfixes_by_id,
            overrides=overrides,
            selected=selected,
            requested_extra_hotfixes=requested_extra_hotfixes,
        )

        copied_files: List[str] = []
        if args.copy_to:
            copied_files = copy_selected_hotfixes(
                selected,
                Path(args.copy_to).resolve(),
                clean_copy_dir=bool(args.clean_copy_dir),
                selection_manifest_name=str(args.selection_manifest_name),
                report_data=report,
            )
            report["copied_files"] = copied_files

        if args.output:
            write_output_json(report, Path(args.output).resolve())

        if args.print_json:
            print(json.dumps(report, indent=2, sort_keys=True))

        print_summary(report, quiet=quiet)

        if copied_files and not quiet:
            log("[resolver] copied files:", quiet=quiet)
            for item in copied_files:
                log(f"  - {item}", quiet=quiet)

        if args.fail_on_unmatched_cves and report["unmatched_cves"]:
            return 3

        return 0

    except UnknownExtraHotfixError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ResolverError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
