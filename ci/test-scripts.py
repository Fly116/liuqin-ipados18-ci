#!/usr/bin/env python3
"""在独立临时目录验证源码摊平、精确补丁与输入保护。"""
import argparse
import ast
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--mesa', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    for path in here.glob('*.py'):
        data = path.read_bytes()
        assert b'\r' not in data, path
        ast.parse(data, filename=str(path))
    args.scratch.mkdir(parents=True, exist_ok=False)
    device = args.scratch / 'device'
    subprocess.run([sys.executable, '-I', str(here / 'prepare-device.py'),
                    str(args.source), str(device)], check=True)
    for name in ('board.toml', 'metal/bridge/build-report.json',
                 'drivers/PongAdreno/submit/NativeAdrenoABI.h',
                 'UniXNU-sheng/package'):
        assert (device / name).exists(), name
    original = args.mesa / 'src/freedreno/vulkan/tu_knl_darwin.cc'
    target = args.scratch / 'mesa/src/freedreno/vulkan/tu_knl_darwin.cc'
    target.parent.mkdir(parents=True)
    disk_before = original.read_bytes()
    before = subprocess.check_output(['git', '-C', str(args.mesa), 'show',
                                      'HEAD:src/freedreno/vulkan/tu_knl_darwin.cc'])
    target.write_bytes(before)
    module = load(here / 'patch-turnip.py')
    subprocess.run([sys.executable, '-I', str(here / 'patch-turnip.py'),
                    str(args.scratch / 'mesa')], check=True)
    assert target.read_text(encoding='utf-8') == before.decode().replace(module.OLD, module.NEW)
    assert original.read_bytes() == disk_before
    result = subprocess.run([sys.executable, '-I', str(here / 'patch-turnip.py'),
                             str(args.scratch / 'mesa')], capture_output=True)
    assert result.returncode != 0, '重复应用必须失败'
    print('PASS：Python 语法、LF 行尾、源码摊平、补丁唯一性、重复应用拒绝、原源码未改动')


if __name__ == '__main__':
    main()
