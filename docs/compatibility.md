# 兼容性与验证范围

| 条件 | 当前状态 |
| --- | --- |
| Windows 11、PANORAMA SE、cm01_se、Android 11、2240×1080 | 一台实体设备验证过原生显示和 USB 连接；通用版安装与自动识别已在同机验证 |
| Windows 10 | 目标支持，尚无独立实体测试；API / 驱动可用性仍取决于系统 |
| NVIDIA GPU + NVML | 完整路径，已在一台 RTX 5070 Ti 上读取；具体 API 可能随型号/驱动不可用 |
| AMD / Intel GPU | LHM 部分回退；多卡须明确选择，尚无独立实体全流程验证 |
| 多 GPU | 可指定 NVML 索引；LHM 使用独立的 hardware_id，不能混用编号 |
| NVMe PCIe Gen 1–5 | 可用 Windows 控制器属性计算接口参照；本机 Gen 4×4 已读到，其他代际有逻辑测试 |
| SATA / USB / RAID | 可以显式选择能提供计数器的磁盘；自动带宽参照可能未知，可手动设置 REF |
| 物理以太网 / Wi-Fi | 使用网卡报告速率；本机以太网已验证，Wi-Fi 名义速率不代表实际吞吐 |
| 非 SE PANORAMA、其他品牌、其他屏幕分辨率 | 当前不支持，主动拒绝自动部署 |
| macOS / Linux 主机 | 当前不支持采集与部署；Linux CI 仅运行平台无关测试 |

安装脚本仅检测设备，不替换画面。`start.cmd` 才推送本项目的 DEX 文件、建立 USB 端口转发并创建临时显示层。依赖固件允许 ADB shell 使用 SurfaceControl；厂商固件更新可能改变权限或内部日志格式。使用本项目不要求 root、刷机或安装 APK。

## 发布验证

- Python 安装、独立虚拟环境创建与依赖安装。
- 设备自动发现及模型/分辨率校验。
- Windows CPU、GPU、磁盘、物理网卡与默认路由发现。
- 本机 NVIDIA 实际传感器和链路能力读取。
- Java 编译与 DEX 打包。
- 通用版采集器只读实机采样，验证自动型号、SSD LINK 参照、网络速率与新鲜 CPU 温度。
- 在实体屏幕的 Android 系统中离屏生成位图，检查过长标签和缺失指标的排版，不替换正在显示的仪表盘。
- 硬件无关测试：不同磁盘编号、不同硬件标签、其他 PCIe 规格、部分显卡数据、未知峰值、计数器重置、手机排除、多屏歧义、进程归属保护。
- v0.5.0：独立采集已在 Ryzen 7 9700X + MSI X870I 上读取温度、封装功耗和 CPU 风扇；KANALI 完全退出后验证实屏、通道恢复和按需任务启停。真实重启、睡眠与其他主板仍需分别验证。
- v0.4.1：26 项测试覆盖启动互斥、临时目录中的快捷方式启用/禁用/归属、USB 延迟出现与未知设备不写入；Windows 实机验证自动启动命令、重复启动、快捷切换和恢复原安装。

软件逻辑测试不会被描述为多台实体电脑验证。当前版本保留已在实体屏幕确认的版式，并将设备相关参数改为自动读取；欢迎使用者提供脱敏后的型号、系统/固件版本和问题复现方式。

## 同品牌其他屏幕

以下官方规格核查于 **2026-10-21**。规格相同仅用于判断适配优先级，不等于本项目协议或固件兼容性已验证。

| 产品 | 官方公开信息 | 本项目当前结论 |
| --- | --- | --- |
| PANORAMA SE 360 | 6.67 英寸 AMOLED，2240×1080，60Hz；[产品页](https://www.tryxzone.com/products/liquid-cooling/panorama/panorama-se/white-360) | 已在一台 `cm01_se` / Android 11 实机验证 |
| 其他 SE 尺寸 / 配色 | 官方 SE 说明书列有 240 / 360、黑 / 白型号；[说明书](https://upload.tryxzone.com/products/manual_PANORAMA_SE.pdf) | 同时满足 `cm01_se` 和 2240×1080 会被当前程序接受；各型号尚无独立实测 |
| PANORAMA / PANORAMA ARGB | ARGB 产品页同为 6.67 英寸 AMOLED、2240×1080、60Hz；[产品页](https://www.tryxzone.com/products/liquid-cooling/panorama/panorama-argb/white-240) | 规格接近，推断有较高适配潜力；不能假定固件相同，当前未开放其他设备型号 |
| PANORAMA SE V2 | 2026-10-19 发布，沿用 6.67 英寸曲面 AMOLED，但显示模组及安装结构有更新；[发布公告](https://www.tryxzone.com/about/news/panorama-se-v2-curved-water-cooler) | 尚无设备型号、ADB 能力和固件实测，不把它直接视为旧 SE |
| STAGE | 两块 4 英寸 IPS 屏幕组合；[官方介绍](https://www.tryxzone.com/about/news/ces20260126) | 需要确认双屏映射、显示接口，并重新安排布局；当前不支持 |
| TURRIS | 5 英寸 IPS 超宽屏，60Hz；[官方介绍](https://www.tryxzone.com/about/news/ces20260126) | 屏幕比例与当前双面布局不同，需要单独适配；当前不支持 |
| 其他系列 | 未逐一核查接口及固件 | 当前不支持，不据品牌名称推断 |

当前原生渲染器的缓冲区为 2240×1080，两个显示区各 1078 像素，中间为 84 像素避让区域，并使用 Android SurfaceControl 隐藏接口。即使外观相近或能在 KANALI 中显示视频，也不能证明它支持这一部署方式。

### 其他型号的适配步骤

1. 使用 `diagnose-screen.cmd` 获取只读报告，确认是否有 ADB 设备以及型号、Android API 和分辨率。没有 ADB 的设备不能走当前传输方式。
2. 在对应实机上单独确认 USB 反向端口、`app_process` 与 SurfaceControl 权限。只读诊断**不测试**这些写入/绘图能力，因此报告匹配也不保证成功。
3. 根据实际显示面、屏幕方向和接缝位置适配渲染缓冲区与版式。
4. 验证持续更新、断线重连、停止后恢复原厂画面及独立传感器读数，再添加明确的设备支持配置。

不要仅修改型号判断来跳过校验后对未知设备运行。该限制反映尚未完成的适配，并非认定硬件一定无法支持。
