"""CoreMaker ECG PC beat estimator with contact and transient-overload gating.

The detector retains the U9.x polarity-aware peak / RR-consensus approach.
Raw samples are never altered or discarded from the viewer's CSV recorder;
only samples admitted to the BPM detector are gated during overload/recovery.
Engineering demonstration only; not for medical diagnosis.
"""
from collections import deque
from statistics import median
from signal_filter import Biquad


class HeartRate:
    MODES = {
        "标准": {"k": 2.25, "floor": 38.0, "refractory": 445, "min_rr": 550, "tolerance": 0.24},
        "灵敏": {"k": 1.80, "floor": 25.0, "refractory": 420, "min_rr": 500, "tolerance": 0.30},
        "高灵敏": {"k": 1.50, "floor": 18.0, "refractory": 390, "min_rr": 450, "tolerance": 0.34},
    }

    # Robust-span contact heuristic carried forward from U9.4 paired tests.
    CONTACT_ON_SPAN = 6500.0
    CONTACT_OFF_SPAN = 4800.0
    CONTACT_WINDOW_S = 1.5
    CONTACT_RELEASE_MS = 1000

    # A single rail sample is marked and excluded from the detector. Two rail
    # samples within 120 ms are treated as a real overload episode.
    RAIL_LIMIT = 32700
    RAIL_CLUSTER_MS = 120
    RECOVERY_CLEAN_MS = 1500

    # Require a longer RR consensus before publishing the first BPM. This is
    # specifically intended to suppress the false first estimate after contact.
    RR_CONFIRM_INTERVALS = 4

    def __init__(self, fs=239, sensitivity="标准"):
        self.fs = float(fs)
        self.sensitivity = sensitivity if sensitivity in self.MODES else "标准"
        self.reset()

    def _reset_detector(self):
        """Clear only the beat detector; preserve contact/overload history."""
        self.stages = [Biquad("high", self.fs, 5), Biquad("low", self.fs, 20)]
        self.samples = deque(maxlen=max(1, int(self.fs * 8)))
        self.age = 0
        self.peaks = []
        self.bpm = None
        self.rr = None
        self.last_calc = None
        self.good_rr = deque(maxlen=5)
        self.last_rr_peak_ms = None
        self.last_valid_beat_ms = None
        self._ready = False

    def reset(self):
        self.raw_window = deque(maxlen=max(1, int(self.fs * 2)))
        self.rail_times = deque(maxlen=8)
        self.overload_active = False
        self.last_clip_ms = None
        self.contact_active = False
        self.contact_since_ms = None
        self.contact_lost_since_ms = None
        self.reason = "等待电极接触"
        self.state = "NO_CONTACT"
        self.trend = deque(maxlen=120)
        self._reset_detector()

    @staticmethod
    def _elapsed(now, then):
        return (int(now) - int(then)) & 0xFFFFFFFF

    def set_sensitivity(self, mode):
        if mode not in self.MODES:
            return
        if mode != self.sensitivity:
            self.sensitivity = mode
            self._reset_detector()
            self.reason = "灵敏度已切换：" + mode + "，重新确认心搏"
            self.state = "DETECTOR_RESET"

    def _raw_span(self):
        if len(self.raw_window) < int(self.fs * self.CONTACT_WINDOW_S):
            return None
        ordered = sorted(self.raw_window)
        n = len(ordered)
        lo = ordered[int(0.05 * (n - 1))]
        hi = ordered[int(0.95 * (n - 1))]
        return float(hi - lo)

    def _candidate_peaks(self, rows):
        values = [v for _, v in rows]
        center = median(values)
        deviation = median([abs(v - center) for v in values])
        cfg = self.MODES[self.sensitivity]
        threshold = max(cfg["floor"], deviation * cfg["k"])
        positive_tail = max(values) - center
        negative_tail = center - min(values)
        polarity = 1.0 if positive_tail >= negative_tail else -1.0
        signal = [polarity * (v - center) for v in values]

        candidates = []
        group_anchor_ms = None
        for i in range(1, len(signal) - 1):
            if (signal[i] <= threshold or signal[i] < signal[i - 1]
                    or signal[i] <= signal[i + 1]):
                continue
            timestamp = rows[i][0]
            if (group_anchor_ms is not None and
                    self._elapsed(timestamp, group_anchor_ms) < cfg["refractory"]):
                if candidates and signal[i] > candidates[-1][1]:
                    candidates[-1] = (i, signal[i])
                continue
            candidates.append((i, signal[i]))
            group_anchor_ms = timestamp
        return [rows[i] for i, _ in candidates]

    def _calculate(self, now):
        self.peaks = []
        if len(self.samples) < int(self.fs * 2.2):
            self.reason = "信号已接入：正在建立心搏窗口"
            self.state = "DETECTING"
            return

        rows = list(self.samples)
        candidates = self._candidate_peaks(rows)
        self.peaks = candidates
        if len(candidates) < self.RR_CONFIRM_INTERVALS + 1:
            self.reason = f"信号已接入：等待连续心搏（{len(candidates)}/{self.RR_CONFIRM_INTERVALS + 1}）"
            self.state = "DETECTING"
            return

        beat_times = [t for t, _ in candidates]
        intervals = [self._elapsed(b, a) for a, b in zip(beat_times, beat_times[1:])]
        cfg = self.MODES[self.sensitivity]
        plausible = [r for r in intervals[-5:] if cfg["min_rr"] <= r <= 1800]
        if len(plausible) < self.RR_CONFIRM_INTERVALS:
            self.reason = "候选心搏不足：等待更多连续 RR 间隔"
            self.state = "DETECTING"
            return

        center = median(plausible)
        good = [r for r in plausible if abs(r - center) <= cfg["tolerance"] * center]
        if len(good) < self.RR_CONFIRM_INTERVALS:
            self.reason = f"RR 一致性确认中（{len(good)}/{len(plausible)}）"
            self.state = "DETECTING"
            return

        newest_peak_ms = beat_times[-1]
        last_age = self._elapsed(now, newest_peak_ms)
        if last_age > max(1800, center * 2.0):
            self.bpm = None
            self.rr = None
            self.good_rr.clear()
            self.last_rr_peak_ms = None
            self.last_valid_beat_ms = None
            self.reason = "最近心搏已过期：等待重新确认"
            self.state = "DETECTING"
            return

        is_new_beat = (self.last_rr_peak_ms is None or
                       self._elapsed(newest_peak_ms, self.last_rr_peak_ms) != 0)
        if is_new_beat:
            rr_value = float(median(good))
            self.good_rr.append(rr_value)
            self.last_rr_peak_ms = newest_peak_ms
            self.last_valid_beat_ms = newest_peak_ms
            self.rr = float(median(self.good_rr))
            self.bpm = 60000.0 / self.rr
            self.reason = "心率估算有效（连续 RR 共识确认）"
            self.state = "VALID"
            self.trend.append((now, self.bpm))
        elif self.bpm is not None and self.last_valid_beat_ms is not None:
            age = self._elapsed(now, self.last_valid_beat_ms)
            if age <= max(1800, center * 2.0):
                self.reason = "保持最近一次确认心率，等待新心搏"
                self.state = "VALID_HOLD"
            else:
                self.bpm = None
                self.rr = None
                self.good_rr.clear()
                self.reason = "心搏超时：等待重新确认"
                self.state = "DETECTING"

    def push(self, ms, raw, gap=False):
        ms = int(ms) & 0xFFFFFFFF
        raw = int(raw)
        if gap:
            self.reset()
            self.reason = "数据中断：重新建立信号"
            self.state = "DATA_GAP"
            return 0.0

        self.raw_window.append(raw)
        clipped = abs(raw) >= self.RAIL_LIMIT

        if clipped:
            # Keep isolated rail points out of the beat filter. A cluster of
            # rail points is a confirmed overload and restarts the clean window.
            while self.rail_times and self._elapsed(ms, self.rail_times[0]) > self.RAIL_CLUSTER_MS:
                self.rail_times.popleft()
            self.rail_times.append(ms)
            if self.overload_active or len(self.rail_times) >= 2:
                if not self.overload_active:
                    self._reset_detector()
                self.overload_active = True
                self.last_clip_ms = ms
                self.bpm = None
                self.rr = None
                self.reason = "接触瞬态过载：保留采集，等待信号恢复"
                self.state = "OVERLOAD"
            else:
                self.reason = "检测到孤立满量程点：该点不参与心搏计算"
                self.state = "RAIL_SAMPLE"
            return 0.0

        if self.overload_active:
            if self.last_clip_ms is not None and self._elapsed(ms, self.last_clip_ms) < self.RECOVERY_CLEAN_MS:
                self.bpm = None
                self.rr = None
                self.reason = "过载恢复观察：等待连续无削顶信号"
                self.state = "RECOVERING"
                return 0.0
            self.overload_active = False
            self.last_clip_ms = None
            self.rail_times.clear()
            self.contact_active = False
            self.contact_since_ms = None
            self.contact_lost_since_ms = None
            self._reset_detector()
            self.reason = "过载已解除：重新建立信号"
            self.state = "SETTLING"

        span = self._raw_span()
        if span is None:
            self.bpm = None
            self.rr = None
            self.reason = "采集中：建立接触质量基线"
            self.state = "BASELINE"
            return 0.0

        if self.contact_active:
            if span < self.CONTACT_OFF_SPAN:
                if self.contact_lost_since_ms is None:
                    self.contact_lost_since_ms = ms
                elif self._elapsed(ms, self.contact_lost_since_ms) >= self.CONTACT_RELEASE_MS:
                    self.contact_active = False
                    self.contact_since_ms = None
                    self.contact_lost_since_ms = None
                    self._reset_detector()
                    self.reason = "未检测到有效接触：等待重新放置电极"
                    self.state = "NO_CONTACT"
                    return 0.0
            else:
                self.contact_lost_since_ms = None
        elif span >= self.CONTACT_ON_SPAN:
            self.contact_active = True
            self.contact_since_ms = ms
            self.contact_lost_since_ms = None
            self._reset_detector()
            self.reason = "检测到电极接触：等待信号稳定"
            self.state = "SETTLING"
            return 0.0
        else:
            self.bpm = None
            self.rr = None
            self.reason = "未检测到有效接触信号"
            self.state = "NO_CONTACT"
            return 0.0

        if not self.contact_active:
            self.bpm = None
            self.rr = None
            self.reason = "未检测到有效接触信号"
            self.state = "NO_CONTACT"
            return 0.0

        if self.contact_since_ms is not None and self._elapsed(ms, self.contact_since_ms) < self.CONTACT_RELEASE_MS:
            self.reason = "电极已接触：正在稳定信号"
            self.state = "SETTLING"
            return 0.0

        if not self._ready:
            value = float(raw)
            for stage in self.stages:
                value = stage.prime(value)
            self._ready = True

        value = float(raw)
        for stage in self.stages:
            value = stage.step(value)
        self.age += 1
        if self.age >= int(1.5 * self.fs):
            self.samples.append((ms, value))

        if self.last_calc is None or self._elapsed(ms, self.last_calc) >= 250:
            self.last_calc = ms
            self._calculate(ms)
        return value
