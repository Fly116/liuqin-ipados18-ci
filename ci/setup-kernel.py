#!/usr/bin/env python3
"""写入 runner 本地路径，确保内核读取同轮用户态 UUID。"""
import json
import os
from pathlib import Path
import subprocess

root = Path.cwd()
device = root / 'device'
developer = subprocess.check_output(['xcode-select', '-p'], text=True).strip()
inputs = {'tree': str(root / 'tree'), 'developer_dir': developer,
          'volume_layout': str(root / 'volume-input/volume-layout.json'),
          'sheng_source': str(device / 'UniXNU-sheng/package')}
(device / 'local.toml').write_text('[pong_build]\n' + ''.join(
    f'{key} = {json.dumps(value)}\n' for key, value in inputs.items()))
values = {'PONG_VOLUME_LAYOUT': inputs['volume_layout'],
          'UNIXNU_DEVICE': str(device), 'PONG_SHENG_ROOT': str(device / 'UniXNU-sheng')}
for key, command in {'PONG_MIG': ['xcrun', '-f', 'mig'],
                     'PONG_MIGCOM': ['xcrun', '-f', 'migcom'],
                     'PONG_IOS_SDK': ['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'],
                     'XNU_SDKVERSION': ['xcrun', '--sdk', 'iphoneos', '--show-sdk-version']}.items():
    values[key] = subprocess.check_output(command, text=True).strip()
values['XNU_SDKROOT'] = values['PONG_IOS_SDK']
with Path(os.environ['GITHUB_ENV']).open('a') as stream:
    for key, value in values.items():
        stream.write(f'{key}={value}\n')
print('已写入 runner 本地构建路径与工具链配置')
