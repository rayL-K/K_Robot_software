import time
import sys
import os

# 将 src 目录添加到模块搜索路径以支持跨目录导入
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.modules.thinking import Brain
from src.modules.inwatching import ScreenWatcher
from src.modules.operating import Operator

def run_test():
    print("--- K-Robot 多步智能体测试初始化 ---")
    
    watcher = ScreenWatcher()
    brain = Brain()
    # 暂时禁用 failsafe 方便无人值守循环测试，实际使用建议开启
    operator = Operator() 
    
    # 设定一个复杂的宏观目标
    goal = "我想在QQ中给棂宝发送一个文件（C:\\Users\\Administrator\\Pictures\\Saved Pictures\\test.png）"
    print(f"最终全局目标: 【{goal}】\n")
    
    step_count = 1
    max_steps = 20 # 防止死循环
    
    while step_count <= max_steps:
        print(f"\n==================== [第 {step_count} 步测试循环] ====================")
        print("========== [1. 感知] 获取屏幕... ==========")
        t0 = time.time()
        screen_b64 = watcher.capture_screen_base64()
        screen_info = watcher.get_screen_size()
        t1 = time.time()
        print(f"[感知完成] 耗时: {t1 - t0:.2f} 秒\n")
        
        print(f"========== [2. 思考] 大脑正在规划与提取坐标... ==========")
        t2 = time.time()
        actions = brain.plan_next_action(goal, screen_b64, screen_size=screen_info)
        t3 = time.time()
        print(f"\n[思考完成] 耗时: {t3 - t2:.2f} 秒\n")
        
        if not actions:
            print("大脑没有返回有效指令，可能需要干预。")
            break
            
        if any(act.get("action") == "done" for act in actions):
            print("🎉 大脑判断目标已经完全达成 (Done)！测试结束。")
            break
            
        print("========== [3. 执行] 双手操作执行决策... ==========")
        t4 = time.time()
        for act in actions:
            print(f"准备执行动作: {act}")
            operator.execute_action(act)
            time.sleep(1) # 操作之间加上合理的停顿
        t5 = time.time()
        print(f"[执行完成] 耗时: {t5 - t4:.2f} 秒\n")
        
        total_time = t5 - t0
        print(f">>> 本轮单步总耗时: {total_time:.2f} 秒 <<<")
        print(f"本轮执行完毕，等待 3 秒后重新评估画面效果...\n")
        time.sleep(3)
        step_count += 1
        
    if step_count > max_steps:
        print(f"达到了最大步数 {max_steps}，强行终止循环。")

if __name__ == "__main__":
    run_test()
