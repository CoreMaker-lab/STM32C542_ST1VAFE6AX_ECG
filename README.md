# CoreMaker ECG — 心电信号采集与实时心率分析平台

# ECG Acquisition and Real-Time Heart Rate Analysis Platform

**硬件平台 / Hardware Platform:** STM32C542CCT6 + ST1VAFE6AX  
**项目类型 / Project Type:** ECG Signal Acquisition · Embedded
Processing · PC Visualization
<img width="1309" height="636" alt="image" src="https://github.com/user-attachments/assets/3f938c89-777b-4e3e-bcd2-7e0a541844e0" />

------------------------------------------------------------------------

## 项目维护者与联系方式 \| Project Maintainer & Contact

- **Name / 姓名**: Billy
- **交流群 / Discussion Group**: 925643491
- **Email / 邮箱**: <a845656974@outlook.com>
- **Phone / 电话**: +86 15622736378

------------------------------------------------------------------------

## 1. 项目简介 \| Overview

**中文**

CoreMaker ECG 是一套基于 ST 生物电模拟前端和 STM32 MCU
的心电信号采集与实时分析演示平台。

系统采用 **STM32C542CCT6** 作为主控 MCU，搭配 **ST1VAFE6AX** ECG
模拟前端，实现 ECG 信号采集、数据处理、实时波形显示及心率估算。通过 USB
虚拟串口连接 PC 上位机，实现采集控制、实时波形监测、心率显示、参数配置和
CSV 数据记录。

本项目展示从模拟前端、嵌入式固件到 PC 上位机的完整应用开发流程。

**English**

CoreMaker ECG is an ECG acquisition and real-time analysis demonstration
platform based on an ST biopotential analog front end and an STM32
microcontroller.

The system uses the **STM32C542CCT6** as its main controller and the
**ST1VAFE6AX** as the ECG analog front end. It demonstrates ECG signal
acquisition, data processing, real-time waveform visualization, and
heart-rate estimation. A USB virtual COM port connects the embedded
device to the PC application for acquisition control, waveform
monitoring, heart-rate display, configuration, and CSV data logging.

The project demonstrates an end-to-end application workflow covering the
analog front end, embedded firmware, and PC software.

## 2. 系统架构 \| System Architecture

| 模块 / Module                  | 器件或平台 / Device or Platform | 主要功能 / Main Function                                                                 |
|--------------------------------|---------------------------------|------------------------------------------------------------------------------------------|
| 主控 MCU / Main MCU            | STM32C542CCT6                   | 数据采集、控制与处理 / Acquisition, control, and processing                              |
| ECG 模拟前端 / ECG AFE         | ST1VAFE6AX                      | ECG 生物电信号前端调理 / ECG analog front-end signal conditioning                        |
| 电极接口 / Electrode Interface | ECG 电极输入 / ECG electrodes   | 获取人体表面生物电信号 / Acquire surface biopotential signals                            |
| 通信接口 / Communication       | USB Virtual COM                 | MCU 与 PC 数据通信 / Data communication between MCU and PC                               |
| PC 软件 / PC Application       | CoreMaker ECG                   | 波形显示、心率估算及数据记录 / Waveform display, heart-rate estimation, and data logging |

### 数据处理流程 \| Data Flow

``` text
ECG Electrodes
      |
      v
ST1VAFE6AX
ECG Analog Front End
      |
      v
STM32C542CCT6
Data Acquisition & Processing
      |
      v
USB Virtual COM
      |
      v
CoreMaker ECG PC Software
      |
      +---- Raw ECG Waveform
      +---- Filtered ECG Waveform
      +---- Heart Rate (BPM)
      +---- Heart Rate Trend
      +---- CSV Data Recording
```

## 3. 主要功能 \| Key Features

### MCU 端 \| Embedded MCU

- 基于 STM32C542CCT6 的嵌入式控制平台。  
  Embedded control platform based on STM32C542CCT6.
- ST1VAFE6AX ECG 模拟前端接口。  
  Interface to the ST1VAFE6AX ECG analog front end.
- ECG 数据采集与基础处理。  
  ECG data acquisition and basic processing.
- 采集状态及运行状态输出。  
  Acquisition and operating status reporting.
- USB 虚拟串口数据通信。  
  USB virtual COM communication.

### PC 上位机 \| PC Application

- 实时 ECG 原始波形显示。  
  Real-time raw ECG waveform display.
- 数字滤波波形显示。  
  Digitally filtered waveform display.
- 实时心率 BPM 估算及趋势显示。  
  Real-time heart-rate estimation in BPM and trend display.
- ECG 采样率切换及心率识别灵敏度配置。  
  ECG sampling-rate selection and heart-rate detection sensitivity
  settings.
- 中文 / English 双语界面。  
  Chinese / English user interface.
- CSV 数据记录与导出。  
  CSV data logging and export.
- 设备状态诊断与复位。  
  Device diagnostics and reset.

### 数字信号处理 \| Digital Signal Processing

- 带通滤波：0.5–40 Hz。  
  Band-pass filtering: 0.5–40 Hz.
- 工频陷波：50 Hz。  
  Power-line notch filtering: 50 Hz.
- 心率估算：基于 ECG 波形特征与 RR 间期分析。  
  Heart-rate estimation based on ECG waveform features and RR-interval
  analysis.

## 4. 采样率配置 \| Sampling Rate Configuration

当前 ECG 采样率支持两个挡位：  
The current ECG sampling-rate options are:

| ECG 采样率 / ECG Sampling Rate | 说明 / Description                                            |
|--------------------------------|---------------------------------------------------------------|
| 120 Hz                         | 基础采集与对比测试 / Basic acquisition and comparison testing |
| 240 Hz                         | 默认推荐采样率 / Default recommended sampling rate            |

**默认配置 / Default:** 240 Hz

**注意 / Note:** 旧版界面中的 XL ODR 480 Hz / 960 Hz
属于加速度计配置参数，并非 ECG 采样率。ECG 采样率应通过 vAFE ECG
采样率选项配置。

The XL ODR settings of 480 Hz / 960 Hz shown in earlier software
versions refer to the accelerometer configuration, not the ECG sampling
rate. Configure the ECG sampling rate using the vAFE ECG sampling-rate
control.

## 5. PC 软件操作 \| PC Software Quick Start

### Step 1. 硬件连接 \| Hardware Connection

通过 USB 将 ECG 开发板连接至 PC。  
Connect the ECG development board to the PC via USB.

### Step 2. 串口配置 \| Serial Port Configuration

打开 CoreMaker ECG 上位机，刷新串口并选择对应 COM 端口。  
Open the CoreMaker ECG PC application, refresh the serial-port list, and
select the corresponding COM port.

| 参数 / Parameter    | 设置 / Setting |
|---------------------|----------------|
| 波特率 / Baud Rate  | 921600         |
| 数据位 / Data Bits  | 8              |
| 校验位 / Parity     | None           |
| 停止位 / Stop Bits  | 1              |
| 流控 / Flow Control | None           |

### Step 3. 连接设备 \| Connect the Device

点击“连接”，确认设备状态正常并持续接收 MCU 数据。  
Click **Connect** and confirm that the device status is normal and MCU
data is being received continuously.

### Step 4. 配置 ECG 采样率 \| Configure the ECG Sampling Rate

选择 120 Hz 或 240 Hz（推荐），应用配置后检查设备状态。  
Select 120 Hz or 240 Hz (recommended), apply the setting, and check the
device status.

### Step 5. 开始采集 \| Start Acquisition

点击“开始采集”，观察原始波形、滤波波形、BPM 心率及心率趋势。  
Click **Start Acquisition** and monitor the raw waveform, filtered
waveform, BPM value, and heart-rate trend.

建议先确保电极接触稳定，再开始采集，以减少接触瞬态造成的基线漂移和波形削顶。  
Ensure stable electrode contact before acquisition to reduce baseline
drift and waveform clipping caused by contact transients.

### Step 6. 数据记录 \| Data Recording

点击“开始记录”启动 CSV
数据记录。停止记录后，数据文件自动保存至程序目录下的 `records`
文件夹。  
Click **Start Recording** to begin CSV logging. After recording is
stopped, the data file is automatically saved in the `records` folder
under the application directory.

## 6. 状态监测 \| Diagnostics

MCU 调试信息包含以下状态字段：  
The MCU diagnostic output includes the following fields:

| 字段 / Field   | 说明 / Description                               |
|----------------|--------------------------------------------------|
| `configured`   | MCU 配置完成状态 / MCU configuration status      |
| `samples`      | 累计采样数量 / Total number of acquired samples  |
| `rate`         | 采样速率统计 / Measured sampling rate            |
| `raw`          | 当前原始采样值 / Current raw sample value        |
| `i2c_err`      | I2C 错误计数 / I2C error counter                 |
| `queue_drop`   | 数据队列丢失计数 / Data queue drop counter       |
| `uart_err`     | 通信错误计数 / Communication error counter       |
| `odr`          | 当前配置的 ODR / Configured ODR                  |
| `ecg_rate_cfg` | ECG 采样率配置 / ECG sampling-rate configuration |

建议测试时持续关注错误计数、采样状态及波形幅度。  
During testing, monitor the error counters, acquisition status, and
waveform amplitude.

## 7. PCB 与硬件设计 \| PCB and Hardware Design

**中文**

本项目采用 STM32C542CCT6 + ST1VAFE6AX 硬件方案。当前 PCB
版本已对布局和走线进行优化，器件型号、参数及电路连接关系保持不变。

硬件设计重点：

- ECG 模拟前端布局。
- MCU 与模拟前端接口。
- USB 通信接口。
- 电极输入及信号采集路径。

**English**

The hardware platform is based on the STM32C542CCT6 and ST1VAFE6AX. The
current PCB revision includes layout and routing optimization, while the
component models, component values, and circuit connectivity remain
unchanged.

Key hardware design areas include:

- ECG analog front-end placement.
- MCU-to-AFE interface.
- USB communication interface.
- Electrode inputs and signal acquisition paths.

## 8. 项目应用方向 \| Applications

- ECG 生物电信号采集技术验证 / ECG biopotential acquisition evaluation.
- 嵌入式 ECG 数据采集开发 / Embedded ECG data acquisition development.
- MCU 与生物电模拟前端应用开发 / MCU and biopotential AFE application
  development.
- 实时心率估算算法验证 / Real-time heart-rate estimation algorithm
  evaluation.
- PC 端生物电信号可视化 / PC-based biopotential signal visualization.
- 生物电信号采集系统原型开发 / Biopotential acquisition system
  prototyping.

## 9. 技术平台 \| Technology Platform

| 类别 / Category                 | 器件或平台 / Device or Platform | 说明 / Description                                                             |
|---------------------------------|---------------------------------|--------------------------------------------------------------------------------|
| 主控 MCU / Main MCU             | STM32C542CCT6                   | 嵌入式控制与数据处理 / Embedded control and data processing                    |
| ECG 模拟前端 / ECG AFE          | ST1VAFE6AX                      | ECG 信号模拟前端 / ECG analog front end                                        |
| 通信接口 / Communication        | USB Virtual COM                 | MCU 与 PC 通信 / MCU-to-PC communication                                       |
| PC 上位机 / PC Application      | CoreMaker ECG                   | 实时显示、配置与控制 / Real-time display, configuration, and control           |
| 数据可视化 / Data Visualization | Real-Time Waveform              | 原始波形、滤波波形及心率趋势 / Raw and filtered waveforms and heart-rate trend |
| 数据存储 / Data Storage         | CSV                             | 采集数据记录与导出 / Acquisition data logging and export                       |
| ECG 采样率 / ECG Sampling Rate  | 120 / 240 Hz                    | 240 Hz 为默认推荐配置 / 240 Hz is the default recommended setting              |

## 10. 使用声明 \| Disclaimer

**中文**

本项目为工程研发与技术演示原型，尚未经医疗器械注册或认证。本系统输出的
ECG 波形、BPM
心率数值及相关分析结果仅用于技术开发、算法验证和工程演示，不可用于临床诊断、治疗决策或替代专业医疗设备。

涉及人体接触测试时，应遵循适用的电气安全、隔离及实验操作规范。

**English**

This project is an engineering development and demonstration prototype.
It has not been registered or certified as a medical device. ECG
waveforms, BPM values, and related analysis results are intended solely
for engineering development, algorithm evaluation, and demonstration.
They must not be used for clinical diagnosis or treatment decisions, or
as a replacement for professional medical equipment.

When conducting tests involving human contact, follow applicable
electrical-safety, isolation, and laboratory procedures.

------------------------------------------------------------------------

## 关于 CoreMaker \| About CoreMaker

**深圳市芯途创科电子技术有限公司 \| Shenzhen CoreMaker Technology Co.,
Ltd.**

**COREMAKER \| STM32 + ST MEMS + ToF Application Development**

专注于 / Focus Areas:

- STM32 MCU 嵌入式应用开发 / STM32 MCU embedded application development
- ST MEMS 传感器应用开发 / ST MEMS sensor application development
- ToF 测距与深度感知方案 / ToF ranging and depth-sensing solutions
- 数据采集与实时分析 / Data acquisition and real-time analysis
- PC 上位机与嵌入式系统协同开发 / PC software and embedded-system
  integration
