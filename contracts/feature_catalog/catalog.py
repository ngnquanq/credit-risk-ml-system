"""Feature definitions and the checks every model feature set must pass (E2).

Definitions live in ``definitions/*.yaml`` (one file per producing group). Ordered model
inputs live in ``sets/<version>.json`` and are resolved by
``feature_preprocessing.load_feature_set``. This module answers whether a set is
acceptable: every entry is defined, protected attributes are excluded, and every
input is available in the online store. It also maps features to the reason codes
shown to applicants (E14).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

_ROOT = Path(__file__).resolve().parent
_GROUPS = ("application", "external", "dwh")
_SENSITIVITY = ("none", "sensitive", "protected")
_DTYPES = ("float", "category")
_LOCALES = ("en", "vi")
# Sets trained before the catalog existed may keep protected inputs; nothing else may.
_STATUSES = ("legacy", "candidate", "approved")


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    group: str
    dtype: str
    producer: str
    feast_field: str
    description: str
    sensitivity: str = "none"
    proxy_for: str | None = None
    reason_code: str | None = None
    valid_min: float | None = None
    valid_max: float | None = None
    sentinel: float | None = None

    @property
    def explainable(self) -> bool:
        """Whether this feature may appear as an applicant-facing reason."""
        return self.reason_code is not None and self.sensitivity == "none" and self.proxy_for is None


@dataclass(frozen=True)
class CatalogCheck:
    unresolved: tuple[str, ...]
    protected_used: tuple[str, ...]
    sensitive_used: tuple[str, ...]
    status: str

    @property
    def ok(self) -> bool:
        if self.unresolved:
            return False
        return not self.protected_used or self.status == "legacy"


class Catalog:
    def __init__(self, definitions: Mapping[str, FeatureDefinition], reasons: Mapping[str, Mapping[str, str]]):
        self._definitions = dict(definitions)
        self._reasons = {code: dict(texts) for code, texts in reasons.items()}
        missing = sorted(
            {d.reason_code for d in self._definitions.values() if d.reason_code} - set(self._reasons)
        )
        if missing:
            raise ValueError(f"Reason codes without texts: {missing}")
        for code, texts in self._reasons.items():
            absent = [locale for locale in _LOCALES if not texts.get(locale)]
            if absent:
                raise ValueError(f"Reason code {code} lacks texts for {absent}")

    @classmethod
    def load(cls, root: Path | str | None = None) -> "Catalog":
        import yaml  # local import: the training images only need the JSON feature sets

        root = Path(root) if root is not None else _ROOT
        definitions: dict[str, FeatureDefinition] = {}
        for group in _GROUPS:
            entries = yaml.safe_load((root / "definitions" / f"{group}.yaml").read_text(encoding="utf-8")) or []
            for entry in entries:
                definition = _parse_definition(entry, group)
                if definition.name in definitions:
                    raise ValueError(f"Feature {definition.name} is defined more than once")
                definitions[definition.name] = definition
        for definition in definitions.values():
            if definition.proxy_for is not None and definition.proxy_for not in definitions:
                raise ValueError(f"{definition.name} is a proxy for unknown feature {definition.proxy_for}")
        reasons = yaml.safe_load((root / "reasons.yaml").read_text(encoding="utf-8")) or {}
        return cls(definitions, reasons)

    def names(self) -> list[str]:
        return list(self._definitions)

    def __contains__(self, name: str) -> bool:
        return name in self._definitions

    def definition(self, name: str) -> FeatureDefinition:
        try:
            return self._definitions[name]
        except KeyError:
            raise KeyError(f"Feature {name} is not in the catalog") from None

    def check_set(self, columns: Iterable[str], status: str) -> CatalogCheck:
        if status not in _STATUSES:
            raise ValueError(f"Unknown feature set status: {status!r}")
        columns = list(columns)
        known = [c for c in columns if c in self._definitions]
        return CatalogCheck(
            unresolved=tuple(c for c in columns if c not in self._definitions),
            protected_used=tuple(c for c in known if self._definitions[c].sensitivity == "protected"),
            sensitive_used=tuple(c for c in known if self._definitions[c].sensitivity == "sensitive"),
            status=status,
        )

    def missing_from_serving(self, columns: Iterable[str], schema_dir: Path | str) -> list[str]:
        """Columns whose Feast field is absent from the generated serving schemas."""
        served = set()
        for path in Path(schema_dir).glob("*_schema.json"):
            served.update(field["name"] for field in json.loads(path.read_text(encoding="utf-8")))
        return [c for c in columns if self.definition(c).feast_field not in served]

    def reason_code(self, name: str) -> str | None:
        definition = self.definition(name)
        return definition.reason_code if definition.explainable else None

    def reason_text(self, code: str, locale: str = "en") -> str:
        return self._reasons[code][locale]


def load_set_status(version: str, root: Path | str | None = None) -> str:
    root = Path(root) if root is not None else _ROOT
    data = json.loads((root / "sets" / f"{version}.json").read_text(encoding="utf-8"))
    return data.get("status", "candidate")


def _parse_definition(entry: dict, group: str) -> FeatureDefinition:
    if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
        raise ValueError(f"Invalid definition in {group}: {entry!r}")
    unknown = set(entry) - set(FeatureDefinition.__dataclass_fields__) - {"name"}
    if unknown:
        raise ValueError(f"{entry['name']}: unknown keys {sorted(unknown)}")
    definition = FeatureDefinition(
        name=entry["name"],
        group=group,
        dtype=entry.get("dtype", ""),
        producer=entry.get("producer", ""),
        feast_field=entry.get("feast_field", ""),
        description=entry.get("description", ""),
        sensitivity=entry.get("sensitivity", "none"),
        proxy_for=entry.get("proxy_for"),
        reason_code=entry.get("reason_code"),
        valid_min=entry.get("valid_min"),
        valid_max=entry.get("valid_max"),
        sentinel=entry.get("sentinel"),
    )
    if definition.dtype not in _DTYPES:
        raise ValueError(f"{definition.name}: dtype must be one of {_DTYPES}")
    if definition.sensitivity not in _SENSITIVITY:
        raise ValueError(f"{definition.name}: sensitivity must be one of {_SENSITIVITY}")
    for field in ("producer", "feast_field", "description"):
        if not getattr(definition, field):
            raise ValueError(f"{definition.name}: {field} is required")
    return definition
