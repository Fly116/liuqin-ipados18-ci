# liuqin iPadOS 18 build tools

为 Xiaomi Pad 6 Pro（liuqin / SM8475）构建实验性 Darwin 24（iPadOS 18.7.10 / 22H374）内核、
用户态镜像与配套产物的 GitHub Actions 工具仓库。

设备侧仓库与完整背景：[`Fly116/UniXNU-liuqin`](https://github.com/Fly116/UniXNU-liuqin)
（README 里有最新进展、里程碑与文档索引）。

## 当前主线

`kernel-upstream.yml`：从**上游最新设备树**重编内核（prelink 打开，slide 由 22H374 kernelcache
自动派生），产物交给本地组装 boot 镜像。

| 项 | 值 |
|---|---|
| 设备源码 | `document97/UniXNU-liuqin@fe0e8d790e24120970083e20c1a7d9c86cdbb87c`（2026-11-21 drop） |
| UniXNU | `UniXNU/UniXNU@c96b29975645b711dc06bc435c3ad27321ce817c` |
| prelink | `board.toml [kernel.prelink] slide = "auto"` → 实测 `0x5ed0000`（基址 `0xfffffff00b000000`） |
| 可选开关 | `prelink=true/false`；`unique_chip_id`（8 位十六进制，用于 ADT 平台种子） |

工作流会：

1. 检出 device / UniXNU（不检 uefi-liuqin，内核构建不需要）；
2. 应用 `ci/patches/*.patch` 到 device 检出（**本地驱动补丁的注入点**，不改上游仓库）；
3. 按 bring-up 需要把 `configs/liuqin_ipados18_defconfig` 里的 `CONFIG_XNU_PONG_WIFI` 与
   `CONFIG_XNU_PONG_BACKLIGHT` 置 `n`（上游这两项需要加密 stock release 的固件源，
   本仓库没有；背光由 ABL 保持开启，显示走软件 UI）；
4. 取 pin 的 `UniXNU-sheng`（PongPower 编译 `QcomRpmh.c` 需要）、`unixnu fetch` 拉 Apple 参考源；
5. 编译内核 → prelink（或 native）→ 收集 `kernel/`、`payload/`、构建日志；
6. 7z AES-256 加密后上传 artifact。

## 其它工作流

| 工作流 | 用途 | 备注 |
|---|---|---|
| `kernel.yml` | 旧主线：`QPRS-6/iPadOS18-liuqin@38ca105d` | 已把 prelink slide 修正为 `0x5ed0000`；保留作对照 |
| `userdata.yml` | 生成 22H374 userdata 镜像（OS / SystemOS / Data 三窗口） | 产物 7 GB 级，加密上传 |
| `metal.yml` | 22H374 Metal 插件 / Mesa parity167 配套产物 | 当前 bring-up 未使用（GPU 后置） |

## 产物与解密

- 所有含二进制/Apple 字节的产物都用仓库 secret `LIUQIN_ARTIFACT_PASSWORD`（≥12 位）做
  AES-256 7z 加密后上传，保留 3 天；本地解密脚本见设备仓库 `docs/ci-fetch-kernel.sh`。
- 构建成功不代表设备已启动；预链接、GPU、触控、重启回程都需要单独实测。

## 边界与安全

- 本仓库只保存构建流程与自有适配脚本，不保存 Apple 系统内容、设备固件、账号凭据、分区镜像。
- 不修改 GPT、A/B 槽或平台固件；设备仓库的 A2 分区方案是用户单独授权的独立事项。
- 上游仓库只读；所有本地修改通过 `ci/patches/` 或构建沙箱注入。

## 本地验证

`python -I ci/test-scripts.py --source <QPRS 源码目录> --mesa <已打 parity167 补丁的 Mesa 目录> --scratch <新临时目录>`。

## 当前状态（2026-11-22）

内核已能跑到「等待根设备」（v114，含 AppleARMCPU DT 校验的二进制绕过补丁），
唯一阻塞是 NativeUfs 的 TUR 探测无完成中断；详见设备仓库
`docs/ufs-tur-analysis-2026-11-22.md` 与 `docs/v114-root-device-ufs-2026-11-22.md`。


## 2026-11-23：UFS bring-up 变体（q–z）

本轮变体补丁目录 `ci/patches-variants/{q,r,s,t,u,v,w,x,y,z}/`：

- q：RPMh 电源轨投票（ldob5/ldoc10）+ QMP PHY 初始化 + UIC bring-up
- r：N + 两轨投票（信任链路，不碰 UIC）
- s：O + 两轨投票 + 等待链路（volatile 描述符）
- t：s + 设备轨（ldob7/ldob9）+ CX/MX + 查询优先
- u：q + 全部电源轨 + 查询优先
- v：GCC CBCR 位语义修正、GDSC、v6 PHY reset、volatile 描述符（v134 首次 transport ready）
- w：liuqin GPT 几何 + SHNGROOT 诊断（v135）
- x：Data 窗口接受裸 APFS + 跳过坏窗口（v136 进入用户态）
- y：恢复 UFS 写路径（pong_ufs_readwrite）
- z：SystemOS union 配置 + init 诊断（union 模式实验）

workflow 新增：ccache、触摸固件注入（`LIUQIN_TOUCH_FW_DIR=ci/firmware`，厂商镜像只存在本私有仓库）、SystemOS union 配置步骤（union=1 要求 CRYPTEX_FILES=0）。
记录文档：https://github.com/Fly116/UniXNU-liuqin/blob/main/docs/ufs-bringup-2026-11-23.md
