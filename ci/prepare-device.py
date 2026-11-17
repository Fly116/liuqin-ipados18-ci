#!/usr/bin/env python3
"""从固定版本源码创建独立的设备构建目录，不修改上游检出。"""
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    if destination.exists():
        raise SystemExit(f'目标目录已存在：{destination}')
    shutil.copytree(source / 'UniXNU-liuqin', destination)
    for name in ('UniXNU-sheng', 'metal'):
        shutil.copytree(source / name, destination / name)
    print(f'设备源码：{destination}')


if __name__ == '__main__':
    main()
