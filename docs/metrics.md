# 指标和参照值

默认每约 1 秒采样，屏幕约每 0.5 秒取数据。指针动画并不提高传感器采样频率。图形保留约 90 秒传输历史；曲线纵轴自动缩放，旁边的占比条使用固定的当前参照值，二者含义不同。

| 屏幕项 | 数据来源与含义 |
| --- | --- |
| GPU LOAD | NVML GPU 利用率；NVML 不可用时取 KANALI GPU load |
| CPU LOAD | psutil 的全系统 CPU 使用率 |
| TEMP | GPU 为 NVML / KANALI；CPU 为 KANALI；横条 0–100 °C 仅为显示刻度，不代表处理器安全上限 |
| VRAM | NVML 已用 / 总显存，GiB；不是系统共享显存 |
| MEM BUSY | NVML memory utilization，采样期间设备内存读写繁忙时间比例；不是显存容量占比，也不是显存 GB/s |
| RAM | 总物理内存减可用内存 / 总量，GiB |
| GPU POWER | NVML 功耗 / 当前功率限制；KANALI 回退只有可用功耗，限制未知时条形比例为空 |
| CPU POWER / FAN | KANALI CPU 功耗和名为 CPU 的风扇转速；不假定最大瓦数或最大 RPM |
| PCIe RX / TX | NVML 的设备接收 / 设备发送吞吐率，对应主机到 GPU / GPU 到主机 |
| SSD READ / WRITE | psutil 选中 PhysicalDrive 的累计字节差 / 真实时间差，不按分区重复累加 |
| NET RX / TX | psutil 选中网卡的收发字节差 / 时间差；包括该网卡的其他应用流量 |

## 单位

- 速率使用十进制：1 MB/s = 1,000,000 B/s，1 GB/s = 1,000 MB/s。
- 内存容量使用 GiB：1 GiB = 1,073,741,824 B。
- NVML PCIe throughput 以 KB/s 返回，除以 1,000 后显示 MB/s。
- 网卡报告的 Mbps 除以 8 得到 MB/s。1,000 Mbps 对应 125 MB/s 的名义单方向速率。

## 固定带宽参照

PCIe 每通道单方向容量：Gen 1 为 250 MB/s，Gen 2 为 500 MB/s；Gen 3 / 4 / 5 分别为 `8,000 / 16,000 / 32,000 × 128/130 ÷ 8 MB/s`。再乘通道数，已扣除线路编码开销，未扣除包、事务等协议开销。未知代际（包括当前尚未实现的 Gen 6）显示未知，不套用旧公式。

- **GPU MAX：** NVML 报告的最大链路代际 × 最大宽度。不是完整主机 PCIe 拓扑的实测上限。GPU 空闲时当前代际可能降低，标题中的当前链路与 MAX 因而不同。
- **SSD LINK：** Windows 为 NVMe 控制器报告的最大 PCIe 链路能力。例如 Gen 4 ×4 约 7,876.9 MB/s。它不等于 SSD 产品的标称连续读写速度，也不等于实际可持续速度。SATA、USB、RAID、无法确认的桥接链路等不会套用 NVMe 公式。
- **SSD REF：** 用户主动设置的读/写参照。可填写自己选择的厂商标称或独立测试值；程序不自动跑压力测试，也不把这个值描述为自动实测峰值。只填写一个方向时，另一个方向占比为空。
- **NET：** 活动网卡报告的链路速率，包含 Wi-Fi 的名义速率；不等于 Internet 接入带宽。Wi-Fi 竞争、半双工、协议开销等使这个比例不能直接用来判定饱和。

PCIe 为全双工，RX/TX **分别**除以单方向参照，不把两个方向相加后除以一个方向的容量。SSD 读写占比也分别显示，不意味着同时读写可各自达到该上限。条形填充在 100% 截止，数字仍可显示超过 100%，以便发现不合适的自定义参照。

高负载、高占比可以帮助定位值得观察的环节，但不足以证明性能瓶颈。软件等待、模型调度、内存访问效率、缓存、磁盘随机 I/O、队列深度等没有由这些条形图直接测量。

## 缺失、重置与失效

传感器缺失、分母未知或累计计数器回退时显示 `—`，不转换成 0。KANALI 传感器数据超过 5 秒不再使用。采集快照超过约 4 秒或 USB 连接失效时屏幕显示 `NO DATA`，停止沿用陈旧数值；渲染器约 15 秒没有新鲜数据时退出，释放叠加层。

NVML 在进程启动时初始化；驱动重置或硬件变更后建议重启仪表盘。存储、网卡和屏幕的自动选择依据本机状态，不承诺对所有固件、驱动或多显卡组合读取完全一致的指标。

## 参考资料

- [NVIDIA NVML 文档](https://docs.nvidia.com/deploy/nvml-api/index.html)
- [psutil 项目与 API](https://github.com/giampaolo/psutil)
- [Microsoft PCIe 自定义属性说明](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddndis/ns-ntddndis-_ndis_pci_device_custom_properties)
- [Android Platform-Tools](https://developer.android.com/tools/releases/platform-tools)
