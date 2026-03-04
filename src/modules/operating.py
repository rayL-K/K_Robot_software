"""
K-Robot 核心模块：操作
职责：处理计算机内部操作。
技术栈：纯粹基于 PyAutoGUI，在接受到大脑给出的坐标和动作指令后，进行真实的鼠标与键盘输入。放弃一切基于窗口句柄的复杂操作。
"""
import time
import os
from typing import Dict, Any
import pyautogui

class Operator:
    """物理动作执行器（双手），将大脑给定的确切坐标决策转换为键鼠物理动作"""
    
    def __init__(self):
        # 开启防止失控：如果在运作时机器人乱跑，将鼠标甩到屏幕四个角落任意一处即可抛出异常终止程序。
        pyautogui.FAILSAFE = True
        # 加入默认执行后延迟，使其操作更拟人，不至于过快导致系统还没反应过来
        pyautogui.PAUSE = 0.5 

    def execute_action(self, action_cmd: Dict[str, Any]) -> bool:
        """
        解析大脑下发的指令字典并执行。
        
        支持的 action_cmd 格式:
        1. {"action": "click", "x": 500, "y": 300, "button": "left"}
        2. {"action": "type", "text": "hello world", "enter": True}
        3. {"action": "hotkey", "keys": ["ctrl", "c"]}
        4. {"action": "scroll", "amount": -500}
        5. {"action": "wait", "time": 2}
        6. {"action": "done"}
        """
        action_type = action_cmd.get("action")
        print(f"[Operator] 正在执行动作: {action_cmd}")
        
        try:
            if action_type == "click" or action_type == "double_click":
                raw_x = action_cmd.get('x')
                raw_y = action_cmd.get('y')
                
                # 增强鲁棒性：处理某些模型喜欢把坐标写成列表的情况，例如 "x": [276, 972]
                if isinstance(raw_x, list) and len(raw_x) >= 2:
                    x, y = int(raw_x[0]), int(raw_x[1])
                elif isinstance(raw_y, list) and len(raw_y) >= 2:
                    x, y = int(raw_y[0]), int(raw_y[1])
                else:
                    x, y = int(raw_x), int(raw_y)
                    
                button = action_cmd.get('button', 'left')
                pyautogui.moveTo(x, y, duration=0.3) # 拟人化的移动过程
                time.sleep(0.1)
                
                if action_type == "double_click":
                    # 双击：用于打开文件夹、文件等
                    pyautogui.doubleClick(x, y, button=button)
                else:
                    # 单击
                    pyautogui.mouseDown(button=button)
                    time.sleep(0.05)
                    pyautogui.mouseUp(button=button)
                time.sleep(0.1)

                
            elif action_type == "type":
                text = action_cmd.get('text', '')
                try:
                    import pyperclip
                    # 使用剪贴板粘贴的方式输入，因为 pyautogui.write 原生不支持通过虚拟按键打出中文
                    pyperclip.copy(text)
                    time.sleep(0.1) # 给系统剪贴板一定响应时间
                    pyautogui.hotkey('ctrl', 'v')
                    time.sleep(0.1)
                except ImportError:
                    print("[Operator] 警告：请安装 pyperclip (uv pip install pyperclip) 以支持中文输入。回退为英文纯键入。")
                    pyautogui.write(text, interval=0.05)
                if action_cmd.get('enter', False):
                    pyautogui.press('enter')
                    
            elif action_type == "hotkey":
                keys = action_cmd.get('keys', [])
                if keys:
                    pyautogui.hotkey(*keys)
                    
            elif action_type == "scroll":
                amount = int(action_cmd.get("amount", -500))
                pyautogui.scroll(amount)
                
            elif action_type == "wait":
                wait_time = float(action_cmd.get("time", 1.0))
                time.sleep(wait_time)
                
            elif action_type == "cmd":
                command = action_cmd.get("command", "")
                if command:
                    import subprocess
                    print(f"[Operator ⚡ 系统级直调]: 正在执行命令 '{command}'")
                    # 后台异步启动，避免阻塞，设置 creationflags 隐藏黑窗口 (针对 Windows)
                    # 如果跨平台，忽略 creationflags
                    if os.name == 'nt':
                        subprocess.Popen(command, shell=True, creationflags=0x08000000)
                    else:
                        subprocess.Popen(command, shell=True)
                    time.sleep(1.0) # 给系统一点启动软件的缓冲时间
                
            elif action_type == "done":
                # 任务完成的标记
                return True
                
            else:
                print(f"[Operator] 遇到未知的动作类型: {action_type}")
                return False
                
            return True
            
        except pyautogui.FailSafeException:
            print("[Operator] 触发安全保护机制 (鼠标被强行移至角落)！执行被紧急终止。")
            raise
        except Exception as e:
            print(f"[Operator] 执行 {action_type} 时遇错: {e}")
            return False

