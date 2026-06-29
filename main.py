import ctypes

ctypes.windll.user32.SetProcessDPIAware()

import pyautogui
import numpy as np
from rapidocr_onnxruntime import RapidOCR
import winsound
import time

# 初始化OCR引擎
ocr = RapidOCR()

# 你要监测的目标文字
target_text = "为保障账号安全，请进行验证"

print("👁️ 开始OCR监测屏幕...")
print("⏱️ 每5秒扫描一次 (按 Ctrl+C 停止)")
print("-" * 50)
alarm_sound = 'alarm.wav'

try:
    while True:
        # 截取全屏
        screenshot = pyautogui.screenshot()
        screen_np = np.array(screenshot)

        # OCR识别
        result, elapse = ocr(screen_np)

        found = False

        if result:
            # 遍历所有识别到的文字
            for line in result:
                text = line[1]  # 获取识别出的文字
                # 检查是否包含目标文字
                if target_text in text:
                    print(f"\n🚨 [{time.strftime('%H:%M:%S')}] 发现目标文字！强制播放警报5秒...")

                    # 1. 使用 SND_ASYNC 异步播放，防止长音频阻塞程序
                    winsound.PlaySound(alarm_sound, winsound.SND_FILENAME | winsound.SND_ASYNC)

                    # 2. 强制等待5秒
                    time.sleep(5)

                    # 3. 5秒后强制停止播放（不管wav实际有多长）
                    winsound.PlaySound(None, 0)

                    found = True
                    break

        if found:
            # 如果找到了，播放完5秒后直接开启下次扫描，不再额外等待
            continue
        else:
            print(f"⏳ [{time.strftime('%H:%M:%S')}] 未找到目标，5秒后重试...")
            # 只有在没找到目标时，才执行常规的5秒等待
            time.sleep(5)

except KeyboardInterrupt:
    print("\n✅ 监测已停止")