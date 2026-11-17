#!/usr/bin/env python3
"""加密构建产物；密码只从环境读取，不写入产物或日志。"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--split', action='store_true')
    args = parser.parse_args()
    password = os.environ.get('ARTIFACT_PASSWORD', '')
    if len(password) < 12:
        raise SystemExit('缺少有效的产物密码')
    directory = args.directory.resolve()
    output = args.output.resolve()
    if not directory.is_dir() or not any(directory.iterdir()):
        raise SystemExit('产物目录不存在或为空')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or list(output.parent.glob(output.name + '.*')):
        raise SystemExit('拒绝覆盖现有加密归档')
    tool = shutil.which('7zz') or shutil.which('7z')
    if not tool:
        raise SystemExit('缺少 sevenzip')
    command = [tool, 'a', '-t7z', '-mx=1', '-mhe=on', '-bsp0', '-bso0',
               '-p' + password]
    if args.split:
        command.append('-v1900m')
    subprocess.run([*command, str(output), '.'], cwd=directory, check=True)
    first = Path(str(output) + '.001') if args.split else output
    subprocess.run([tool, 't', '-bsp0', '-bso0', '-p' + password, str(first)], check=True)
    for path in sorted(output.parent.glob(output.name + '*')):
        digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
        print(f'{path.name} {path.stat().st_size} sha256={digest}')


if __name__ == '__main__':
    main()
