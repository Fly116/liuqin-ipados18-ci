# liuqin iPadOS 18 build tools

为 Xiaomi Pad 6 Pro（liuqin）构建固定版本的实验性 Darwin 24 图形库、用户态和内核。上游为 `QPRS-6/iPadOS18-liuqin@38ca105d915283d6c5342063965ab13572288e8a`，UniXNU 为 `c96b29975645b711dc06bc435c3ad27321ce817c`。

## 边界

- 本仓库只保存构建流程和自有适配脚本，不保存 Apple 系统内容、设备固件、账号凭据、设备分区镜像。
- 含二进制的产物统一使用仓库 secret `LIUQIN_ARTIFACT_PASSWORD` 加密，保留三天；密码至少十二位。
- 构建成功不代表设备已启动。预链接、GPU、触控、重启回程都需要单独实测。
- 不修改 GPT、A/B 槽或平台固件。安装目标仅为已授权的 userdata，Ubuntu 根分区和启动镜像保持不变。
- 上游目前仍有 Wi-Fi、蓝牙、音频及图形细节等限制，不能把实验性桌面启动等同于完整 iPad 的日常可用性。

## 构建

`metal` 流程在 Intel macOS runner 上构建固定 Mesa parity167 分支和 22H374 Metal 插件。源码检出、构建目录和产物目录相互分离；提交前应用 liuqin 写合并映射缓存刷新修复。

本地验证：`python -I ci/test-scripts.py --source <QPRS 源码目录> --mesa <已打 parity167 补丁的 Mesa 目录> --scratch <新临时目录>`。
