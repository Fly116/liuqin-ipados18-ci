#!/usr/bin/env python3
"""第一波（候选 39）设备源码适配补丁：满血 CPU/GPU 调频、256B 零拷贝表面、核心外设与 UI 适配。"""
import argparse
import difflib
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent

TOUCH_PATCHES = (
    'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-liuqin-touch-irq-gating.patch',
    'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-liuqin-touch-idle.patch',
    'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-touch-fault-pattern.patch',
    'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-touch-hardware-irq.patch',
    'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-touch-raw-latch.patch',
)

EXTRA_XNU_PATCHES = (
    'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-liuqin-icache-phystokv.patch',
    'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-liuqin-osmetaclass-kextlock.patch',
)

GPU_OPPS = (
    (818000000, 384),
    (818000000, 384),
    (791000000, 320),
    (734000000, 256),
    (640000000, 224),
    (599000000, 192),
    (545000000, 144),
    (492000000, 128),
    (421000000, 80),
    (350000000, 64),
    (317000000, 64),
    (285000000, 56),
    (220000000, 56),
)


def replace_exact(path: Path, old: str, new: str) -> None:
    """在保持原有换行风格的前提下执行唯一精确替换。"""
    raw = path.read_bytes()
    crlf = b'\r\n' in raw
    text = raw.replace(b'\r\n', b'\n').decode('utf-8')
    if text.count(old) != 1:
        raise ValueError(f'{path} 的匹配锚点出现次数不是 1（实际 {text.count(old)} 次）')
    updated = text.replace(old, new)
    if crlf:
        updated = updated.replace('\n', '\r\n')
    path.write_bytes(updated.encode('utf-8'))


def patch_cpu_policy(device: Path) -> None:
    """升级 SM8475 三域最高频率至 liuqin 满血档位并修复低频起步锁死。"""
    policy = device / 'drivers/ArmCpu/PongCpuPolicy.h'
    replace_exact(
        policy,
        'static Domain domains[]={{0,4,1804800},{4,3,2496000},{7,1,2995200}};',
        'static Domain domains[]={{0,4,2016000},{4,3,2745600},{7,1,3187200}};',
    )
    replace_exact(
        policy,
        'if(cores==4 && khz<=d.cap_khz)d.khz[i]=khz;',
        'if((cores==4 || (d.count==1 && cores==2)) && khz<=d.cap_khz)d.khz[i]=khz;',
    )
    replace_exact(
        policy,
        '            unsigned freq=d.khz[current];if(!freq)freq=d.cap_khz;\n'
        '            uint64_t requested=uint64_t(freq)*load*125/10000;\n'
        '            if(load>=90)requested=uint64_t(freq)*2;\n'
        '            unsigned cap=d.cap_khz;\n'
        '            if(d.regs[0x30c/4]&4) {\n'
        '                const unsigned hardware=(d.regs[0x20/4]&255)*19200u;\n'
        '                if(hardware && hardware<cap)cap=hardware;\n'
        '            }',
        '            unsigned freq=d.khz[current];if(!freq)freq=d.cap_khz;\n'
        '            unsigned cap=d.cap_khz;\n'
        '            if(d.regs[0x30c/4]&4) {\n'
        '                const unsigned hardware=(d.regs[0x20/4]&255)*19200u;\n'
        '                if(hardware && hardware<cap)cap=hardware;\n'
        '            }\n'
        '            /* 按域上限而非当前起步低频计算需求，防止大核卡死在 787.2 MHz */\n'
        '            uint64_t requested=uint64_t(cap)*load*125/10000;\n'
        '            if(load>=75)requested=cap;',
    )


def patch_gpu_profile(device: Path) -> None:
    """将 Adreno 730 OPP 表替换为平板 Ubuntu 实测 12 档频率与 GFX 电压。"""
    profile = device / 'drivers/PongAdreno/PongAdrenoPowerProfile.h'
    raw = profile.read_bytes()
    crlf = b'\r\n' in raw
    text = raw.replace(b'\r\n', b'\n').decode('utf-8')
    block_match = re.search(
        r'const PongPowerLevel PongAdrenoPowerLevels\[13\]=\{\n((?:\s*\{[^}]+\},\n){13})\};',
        text,
    )
    if not block_match:
        raise ValueError(f'{profile} 中未找到 13 项 PongAdrenoPowerLevels 定义')
    rows = re.findall(
        r'\{(0x[0-9a-fA-F]+u),(0x[0-9a-fA-F]+u),(0x[0-9a-fA-F]+u),(0x[0-9a-fA-F]+u),(0x[0-9a-fA-F]+u),(0x[0-9a-fA-F]+u),(0x[0-9a-fA-F]+u)\}',
        block_match.group(1),
    )
    if len(rows) != 13:
        raise ValueError(f'{profile} 的 GPU 档位解析数量不是 13')
    if int(rows[0][0].rstrip('u'), 16) != 900000000:
        raise ValueError(f'{profile} 已经改写过，拒绝重复应用')
    rebuilt = []
    for (hz, level), row in zip(GPU_OPPS, rows):
        old_cx = int(row[2].rstrip('u'), 16)
        cx = min(max(old_cx, level), 384)
        rebuilt.append(f'    {{{hex(hz)}u,{hex(level)}u,{hex(cx)}u,{row[3]},{row[4]},{row[5]},{row[6]}}},')
    replacement = 'const PongPowerLevel PongAdrenoPowerLevels[13]={\n' + '\n'.join(rebuilt) + '\n};'
    updated = text[:block_match.start()] + replacement + text[block_match.end():]
    if crlf:
        updated = updated.replace('\n', '\r\n')
    profile.write_bytes(updated.encode('utf-8'))


def patch_iosurface_align(device: Path) -> None:
    """强制内核托管的 IOSurface 按 256B 对齐步长，打通 Turnip 零拷贝直绘。"""
    patches_dir = device / 'patches/xnu-ipados18'
    name = 'z' * 92 + '-liuqin-iosurface-align256.patch'
    target = patches_dir / name
    if target.exists():
        raise ValueError(f'{target} 已存在，拒绝重复应用')
    base_patch = (patches_dir / '0001-pong-darwin24.patch').read_text(encoding='utf-8')
    rel = 'iokit/Kernel/MiniIOSurface.cpp'
    section = base_patch.split('diff --git a/' + rel + ' b/' + rel + '\n')[1].split('\ndiff --git ', 1)[0]
    before = ''.join(line[1:] + '\n' for line in section.splitlines()
                     if line.startswith('+') and not line.startswith('+++'))
    after = before
    repls = (
        ('#define MINISURF_ROW_ALIGN      64\n', '#define MINISURF_ROW_ALIGN      256\n'),
        (
            '\t\t\tp->bytesPerRow = dictNumber(pd, "IOSurfacePlaneBytesPerRow", 0);\n'
            '\t\t\tif (p->bytesPerRow == 0) {\n'
            '\t\t\t\tp->bytesPerRow = alignUp((uint64_t) ((p->width + pew - 1) / pew) * p->bytesPerElement, MINISURF_ROW_ALIGN);\n'
            '\t\t\t}\n'
            '\t\t\tp->size = dictNumber(pd, "IOSurfacePlaneSize", 0);\n'
            '\t\t\tif (p->size == 0) {\n'
            '\t\t\t\tuint64_t planeSize = (uint64_t)p->bytesPerRow * ((p->height + peh - 1) / peh);\n'
            '\t\t\t\tif (planeSize > MINISURF_MAX_ALLOC) {\n'
            '\t\t\t\t\ts->release();\n'
            '\t\t\t\t\treturn NULL;\n'
            '\t\t\t\t}\n'
            '\t\t\t\tp->size = (uint32_t)planeSize;\n'
            '\t\t\t}\n',
            '\t\t\tp->bytesPerRow = dictNumber(pd, "IOSurfacePlaneBytesPerRow", 0);\n'
            '\t\t\tif (p->bytesPerRow == 0) {\n'
            '\t\t\t\tp->bytesPerRow = alignUp((uint64_t) ((p->width + pew - 1) / pew) * p->bytesPerElement, MINISURF_ROW_ALIGN);\n'
            '\t\t\t} else if (wrapped == NULL) {\n'
            '\t\t\t\tp->bytesPerRow = (uint32_t)alignUp((uint64_t) p->bytesPerRow, MINISURF_ROW_ALIGN);\n'
            '\t\t\t}\n'
            '\t\t\tp->size = dictNumber(pd, "IOSurfacePlaneSize", 0);\n'
            '\t\t\t{\n'
            '\t\t\t\tuint64_t minPlaneSize = (uint64_t)p->bytesPerRow * ((p->height + peh - 1) / peh);\n'
            '\t\t\t\tif (p->size == 0 || (wrapped == NULL && p->size < minPlaneSize)) {\n'
            '\t\t\t\t\tif (minPlaneSize > MINISURF_MAX_ALLOC) {\n'
            '\t\t\t\t\t\ts->release();\n'
            '\t\t\t\t\t\treturn NULL;\n'
            '\t\t\t\t\t}\n'
            '\t\t\t\t\tp->size = (uint32_t)minPlaneSize;\n'
            '\t\t\t\t}\n'
            '\t\t\t}\n',
        ),
        (
            '\tbpr = dictNumber(props, "IOSurfaceBytesPerRow", 0);\n'
            '\tif (bpr == 0) {\n'
            '\t\tbpr = planeCount ? s->planes[0].bytesPerRow\n'
            '\t\t    : alignUp((uint64_t) ((width + ew - 1) / ew) * bpe, MINISURF_ROW_ALIGN);\n'
            '\t}\n',
            '\tbpr = dictNumber(props, "IOSurfaceBytesPerRow", 0);\n'
            '\tif (bpr == 0) {\n'
            '\t\tbpr = planeCount ? s->planes[0].bytesPerRow\n'
            '\t\t    : alignUp((uint64_t) ((width + ew - 1) / ew) * bpe, MINISURF_ROW_ALIGN);\n'
            '\t} else if (wrapped == NULL) {\n'
            '\t\tbpr = (uint32_t)alignUp((uint64_t) bpr, MINISURF_ROW_ALIGN);\n'
            '\t\tif (planeCount == 1 && s->planes[0].offset == 0 && bpr > s->planes[0].bytesPerRow) {\n'
            '\t\t\tuint64_t p0Size = (uint64_t)bpr * ((s->planes[0].height + s->planes[0].elementHeight - 1) / s->planes[0].elementHeight);\n'
            '\t\t\tif (p0Size > MINISURF_MAX_ALLOC) {\n'
            '\t\t\t\ts->release();\n'
            '\t\t\t\treturn NULL;\n'
            '\t\t\t}\n'
            '\t\t\ts->planes[0].bytesPerRow = bpr;\n'
            '\t\t\tif (s->planes[0].size < p0Size) s->planes[0].size = (uint32_t)p0Size;\n'
            '\t\t\tif (needed < p0Size) needed = p0Size;\n'
            '\t\t}\n'
            '\t}\n',
        ),
    )
    for old, new in repls:
        if after.count(old) != 1:
            raise ValueError(f'MiniIOSurface.cpp 锚点匹配次数非 1: {old[:40]}')
        after = after.replace(old, new)
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile='a/' + rel,
        tofile='b/' + rel,
    )
    target.write_bytes(('diff --git a/' + rel + ' b/' + rel + '\n' + ''.join(diff)).encode('utf-8'))
    series = patches_dir / 'series'
    if series.is_file():
        replace_exact(
            series,
            'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-console-loghook.patch\n',
            'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-console-loghook.patch\n' + name + '\n',
        )


def patch_touch_and_hall(device: Path) -> None:
    """补齐本地已验证的 NT36532 触控补丁，并加入霍尔磁控开关状态日志。"""
    patches_dir = device / 'patches/xnu-ipados18'
    nt = patches_dir / 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-nt36532.patch'
    replace_exact(
        nt,
        '+\t/* nvt_check_spi_dma_tx_info(): 200 tries, 1 ms apart, 0x00 means the\n'
        '+\t * copy engine has moved the image into ILM and DLM. */\n'
        '+\ttxinfo = 0xff;\n'
        '+\tfor (polls = 0; polls < 200; polls++) {\n'
        '+\t\tuint8_t info[2] = { 0 };\n'
        '+\n'
        '+\t\t(void)tch_nvt_read(NVT_SPI_DMA_TX_INFO, info, sizeof(info));',
        '+\t/* NT36532 的自动复制模式 2 读取 TX_AUTO_COPY_EN，不能读取模式 1 的状态寄存器。\n'
        '+\t * 与 Ubuntu 驱动一致：最多等待 200 次，每次 1ms，0 表示复制完成。 */\n'
        '+\ttxinfo = 0xff;\n'
        '+\tfor (polls = 0; polls < 200; polls++) {\n'
        '+\t\tuint8_t info[1] = { 0 };\n'
        '+\n'
        '+\t\t(void)tch_nvt_read(NVT_TX_AUTO_COPY_EN, info, sizeof(info));',
    )
    for name in (*TOUCH_PATCHES, *EXTRA_XNU_PATCHES):
        src = HERE / 'patches' / name
        dst = patches_dir / name
        if dst.exists():
            raise ValueError(f'{dst} 已存在，拒绝重复应用')
        shutil.copy2(src, dst)

    # 基于 0001-pong-darwin24.patch 中的 bsd/dev/pong_buttons.c 生成霍尔盖子传感器补丁。
    base_patch = (patches_dir / '0001-pong-darwin24.patch').read_text(encoding='utf-8')
    rel = 'bsd/dev/pong_buttons.c'
    section = base_patch.split('diff --git a/' + rel + ' b/' + rel + '\n')[1].split('\ndiff --git ', 1)[0]
    before = ''.join(line[1:] + '\n' for line in section.splitlines()
                     if line.startswith('+') and not line.startswith('+++'))
    after = before
    repls = (
        (
            'static vm_offset_t core,cnfg,observer,channels_base,pdc;',
            'static vm_offset_t core,cnfg,observer,channels_base,pdc,hall_gpio;\nstatic int hall_last=-1;',
        ),
        (
            '    for (unsigned i=0;i<3;i++) keys[i].live=keys[i].usable && !keys[i].last;\n'
            '    printf("Pong keys: arbiter v%u channels=%u PON=%u GPIO6=%u; power=%u up=%u down=%u\\n",\n'
            '        v7?7:5,channels,pon.channel,pin.channel,keys[0].usable,keys[1].usable,keys[2].usable);',
            '    for (unsigned i=0;i<3;i++) keys[i].live=keys[i].usable && !keys[i].last;\n'
            '    unsigned hall_en=0;PE_parse_boot_argn("liuqin_hall_lid",&hall_en,sizeof(hall_en));\n'
            '    if (hall_en==1) hall_gpio=ml_io_map(0x0f10a000,0x1000);\n'
            '    printf("Pong keys: arbiter v%u channels=%u PON=%u GPIO6=%u; power=%u up=%u down=%u hall=%u\\n",\n'
            '        v7?7:5,channels,pon.channel,pin.channel,keys[0].usable,keys[1].usable,keys[2].usable,hall_gpio!=0);',
        ),
        (
            '        failures=good?0:failures+1;',
            '        if (hall_gpio) {\n'
            '            int closed=(rd(hall_gpio+4)&1u)==0?1:0;\n'
            '            if (closed!=hall_last) {\n'
            '                hall_last=closed;\n'
            '                printf("Pong keys: hall lid state=%s\\n",closed?"closed":"open");\n'
            '            }\n'
            '        }\n'
            '        failures=good?0:failures+1;',
        ),
    )
    for old, new in repls:
        if after.count(old) != 1:
            raise ValueError(f'pong_buttons.c 霍尔补丁锚点匹配次数非 1: {old[:40]}')
        after = after.replace(old, new)
    hall_name = 'z' * 94 + '-liuqin-hall-lid.patch'
    hall_path = patches_dir / hall_name
    if hall_path.exists():
        raise ValueError(f'{hall_path} 已存在，拒绝重复应用')
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile='a/' + rel,
        tofile='b/' + rel,
    )
    hall_path.write_bytes(('diff --git a/' + rel + ' b/' + rel + '\n' + ''.join(diff)).encode('utf-8'))


def patch_power_build_script(script_path: Path, is_merged: bool) -> None:
    """更新 build-pong-power-native.py，无 TFA98xx 容器时编出占位声卡配置并选中 LiuqinBacklight。"""
    if is_merged:
        old_audio = (
            ' if not minimal:\n'
            "  subprocess.run([os.sys.executable,str(ROOT/'scripts/prepare-pong-audio.py'),'--container',str(input_path('audio_container')),'--output',str(out/'PongAmpProfiles.h')],check=True)\n"
        )
        new_audio = (
            ' if not minimal:\n'
            '  try:\n'
            "   container=input_path('audio_container')\n"
            '  except Exception:\n'
            '   container=None\n'
            "  if container and container.is_file():\n"
            "   subprocess.run([os.sys.executable,str(ROOT/'scripts/prepare-pong-audio.py'),'--container',str(container),'--output',str(out/'PongAmpProfiles.h')],check=True)\n"
            '  else:\n'
            "   (out/'PongAmpProfiles.h').write_text('#define PONG_AMP_PROFILES_ABSENT 1\\nstruct PongAmpField {unsigned field,value;};\\nstatic constexpr PongAmpField kPongAmp0[]={{0,0}};\\nstatic constexpr PongAmpField kPongAmp1[]={{0,0}};\\n')\n"
        )
    else:
        old_audio = (
            " subprocess.run([os.sys.executable,str(ROOT/'scripts/prepare-pong-audio.py'),"
            "'--container',str(pong_paths.audio_inputs()/'tfa98xx.cnt'),'--output',str(out/'PongAmpProfiles.h')],check=True)\n"
        )
        new_audio = (
            " container=pong_paths.audio_inputs()/'tfa98xx.cnt'\n"
            ' if container.is_file():\n'
            "  subprocess.run([os.sys.executable,str(ROOT/'scripts/prepare-pong-audio.py'),'--container',str(container),'--output',str(out/'PongAmpProfiles.h')],check=True)\n"
            ' else:\n'
            "  (out/'PongAmpProfiles.h').write_text('#define PONG_AMP_PROFILES_ABSENT 1\\nstruct PongAmpField {unsigned field,value;};\\nstatic constexpr PongAmpField kPongAmp0[]={{0,0}};\\nstatic constexpr PongAmpField kPongAmp1[]={{0,0}};\\n')\n"
        )
    replace_exact(script_path, old_audio, new_audio)
    replace_exact(
        script_path,
        " backlight='PongBacklightKtz.cpp' if os.environ.get('PONG_BACKLIGHT_KTZ8866')=='1' else 'PongBacklight.cpp'\n",
        " backlight='LiuqinBacklight.cpp' if (ROOT/'drivers/PongPower/LiuqinBacklight.cpp').is_file() else ('PongBacklightKtz.cpp' if os.environ.get('PONG_BACKLIGHT_KTZ8866')=='1' else 'PongBacklight.cpp')\n",
    )
    replace_exact(
        script_path,
        "  if name in ('PongBacklight.cpp','PongBacklightKtz.cpp'):obj=late_init(obj,name,'PongBacklightStaticInit')",
        "  if name in ('PongBacklight.cpp','PongBacklightKtz.cpp','LiuqinBacklight.cpp'):obj=late_init(obj,name,'PongBacklightStaticInit')",
    )


def patch_power_backlight_adsp(device: Path) -> None:
    """启用 PongPower + LiuqinBacklight + ADSP(0x9fd00000/RAM) 并防止关机钩子顶掉重启复位。"""
    defconfig = device / 'configs/liuqin_ipados18_defconfig'
    replace_exact(defconfig, 'CONFIG_XNU_PONG_BACKLIGHT=n', 'CONFIG_XNU_PONG_BACKLIGHT=y')
    replace_exact(defconfig, 'CONFIG_XNU_PONG_POWER=n', 'CONFIG_XNU_PONG_POWER=y')

    dst_bl = device / 'drivers/PongPower/LiuqinBacklight.cpp'
    if dst_bl.exists():
        raise ValueError(f'{dst_bl} 已存在，拒绝重复应用')
    shutil.copy2(HERE / 'overrides/LiuqinBacklight.cpp', dst_bl)

    patch_power_build_script(device / 'kits/PongPlatform24/build-support/merged-scripts/build-pong-power-native.py', True)
    patch_power_build_script(device / 'scripts/build-pong-power-native.py', False)

    # 同步修复直跑 scripts/ 下对 XNU_PONG_POWER 的判断与宏透传。
    replace_exact(
        device / 'scripts/build-pong-platform-macos.py',
        "        '-DXNU_PONG_WIFI='+env.get('XNU_PONG_WIFI','0'),\n",
        "        '-DXNU_PONG_POWER='+env.get('XNU_PONG_POWER','0'),\n"
        "        '-DXNU_PONG_WIFI='+env.get('XNU_PONG_WIFI','0'),\n",
    )
    replace_exact(
        device / 'scripts/build-xnu-ipados18.sh',
        'if [ "${XNU_PONG_WIFI:-0}" = 1 ] || [ "${XNU_PONG_BACKLIGHT:-0}" = 1 ]; then\n'
        '  python3 "$PONG_NATIVE_DRIVER_SOURCE/scripts/build-pong-power-native.py" --tree "$ROOT"',
        'if [ "${XNU_PONG_POWER:-0}" = 1 ] || [ "${XNU_PONG_WIFI:-0}" = 1 ] || [ "${XNU_PONG_BACKLIGHT:-0}" = 1 ]; then\n'
        '  python3 "$PONG_NATIVE_DRIVER_SOURCE/scripts/build-pong-power-native.py" --tree "$ROOT"',
    )
    replace_exact(
        device / 'scripts/build-xnu-ipados18.sh',
        '  if [ "${XNU_PONG_WIFI:-0}" = 1 ] || [ "${XNU_PONG_BACKLIGHT:-0}" = 1 ]; then\n'
        '    POWER_ARCHIVE=$ROOT/build/pong-power/libPongPower.a',
        '  if [ "${XNU_PONG_POWER:-0}" = 1 ] || [ "${XNU_PONG_WIFI:-0}" = 1 ] || [ "${XNU_PONG_BACKLIGHT:-0}" = 1 ]; then\n'
        '    POWER_ARCHIVE=$ROOT/build/pong-power/libPongPower.a',
    )

    replace_exact(
        device / 'drivers/PongPower/PongAudio.cpp',
        'extern "C" void sheng_audio_probe(void){unsigned mode=0;PE_parse_boot_argn("pong_audio",&mode,sizeof mode);if(!mode||lock)return;',
        'extern "C" void sheng_audio_probe(void){unsigned mode=0;PE_parse_boot_argn("pong_audio",&mode,sizeof mode);if(!mode||lock)return;\n'
        '#if defined(PONG_AMP_PROFILES_ABSENT)\n'
        ' IOLog("PongAudio: CS35L41 board has no TFA98xx profiles; audio stays off\\n");return;\n'
        '#endif\n',
    )

    # 移除 PongPower 的关机钩子，保留 LiuqinSession 的看门狗/自动回程重启；并解耦 USB 与音频初始化。
    pong_power = device / 'drivers/PongPower/PongPower.cpp'
    replace_exact(
        pong_power,
        'static int (*previous_halt_restart)(unsigned int);\n'
        'static uint32_t pong_panic_latched;\n'
        'static int\n'
        'pong_halt_restart(unsigned int type)\n'
        '{\n'
        '    /* The XNU shutdown slider reaches PEHaltRestart(kPEHaltCPU); the stock\n'
        '     * Pong platform has no handler, so the CPUs spin forever. PSCI\n'
        '     * SYSTEM_OFF / SYSTEM_RESET is the firmware\'s own power path (the same\n'
        '     * conduit PongBootCapture uses for its reset target). */\n'
        '    /* XNU reports kPEPanicBegin / kPEPanicRestartCPU before the panic path\n'
        '     * calls halt_all_cpus(). Keep the previous behaviour there (CPUs spin,\n'
        '     * panic text stays on screen) instead of power-cycling it away. */\n'
        '    if (type == kPEPanicBegin || type == kPEPanicRestartCPU ||\n'
        '        type == kPEPanicRestartCPUNoCallouts) {\n'
        '        __atomic_store_n(&pong_panic_latched, 1, __ATOMIC_RELEASE);\n'
        '        return previous_halt_restart ? previous_halt_restart(type) : -1;\n'
        '    }\n'
        '    if (type == kPEHaltCPU || type == kPERestartCPU) {\n'
        '        if (__atomic_load_n(&pong_panic_latched, __ATOMIC_ACQUIRE)) {\n'
        '            return previous_halt_restart ? previous_halt_restart(type) : -1;\n'
        '        }\n'
        '        register uint64_t x0 __asm__("x0") = (type == kPEHaltCPU) ? 0x84000008u : 0x84000009u;\n'
        '        register uint64_t x1 __asm__("x1") = 0;\n'
        '        register uint64_t x2 __asm__("x2") = 0;\n'
        '        register uint64_t x3 __asm__("x3") = 0;\n'
        '        __asm__ volatile("smc #0" : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)\n'
        '                         :: "memory", "x4", "x5", "x6", "x7", "x8", "x9",\n'
        '                            "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17");\n'
        '        return -1;\n'
        '    }\n'
        '    return previous_halt_restart ? previous_halt_restart(type) : -1;\n'
        '}\n'
        'void pong_power_start_optional(void) {\n'
        ' pong_rpmh_init();\n'
        ' static uint32_t halt_installed;\n'
        ' if (!__atomic_exchange_n(&halt_installed, 1, __ATOMIC_ACQ_REL)) {\n'
        '  previous_halt_restart = PE_halt_restart;\n'
        '  PE_halt_restart = pong_halt_restart;\n'
        ' }\n'
        '#ifndef PONG_POWER_BACKLIGHT_ONLY\n'
        ' // Register the transport classes independently of ADSP readiness. Actual\n'
        ' // USB/audio services still publish only after their own hardware succeeds.\n'
        ' if(pong_audio_service_classes_ready())PongUsb::start();',
        'void pong_power_start_optional(void) {\n'
        ' pong_rpmh_init();\n'
        '#ifndef PONG_POWER_BACKLIGHT_ONLY\n'
        ' // 仅在显式启用 USB 或 ADSP 时预注册音频/USB 服务类，同时底层 OSMetaClass 已修复锁序死锁。\n'
        ' unsigned usb_en=0,adsp_en=0;\n'
        ' PE_parse_boot_argn("pong_usb",&usb_en,sizeof usb_en);\n'
        ' PE_parse_boot_argn("pong_adsp",&adsp_en,sizeof adsp_en);\n'
        ' if(usb_en==1 || adsp_en>=1)(void)pong_audio_service_classes_ready();\n'
        ' PongUsb::start();',
    )

    replace_exact(
        device / 'drivers/PongUsb/PongUsbPhy.h',
        ' const uint8_t params[][2]={{6,0x40},{7,0x22},{8,0x64}};',
        ' const uint8_t params[][2]={{6,0x40},{7,0x00},{8,0x63},{0x0a,0x03}};',
    )
    usb_dev = device / 'drivers/PongUsb/PongUsbDevice.h'
    replace_exact(
        usb_dev,
        ' const char *value=index==1?(iphoneIdentity?"Apple Inc.":"UniXNU Pong"):\n'
        '  index==2?(iphoneIdentity?"iPhone":muxEnabled?"Pong iOS USB + console":"Pong XNU console"):\n'
        '  index==3?(native?serial:"PONG-SM8475"):index==4?"Pong XNU console":"";',
        ' const char *value=index==1?(iphoneIdentity?"Apple Inc.":"UniXNU Liuqin"):\n'
        '  index==2?(iphoneIdentity?"iPhone":muxEnabled?"Liuqin iOS USB + console":"Liuqin XNU console"):\n'
        '  index==3?(native?serial:"LIUQIN-SM8475"):index==4?"Liuqin XNU console":"";',
    )
    replace_exact(
        usb_dev,
        ' core.w(DWC3_DEVTEN,0xf);log.open(0x85200000,0x200000);',
        ' core.w(DWC3_DEVTEN,0xf);log.open(0xa7000000,0x200000);',
    )
    replace_exact(
        usb_dev,
        ' const int online=pong_battery_usb_online();if(online<0 || bool(online)==cableConnected)return;',
        ' int online=pong_battery_usb_online();\n'
        ' if(online<0){unsigned vbus=0;PE_parse_boot_argn("liuqin_usb_vbus",&vbus,sizeof vbus);if(vbus==1)online=1;}\n'
        ' if(online<0 || bool(online)==cableConnected)return;',
    )

    adsp = device / 'drivers/PongPower/PongAdsp.cpp'
    replace_exact(
        adsp,
        '#include <pexpert/pexpert.h>',
        '#include <pexpert/pexpert.h>\n'
        '#include <pexpert/device_tree.h>\n'
        'extern "C" bool pong_ufs_ready(void) __attribute__((weak_import));\n'
        'extern "C" void pong_log_panic_flush(void) __attribute__((weak_import));',
    )
    replace_exact(
        adsp,
        'constexpr uint64_t kAdspBase = 0x85700000, kAdspSize = 0x2800000, kDtbBase = 0x9e980000, kDtbSize = 0x80000;',
        'constexpr uint64_t kAdspBase = 0x9fd00000, kAdspSize = 0x3100000, kDtbBase = 0x9e980000, kDtbSize = 0x80000;',
    )
    replace_exact(
        adsp,
        'struct Image {  // plain data, zero at start: the two live in static storage (a few KiB of header table each, kept off the stack)\n'
        '    void *file;\n'
        '    uint64_t size;\n'
        '    QcomMdtImage mdt;\n'
        '    IOBufferMemoryDescriptor *meta;\n'
        '    bool metaPrepared;\n'
        '};',
        'struct Image {  // plain data, zero at start: the two live in static storage (a few KiB of header table each, kept off the stack)\n'
        '    void *file;\n'
        '    IOMemoryMap *ramMap;\n'
        '    const uint8_t *ramBytes;\n'
        '    uint64_t size;\n'
        '    QcomMdtImage mdt;\n'
        '    IOBufferMemoryDescriptor *meta;\n'
        '    bool metaPrepared;\n'
        '};',
    )
    replace_exact(
        adsp,
        'int fileRead(void *context, uint64_t offset, void *to, size_t length) {return sheng_fw_read(context, offset, to, length);}\n'
        'void release(Image &image) {\n'
        '    if (image.file) sheng_fw_close(image.file);\n'
        '    if (image.meta) {if(image.metaPrepared)image.meta->complete();image.meta->release();}\n'
        '    image.file = nullptr; image.meta = nullptr;image.metaPrepared=false;\n'
        '}\n'
        'int openImage(Image &image, const char *path) {\n'
        '    int rc = sheng_fw_open(path, &image.file, &image.size);\n'
        '    if (rc) {image.file = nullptr; return rc;}\n'
        '    rc = qcom_mdt_parse(&image.mdt, image.size, fileRead, image.file);\n'
        '    return rc ? 1000 - rc : 0;\n'
        '}',
        'int readImage(const Image &image, uint64_t offset, void *to, size_t length) {\n'
        '    if (image.ramBytes) {\n'
        '        if (offset > image.size || length > image.size - offset) return EINVAL;\n'
        '        memcpy(to, image.ramBytes + offset, length);\n'
        '        return 0;\n'
        '    }\n'
        '    return sheng_fw_read(image.file, offset, to, length);\n'
        '}\n'
        'int fileRead(void *context, uint64_t offset, void *to, size_t length) {\n'
        '    return readImage(*static_cast<const Image *>(context), offset, to, length);\n'
        '}\n'
        'void release(Image &image) {\n'
        '    if (image.file) sheng_fw_close(image.file);\n'
        '    if (image.ramMap) image.ramMap->release();\n'
        '    if (image.meta) {if(image.metaPrepared)image.meta->complete();image.meta->release();}\n'
        '    image.file = nullptr; image.ramMap = nullptr; image.ramBytes = nullptr;\n'
        '    image.meta = nullptr; image.metaPrepared = false;\n'
        '}\n'
        'int openImage(Image &image, const char *path) {\n'
        '    DTEntry chosen = nullptr;\n'
        '    const void *prop = nullptr;\n'
        '    unsigned propSize = 0;\n'
        '    if (strcmp(path, "/pong/firmware/adsp.mbn") == 0 &&\n'
        '        SecureDTLookupEntry(nullptr, "/chosen", &chosen) == kSuccess &&\n'
        '        SecureDTGetProperty(chosen, "pong-adsp-fw-range", &prop, &propSize) == kSuccess &&\n'
        '        propSize == 16) {\n'
        '        uint64_t range[2] = {};\n'
        '        memcpy(range, prop, sizeof(range));\n'
        '        if (range[0] && range[1] && range[1] <= 64ULL * 1024 * 1024) {\n'
        '            IODeviceMemory *mem = IODeviceMemory::withRange(range[0], range[1]);\n'
        '            IOMemoryMap *map = mem ? mem->map(kIOMapAnywhere | kIOMapWriteCombineCache) : nullptr;\n'
        '            if (mem) mem->release();\n'
        '            if (!map) return ENOMEM;\n'
        '            image.ramMap = map;\n'
        '            image.ramBytes = reinterpret_cast<const uint8_t *>(map->getVirtualAddress());\n'
        '            image.size = range[1];\n'
        '            IOLog("PongAdsp: using RAM-staged adsp.mbn pa=0x%llx bytes=%llu\\n",\n'
        '                  (unsigned long long)range[0], (unsigned long long)range[1]);\n'
        '            int rc = qcom_mdt_parse(&image.mdt, image.size, fileRead, &image);\n'
        '            return rc ? 1000 - rc : 0;\n'
        '        }\n'
        '    }\n'
        '    int rc = sheng_fw_open(path, &image.file, &image.size);\n'
        '    if (rc) {image.file = nullptr; return rc;}\n'
        '    rc = qcom_mdt_parse(&image.mdt, image.size, fileRead, &image);\n'
        '    return rc ? 1000 - rc : 0;\n'
        '}',
    )
    replace_exact(
        adsp,
        '    if (qcom_mdt_metadata(&image.mdt, fileRead, image.file, va, bytes)) return -5;',
        '    if (qcom_mdt_metadata(&image.mdt, fileRead, &image, va, bytes)) return -5;',
    )
    replace_exact(
        adsp,
        '            if (file && sheng_fw_read(image.file, s.file_offset + done, bounce, file)) {rc = -5; break;}',
        '            if (file && readImage(image, s.file_offset + done, bounce, file)) {rc = -5; break;}',
    )
    replace_exact(
        adsp,
        'void adspThread(void *, wait_result_t) {\n'
        '    thread_set_thread_name(current_thread(), "pong_adsp");\n'
        '    unsigned mode = 0;\n'
        '    PE_parse_boot_argn("pong_adsp", &mode, sizeof mode);',
        'void adspThread(void *, wait_result_t) {\n'
        '    thread_set_thread_name(current_thread(), "pong_adsp");\n'
        '    unsigned mode = 0;\n'
        '    PE_parse_boot_argn("pong_adsp", &mode, sizeof mode);\n'
        '    if (!mode) {\n'
        '        releaseFirmwareScratch();\n'
        '        return;\n'
        '    }\n'
        '    for (unsigned waited = 0; pong_ufs_ready && !pong_ufs_ready() && waited < 300; ++waited) {\n'
        '        IOSleep(100);\n'
        '    }\n'
        '    IOSleep(3000);\n'
        '    IOLog("PongAdsp: starting deferred worker mode=%u ufs_ready=%d\\n",\n'
        '          mode, pong_ufs_ready ? (pong_ufs_ready() ? 1 : 0) : -1);\n'
        '    if (pong_log_panic_flush) pong_log_panic_flush();',
    )
    replace_exact(
        adsp,
        '    stage(StSurveyed);\n    const bool loaded=mode>=2 && start();',
        '    stage(StSurveyed);\n'
        '    IOLog("PongAdsp: surveyed; entering PAS start=%d\\n", mode >= 2 ? 1 : 0);\n'
        '    if (pong_log_panic_flush) pong_log_panic_flush();\n'
        '    const bool loaded=mode>=2 && start();',
    )


def patch_userland_ui(device: Path) -> None:
    """开启 PONG_IOSURFACE_PADDING=1 环境变量传递并同步 lsd 无无线绕过补丁。"""
    dst = device / 'userland/liuqin_mg_wifi18.h'
    if dst.exists():
        raise ValueError(f'{dst} 已存在，拒绝重复应用')
    shutil.copy2(HERE / 'overrides/liuqin_mg_wifi18.h', dst)

    ui = device / 'userland/ui_compat18.c'
    replace_exact(
        ui,
        '    fprintf(stderr,"Pong UI18: 22H374 %s selected\\n",label);return true;\n}',
        '    fprintf(stderr,"Pong UI18: 22H374 %s selected\\n",label);return true;\n}\n\n#include "liuqin_mg_wifi18.h"',
    )
    replace_exact(
        ui,
        '__attribute__((constructor)) static void pong_ui18_start(void)\n'
        '{\n'
        '    const char *name=getprogname();\n'
        '    if(!name)return;\n',
        '__attribute__((constructor)) static void pong_ui18_start(void)\n'
        '{\n'
        '    const char *name=getprogname();\n'
        '    if(!name)return;\n'
        '    if(boot_option("liuqin_iosurface_pad=1"))\n'
        '        setenv("PONG_IOSURFACE_PADDING","1",0);\n',
    )
    replace_exact(
        ui,
        '    if(strcmp(name,"lsd")==0) {\n'
        '        launchservices_process=true;\n',
        '    if(strcmp(name,"lsd")==0) {\n'
        '        launchservices_process=true;\n'
        '        if(boot_option("liuqin_lsd_nowifi=1"))\n'
        '            _dyld_register_func_for_add_image(liuqin_mg_wifi_image);\n',
    )


def patch_console_loghook(device: Path) -> None:
    """将 UFS 控制台抓包点提前到 disableConsoleOutput 之前，避免静音后丢日志。"""
    hook = device / 'patches/xnu-ipados18/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-console-loghook.patch'
    raw = hook.read_bytes()
    if b'\r' in raw:
        raise ValueError(f'{hook} 不是 LF 行尾')
    text = raw.decode('utf-8')
    if 'cons_ops[idx].putc(c, poll);' not in text:
        raise ValueError(f'{hook} 缺少预期的 _cnputc 基线，拒绝重复应用或覆盖')
    updated = (
        'diff --git a/osfmk/console/serial_console.c b/osfmk/console/serial_console.c\n'
        '--- a/osfmk/console/serial_console.c\n'
        '+++ b/osfmk/console/serial_console.c\n'
        '@@ -112,6 +112,22 @@\n'
        ' \n'
        ' extern int serial_getc(void);\n'
        ' extern void serial_putc_options(char, bool);\n'
        '+extern void pong_log_putc(char c) __attribute__((weak_import));\n'
        '+int pong_console_muted;\n'
        '+\n'
        '+static inline void\n'
        '+pong_log_write_chars(const char *str, int size)\n'
        '+{\n'
        '+\tif (!pong_log_putc || str == NULL || size <= 0) {\n'
        '+\t\treturn;\n'
        '+\t}\n'
        '+\tfor (int idx = 0; idx < size; idx++) {\n'
        '+\t\tif (str[idx] == \'\\n\') {\n'
        '+\t\t\tpong_log_putc(\'\\r\');\n'
        '+\t\t}\n'
        '+\t\tpong_log_putc(str[idx]);\n'
        '+\t}\n'
        '+}\n'
        ' \n'
        ' #if DEBUG || DEVELOPMENT\n'
        ' TUNABLE(bool, allow_printf_from_interrupts_disabled_context, "nointr_consio", false);\n'
        '@@ -261,6 +277,8 @@\n'
        ' \t}\n'
        ' \n'
        '-\tcons_ops[idx].putc(c, poll);\n'
        '+\tif (!pong_console_muted) {\n'
        '+\t\tcons_ops[idx].putc(c, poll);\n'
        '+\t}\n'
        ' }\n'
        ' \n'
        ' /**\n'
        '@@ -527,7 +545,8 @@\n'
        ' void\n'
        ' console_write(char *str, int size)\n'
        ' {\n'
        '+\tpong_log_write_chars(str, size);\n'
        ' #if defined(PONG) && defined(XNU_PONG_RAMOOPS_CONSOLE) && XNU_PONG_RAMOOPS_CONSOLE\n'
        ' \tpong_ramoops_console_write(str, size);\n'
        ' #endif\n'
        ' \tif (disableConsoleOutput) {\n'
        '@@ -615,7 +634,8 @@\n'
        ' void\n'
        ' console_write_unbuffered(char c)\n'
        ' {\n'
        '+\tpong_log_write_chars(&c, 1);\n'
        ' #if defined(PONG) && defined(XNU_PONG_RAMOOPS_CONSOLE) && XNU_PONG_RAMOOPS_CONSOLE\n'
        ' \tpong_ramoops_console_write(&c, 1);\n'
        ' #endif\n'
        ' \tif (disableConsoleOutput) {\n'
    )
    hook.write_bytes(updated.encode('utf-8'))


def apply(device: Path) -> None:
    """对独立设备目录应用第一波全部性能与板级驱动补丁。"""
    patch_cpu_policy(device)
    patch_gpu_profile(device)
    patch_iosurface_align(device)
    patch_touch_and_hall(device)
    patch_power_backlight_adsp(device)
    patch_userland_ui(device)
    patch_console_loghook(device)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', type=Path)
    apply(parser.parse_args().device.resolve())
    print('已应用 liuqin 第一波（CPU/GPU/IOSurface/触控/霍尔/电源背光 ADSP/UI）全部适配')


if __name__ == '__main__':
    main()
