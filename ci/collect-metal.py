#!/usr/bin/env python3
"""收集图形库产物和失败位置，不公开二进制。"""
from pathlib import Path
import shutil

out = Path('products')
out.mkdir(exist_ok=True)
for name in ('runtime',):
    path = Path(name)
    if path.is_dir():
        shutil.copytree(path, out / name)
for name in ('configure.log', 'build.log', 'build-report.json', 'meson-logs/meson-log.txt'):
    source = Path('turnip-build') / name
    if source.is_file():
        destination = out / 'turnip' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if source.suffix in ('.log', '.txt'):
            print(f'=== {source} ===')
            print('\n'.join(source.read_text(errors='replace').splitlines()[-100:]))
(out / 'status.txt').write_text('runtime_present=' + str((out / 'runtime/build-report.json').is_file()) + '\n')
