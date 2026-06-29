# 屏幕文字监测系统

实时监测屏幕指定文字，检测到后循环播放警报，用户确认后自动恢复监测。

## 功能

- **OCR 屏幕监测** — 定时截屏识别，支持多关键词
- **持续警报** — 检测到目标文字后循环播放警报音，暂停扫描
- **已知晓确认** — 手动点击按钮停止警报，按设定间隔自动恢复监测
- **缩放加速** — 可调节截图缩放比例（30%~100%），降低 CPU 占用
- **可配置** — 关键词、监测间隔、缩放比例均可调
- **GPU 可选** — 安装 `onnxruntime-gpu` 后自动启用 CUDA 加速

## 运行

```bash
# 安装依赖
pip install PySide6 rapidocr-onnxruntime pyautogui numpy opencv-python

# 运行
python main_qt.py
```

首次运行会自动在程序同级目录生成 `alarm.wav` 警报音文件，也可替换为自己的 `.wav` 文件。

## 打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "屏幕文字监测" ^
    --hidden-import PySide6 ^
    --hidden-import rapidocr_onnxruntime ^
    --hidden-import onnxruntime ^
    --hidden-import cv2 ^
    --collect-all rapidocr_onnxruntime ^
    main_qt.py
```

产物在 `dist/` 目录，约 115MB。分发时将 `alarm.wav` 与 exe 放在同一目录即可。

## 目录结构

```
├── main_qt.py          # Qt 主程序
├── main.py             # 命令行版（原始）
├── alarm.wav           # 警报音（自动生成，不提交 git）
└── dist/               # 打包产物（不提交 git）
```
