#!/usr/bin/env python3
"""对独立设备副本应用 liuqin 无人值守诊断适配。"""
import argparse
import difflib
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def read_lf(path):
    data = path.read_bytes()
    if b'\r' in data:
        raise ValueError(f'{path} 不是 LF 行尾')
    return data.decode('utf-8')


def replace(path, old, new):
    text = read_lf(path)
    if text.count(old) != 1:
        raise ValueError(f'{path} 的固定基线匹配次数不是一')
    path.write_bytes(text.replace(old, new).encode('utf-8'))


def preserve_ramoops(device):
    patch = read_lf(device / 'patches/xnu-ipados18/0001-pong-darwin24.patch')
    relative = 'osfmk/arm64/pong_ramoops_console.h'
    section = patch.split('diff --git a/' + relative + ' b/' + relative + '\n')[1].split('\ndiff --git ', 1)[0]
    before = ''.join(line[1:] + '\n' for line in section.splitlines()
                     if line.startswith('+') and not line.startswith('+++'))
    start = before.index('\theader->sig = 0;\n', before.index('pong_ramoops_console_init(void)'))
    end = before.index('\tstatic const char ready[]', start)
    new = '''\tconst uint32_t capacity = PONG_RAMOOPS_DATA_BYTES;
\tif (header->sig == PONG_RAMOOPS_MAGIC && header->size <= capacity &&
\t    header->start <= capacity) {
\t\tpong_ramoops_size = header->size;
\t\tpong_ramoops_start = header->size < capacity ? 0 : header->start % capacity;
\t} else {
\t\theader->sig = 0;
\t\theader->start = 0;
\t\theader->size = 0;
\t\t__asm__ volatile("dsb sy" ::: "memory");
\t\theader->sig = PONG_RAMOOPS_MAGIC;
\t}
\tCleanPoC_DcacheRegion_Force(mapped, PONG_RAMOOPS_HEADER_BYTES);
\t__asm__ volatile("dsb sy" ::: "memory");
\tpong_ramoops_base = mapped;
\tstruct pong_ramoops_header *diagnostic =
\t    (struct pong_ramoops_header *)(uintptr_t)(mapped + PONG_RAMOOPS_CONSOLE_BYTES);
\t/* pmsg 只追加；保留引导器写下的阶段记录。 */
\tif (diagnostic->sig == PONG_RAMOOPS_MAGIC && diagnostic->size <= capacity &&
\t    diagnostic->start == diagnostic->size) {
\t\tpong_diagnostic_size = diagnostic->size;
\t}
'''
    after = before[:start] + new + before[end:]
    output = device / 'patches/xnu-ipados18' / ('z' * 80 + '-liuqin-pong-ramoops-preserve.patch')
    diff = difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                fromfile='a/' + relative, tofile='b/' + relative)
    output.write_bytes(('diff --git a/' + relative + ' b/' + relative + '\n' + ''.join(diff)).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', type=Path)
    device = parser.parse_args().device.resolve()
    platform = device / 'drivers/ArmDTPlatform/ArmDTPlatform.cpp'
    text = read_lf(platform)
    start = text.index('/* The shutdown slider')
    end = text.index('#if XNU_PONG_WIFI', start)
    replace(platform, text[start:end], '#include "LiuqinSession.h"\n')
    shutil.copy2(HERE / 'overrides/LiuqinSession.h', platform.parent / 'LiuqinSession.h')
    config = device / 'configs/liuqin_ipados18_defconfig'
    replace(config, 'CONFIG_XNU_PONG_RAMOOPS_CONSOLE=n', 'CONFIG_XNU_PONG_RAMOOPS_CONSOLE=y')
    replace(config,
            '#   PONG_RAMOOPS_CONSOLE / PONG_VOLATILE_PANIC_LOG: the pong patch writes at the fixed\n'
            "#     0x85200000, inside liuqin's stock PIL reservation; liuqin's ramoops is 0xA7000000.\n",
            '#   ramoops 控制台已适配 liuqin 的 0xA7000000 保留区；不启用独立的 volatile panic 区。\n')
    replace(device / 'patches/xnu-ipados18/0001-pong-darwin24.patch',
            '+#define PONG_RAMOOPS_PHYS_BASE 0x85200000ULL',
            '+#define PONG_RAMOOPS_PHYS_BASE 0xA7000000ULL')
    preserve_ramoops(device)
    ufs = device / 'drivers/NativeUfs/PongUfsTransport.cpp'
    replace(ufs,
            'static uint32_t gPongLogEnabled, gPongLogWritten, gPongLogFlushes;',
            'static uint32_t gPongLogEnabled, gPongLogWritten, gPongLogFlushes;\n'
            'static uint32_t gPongLogMaxFlushes = 240;')
    replace(ufs, '    if (gPongLogFlushes >= 240) return; // ~20 min at 5 s',
            '    if (gPongLogFlushes >= gPongLogMaxFlushes) return;')
    replace(ufs, '    if (gPongLogEnabled || !layout.imageBytes) return;',
            '    if (gPongLogEnabled || !layout.imageBytes) return;\n'
            '    PE_parse_boot_argn("pong_log_flushes", &gPongLogMaxFlushes, sizeof(gPongLogMaxFlushes));')
    print('已应用 liuqin 会话复位、日志时限、ramoops 地址与引导记录保留适配')


if __name__ == '__main__':
    main()
