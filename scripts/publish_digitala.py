#!/usr/bin/env python3
"""Adopted host command; all authority comes from the existing holder's sealed task."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.check_issuer import DigitalaPublisher, HostIssuer
from runtime.integration import GateClosed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True)
    arguments = parser.parse_args()
    try:
        receipt = DigitalaPublisher(HostIssuer()).publish_sealed(arguments.task)
    except (GateClosed, OSError, ValueError, KeyError):
        # Never echo private request contents or transport error bodies.
        print(json.dumps({'published': False, 'reason': 'Host publication refused; inspect private observations'}))
        return 2
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
