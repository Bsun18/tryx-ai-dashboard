# 独立采集模式

从 v0.5.0 开始，默认使用 `sensor_backend: "native"`。日常运行不需要打开 KANALI，也不需要 LibreHardwareMonitor 的图形程序。

## 安装

1. 安装 Python 3.10+（包含 Tcl/Tk），解压项目，运行 `setup.cmd`，准备 Python 环境和桌面入口。暂时没有 ADB 时会提示下一步。
2. 先停止正在运行的仪表盘，再运行 `setup-native.cmd`，阅读组件说明，输入 `y`，允许一次 Windows 管理员授权。请使用与仪表盘相同的 Windows 管理员账户；不支持用另一个账户代输凭据安装。
3. 安装器从 Google 下载 Platform-Tools 37.0.1，从各项目官方 GitHub 下载 LibreHardwareMonitor 0.9.6 和 PawnIO 2.2.0。下载校验 SHA256；执行驱动安装前还验证 PawnIO 发布者数字签名。用户获取的依赖不打包进本项目发布 ZIP。
4. 打开控制台启动仪表盘。首次传感器初始化需要数秒。如果原来启用了 KANALI 自启动，可在 KANALI 自己的设置或 Windows 启动设置中关闭。通用安装器不会替用户退出 KANALI或修改它的任务。

安装需要 Windows 自带的 .NET Framework 4.7.2+ 和 64 位系统。传感器宿主由安装脚本使用系统 .NET Framework 编译器编译，无需安装 Visual Studio 或 .NET SDK。屏幕的 USB 驱动仍须正确安装：本机验证沿用了既有设备驱动，未验证完全未安装过 KANALI 的全新 Windows。

## 数据通路与权限

```text
CPU / 主板 → PawnIO → LibreHardwareMonitor → SensorHost
                                               ↓ 只读快照
GPU → NVML ───────────────────────────────→ 普通权限采集器
内存 / 磁盘 / 网络 → Windows / psutil ──────→    ↓
                            本机 HTTP → 官方 ADB / USB → Android 原生表盘
```

- 传感器宿主安装到 `%ProgramFiles%\TRYX AI Dashboard Sensors`，普通用户不能修改程序或 DLL；高权限任务不执行项目目录里的 Python/PowerShell。
- 按需任务名为 `TRYX AI Sensors-<当前用户 SID>`，无登录触发器、无密码存储。采集器启动时请求运行；本身没有窗口。
- 普通权限采集器每秒更新 `%USERPROFILE%\.tryx-ai-dashboard\sensors.lease` 中的时间戳。该位置避开 Store 应用的 AppData 重定向。关闭仪表盘后，宿主在约 20–30 秒内自行退出；时间戳不包含命令、程序路径或调节参数。
- 传感器数据写入 `%ProgramData%\TryxAiDashboard\<用户 SID>\sensors.json`。此目录普通用户只读。单次读取不执行数据里的任何内容。
- 任务与驱动安装需要一次管理员授权；之后开关、登录自启、读取快照都使用普通权限。
- 宿主只调用传感器更新接口，不调用风扇控制、电压调整或超频接口。不会加载 KANALI DLL，也不读取 KANALI 设备日志。
- 运行期间不需要联网。Windows 登录前的显示、真正睡眠唤醒和断电重启仍需在每台设备上验证。

## 指标选择

CPU 温度优先取处理器的 Tctl/Tdie 或 Package 温度，CPU 功耗取 Package；不能把单个核心、主板环境温度或水泵转速冒充对应指标。功耗采用传感器定义，可能与 KANALI 使用的口径或采样时刻不同。

只有明确标记为 CPU Fan / CPU Fan #1 / CPU 的主板风扇才自动匹配。泛称 `Fan #1`、多个同名风扇、多个 CPU 或多个非 NVML 显卡的情况保留未知，或由用户明确选择。

需要指定时，在 `config.json` 设置：

| 参数 | 值来源 |
| --- | --- |
| `cpu_hardware_id` | `sensors.json` 的 CPU `hardware_id`；多 CPU 时选择一个 |
| `cpu_temp_sensor_id` | 所选 CPU 温度传感器的 `id` |
| `cpu_power_sensor_id` | 所选 CPU 功耗传感器的 `id` |
| `fan_sensor_id` | 主板风扇的 `id` |
| `native_gpu_hardware_id` | NVML 不可用时选择 LHM 的显卡 `hardware_id`；与 NVML `gpu_index` 不是同一个编号 |

未知字段不猜测、不以 0 代替。快照超过 5 秒、时间戳来自未来或字段不是有限数值时停止使用。CPU Fan 的真实 0 RPM 可以显示 0。

## 关闭与卸载

日常停止仍使用桌面开关或控制台。关闭后宿主会自行退出，驱动保持安装，以便下次启动。

卸载：先停止仪表盘、取消其登录自启，然后以管理员 PowerShell 运行项目内 `scripts/uninstall_native.ps1`。它只移除本用户的传感器任务；没有其他用户任务引用时移除受保护的宿主目录。它保留 ProgramData 中的诊断/迁移备份，也不自动卸载可能被其他监控工具共用的 PawnIO。确定其他软件不使用时，可在 Windows“已安装的应用”中单独卸载 PawnIO。

需要旧版数据源时，停止仪表盘，在配置中设置 `sensor_backend: "kanali"`，再启动 KANALI 和仪表盘。该模式才会读取厂商传感器消息、复用已有厂商启动任务。

## 本机实测范围

Windows 11、Ryzen 7 9700X、MSI MPG X870I EDGE TI EVO WIFI：LHM 识别 Nuvoton NCT6687D-R，读取 CPU Tctl/Tdie、CPU Package 功耗与 CPU Fan。已在 KANALI 全部退出、使用 Google 官方 ADB 的状态下运行实体 PANORAMA SE 表盘。

已测试软件数据通道中断后的重建、停止后传感器宿主退出、再次按需启动。软件模拟断线不等同于物理拔插或真实睡眠恢复；没有为了测试重启或休眠正在使用的电脑。
