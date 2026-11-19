"""CoreMaker ECG U9.9 bilingual PC viewer; independent ECG 120/240 Hz and XL ODR controls."""
import csv
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque

import serial
import serial.tools.list_ports

from signal_filter import SignalFilter
from heart_rate import HeartRate


class Viewer:
    # UI language only. Internal algorithm keys remain Chinese to preserve U9.5 behavior.
    SENSITIVITY = {
        "标准": {"zh": "标准", "en": "Standard"},
        "灵敏": {"zh": "灵敏", "en": "Sensitive"},
        "高灵敏": {"zh": "高灵敏", "en": "High"},
    }
    PARITY = {"无": {"zh": "无", "en": "None"}, "偶": {"zh": "偶", "en": "Even"}, "奇": {"zh": "奇", "en": "Odd"}}
    FLOW = {"无": {"zh": "无", "en": "None"}, "RTS/CTS": {"zh": "RTS/CTS", "en": "RTS/CTS"}, "XON/XOFF": {"zh": "XON/XOFF", "en": "XON/XOFF"}}

    REASON_EN = {
        "等待电极接触": "Waiting for electrode contact",
        "灵敏度已切换：": "Sensitivity changed: ",
        "，重新确认心搏": "; re-confirming beats",
        "信号已接入：正在建立心搏窗口": "Signal detected: building beat window",
        "信号已接入：等待连续心搏（": "Signal detected: waiting for consecutive beats (",
        "候选心搏不足：等待更多连续 RR 间隔": "Not enough beat candidates: waiting for more consecutive RR intervals",
        "RR 一致性确认中（": "Confirming RR consistency (",
        "最近心搏已过期：等待重新确认": "Latest beat expired: waiting for re-confirmation",
        "心率估算有效（连续 RR 共识确认）": "Heart-rate estimate valid (consecutive RR consensus confirmed)",
        "保持最近一次确认心率，等待新心搏": "Holding last confirmed heart rate; waiting for next beat",
        "心搏超时：等待重新确认": "Beat timeout: waiting for re-confirmation",
        "接触瞬态过载：保留采集，等待信号恢复": "Contact transient overload: acquisition continues; waiting for recovery",
        "检测到孤立满量程点：该点不参与心搏计算": "Isolated full-scale sample detected; excluded from beat detection",
        "过载恢复观察：等待连续无削顶信号": "Overload recovery: waiting for a clean, unclipped signal",
        "过载已解除：重新建立信号": "Overload cleared: rebuilding signal",
        "采集中：建立接触质量基线": "Acquiring: establishing contact-quality baseline",
        "检测到电极接触：等待信号稳定": "Electrode contact detected: waiting for signal to settle",
        "未检测到有效接触：等待重新放置电极": "No valid contact: reposition the electrodes",
        "电极已接触：正在稳定信号": "Electrodes connected: stabilizing signal",
        "未检测到有效接触信号": "No valid electrode contact detected",
        "数据中断：重新建立信号": "Data interruption: rebuilding signal",
        "信号已接入：正在建立心搏窗口": "Signal detected: building beat window",
    }

    def __init__(self, root):
        self.root = root
        self.lang = "zh"
        self.root.title("CoreMaker ECG U9.9 | 中英文双语 · ECG 120/240 Hz")
        self.root.geometry("1320x960")

        self.port = None
        self.acquiring = False
        self.buffer = bytearray()
        self.data = deque(maxlen=3600)
        self.last_seq = None
        self.last_ms = None
        self.gaps = 0
        self.bad = 0
        self.last_rx = 0
        self.sample_deltas = deque(maxlen=120)
        self.actual_fs = 240.0
        self.xl_odr_applied = 240
        self.xl_odr_pending = None
        self.ecg_rate_applied = 240
        self.ecg_rate_pending = None
        self.fs_mismatch = False
        self.file = None
        self.writer = None
        self.flush_time = 0
        self.filter = SignalFilter(240.0)
        self.heart = HeartRate(240.0, sensitivity="标准")
        self.serial_fields = []
        self._labels = []
        self._buttons = []

        self._build_ui()
        self.set_language("zh")
        self.refresh()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(40, self.update)

    def _label(self, parent, zh, en, **kwargs):
        widget = ttk.Label(parent, text=zh, **kwargs)
        self._labels.append((widget, zh, en))
        return widget

    def _button(self, parent, zh, en, command, **kwargs):
        widget = ttk.Button(parent, text=zh, command=command, **kwargs)
        self._buttons.append((widget, zh, en))
        return widget

    def _build_ui(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x")
        self.combo = ttk.Combobox(bar, width=14)
        self.combo.pack(side="left", padx=2)
        self.refresh_btn = self._button(bar, "刷新串口", "Refresh ports", self.refresh)
        self.refresh_btn.pack(side="left", padx=2)
        self.connect_btn = self._button(bar, "连接 / 断开", "Connect / Disconnect", self.connect)
        self.connect_btn.pack(side="left", padx=2)
        self.start_btn = tk.Button(bar, text="▶ 开始采集", command=self.start_acquisition, bg="#16834a", fg="white", activebackground="#1b9b5a", relief="raised", padx=8)
        self.start_btn.pack(side="left", padx=(4, 2))
        self.stop_btn = tk.Button(bar, text="■ 停止采集", command=self.stop_acquisition, bg="#b83232", fg="white", activebackground="#d04444", relief="raised", padx=8, state="disabled")
        self.stop_btn.pack(side="left", padx=2)
        self.acq_state = tk.StringVar(value="采集状态：已停止")
        self.acq_state_label = ttk.Label(bar, textvariable=self.acq_state)
        self.acq_state_label.pack(side="left", padx=8)
        self.status_btn = self._button(bar, "采集状态", "Status", lambda: self.send("RAWSTAT"))
        self.status_btn.pack(side="left", padx=2)
        self.diag_btn = self._button(bar, "诊断", "Diagnostics", lambda: self.send("DIAG"))
        self.diag_btn.pack(side="left", padx=2)
        self.reset_btn = self._button(bar, "复位", "Reset", lambda: self.send("RESET"))
        self.reset_btn.pack(side="left", padx=2)
        self.lang_label = self._label(bar, "语言", "Language")
        self.lang_label.pack(side="left", padx=(12, 3))
        self.lang_var = tk.StringVar(value="中文")
        self.lang_box = ttk.Combobox(bar, textvariable=self.lang_var, values=["中文", "English"], state="readonly", width=9)
        self.lang_box.pack(side="left")
        self.lang_box.bind("<<ComboboxSelected>>", self._on_language_selected)

        csvbar = ttk.LabelFrame(self.root, text="CSV 数据记录（关闭上位机时自动保存）")
        csvbar.pack(fill="x", padx=4, pady=(2, 4))
        self.csvbar = csvbar
        self.start_record_btn = tk.Button(csvbar, text="● 开始记录", command=self.toggle_record, bg="#1769aa", fg="white", activebackground="#2584cc", relief="raised", padx=14, state="normal")
        self.start_record_btn.pack(side="left", padx=5, pady=4)
        self.csv_state = tk.StringVar(value="未记录｜文件将自动保存到程序目录 records 文件夹")
        ttk.Label(csvbar, textvariable=self.csv_state).pack(side="left", padx=10)

        settings = ttk.LabelFrame(self.root, text="串口参数（断开后修改，重新连接生效）")
        settings.pack(fill="x", padx=4, pady=3)
        self.settings_frame = settings
        self.serial_vars = {}
        serial_defs = [
            ("baud", "波特率", "Baud rate", ["9600", "57600", "115200", "230400", "460800", "921600", "1000000", "2000000", "3000000", "4000000"], "921600"),
            ("bits", "数据位", "Data bits", ["7", "8"], "8"),
            ("parity", "校验", "Parity", ["无", "偶", "奇"], "无"),
            ("stop", "停止位", "Stop bits", ["1", "2"], "1"),
            ("flow", "流控", "Flow control", ["无", "RTS/CTS", "XON/XOFF"], "无"),
        ]
        self.serial_label_widgets = {}
        for key, zh, en, values, default in serial_defs:
            label = self._label(settings, zh, en)
            label.pack(side="left", padx=3)
            self.serial_label_widgets[key] = label
            var = tk.StringVar(value=default)
            self.serial_vars[key] = var
            setattr(self, key, var)
            box = ttk.Combobox(settings, textvariable=var, values=values, state="readonly", width=10)
            box.pack(side="left")
            self.serial_fields.append(box)
            if key == "parity":
                self.parity_box = box
            elif key == "flow":
                self.flow_box = box
        self.mcu_note = self._label(settings, "当前 MCU：921600 / 8N1 / 无流控", "MCU default: 921600 / 8N1 / no flow control")
        self.mcu_note.pack(side="left", padx=10)

        row = ttk.Frame(self.root)
        row.pack(fill="x", padx=3, pady=2)
        self.ecg_rate_label = self._label(row, "ECG 采样率：", "ECG sample rate:")
        self.ecg_rate_label.pack(side="left")
        self.ecg_rate = tk.StringVar(value="240")
        self.ecg_rate_box = ttk.Combobox(row, textvariable=self.ecg_rate, values=["120", "240"], state="readonly", width=6)
        self.ecg_rate_box.pack(side="left")
        self.ecg_rate_btn = self._button(row, "应用 ECG 采样率", "Apply ECG rate", self.set_ecg_rate)
        self.ecg_rate_btn.pack(side="left", padx=3)

        self.rate_label = self._label(row, "XL ODR（加速度计）：", "XL ODR (accelerometer):")
        self.rate_label.pack(side="left", padx=(12, 0))
        self.xl_odr = tk.StringVar(value="240")
        self.rate_box = ttk.Combobox(row, textvariable=self.xl_odr, values=["120", "240", "480", "960"], state="readonly", width=6)
        self.rate_box.pack(side="left")
        self.rate_btn = self._button(row, "应用 XL ODR", "Apply XL ODR", self.set_rate)
        self.rate_btn.pack(side="left", padx=3)

        self.sens_label = self._label(row, "识别灵敏度：", "Detection sensitivity:")
        self.sens_label.pack(side="left", padx=(10, 2))
        self.sensitivity = tk.StringVar(value="标准")
        self.sensitivity_display = tk.StringVar(value="标准")
        self.sens_box = ttk.Combobox(row, textvariable=self.sensitivity_display, values=["标准", "灵敏", "高灵敏"], state="readonly", width=9)
        self.sens_box.pack(side="left")
        self.apply_sens_btn = self._button(row, "应用", "Apply", self.apply_sensitivity)
        self.apply_sens_btn.pack(side="left", padx=3)

        row2 = ttk.Frame(self.root)
        row2.pack(fill="x", padx=3, pady=1)
        self.rate_note = self._label(row2, "ECG：240 Hz（陷波关闭）/ 120 Hz（陷波开启）；XL ODR 独立设置。", "ECG: 240 Hz (notch off) / 120 Hz (notch on); XL ODR is independent.")
        self.rate_note.pack(side="left", padx=4)
        self.window_label = self._label(row2, "波形窗口：", "Waveform window:")
        self.window_label.pack(side="left", padx=(14, 2))
        self.window = tk.StringVar(value="5")
        self.window_box = ttk.Combobox(row2, textvariable=self.window, values=["2", "5", "10"], state="readonly", width=4)
        self.window_box.pack(side="left")
        self.filter_note = self._label(row2, "秒 | PC 高通 5 Hz | PC 低通 20 Hz | 单位：计数", "s | PC HPF 5 Hz | PC LPF 20 Hz | Unit: counts")
        self.filter_note.pack(side="left", padx=4)

        self.rate_capability = self._label(self.root, "说明：ECG 采样率选择 120 / 240 Hz：120 Hz 模式启用芯片内部陷波，vAFE 带宽约 0.08–14.8 Hz；240 Hz 模式关闭内部陷波，带宽约 0.15–318 Hz。XL ODR 独立配置为 120 / 240 / 480 / 960 Hz。当前串口仅输出 ECG 数据，不输出 XL 三轴数据。", "Note: ECG rate options are 120 / 240 Hz. 120 Hz enables the internal notch (vAFE bandwidth about 0.08–14.8 Hz); 240 Hz disables it (about 0.15–318 Hz). XL ODR is configured independently at 120 / 240 / 480 / 960 Hz. UART currently streams ECG only, not XL XYZ data.", wraplength=1280)
        self.rate_capability.pack(fill="x", padx=6)

        self.info = tk.StringVar(value="请选择串口连接 STM32C542 ECG 固件，默认 921600 / 8N1")
        ttk.Label(self.root, textvariable=self.info).pack(fill="x")
        self.quality = tk.StringVar(value="暂无数据")
        tk.Label(self.root, textvariable=self.quality, fg="#a33800", anchor="w").pack(fill="x")
        self.record_info = tk.StringVar(value="CSV 未保存")
        ttk.Label(self.root, textvariable=self.record_info).pack(fill="x")

        card = tk.Frame(self.root, bg="#142a3c")
        card.pack(fill="x")
        self.hr_text = tk.StringVar(value="-- BPM")
        self.hr_detail = tk.StringVar(value="等待稳定信号")
        tk.Label(card, textvariable=self.hr_text, font=("Microsoft YaHei", 36, "bold"), fg="#45e0b7", bg="#142a3c").pack(side="left", padx=20)
        tk.Label(card, textvariable=self.hr_detail, font=("Microsoft YaHei", 12), fg="white", bg="#142a3c", justify="left").pack(side="left", padx=20)
        self.demo_note = self._label(card, "工程原型估算\n未经医疗验证", "Engineering prototype estimate\nNot medically validated")
        self.demo_note.configure(background="#142a3c", foreground="#a9bbc9", justify="right")
        self.demo_note.pack(side="right", padx=20)

        self.canvas = tk.Canvas(self.root, bg="#101d2b")
        self.canvas.pack(fill="both", expand=True)
        self.log = tk.Text(self.root, height=4)
        self.log.pack(fill="x")

    def _on_language_selected(self, _event=None):
        self.set_language("en" if self.lang_var.get() == "English" else "zh")

    def set_language(self, lang):
        self.lang = "en" if lang == "en" else "zh"
        self.lang_var.set("English" if self.lang == "en" else "中文")
        for widget, zh, en in self._labels:
            try:
                widget.configure(text=(en if self.lang == "en" else zh))
            except tk.TclError:
                pass
        for widget, zh, en in self._buttons:
            try:
                widget.configure(text=(en if self.lang == "en" else zh))
            except tk.TclError:
                pass
        self.start_btn.configure(text="▶ Start acquisition" if self.lang == "en" else "▶ 开始采集")
        self.stop_btn.configure(text="■ Stop acquisition" if self.lang == "en" else "■ 停止采集")
        self.start_record_btn.configure(text=("■ Stop & Save" if self.file and self.lang == "en" else "● Start recording" if self.lang == "en" else "■ 停止记录并保存" if self.file else "● 开始记录"))
        self.csvbar.configure(text="CSV Recording (auto-saved on exit)" if self.lang == "en" else "CSV 数据记录（关闭上位机时自动保存）")
        self.settings_frame.configure(text="Serial settings (edit while disconnected)" if self.lang == "en" else "串口参数（断开后修改，重新连接生效）")
        # Keep algorithm mode canonical; only translate the visible combobox value.
        self.sens_box.configure(values=[self.SENSITIVITY[k][self.lang] for k in ("标准", "灵敏", "高灵敏")])
        self.sensitivity_display.set(self.SENSITIVITY[self.sensitivity.get()][self.lang])
        # Keep parity/flow canonical values internally while presenting the selected language.
        parity_key = self._parity_key()
        self.parity_box.configure(values=[self.PARITY[k][self.lang] for k in ("无", "偶", "奇")])
        self.parity.set(self.PARITY[parity_key][self.lang])
        flow_key = self._flow_key()
        self.flow_box.configure(values=[self.FLOW[k][self.lang] for k in ("无", "RTS/CTS", "XON/XOFF")])
        self.flow.set(self.FLOW[flow_key][self.lang])
        self.root.title("CoreMaker ECG U9.7 | Bilingual Contact Recovery" if self.lang == "en" else "CoreMaker ECG U9.9 | 中英文双语 · ECG 120/240 Hz")
        self.update_acq_controls()
        self._refresh_record_status_text()
        if not self.file and self.record_info.get() in ("CSV 未保存", "CSV not saved"):
            self.record_info.set("CSV not saved" if self.lang == "en" else "CSV 未保存")
        self.info.set(self.tr(self.info.get()))
        self.quality.set(self.tr(self.quality.get()))
        self.hr_detail.set(self.tr(self.hr_detail.get()))
        self.csv_state.set(self.tr(self.csv_state.get()))
        self.record_info.set(self.tr(self.record_info.get()))

    def _parity_key(self):
        value = self.parity.get()
        for key, names in self.PARITY.items():
            if value in names.values():
                return key
        return "无"

    def _flow_key(self):
        value = self.flow.get()
        for key, names in self.FLOW.items():
            if value in names.values():
                return key
        return "无"

    def _mode_from_display(self):
        value = self.sensitivity_display.get()
        for key, names in self.SENSITIVITY.items():
            if value in names.values():
                return key
        return "标准"

    def tr(self, text):
        if not text:
            return text
        result = str(text)
        replacements = {
            "采集状态：未开始": "Acquisition: not started",
            "采集状态：正在采集": "Acquisition: running",
            "采集状态：已停止": "Acquisition: stopped",
            "暂无数据": "No data yet",
            "CSV 未保存": "CSV not saved",
            "CSV 记录中：": "Recording CSV: ",
            "CSV 保存失败": "CSV save failed",
            "CSV 保存失败：": "CSV save failed: ",
            "CSV 写入失败，请检查磁盘空间或权限": "CSV write failed; check disk space or permissions",
            "串口": "Serial port",
            "采集控制": "Acquisition control",
            "采样挡位": "Sample rate",
            "ECG 采样率": "ECG sample rate",
            "ECG 采样率切换正在等待 MCU 确认，请稍候": "Waiting for MCU confirmation of the ECG rate change",
            "ECG 采样率已经是 ": "ECG sample rate is already ",
            " Hz（MCU 已确认）": " Hz (confirmed by MCU)",
            "CSV 已自动保存：": "CSV auto-saved: ",
            "CSV 已停止并保存：": "CSV stopped and saved: ",
            "● 正在记录；再次点击按钮即可停止并保存 CSV": "● Recording; click again to stop and save CSV",
            "✓ CSV 已保存：": "✓ CSV saved: ",
            "未记录｜文件将自动保存到程序目录 records 文件夹": "Not recording | Files are saved to the PC program's records folder",
            "已断开": "Disconnected",
            "已连接；点击「开始采集」启动数据流": "Connected; click Start acquisition to begin streaming",
            "已发送 START；等待 MCU 数据": "START sent; waiting for MCU data",
            "已发送 STOP；MCU 应停止发送采样数据": "STOP sent; MCU should stop streaming",
            "请先连接串口": "Please connect to a serial port first",
            "请先连接 STM32C542 ECG 固件": "Connect to the STM32C542 ECG firmware first",
            "已发送 ": "Requested ",
            " Hz 挡位请求；PC 将根据 MCU 时间戳核验真实采样率": " Hz; PC will verify the actual rate using MCU timestamps",
            "心搏识别灵敏度：": "Beat detection sensitivity: ",
            "（仅调整 PC 算法，不改变 MCU 采样）": " (PC algorithm only; MCU sampling is unchanged)",
            "MCU挡位切换失败，请查看日志": "MCU rate change failed; check the log",
            "接近满量程 / 可能削顶": "Near full scale / possible clipping",
            "滤波稳定中": "Filter settling",
            "滤波已稳定（不代表心电质量合格）": "Filter settled (does not guarantee ECG signal quality)",
            "暂无新数据": "No new data",
            "已断开": "Disconnected",
            "原始波形": "Raw waveform",
            "滤波波形 0.5–40 Hz + 50 Hz 陷波": "Filtered waveform 0.5–40 Hz + 50 Hz notch",
            "自动缩放": "Auto scale",
            "最近 ": "Last ",
            " 秒 | 计数": " s | counts",
            "心率趋势 | 最近 60 秒 | 次/分钟": "Heart-rate trend | last 60 s | BPM",
            "PC 序号缺口=": "PC sequence gaps=",
            "解析错误=": "parse errors=",
            "检测到 MCU 实际采样率约 ": "MCU actual sample rate detected: about ",
            " Hz；已按实际时间戳重配 PC 算法": " Hz; PC algorithms reconfigured from timestamps",
            "已连接 ": "Connected to ",
            "秒     ": "s     ",
            "范围=": "Range=",
            "原始均值=": "Raw mean=",
            "近满量程=": "Near-rail=",
            " | MCU实际Fs≈": " | MCU actual Fs≈",
        }
        if self.lang == "en":
            forward = dict(self.REASON_EN)
            forward.update(replacements)
            for zh, en in sorted(forward.items(), key=lambda item: len(item[0]), reverse=True):
                result = result.replace(zh, en)
        else:
            reverse = {en: zh for zh, en in self.REASON_EN.items()}
            reverse.update({en: zh for zh, en in replacements.items()})
            for en, zh in sorted(reverse.items(), key=lambda item: len(item[0]), reverse=True):
                result = result.replace(en, zh)
        return result

    def _refresh_record_status_text(self):
        if self.file:
            self.csv_state.set(self.tr("● 正在记录；再次点击按钮即可停止并保存 CSV"))
        elif not self.record_info.get() or self.record_info.get() in ("CSV 未保存", "CSV not saved"):
            self.csv_state.set(self.tr("未记录｜文件将自动保存到程序目录 records 文件夹"))

    def lock_serial(self, connected):
        for box in self.serial_fields:
            box.configure(state="disabled" if connected else "readonly")
        self.combo.configure(state="disabled" if connected else "normal")

    def refresh(self):
        self.combo["values"] = [p.device for p in serial.tools.list_ports.comports()]
        if not self.combo.get() and self.combo["values"]:
            self.combo.current(0)

    def clear_stream(self):
        # Reset PC processing around the last MCU-confirmed ECG vAFE ODR.
        requested = float(self.ecg_rate_applied)
        self.buffer.clear()
        self.data.clear()
        self.last_seq = None
        self.last_ms = None
        self.sample_deltas.clear()
        self.actual_fs = requested
        self.fs_mismatch = False
        self.filter = SignalFilter(requested)
        self.heart = HeartRate(requested, sensitivity=self.sensitivity.get())
        self.last_rx = 0

    def connect(self):
        if self.port:
            self.port.close()
            self.port = None
            self.info.set(self.tr("已断开"))
            self.heart.reset()
            self.lock_serial(False)
            self.update_acq_controls()
            return
        try:
            parity_key = self._parity_key()
            flow_key = self._flow_key()
            self.port = serial.Serial(
                self.combo.get(), int(self.baud.get()), bytesize=int(self.bits.get()),
                parity={"无": "N", "偶": "E", "奇": "O"}[parity_key],
                stopbits=int(self.stop.get()), rtscts=flow_key == "RTS/CTS",
                xonxoff=flow_key == "XON/XOFF", timeout=0, write_timeout=0.5
            )
            self.clear_stream()
            self.gaps = 0
            self.bad = 0
            self.lock_serial(True)
            self.send("DIAG")
            self.acquiring = False
            self.update_acq_controls()
            self.info.set(self.tr("已连接；点击「开始采集」启动数据流"))
        except (serial.SerialException, ValueError) as e:
            messagebox.showerror(self.tr("串口"), str(e))

    def update_acq_controls(self):
        connected = self.port is not None
        self.start_btn.configure(state=("disabled" if (not connected or self.acquiring) else "normal"), text=("▶ Start acquisition" if self.lang == "en" else "▶ 开始采集"))
        self.stop_btn.configure(state=("normal" if (connected and self.acquiring) else "disabled"), text=("■ Stop acquisition" if self.lang == "en" else "■ 停止采集"))
        state = "采集状态：正在采集" if self.acquiring else "采集状态：已停止"
        self.acq_state.set(self.tr(state))

    def start_acquisition(self):
        if not self.port:
            messagebox.showwarning(self.tr("采集控制"), self.tr("请先连接串口"))
            return
        if self.send("START"):
            self.acquiring = True
            self.update_acq_controls()
            self.info.set(self.tr("已发送 START；等待 MCU 数据"))

    def stop_acquisition(self):
        if not self.port:
            return
        if self.send("STOP"):
            self.acquiring = False
            self.update_acq_controls()
            self.info.set(self.tr("已发送 STOP；MCU 应停止发送采样数据"))

    def send(self, cmd):
        if self.port:
            try:
                self.port.write((cmd + "\r\n").encode())
                if cmd in ("RESET", "START", "STOP"):
                    self.filter.reset()
                    self.heart.reset()
                    self.data.clear()
                return True
            except (serial.SerialException, OSError) as e:
                self.info.set(str(e))
        return False

    def set_ecg_rate(self):
        if not self.port:
            messagebox.showwarning(self.tr("ECG 采样率"), self.tr("请先连接 STM32C542 ECG 固件"))
            return
        try:
            requested = int(self.ecg_rate.get())
            if requested not in (120, 240):
                raise ValueError("ECG vAFE rate must be 120 or 240 Hz.")
        except (ValueError, TypeError) as e:
            messagebox.showerror(self.tr("ECG 采样率"), str(e))
            return
        if self.ecg_rate_pending is not None:
            self.info.set(self.tr("ECG 采样率切换正在等待 MCU 确认，请稍候"))
            return
        if requested == self.ecg_rate_applied:
            self.info.set(self.tr(f"ECG 采样率已经是 {requested} Hz（MCU 已确认）"))
            return
        if not self.send("RATE " + str(requested)):
            return
        self.ecg_rate_pending = requested
        if self.lang == "en":
            self.info.set(f"Applying ECG vAFE rate {requested} Hz; MCU will briefly reconfigure the sensor and confirm the result.")
        else:
            self.info.set(f"正在应用 ECG 采样率 {requested} Hz；MCU 将短暂重新配置传感器，并返回确认结果。")
        self.root.after(700, lambda: self.send("RAWSTAT"))

    def set_rate(self):
        if not self.port:
            messagebox.showwarning(self.tr("采样挡位"), self.tr("请先连接 STM32C542 ECG 固件"))
            return
        try:
            odr = int(self.xl_odr.get())
            if odr not in (120, 240, 480, 960):
                raise ValueError("XL ODR must be one of 120, 240, 480, 960 Hz.")
        except (ValueError, TypeError) as e:
            messagebox.showerror(self.tr("采样挡位"), str(e))
            return
        # XL ODR is an independent sensor setting. Do NOT send RATE (that command
        # belongs to the ECG vAFE profile and only accepts 120/240).
        if not self.send("XL_ODR " + str(odr)):
            return
        self.xl_odr_pending = odr
        if self.lang == "en":
            self.info.set(f"Applying XL ODR {odr} Hz; waiting for MCU register readback. ECG vAFE remains 240 Hz.")
        else:
            self.info.set(f"正在应用 XL ODR {odr} Hz，等待 MCU 寄存器回读确认；ECG vAFE 仍为 240 Hz。")
        self.root.after(500, lambda: self.send("RAWSTAT"))

    def apply_sensitivity(self):
        mode = self._mode_from_display()
        self.sensitivity.set(mode)
        self.heart.set_sensitivity(mode)
        self.info.set(self.tr("心搏识别灵敏度：") + self.SENSITIVITY[mode][self.lang] + self.tr("（仅调整 PC 算法，不改变 MCU 采样）"))

    def apply_fs(self):
        try:
            self.filter = SignalFilter(self.actual_fs)
            self.heart = HeartRate(self.actual_fs, self.sensitivity.get())
            self.data.clear()
        except ValueError as e:
            messagebox.showerror("Fs", str(e))

    def toggle_record(self):
        if self.file:
            self.stop_record(auto=False)
        else:
            self.start_record()

    def start_record(self):
        if self.file:
            return
        try:
            record_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "records")
            os.makedirs(record_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(record_dir, "ECG_" + stamp + ".csv")
            suffix = 1
            while os.path.exists(path):
                path = os.path.join(record_dir, f"ECG_{stamp}_{suffix}.csv")
                suffix += 1
            self.heart.reset()
            self.file = open(path, "w", newline="", encoding="utf-8-sig")
            self.writer = csv.writer(self.file)
            self.writer.writerow(["host_unix_s", "seq", "mcu_read_ms", "raw_counts", "filtered_counts", "filter_settled", "near_rail", "ecg_vafe_nominal_fs_hz", "xl_odr_hz", "filter_fs_hz", "estimated_actual_fs_hz", "heart_rate_bpm", "rr_ms", "hr_state"])
            self.file.flush()
            self.flush_time = time.monotonic()
            self.record_info.set(self.tr("CSV 记录中：") + path)
            self.csv_state.set(self.tr("● 正在记录；再次点击按钮即可停止并保存 CSV"))
            self.start_record_btn.configure(state="normal", text=("■ Stop & Save" if self.lang == "en" else "■ 停止记录并保存"), bg="#b83232", activebackground="#d04444")
        except OSError as e:
            self.file = None
            self.writer = None
            messagebox.showerror(self.tr("CSV 保存失败"), str(e))

    def stop_record(self, auto=False):
        if not self.file:
            return
        path = getattr(self.file, "name", "")
        try:
            self.file.flush()
            self.file.close()
        except OSError as e:
            if not auto:
                messagebox.showerror(self.tr("CSV 保存失败"), str(e))
        finally:
            self.file = None
            self.writer = None
            prefix = "CSV auto-saved: " if auto and self.lang == "en" else "CSV stopped and saved: " if self.lang == "en" else "CSV 已自动保存：" if auto else "CSV 已停止并保存："
            self.record_info.set(prefix + path)
            self.csv_state.set(("✓ CSV saved: " if self.lang == "en" else "✓ CSV 已保存：") + os.path.basename(path))
            self.start_record_btn.configure(state="normal", text=("● Start recording" if self.lang == "en" else "● 开始记录"), bg="#1769aa", activebackground="#2584cc")

    def update_actual_fs(self, ms):
        """Estimate actual MCU sample rate from a rolling set of MCU timestamps."""
        if self.last_ms is not None:
            dt = (int(ms) - int(self.last_ms)) & 0xFFFFFFFF
            if 1 <= dt <= 100:
                self.sample_deltas.append(dt)
        if len(self.sample_deltas) >= 40:
            dt_ms = float(sum(self.sample_deltas)) / len(self.sample_deltas)
            measured = 1000.0 / dt_ms
            if 100.0 <= measured <= 1200.0:
                self.actual_fs = measured
                if abs(measured - self.filter.fs) / self.filter.fs > 0.035:
                    self.fs_mismatch = True
                    self.filter = SignalFilter(measured)
                    self.heart = HeartRate(measured, self.sensitivity.get())
                    self.data.clear()
                    msg = f"检测到 MCU 实际采样率约 {measured:.1f} Hz；已按实际时间戳重配 PC 算法"
                    self.info.set(self.tr(msg))
                else:
                    self.fs_mismatch = False

    @staticmethod
    def _int_field(line, key):
        prefix = key + "="
        for token in line.split():
            if token.startswith(prefix):
                try:
                    return int(token[len(prefix):], 10)
                except ValueError:
                    return None
        return None

    def line(self, line):
        if line.startswith("D,"):
            try:
                _, seq, ms, raw = line.split(",")
                seq = int(seq)
                ms = int(ms)
                raw = int(raw)
                if not (0 <= seq <= 0xFFFFFFFF and 0 <= ms <= 0xFFFFFFFF and -32768 <= raw <= 32767):
                    raise ValueError()
            except ValueError:
                self.bad += 1
                return
            gap = False
            if self.last_seq is not None:
                delta = (seq - self.last_seq) & 0xFFFFFFFF
                gap = delta != 1
                if 1 < delta < 0x80000000:
                    self.gaps += delta - 1
                elif delta != 1:
                    self.data.clear()
            if self.last_ms is not None and ((ms - self.last_ms) & 0xFFFFFFFF) > 50:
                gap = True
            self.update_actual_fs(ms)
            y, valid, clip = self.filter.push(raw, gap)
            self.heart.push(ms, raw, gap)
            self.data.append((ms, raw, y, valid, clip, gap))
            self.last_seq = seq
            self.last_ms = ms
            self.last_rx = time.monotonic()
            if self.writer:
                try:
                    reason = self.tr(self.heart.reason)
                    self.writer.writerow([f"{time.time():.6f}", seq, ms, raw, f"{y:.4f}", int(valid), int(clip), int(self.ecg_rate_applied), int(self.xl_odr_applied), self.filter.fs, f"{self.actual_fs:.2f}", "" if self.heart.bpm is None else round(self.heart.bpm, 2), "" if self.heart.rr is None else round(self.heart.rr, 2), reason])
                    if time.monotonic() - self.flush_time > 1:
                        self.file.flush()
                        self.flush_time = time.monotonic()
                except OSError as e:
                    self.info.set(self.tr("CSV 保存失败：") + str(e))
                    self.file.close()
                    self.file = None
                    self.writer = None
                    self.csv_state.set(self.tr("CSV 写入失败，请检查磁盘空间或权限"))
                    self.start_record_btn.configure(state="normal", text=("● Start recording" if self.lang == "en" else "● 开始记录"), bg="#1769aa", activebackground="#2584cc")
        else:
            self.log.insert("end", line + "\n")
            self.log.see("end")
            if int(self.log.index("end-1c").split(".")[0]) > 120:
                self.log.delete("1.0", "30.0")
            if line.startswith("RATE OK"):
                actual_rate = self._int_field(line, "ecg_rate_cfg")
                requested_rate = self._int_field(line, "requested")
                rc = self._int_field(line, "rc")
                if actual_rate in (120, 240) and requested_rate == actual_rate and rc == 0:
                    changed = actual_rate != self.ecg_rate_applied
                    self.ecg_rate_applied = actual_rate
                    self.ecg_rate_pending = None
                    self.ecg_rate.set(str(actual_rate))
                    if changed:
                        self.clear_stream()
                    msg = (f"ECG vAFE rate confirmed: {actual_rate} Hz; XL ODR remains {self.xl_odr_applied} Hz."
                           if self.lang == "en" else
                           f"ECG vAFE 采样率已由 MCU 确认：{actual_rate} Hz；XL ODR 保持 {self.xl_odr_applied} Hz。")
                    self.info.set(msg)
                else:
                    self.ecg_rate_pending = None
                    self.ecg_rate.set(str(self.ecg_rate_applied))
                    self.info.set("ECG rate acknowledgement invalid; previous setting restored. Check MCU log."
                                  if self.lang == "en" else
                                  "ECG 采样率确认信息无效，已恢复显示上次确认挡位，请检查 MCU 日志。")
            elif (line.startswith("RATE FAIL") or line.startswith("ERR RATE") or
                  (line.startswith("ERR UNKNOWN COMMAND") and self.ecg_rate_pending is not None)):
                self.ecg_rate_pending = None
                self.ecg_rate.set(str(self.ecg_rate_applied))
                self.info.set("MCU rejected ECG RATE command; previous setting restored."
                              if self.lang == "en" else
                              "MCU 拒绝 ECG RATE 指令，已恢复上次确认挡位。")
            if line.startswith("XL_ODR OK"):
                actual_odr = self._int_field(line, "odr")
                if actual_odr in (120, 240, 480, 960):
                    self.xl_odr_applied = actual_odr
                    self.xl_odr_pending = None
                    self.xl_odr.set(str(actual_odr))
                    msg = (f"XL ODR applied and read back: {actual_odr} Hz; ECG vAFE remains 240 Hz."
                           if self.lang == "en" else
                           f"XL ODR 已应用并经寄存器回读确认：{actual_odr} Hz；ECG vAFE 仍为 240 Hz。")
                    self.info.set(msg)
                else:
                    self.xl_odr_pending = None
                    self.info.set("XL ODR readback invalid; check MCU log." if self.lang == "en" else "XL ODR 回读值无效，请检查 MCU 日志")
            elif (line.startswith("XL_ODR FAIL") or line.startswith("ERR XL_ODR") or
                  (line.startswith("ERR UNKNOWN COMMAND") and self.xl_odr_pending is not None)):
                self.xl_odr_pending = None
                self.xl_odr.set(str(self.xl_odr_applied))
                self.info.set("MCU rejected XL ODR command; firmware update is required. Showing confirmed setting."
                              if self.lang == "en" else
                              "MCU 不支持 XL_ODR 指令，需要更新固件；已恢复显示实际挡位")
            if line.startswith("STAT "):
                actual_odr = self._int_field(line, "odr")
                actual_ecg_rate = self._int_field(line, "ecg_rate_cfg")
                if actual_odr in (120, 240, 480, 960) and self.xl_odr_pending is None:
                    self.xl_odr_applied = actual_odr
                    self.xl_odr.set(str(actual_odr))
                if actual_ecg_rate in (120, 240) and self.ecg_rate_pending is None:
                    if actual_ecg_rate != self.ecg_rate_applied:
                        self.ecg_rate_applied = actual_ecg_rate
                        self.ecg_rate.set(str(actual_ecg_rate))
                        self.clear_stream()
                    else:
                        self.ecg_rate.set(str(actual_ecg_rate))
                self.info.set(line + f" | PC sequence gaps={self.gaps} parse errors={self.bad}" if self.lang == "en" else line + f" | PC 序号缺口={self.gaps} 解析错误={self.bad}")
            if line.startswith("CONFIG "):
                actual_odr = self._int_field(line, "xl_odr")
                actual_ecg_rate = self._int_field(line, "ecg_rate_cfg")
                if actual_odr in (120, 240, 480, 960):
                    self.xl_odr_applied = actual_odr
                    self.xl_odr.set(str(actual_odr))
                if actual_ecg_rate in (120, 240):
                    changed = actual_ecg_rate != self.ecg_rate_applied
                    self.ecg_rate_applied = actual_ecg_rate
                    self.ecg_rate_pending = None
                    self.ecg_rate.set(str(actual_ecg_rate))
                    if changed:
                        self.clear_stream()
                self.filter.reset()
                self.heart.reset()
                self.data.clear()

    def draw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        fresh = self.port is not None and time.monotonic() - self.last_rx <= 2
        bpm = self.heart.bpm if fresh else None
        self.hr_text.set("-- BPM" if bpm is None else f"{bpm:.0f} BPM")
        reason = self.tr(self.heart.reason)
        if bpm is not None:
            detail = f"RR {self.heart.rr:.0f} ms | {reason}\n" + ("Orange markers: beat candidates (demo)" if self.lang == "en" else "橙点：心搏候选峰（工程演示）")
        else:
            detail = reason if fresh else ("No new data / disconnected" if self.lang == "en" else "暂无新数据 / 已断开")
        self.hr_detail.set(detail)
        if not self.data or w < 150 or h < 160:
            return
        span = float(self.window.get()) * 1000
        now = self.data[-1][0]
        pts = [v for v in self.data if ((now - v[0]) & 0xFFFFFFFF) <= span]
        clip = sum(v[4] for v in pts)
        mean = sum(v[1] for v in pts) / len(pts)
        stale = time.monotonic() - self.last_rx > 2
        if stale:
            state = "No new data" if self.lang == "en" else "暂无新数据"
        elif clip:
            state = "Near full scale / possible clipping" if self.lang == "en" else "接近满量程 / 可能削顶"
        elif not pts[-1][3]:
            state = "Filter settling" if self.lang == "en" else "滤波稳定中"
        else:
            state = "Filter settled (not an ECG quality guarantee)" if self.lang == "en" else "滤波已稳定（不代表心电质量合格）"
        if self.lang == "en":
            q = f"{state} | ECG Fs≈{self.actual_fs:.1f} Hz (mode {self.ecg_rate_applied}) | XL ODR={self.xl_odr_applied} Hz" + (f" (request {self.xl_odr_pending})" if self.xl_odr_pending else "") + f" | raw mean={mean:.0f} | range={min(v[1] for v in pts)}..{max(v[1] for v in pts)} | near-rail={clip/len(pts):.1%} | {reason}"
        else:
            q = f"{state} | ECG实际Fs≈{self.actual_fs:.1f} Hz（配置 {self.ecg_rate_applied} Hz） | XL ODR={self.xl_odr_applied} Hz" + (f"（请求 {self.xl_odr_pending}）" if self.xl_odr_pending else "") + f" | 原始均值={mean:.0f} | 范围={min(v[1] for v in pts)}..{max(v[1] for v in pts)} | 近满量程={clip/len(pts):.1%} | {reason}"
        self.quality.set(q)

        titles = [("Raw waveform" if self.lang == "en" else "原始波形"), ("Filtered waveform 0.5–40 Hz + 50 Hz notch" if self.lang == "en" else "滤波波形 0.5–40 Hz + 50 Hz 陷波")]
        for pane, index, color in [(0, 1, "#67baff"), (1, 2, "#45e0b7")]:
            top = pane * h * 0.37 + 30
            bottom = (pane + 1) * h * 0.37 - 25
            values = [v[index] for v in pts if index == 1 or v[3]]
            lo = min(values) if values else -1
            hi = max(values) if values else 1
            pad = max(5, (hi - lo) * 0.1)
            lo -= pad
            hi += pad
            c.create_text(12, top - 18, anchor="w", fill="white", text=titles[pane] + (" | Auto scale" if self.lang == "en" else " | 自动缩放"))
            for k in range(5):
                yy = top + (bottom - top) * k / 4
                c.create_line(70, yy, w - 15, yy, fill="#23394b")
            c.create_text(5, top, anchor="nw", fill="white", text=f"{hi:.0f}")
            c.create_text(5, bottom, anchor="sw", fill="white", text=f"{lo:.0f}")
            coords = []
            for v in pts:
                x = 70 + (w - 85) * (1 - ((now - v[0]) & 0xFFFFFFFF) / span)
                if v[5] or (index == 2 and not v[3]):
                    if len(coords) >= 4:
                        c.create_line(*coords, fill=color, width=1)
                    coords = []
                if index == 1 or v[3]:
                    coords.extend([x, top + (bottom - top) * (hi - v[index]) / (hi - lo)])
                if pane == 0 and v[4]:
                    c.create_line(x, top, x, top + 8, fill="#ff6b68")
            if len(coords) >= 4:
                c.create_line(*coords, fill=color, width=1)
            if pane == 1 and bpm is not None:
                for pm, _ in self.heart.peaks:
                    age = (now - pm) & 0xFFFFFFFF
                    if age > span:
                        continue
                    v = min(pts, key=lambda row: abs(row[0] - pm))
                    if not v[3]:
                        continue
                    xx = 70 + (w - 85) * (1 - age / span)
                    yy = top + (bottom - top) * (hi - v[2]) / (hi - lo)
                    c.create_oval(xx - 4, yy - 4, xx + 4, yy + 4, fill="#ff986d", outline="")
            c.create_text(w - 15, bottom + 16, anchor="e", fill="white", text=(f"Last {span/1000:g} s | counts" if self.lang == "en" else f"最近 {span/1000:g} 秒 | 计数"))

        top = h * 0.74 + 25
        bottom = h - 25
        c.create_text(12, top - 15, anchor="w", fill="white", text=("Heart-rate trend | last 60 s | BPM" if self.lang == "en" else "心率趋势 | 最近 60 秒 | 次/分钟"))
        for value in (40, 80, 120, 160, 180):
            yy = bottom - (value - 40) / 140 * (bottom - top)
            c.create_line(70, yy, w - 15, yy, fill="#23394b")
            c.create_text(8, yy, anchor="w", fill="#a9bbc9", text=str(value))
        coords = []
        previous = None
        for ms, value in self.heart.trend:
            age = (now - ms) & 0xFFFFFFFF
            if age > 60000:
                continue
            if previous is not None and ((ms - previous) & 0xFFFFFFFF) > 1500:
                if len(coords) >= 4:
                    c.create_line(*coords, fill="#67baff", width=2)
                coords = []
            coords.extend([70 + (w - 85) * (1 - age / 60000), bottom - (value - 40) / 140 * (bottom - top)])
            previous = ms
        if len(coords) >= 4:
            c.create_line(*coords, fill="#67baff", width=2)

    def update(self):
        try:
            if self.port:
                try:
                    self.buffer.extend(self.port.read(min(self.port.in_waiting, 32768)))
                    processed = 0
                    while b"\n" in self.buffer and processed < 2500:
                        processed += 1
                        raw, _, self.buffer = self.buffer.partition(b"\n")
                        self.line(raw.decode("ascii", errors="replace").strip())
                    if len(self.buffer) > 65536:
                        self.buffer.clear()
                        self.bad += 1
                        self.filter.reset()
                        self.heart.reset()
                except (serial.SerialException, OSError) as e:
                    self.info.set(str(e))
                    self.port.close()
                    self.port = None
                    self.lock_serial(False)
                    self.update_acq_controls()
            self.draw()
        finally:
            if self.root.winfo_exists():
                self.root.after(40, self.update)

    def close(self):
        if self.file:
            self.stop_record(auto=True)
        if self.port:
            try:
                if self.acquiring:
                    self.port.write(b"STOP\r\n")
            except Exception:
                pass
            try:
                self.port.close()
            except Exception:
                pass
            self.port = None
        self.acquiring = False
        self.root.destroy()


if __name__ == "__main__":
    Viewer(tk.Tk())
    tk.mainloop()
