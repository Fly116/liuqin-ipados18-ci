#!/usr/bin/env python3
"""收集用户态构建记录与布局，不在明文日志输出系统文件。"""
import os
from pathlib import Path
import shutil

out = Path('products')
out.mkdir(exist_ok=True)
for pattern in ('volume-layout.json', 'userland-report.json', 'sparse-report.json', 'ufs/*'):
    for path in Path('.').glob(pattern):
        if path.is_file():
            shutil.copy2(path, out / path.name)
prepared = Path(os.environ['RUNNER_TEMP']) / 'userland'
for name in ('result.json', 'apply-complete.json', 'build-plan.json'):
    source = prepared / name
    if source.is_file():
        shutil.copy2(source, out / name)
(out / 'status.txt').write_text('userland_complete=' + str((prepared / 'apply-complete.json').is_file()) + '\n')
