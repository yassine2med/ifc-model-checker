import json
from pathlib import Path

import pytest

from ifccheck.__main__ import main
from ifccheck.checker import check_model, load_rules, summarise
from ifccheck.ifc import ParseError, parse

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_office.ifc"

MINI = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCOWNERHISTORY($,$,$,.NOCHANGE.,$,$,$,0);
#2=IFCPROJECT('0000000000000000000001',#1,'P',$,$,$,$,$,$);
#3=IFCSITE('0000000000000000000002',#1,'S',$,$,$,$,$,.ELEMENT.,$,$,$,$,$);
#4=IFCBUILDING('0000000000000000000003',#1,'B',$,$,$,$,$,.ELEMENT.,$,$,$);
#5=IFCBUILDINGSTOREY('0000000000000000000004',#1,'L1',$,$,$,$,$,.ELEMENT.,0.);
#6=IFCWALL('0000000000000000000005',#1,'It''s a wall',$,$,$,$,$,$);
#7=IFCRELCONTAINEDINSPATIALSTRUCTURE('0000000000000000000006',#1,$,$,(#6),#5);
ENDSEC;
END-ISO-10303-21;
"""


@pytest.fixture(scope="module")
def sample_issues():
    return check_model(parse(SAMPLE.read_text()), load_rules(None))


def rules_hit(issues):
    return {(i.rule, i.name) for i in issues}


def test_parser_reads_all_entities():
    assert len(parse(SAMPLE.read_text()).entities) == 231


def test_parser_handles_escaped_quote():
    model = parse(MINI)
    assert model.by_type("IFCWALL")[0].name == "It's a wall"


def test_parser_rejects_non_ifc():
    with pytest.raises(ParseError):
        parse("hello")


def test_minimal_model_has_only_material_warning():
    issues = check_model(parse(MINI), load_rules(None))
    assert {i.rule for i in issues} == {"material-required", "property-required"}
    assert all(i.severity == "warning" for i in issues)


def test_duplicate_guid_found(sample_issues):
    dup = [i for i in sample_issues if i.rule == "guid-unique"]
    assert {i.name for i in dup} == {"Ceiling Tile A", "Ceiling Tile B"}


def test_short_guid_found(sample_issues):
    assert ("guid-valid", "Reception Desk") in rules_hit(sample_issues)


def test_orphan_wall_found(sample_issues):
    assert ("storey-required", "Orphan Wall X1") in rules_hit(sample_issues)


def test_missing_material_found(sample_issues):
    assert ("material-required", "Interior Partition P2") in rules_hit(sample_issues)


def test_empty_name_found(sample_issues):
    assert any(i.rule == "name-required" and i.entity_type == "IFCWALL" for i in sample_issues)


def test_missing_fire_rating_found(sample_issues):
    names = {i.name for i in sample_issues if i.rule == "property-required"}
    assert names == {"Exterior Wall N2", "Door D02"}


def test_errors_sorted_first(sample_issues):
    severities = [i.severity for i in sample_issues]
    assert severities == sorted(severities, key=lambda s: s != "error")


def test_strict_rules_flag_small_space():
    issues = check_model(parse(SAMPLE.read_text()), load_rules(str(SAMPLE.parent / "rules_strict.json")))
    small = {i.name for i in issues if i.rule == "space-area"}
    assert small == {"Storage"}


def test_summary_counts_walls():
    assert summarise(parse(SAMPLE.read_text()))["IFCWALL"] == 8


def test_cli_exit_codes(capsys):
    assert main(["check", str(SAMPLE)]) == 1
    assert main(["check", str(SAMPLE.parent / "missing.ifc")]) == 2
    assert main(["rules"]) == 0


def test_cli_json_output(capsys):
    main(["check", str(SAMPLE), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert any(item["rule"] == "guid-unique" for item in data)
