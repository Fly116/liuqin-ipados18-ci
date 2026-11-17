#!/usr/bin/env python3
"""等待指定用户态构建的实际卷布局，终止状态缺产物时立即失败。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id', type=int)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    repo = os.environ['GITHUB_REPOSITORY']
    deadline = time.monotonic() + 2400
    prefix = f'repos/{repo}/actions'
    print(f'等待用户态 run {args.run_id} 的非占位卷布局', flush=True)
    while time.monotonic() < deadline:
        items = api(f'{prefix}/runs/{args.run_id}/artifacts')['artifacts']
        matches = [x for x in items if x['name'] == 'volume-layout' and not x['expired']]
        if matches:
            subprocess.run(['gh', 'run', 'download', str(args.run_id), '-R', repo,
                            '-n', 'volume-layout', '-D', str(args.output)], check=True)
            return
        run = api(f'{prefix}/runs/{args.run_id}')
        if run['status'] == 'completed':
            raise SystemExit('用户态构建已结束但没有卷布局：' + str(run['conclusion']))
        time.sleep(30)
    raise SystemExit('等待用户态卷布局超时')


if __name__ == '__main__':
    main()
