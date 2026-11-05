#!/usr/bin/env python3
"""Compare an ES|QL JSON response with independently generated expectations."""

import argparse
import json
import math
import sys
from pathlib import Path


def validate(response, expected):
    if response.get("is_partial"):
        raise ValueError("Elasticsearch returned partial results")
    if response.get("warnings"):
        raise ValueError("Elasticsearch returned warnings")
    if "error" in response:
        raise ValueError("Elasticsearch returned an error")
    names = [column["name"] for column in response["columns"]]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate response column names")
    actual = []
    for values in response["values"]:
        if len(values) != len(names):
            raise ValueError("Response row and column lengths differ")
        actual.append(dict(zip(names, values)))
    if len(actual) != len(expected):
        raise ValueError(f"Expected {len(expected)} rows, received {len(actual)}")
    for index, (got, wanted) in enumerate(zip(actual, expected), start=1):
        if got.keys() != wanted.keys():
            raise ValueError(f"Row {index}: response columns differ from expectations")
        for name, value in wanted.items():
            measured = got[name]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                matches = isinstance(measured, (int, float)) and not isinstance(measured, bool)
                matches = matches and math.isclose(measured, value, rel_tol=1e-8, abs_tol=1e-6)
            else:
                matches = measured == value
            if not matches:
                raise ValueError(f"Row {index}, {name}: expected {value!r}, received {measured!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    parser.add_argument("expected", type=Path)
    parser.add_argument("query", help="Query file stem, for example 01-inspect")
    args = parser.parse_args()
    try:
        response = json.loads(args.response.read_text())
        expected = json.loads(args.expected.read_text())[args.query]
        validate(response, expected)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL {args.query}: {exc}", file=sys.stderr)
        return 1
    print(f"PASS {args.query}: {len(expected)} rows match independent expectations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
