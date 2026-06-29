import sys
import ctypes
import time
import os
import wave

import numpy as np
import cv2
import pyautogui
from rapidocr_onnxruntime import RapidOCR

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QSpinBox, QGroupBox, QTextBrowser, QStatusBar
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor

import winsound

ctypes.windll.user32.SetProcessDPIAware()


def _app_dir():
    """exe 所在目录，开发时返回脚本所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_alarm_path():
    return os.path.join(_app_dir(), 'alarm.wav')


def generate_alarm_wav(duration=2.5):
    filepath = get_alarm_path()
    if os.path.exists(filepath):
        return
    sample_rate = 22050
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, False)
    signal = np.sin(2 * np.pi * 800 * t)
    mod = (np.sin(2 * np.pi * 6 * t) + 1) * 0.25 + 0.5
    signal = signal * mod
    fade = int(0.02 * sample_rate)
    signal[:fade] *= np.linspace(0, 1, fade)
    signal[-fade:] *= np.linspace(1, 0, fade)
    signal = (signal * 32767).astype(np.int16)
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(signal.tobytes())


class OCRWorker(QThread):
    status_signal = Signal(str)
    found_signal = Signal(str)
    error_signal = Signal(str)
    init_done = Signal()

    def __init__(self):
        super().__init__()
        self._running = True
        self._paused = False
        self._resume_time = 0
        self.keywords = []
        self.interval = 3
        self.scale = 0.5
        self.ocr = None

    def run(self):
        self.status_signal.emit("⏳ 正在初始化OCR引擎，请稍候...")
        try:
            self.ocr = RapidOCR()
        except Exception as e:
            self.error_signal.emit(f"OCR初始化失败: {e}")
            return

        self.init_done.emit()
        self.status_signal.emit("🔍 OCR就绪，开始监测...")

        while self._running and not self.isInterruptionRequested():
            if self._paused:
                self._sleep_check(0.3)
                continue

            if self._resume_time:
                waited = time.time() - self._resume_time
                left = self.interval - waited
                if left > 0:
                    self.status_signal.emit(
                        f"⏳ 已知晓，{left:.0f}秒后恢复监测..."
                    )
                    self._sleep_check(left)
                self._resume_time = 0

            cycle_start = time.time()

            try:
                screenshot = pyautogui.screenshot()
                screen_np = np.array(screenshot)
                if self.scale < 1.0:
                    h, w = screen_np.shape[:2]
                    new_w, new_h = int(w * self.scale), int(h * self.scale)
                    screen_np = cv2.resize(screen_np, (new_w, new_h))
                result, _ = self.ocr(screen_np)

                found = False
                if result:
                    for line in result:
                        text = line[1]
                        for keyword in self.keywords:
                            if keyword.strip() and keyword.strip() in text:
                                self.found_signal.emit(keyword)
                                self._paused = True
                                found = True
                                break
                        if found:
                            break

                if not found and self._running and not self.isInterruptionRequested():
                    elapsed = time.time() - cycle_start
                    left = self.interval - elapsed
                    self.status_signal.emit(
                        f"⏳ 未检测到目标文字 ({time.strftime('%H:%M:%S')})"
                    )
                    if left > 0:
                        self._sleep_check(left)

            except Exception as e:
                if self._running:
                    self.error_signal.emit(str(e))
                self._sleep_check(2)

    def _sleep_check(self, seconds):
        """Sleep in small increments, checking for interruption."""
        step = 0.1
        elapsed = 0.0
        while elapsed < seconds and self._running and not self.isInterruptionRequested():
            time.sleep(min(step, seconds - elapsed))
            elapsed += step

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False
        self._resume_time = time.time()

    def stop(self):
        self._running = False
        self._paused = False
        self.requestInterruption()


class MonitorWindow(QMainWindow):
    MAX_LOG_LINES = 2000

    def __init__(self):
        super().__init__()
        self.setWindowTitle("屏幕文字监测系统")
        self.setMinimumSize(1000, 600)
        self.resize(1000, 600)

        self.monitoring = False
        self.alerting = False
        self.worker = None

        self._setup_ui()
        self._apply_styles()
        generate_alarm_wav()

    # ── UI construction ──────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # 标题
        title = QLabel("屏幕文字监测系统")
        title.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50; padding: 8px 0;")
        layout.addWidget(title)

        # ── 关键词 + 设置区域 ──
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # 关键词编辑
        self.kw_group = QGroupBox("监测关键词 (每行一个)")
        self.kw_group.setFont(QFont("Microsoft YaHei", 13))
        kw_vbox = QVBoxLayout(self.kw_group)
        self.keywords_edit = QTextEdit()
        self.keywords_edit.setFont(QFont("Microsoft YaHei", 13))
        self.keywords_edit.setPlaceholderText("输入要监测的关键词，每行一个...")
        self.keywords_edit.setText("为保障账号安全，请进行验证")
        self.keywords_edit.setMinimumHeight(110)
        kw_vbox.addWidget(self.keywords_edit)
        top_row.addWidget(self.kw_group, 1)

        # 设置
        set_group = QGroupBox("监测设置")
        set_group.setFont(QFont("Microsoft YaHei", 13))
        set_vbox = QVBoxLayout(set_group)
        set_vbox.setSpacing(14)

        iv_row = QHBoxLayout()
        iv_lbl = QLabel("监测间隔:")
        iv_lbl.setFont(QFont("Microsoft YaHei", 13))
        self.interval_spin = QSpinBox()
        self.interval_spin.setFont(QFont("Microsoft YaHei", 13))
        self.interval_spin.setMinimum(1)
        self.interval_spin.setMaximum(120)
        self.interval_spin.setValue(3)
        self.interval_spin.setSuffix(" 秒")
        self.interval_spin.setFixedHeight(38)
        iv_row.addWidget(iv_lbl)
        iv_row.addWidget(self.interval_spin)
        iv_row.addStretch()
        set_vbox.addLayout(iv_row)

        # 缩放比例（降低CPU占用）
        sc_row = QHBoxLayout()
        sc_lbl = QLabel("缩放比例:")
        sc_lbl.setFont(QFont("Microsoft YaHei", 13))
        self.scale_slider = QSpinBox()
        self.scale_slider.setFont(QFont("Microsoft YaHei", 13))
        self.scale_slider.setMinimum(30)
        self.scale_slider.setMaximum(100)
        self.scale_slider.setValue(50)
        self.scale_slider.setSuffix("%")
        self.scale_slider.setFixedHeight(38)
        self.scale_slider.setToolTip("数值越小占用越低，但可能影响识别率")
        sc_row.addWidget(sc_lbl)
        sc_row.addWidget(self.scale_slider)
        sc_row.addStretch()
        set_vbox.addLayout(sc_row)
        set_vbox.addStretch()
        top_row.addWidget(set_group, 2)
        layout.addLayout(top_row)

        # ── 状态显示 ──
        self.status_label = QLabel("就绪 — 请点击「开始监测」")
        self.status_label.setFont(QFont("Microsoft YaHei", 16))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(56)
        self.status_label.setStyleSheet(
            "background-color: #eaf0f6; border-radius: 10px; padding: 10px; color: #34495e;"
        )
        layout.addWidget(self.status_label)

        # ── 已知晓按钮 ──
        self.known_button = QPushButton()
        self.known_button.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        self.known_button.setMinimumHeight(65)
        self.known_button.setVisible(False)
        self.known_button.clicked.connect(self._on_known)
        layout.addWidget(self.known_button)

        # ── 日志 ──
        log_group = QGroupBox("检测日志")
        log_group.setFont(QFont("Microsoft YaHei", 13))
        log_vbox = QVBoxLayout(log_group)
        self.log_browser = QTextBrowser()
        self.log_browser.setFont(QFont("Consolas", 11))
        self.log_browser.setMinimumHeight(80)
        log_vbox.addWidget(self.log_browser)
        layout.addWidget(log_group, 1)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(24)
        btn_row.addStretch()

        self.start_btn = QPushButton("▶  开始监测")
        self.start_btn.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        self.start_btn.setMinimumSize(200, 52)
        self.start_btn.clicked.connect(self._on_start)

        self.stop_btn = QPushButton("⏹  停止监测")
        self.stop_btn.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        self.stop_btn.setMinimumSize(200, 52)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)

        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status_bar = QStatusBar()
        self.status_bar.setFont(QFont("Microsoft YaHei", 10))
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("系统就绪")

    def _apply_styles(self):
        base = """
            QMainWindow { background-color: #f5f6fa; }
            QGroupBox {
                border: 2px solid #dcdde1; border-radius: 10px;
                margin-top: 18px; padding-top: 18px;
                font-weight: bold; color: #2f3640;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 16px; padding: 0 8px;
            }
            QTextEdit, QTextBrowser {
                border: 2px solid #dcdde1; border-radius: 8px;
                padding: 8px; background-color: #ffffff;
            }
            QSpinBox {
                border: 2px solid #dcdde1; border-radius: 6px;
                padding: 5px 10px; font-size: 14px; background-color: #ffffff;
            }
            QPushButton {
                border: none; border-radius: 10px; padding: 10px 24px;
            }
        """
        self.setStyleSheet(base)

        self.start_btn.setStyleSheet("""
            QPushButton { background-color: #27ae60; color: white; }
            QPushButton:hover { background-color: #219a52; }
            QPushButton:pressed { background-color: #1e8449; }
            QPushButton:disabled { background-color: #bdc3c7; color: #7f8c8d; }
        """)
        self.stop_btn.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:pressed { background-color: #a93226; }
            QPushButton:disabled { background-color: #bdc3c7; color: #7f8c8d; }
        """)
        self.known_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c; color: white;
                border: 3px solid #c0392b; border-radius: 14px;
            }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:pressed { background-color: #a93226; }
        """)

    # ── 日志 ─────────────────────────────────────────────────────────

    def _log(self, msg):
        t = time.strftime('%H:%M:%S')
        self.log_browser.append(f"[{t}] {msg}")
        doc = self.log_browser.document()
        while doc.blockCount() > self.MAX_LOG_LINES:
            cursor = QTextCursor(doc.begin())
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

    # ── 线程安全停止 worker ──────────────────────────────────────────

    def _safe_stop_worker(self):
        if not self.worker:
            return
        try:
            self.worker.status_signal.disconnect(self._on_status)
        except Exception:
            pass
        try:
            self.worker.found_signal.disconnect(self._on_found)
        except Exception:
            pass
        try:
            self.worker.error_signal.disconnect(self._on_error)
        except Exception:
            pass
        try:
            self.worker.init_done.disconnect(self._on_init_done)
        except Exception:
            pass

        self.worker.stop()
        if not self.worker.wait(3000):
            self.worker.terminate()
            self.worker.wait(2000)
        self.worker = None

    # ── 开始 / 停止 ──────────────────────────────────────────────────

    def _on_start(self):
        if self.monitoring:
            return
        kw_text = self.keywords_edit.toPlainText().strip()
        if not kw_text:
            self.status_label.setText("❌ 请输入至少一个监测关键词")
            return
        keywords = [k.strip() for k in kw_text.split('\n') if k.strip()]
        interval = self.interval_spin.value()
        scale = self.scale_slider.value() / 100.0

        self.monitoring = True
        self.alerting = False
        self.kw_group.hide()

        self.known_button.setVisible(False)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.interval_spin.setEnabled(False)
        self.scale_slider.setEnabled(False)

        self.status_label.setText("⏳ 正在初始化OCR引擎，请稍候...")
        self.status_bar.showMessage(f"OCR初始化中...")

        self.worker = OCRWorker()
        self.worker.keywords = keywords
        self.worker.interval = interval
        self.worker.scale = scale
        self.worker.status_signal.connect(self._on_status)
        self.worker.found_signal.connect(self._on_found)
        self.worker.error_signal.connect(self._on_error)
        self.worker.init_done.connect(self._on_init_done)
        self.worker.start()

        self._log(f"监测已启动 (间隔 {interval} 秒)")

    def _on_init_done(self):
        self.status_bar.showMessage(
            f"正在监测 — 间隔 {self.interval_spin.value()} 秒"
        )

    def _on_stop(self):
        if not self.monitoring:
            return
        self.monitoring = False
        self.alerting = False
        winsound.PlaySound(None, 0)

        self._safe_stop_worker()

        self.kw_group.show()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.interval_spin.setEnabled(True)
        self.scale_slider.setEnabled(True)
        self.known_button.setVisible(False)

        self.status_label.setText("⏸ 监测已停止")
        self.status_bar.showMessage("系统就绪")
        self._log("监测已停止")

    # ── 检测到关键词 ─────────────────────────────────────────────────

    def _on_found(self, keyword):
        if not self.monitoring or self.alerting:
            return
        self.alerting = True
        if self.worker:
            self.worker.pause()

        self.known_button.setVisible(True)
        self.known_button.setText(f"✅ 已知晓 — 检测到「{keyword}」点击停止警报并继续监测")
        self.status_label.setText(f"🚨 检测到关键词: {keyword} — 正在播放警报...")
        self.status_bar.showMessage("⚠ 警报中... 请点击「已知晓」按钮停止")

        alarm = get_alarm_path()
        if os.path.exists(alarm):
            winsound.PlaySound(alarm, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)

        self._log("🚨 监测到目标文字")

    # ── 已知晓 ───────────────────────────────────────────────────────

    def _on_known(self):
        if not self.alerting:
            return
        winsound.PlaySound(None, 0)
        self.alerting = False
        self.known_button.setVisible(False)
        self.status_label.setText("🔍 已确认，继续监测中...")
        self.status_bar.showMessage("继续监测")
        if self.worker:
            self.worker.resume()
        self._log("✅ 用户已确认警报")

    # ── 信号回调 ─────────────────────────────────────────────────────

    def _on_status(self, msg):
        if not self.monitoring:
            return
        if not self.alerting:
            self.status_label.setText(msg)
            self.status_bar.showMessage(msg)
        self._log(msg)

    def _on_error(self, msg):
        if self.monitoring:
            self._log(f"❌ 错误: {msg}")

    # ── 退出 ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        winsound.PlaySound(None, 0)
        self.monitoring = False
        self._safe_stop_worker()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    window = MonitorWindow()
    window.show()
    sys.exit(app.exec())
