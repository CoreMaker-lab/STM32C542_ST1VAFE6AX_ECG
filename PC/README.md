# CoreMaker ECG U9.9 PC 上位机（中英文双语）

## 本版修改

- 新增独立的 **ECG vAFE 采样率**选择：120 / 240 Hz，默认 240 Hz。
- ECG 采样率通过 MCU `RATE 120` / `RATE 240` 命令配置。
- 只有收到 MCU `RATE OK ... ecg_rate_cfg=... rc=0` 确认后，PC 才更新已应用挡位；失败时恢复上次确认值。
- 切换 ECG 采样率后，PC 清空旧时间窗口并按新挡位重建显示滤波器与心搏检测器；随后继续使用 MCU 时间戳估算真实采样率。
- 保留独立 XL 加速度计 ODR 选择：120 / 240 / 480 / 960 Hz。XL ODR 不会改变 ECG vAFE 采样率。
- 默认中文，支持 English；保留 U9.8 接触判断、过载恢复、RR 共识与 CSV 记录功能。
- CSV 的 `ecg_vafe_nominal_fs_hz` 列现在记录 MCU 已确认的 ECG 120/240 Hz 配置，不再写死 240。

## ST1VAFE6AX ECG 两种模式

| ECG vAFE 配置 | 实际 ODR | 内部滤波 | 典型带宽 |
|---|---:|---|---|
| 240 Hz | 240 Hz | Notch 关闭 | 0.15–318 Hz（HPF 开启时） |
| 120 Hz | 120 Hz | Notch 开启 | 0.08–14.8 Hz（HPF 开启时） |

120 Hz 模式不只是把 PC 时间轴改成 120 Hz；MCU 通过 `RATE 120` 配置芯片内部 notch profile，vAFE ODR 随之变为 120 Hz。240 Hz 模式关闭该 notch profile。

XL ODR 是另一组独立设置，仍可选择 120 / 240 / 480 / 960 Hz。

## MCU 固件要求

请配套使用 U9.8 MCU 补丁工程（支持独立 `RATE 120|240` 与 `XL_ODR 120|240|480|960` 命令）。

- `RATE 120` / `RATE 240`：配置 ECG vAFE 模式并触发 MCU 传感器重新配置；切换时数据流会短暂中断。
- `XL_ODR 120|240|480|960`：只配置 XL 加速度计 ODR，不改变 ECG vAFE 模式。

## 安装

1. 关闭旧版上位机。
2. 解压 ZIP，将 `PC` 文件夹覆盖到原工程的 PC 目录。
3. 首次运行 `install_windows.bat`。
4. 运行 `start_windows.bat`。
5. ECG 默认 240 Hz；需要时在“ECG 采样率”中选择 120 Hz 并点击“应用 ECG 采样率”。
6. XL ODR 在独立的“XL ODR（加速度计）”控件中设置。

## 验证边界

- Python 语法检查与命令/状态解析静态测试通过。
- 当前未连接实物板执行 120↔240 Hz 实时切换验证。
- 本版只修改 PC 上位机，不修改 MCU 工程、传感器驱动、PCB 或心搏算法。
- 工程演示原型，未经医疗器械认证，不用于医疗诊断。

## 官方资料

ST TN1571 / ST1VAFE6AX datasheet：vAFE ODR 为 240 Hz（notch off）或 120 Hz（notch on）。
