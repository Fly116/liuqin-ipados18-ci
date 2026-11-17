#!/usr/bin/env python3
"""拒绝占位卷布局，防止内核与根卷 UUID 不一致。"""
import argparse
import json
from pathlib import Path
import uuid


def check(path):
    layout = json.loads(path.read_text())
    if layout.get('ci_placeholder'):
        raise ValueError('卷布局仍为占位符')
    identifiers = [str(uuid.UUID(layout[key]['uuid'])).upper()
                   for key in ('os', 'systemos', 'data')]
    if len(set(identifiers)) != 3:
        raise ValueError('三个卷必须具有不同 UUID')
    return layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layout', type=Path)
    parser.add_argument('report', type=Path, nargs='?')
    args = parser.parse_args()
    layout = check(args.layout)
    if args.report:
        report = json.loads(args.report.read_text())
        if report.get('build') != '22H374':
            raise SystemExit('用户态不是 22H374')
    for role in ('os', 'systemos', 'data'):
        print(role, layout[role]['uuid'])


if __name__ == '__main__':
    main()
