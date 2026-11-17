#!/usr/bin/env python3
"""使用 macOS iPhoneOS SDK 编译并按 4 KiB 页签名 22H374 libpong-ui18.dylib。"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    device = args.device.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    developer = subprocess.check_output(['xcode-select', '-p'], text=True).strip()
    env = {'DEVELOPER_DIR': developer}
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'],
                                  env=env, text=True).strip()
    destination = output / 'libpong-ui.dylib'
    sources = [
        device / 'userland/ui_compat18.c',
        device / 'userland/settings_compat18.c',
        device / 'userland/boot_snapshot18.c',
        device / 'userland/touch.c',
        device / 'userland/sileo_spawn.c',
    ]
    cmd = [
        'xcrun', '--sdk', 'iphoneos', 'clang',
        '-target', 'arm64-apple-ios18.0',
        '-isysroot', sdk,
        '-Os', '-fblocks', '-dynamiclib', '-Wall', '-Wextra', '-Werror',
        '-Wl,-no_fixup_chains',
        '-install_name', '/pong/libpong-ui18.dylib',
        '-framework', 'CoreFoundation',
        '-framework', 'CoreGraphics',
        '-lobjc',
        *map(str, sources),
        '-o', str(destination),
    ]
    subprocess.run(cmd, env=env, check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', '--pagesize', '4096', str(destination)], check=True)
    shutil.copy2(destination, output / 'libpong-ui18.dylib')
    (output / 'ui-compile-command.json').write_text(json.dumps(cmd, indent=2) + '\n', encoding='utf-8')
    print(f'已编译并签名 {destination} ({destination.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
