#!/usr/bin/env python3
"""在 liuqin 提交线程上刷新命令缓冲的写合并映射。"""
import argparse
from pathlib import Path

OLD = '''   for (unsigned i = 0; i < num_entries; i++) {
      cmds[i] = (NativeAdrenoAbiSubmitBuffer) {'''
NEW = '''   for (unsigned i = 0; i < num_entries; i++) {
      /* liuqin 的写合并映射必须由提交线程在交给 GPU 前刷出。 */
      if (entries[i].bo->map)
         tu_bo_sync_cache(device, (struct tu_bo *)entries[i].bo,
                          entries[i].offset, entries[i].size,
                          TU_MEM_SYNC_CACHE_TO_GPU);
      cmds[i] = (NativeAdrenoAbiSubmitBuffer) {'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesa', type=Path)
    path = parser.parse_args().mesa / 'src/freedreno/vulkan/tu_knl_darwin.cc'
    data = path.read_bytes()
    if b'\r' in data:
        raise SystemExit('源文件不是 LF 行尾，停止修改')
    text = data.decode('utf-8')
    if text.count(OLD) != 1:
        raise SystemExit('提交函数与固定基线不一致，停止修改')
    path.write_bytes(text.replace(OLD, NEW).encode('utf-8'))
    print('已应用 liuqin 命令提交缓存修复')


if __name__ == '__main__':
    main()
