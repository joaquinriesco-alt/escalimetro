#!/usr/bin/env python3
"""E44 — CLI de la campaña. Sin red: trabaja con bundles capturados fuera del ejecutor.

    import <bundle_dir> | status | index | run-improve <id> | run-create <id> [--confirm-paid]
    correct <id> "<texto>" | close <id> [--minutes N] | reveal <id> | exclude <id> "<motivo>"
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from webapp import campaign, store                                  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd")
    ap.add_argument("arg", nargs="?")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--confirm-paid", action="store_true")
    ap.add_argument("--minutes", type=float)
    a = ap.parse_args(argv)
    if a.cmd in ("import", "run-improve", "run-create", "correct", "close", "reveal"):
        store.init()
    if a.cmd == "import":
        out = campaign.import_bundle(a.arg)
    elif a.cmd == "status":
        out = campaign.summary()
    elif a.cmd == "index":
        out = campaign.build_index()
    elif a.cmd == "run-improve":
        out = campaign.run_improve(a.arg)
    elif a.cmd == "run-create":
        out = campaign.run_create(a.arg, confirm_paid=a.confirm_paid)
    elif a.cmd == "correct":
        out = campaign.correct_create(a.arg, a.text, confirm_paid=a.confirm_paid)
    elif a.cmd == "close":
        out = campaign.close_blind(a.arg, human_minutes=a.minutes)
    elif a.cmd == "reveal":
        out = campaign.reveal(a.arg)
    elif a.cmd == "exclude":
        campaign.exclude(a.arg, a.text or "")
        out = "ok"
    else:
        ap.error("comando desconocido")
    print(out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
