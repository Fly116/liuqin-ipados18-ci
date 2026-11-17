#!/usr/bin/env python3
"""收集原生/预链接内核、工具输入与失败日志，统一交给加密步骤。"""
from pathlib import Path
import shutil

out = Path('products')
out.mkdir(exist_ok=True)
roots = [Path('UniXNU/out'), Path('tree/build'), Path('device/mac-build')]
files = set()
names = {'kernel.macho', 'kernel.json', 'kernel.failed.json', 'mach.development.pong',
         'hardware.dtb', 'kernelcache.decompressed', 'PONG_BUILD_RESULT.json', '.config',
         'bindings.json', 'PongIOAcceleratorBindings.S', 'build-report.json'}
for root in roots:
    if not root.exists():
        continue
    for path in root.rglob('*'):
        if path.is_file() and (path.name in names or path.suffix == '.log'):
            files.add(path)
for pattern in ('build-*.log', 'kernel-build.log', 'PONG_BUILD_RESULT.json',
                'device/local.toml', 'volume-input/*.json'):
    files.update(path for path in Path('.').glob(pattern) if path.is_file())
for path in sorted(files):
    destination = out / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    if path.suffix == '.log':
        lines = path.read_text(errors='replace').splitlines()
        errors = [line for line in lines if any(x in line.lower() for x in
                  ('error:', 'fatal error', 'traceback', 'exception', 'failed', 'no such file'))]
        if errors:
            print(f'=== {path}: errors ===')
            print('\n'.join(errors[-40:]))
        print(f'=== {path}: tail ===')
        print('\n'.join(line for line in lines[-80:] if 'INSTALLHDR' not in line))
(out / 'status.txt').write_text('kernel_candidates=' + str(len(list(out.rglob('kernel.macho')))) + '\n')
