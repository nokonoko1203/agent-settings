#!/usr/bin/env python3
"""Offline protocol stub, not a semantic review. Counter path is relative to report root."""

import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--verdict", choices=["成立", "飛躍あり", "矛盾"], default="成立")
parser.add_argument("--counter", type=Path)
args = parser.parse_args()
payload = json.load(sys.stdin)
if set(payload) != {"conclusion", "premises"} or not isinstance(payload["premises"], list):
    sys.exit(2)
for row in [payload["conclusion"], *payload["premises"]]:
    if set(row) != {"id", "kind", "text"}:
        sys.exit(2)
if args.counter:
    args.counter.parent.mkdir(parents=True, exist_ok=True)
    with args.counter.open("a", encoding="utf-8") as stream:
        stream.write(payload["conclusion"]["id"] + "\n")
print(json.dumps({"verdict": args.verdict, "reason": "通信しない定型スタブによる判定"}, ensure_ascii=False))
