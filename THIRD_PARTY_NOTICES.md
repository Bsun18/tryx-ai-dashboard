# 第三方组件说明

本项目发布包中的 `renderer/renderer.jar` 由本项目 Java 源代码编译，包含 `classes.dex`；编译所使用的 Android SDK / JDK 不打包在其中。

| 组件 | 使用方式 | 条款 / 来源 |
| --- | --- | --- |
| psutil 7.2.2 | 用户安装时从 PyPI 下载，独立安装在 `.venv` | [BSD 3-Clause，psutil LICENSE](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| Python | 用户自行安装 | [Python license](https://docs.python.org/3/license.html) |
| NVIDIA NVML | 调用用户已安装驱动中的库，不分发 NVIDIA 二进制文件 | [NVML 文档](https://docs.nvidia.com/deploy/nvml-api/index.html) |
| Android Platform-Tools / ADB | 独立安装脚本从 Google 下载 37.0.1，校验 SHA256；不随仓库分发 | [Google 官方下载与条款](https://developer.android.com/tools/releases/platform-tools) |
| LibreHardwareMonitor 0.9.6 | 安装时从官方发布下载；集成 DLL，保留许可及第三方声明 | [MPL-2.0 / 官方项目](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) |
| PawnIO 2.2.0 | 安装时从官方发布下载，验证散列和发布者签名；系统驱动 | [官方发行与条款](https://pawnio.eu/) |
| .NET Framework | 使用 Windows 已安装的运行时与编译器 | Microsoft 对应条款 |
| KANALI | 仅显式旧版后端需要，独立模式不调用 | 厂商软件及其附属组件适用各自条款 |
| Android SDK / JDK | 仅重新编译时需要，由开发者自行获取 | 各自发行版本的许可与条款 |

本项目不授予任何第三方组件、品牌或商标的额外权利，也不是 TRYX、KANALI、NVIDIA 或 Google 的官方产品。
