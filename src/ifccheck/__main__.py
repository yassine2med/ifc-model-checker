"""Command line entry: python -m ifccheck check|summary|rules."""

from __future__ import annotations

import argparse
import json
import sys

from .checker import DEFAULT_RULES, check_model, load_rules, summarise
from .ifc import ParseError, load


def main(argv: list[str] | None = None) -> int:
    """Return 0 when no errors, 1 when errors exist, 2 on a bad or missing file."""
    parser = argparse.ArgumentParser(prog="ifccheck", description="Rule checks for IFC STEP files")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="run the rules on an IFC file")
    check.add_argument("file")
    check.add_argument("--rules", help="JSON file that overrides the default rules")
    check.add_argument("--format", choices=["text", "json"], default="text")
    check.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    summary = sub.add_parser("summary", help="count entities by type")
    summary.add_argument("file")
    sub.add_parser("rules", help="print the default rules as JSON")
    args = parser.parse_args(argv)

    if args.command == "rules":
        print(json.dumps(DEFAULT_RULES, indent=2))
        return 0
    try:
        model = load(args.file)
        if args.command == "summary":
            print(f"schema {model.schema or 'unknown'}, {len(model.entities)} entities")
            for kind, count in list(summarise(model).items())[:15]:
                print(f"{count:4}  {kind}")
            return 0
        issues = check_model(model, load_rules(args.rules))
    except FileNotFoundError as exc:
        print(f"File not found: {exc.filename}", file=sys.stderr)
        return 2
    except (ParseError, json.JSONDecodeError) as exc:
        print(f"Cannot read input: {exc}", file=sys.stderr)
        return 2
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = len(issues) - errors
    if args.format == "json":
        print(json.dumps([i.as_dict() for i in issues], indent=2))
    else:
        for issue in issues:
            print(issue.line())
        print(f"{errors} error(s), {warnings} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
