"""Rule checks on a parsed IFC model."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .ifc import GUID_CHARS, Model

DEFAULT_RULES = {
    "require_name": ["IFCWALL", "IFCDOOR", "IFCWINDOW", "IFCSLAB", "IFCCOLUMN", "IFCBEAM",
                     "IFCCOVERING", "IFCFURNISHINGELEMENT", "IFCSPACE"],
    "require_storey": ["IFCWALL", "IFCDOOR", "IFCWINDOW", "IFCSLAB", "IFCCOLUMN", "IFCBEAM",
                       "IFCCOVERING", "IFCFURNISHINGELEMENT"],
    "require_material": ["IFCWALL", "IFCDOOR", "IFCWINDOW", "IFCSLAB", "IFCCOLUMN", "IFCBEAM"],
    "required_properties": {
        "IFCWALL": ["Pset_WallCommon.FireRating", "Pset_WallCommon.IsExternal"],
        "IFCDOOR": ["Pset_DoorCommon.FireRating"],
        "IFCWINDOW": ["Pset_WindowCommon.ThermalTransmittance"],
    },
    "min_space_area": 1.0,
}

SEVERITY = {
    "project-structure": "error",
    "guid-valid": "error",
    "guid-unique": "error",
    "name-required": "warning",
    "storey-required": "error",
    "material-required": "warning",
    "property-required": "warning",
    "space-area": "error",
}


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str
    entity_id: int | None
    entity_type: str
    name: str
    message: str

    def line(self) -> str:
        who = f"#{self.entity_id} {self.entity_type} '{self.name}'" if self.entity_id else "model"
        return f"{self.severity.upper():7} {self.rule}: {who}: {self.message}"

    def as_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "id": self.entity_id,
                "type": self.entity_type, "name": self.name, "message": self.message}


def load_rules(path: str | None) -> dict:
    rules = json.loads(json.dumps(DEFAULT_RULES))
    if path:
        with open(path, encoding="utf-8") as handle:
            rules.update(json.load(handle))
    return rules


def _issue(rule, e, message):
    return Issue(rule, SEVERITY[rule], e.id if e else None, e.type if e else "", e.name if e else "", message)


def _upper(items):
    return [t.upper() for t in items]


def space_area(model: Model, space) -> float | None:
    quantities = model.quantities(space)
    for key in ("NetFloorArea", "GrossFloorArea"):
        if key in quantities:
            return quantities[key]
    return None


def check_model(model: Model, rules: dict | None = None) -> list[Issue]:
    rules = rules or DEFAULT_RULES
    issues: list[Issue] = []

    projects = model.by_type("IFCPROJECT")
    if len(projects) != 1:
        issues.append(_issue("project-structure", None, f"expected exactly 1 IfcProject, found {len(projects)}"))
    for kind in ("IFCSITE", "IFCBUILDING", "IFCBUILDINGSTOREY"):
        if not model.by_type(kind):
            issues.append(_issue("project-structure", None, f"no {kind} in the model"))

    rooted = [e for e in model.entities.values() if isinstance(e.arg(0), str) and len(e.args) > 2
              and e.type not in ("IFCPROPERTYSINGLEVALUE", "IFCMATERIAL")
              and not e.type.startswith("IFCQUANTITY")]
    rooted = [e for e in rooted if e.type.startswith("IFC") and e.arg(1) is not None]
    seen: dict[str, list] = {}
    for e in rooted:
        gid = e.global_id
        if len(gid) != 22 or not set(gid) <= GUID_CHARS:
            issues.append(_issue("guid-valid", e, f"GlobalId '{gid}' is not a 22 character IFC GUID"))
        seen.setdefault(gid, []).append(e)
    for gid, group in seen.items():
        if len(group) > 1:
            for e in group:
                others = ", ".join(f"#{o.id}" for o in group if o is not e)
                issues.append(_issue("guid-unique", e, f"GlobalId '{gid}' is also used by {others}"))

    for kind in _upper(rules.get("require_name", [])):
        for e in model.by_type(kind):
            if not e.name.strip():
                issues.append(_issue("name-required", e, "Name is empty"))
    for kind in _upper(rules.get("require_storey", [])):
        for e in model.by_type(kind):
            if model.storey(e) is None:
                issues.append(_issue("storey-required", e, "not placed in any building storey"))
    for kind in _upper(rules.get("require_material", [])):
        for e in model.by_type(kind):
            if model.material(e) is None:
                issues.append(_issue("material-required", e, "no material assigned"))
    for kind, wanted in rules.get("required_properties", {}).items():
        for e in model.by_type(kind.upper()):
            props = model.properties(e)
            for path in wanted:
                pset, _, prop = path.partition(".")
                value = props.get(pset, {}).get(prop)
                if value is None or value == "":
                    issues.append(_issue("property-required", e, f"missing property {path}"))
    minimum = float(rules.get("min_space_area", 0))
    for e in model.by_type("IFCSPACE"):
        area = space_area(model, e)
        if area is None:
            issues.append(_issue("space-area", e, "no area quantity"))
        elif area < minimum:
            issues.append(_issue("space-area", e, f"area {area:g} is below the minimum {minimum:g}"))
    return sorted(issues, key=lambda i: (i.severity != "error", i.rule, i.entity_id or 0))


def summarise(model: Model) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in model.entities.values():
        counts[e.type] = counts.get(e.type, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
