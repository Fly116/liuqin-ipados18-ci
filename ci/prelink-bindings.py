#!/usr/bin/env python3
"""按真实 kernelcache 和预链接 slide 生成 GPU 父类绑定输入。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tomllib


def calculate(device, kernelcache):
    spec = importlib.util.spec_from_file_location('native_prelink', device / 'kits/NativePrelink/native_prelink.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module.arm64_image(kernelcache.read_bytes())
    image = module.macho(data)
    names = {'__PRELINK_TEXT', '__PLK_TEXT_EXEC', '__PLK_DATA_CONST', '__PRELINK_DATA'}
    segments = [s for s in image['segments'] if s['name'] in names and s['size']]
    if {s['name'] for s in segments} != names:
        raise ValueError('kernelcache 缺少预链接段')
    base = min(s['va'] for s in segments)
    abi = json.loads((device / 'configs/pong-iogpu-22H374.json').read_text())
    if base != int(abi['original_prelink_base'], 16):
        raise ValueError('真实 kernelcache 与 GPU ABI 地址基线不一致')
    board = tomllib.loads((device / 'board.toml').read_text())
    slide = int(board['kernel']['prelink']['slide'], 0)
    if slide % 4096:
        raise ValueError('预链接 slide 未按 4KiB 对齐')
    for key in ('constructor', 'destructor', 'metaclass', 'metaclass_constructor'):
        module.backed_offset(image['segments'], int(abi[key], 16), 8, len(data))
    return {'build': '22H374', 'fixed_prelink_base': hex(base + slide),
            'original_prelink_base': hex(base), 'slide': hex(slide),
            'kernelcache_sha256': hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', type=Path)
    parser.add_argument('kernelcache', type=Path)
    args = parser.parse_args()
    result = calculate(args.device.resolve(), args.kernelcache.resolve())
    output = args.device / 'mac-build/native-ufs/bindings.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
