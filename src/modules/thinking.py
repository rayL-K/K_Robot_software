"""
K-Robot 核心模块：思考、推理与决策
职责：管理对话上下文、情感状态和，对机内与机外进行决策与操控。
技术栈：使用大模型中转 API 传入 Base64 屏幕截图，要求模型返回包含确切操作坐标的 JSON 结构，并交由 operating 模块执行。

性能优化：
- 方案1: Planner 首次输出完整 master_plan，后续只输出 next_step + replan 标志（减少输出 tokens）
- JSON 解析增强鲁棒性：支持截断恢复、markdown包裹清理、正则兜底提取
"""
import json
import re
import os
import time
from typing import Dict, Any, List, Optional

from openai import OpenAI
from httpx import Timeout


def robust_extract_json(raw_text: str) -> Optional[dict]:
    """
    从可能被污染的模型输出中，极力提取出一个合法的 JSON 字典。
    
    应对的脏数据场景：
    1. ```json ... ``` markdown 包裹
    2. JSON 前后有解释性文字
    3. JSON 被截断（缺少闭合括号）
    4. 字段值被截断（缺少闭合引号）
    5. 多余的转义字符
    """
    if not raw_text or not raw_text.strip():
        return None
    
    text = raw_text.strip()
    
    # 1. 清理 markdown 包裹
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()
    
    # 2. 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 3. 尝试提取 {...} 最外层花括号对
    brace_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # 4. 尝试找到以 { 开头的部分，手动补全截断的 JSON
    brace_start = text.find('{')
    if brace_start >= 0:
        fragment = text[brace_start:]
        
        # 尝试逐步补全闭合
        for suffix in ['', '"', '"}', '"}', 'false}', 'true}', '"]}']:
            try:
                return json.loads(fragment + suffix)
            except json.JSONDecodeError:
                continue
        
        # 更激进的补全：统计未闭合的括号
        open_braces = fragment.count('{') - fragment.count('}')
        open_quotes = fragment.count('"') % 2  # 奇数说明有未闭合引号
        
        repair = fragment
        if open_quotes:
            repair += '"'
        repair += '}' * max(open_braces, 0)
        
        try:
            return json.loads(repair)
        except json.JSONDecodeError:
            pass
    
    # 5. 最终兜底：用正则直接提取关键字段
    return None


def robust_extract_field(raw_text: str, field_name: str) -> Optional[str]:
    """
    即使 JSON 完全无法解析，也能用正则从原始文本中提取指定字段的值。
    支持完整值和被截断的值。
    """
    if not raw_text:
        return None
    
    # 精准匹配：完整的 "field": "value"
    match = re.search(rf'"{field_name}"\s*:\s*"([^"]*)"', raw_text)
    if match:
        return match.group(1)
    
    # 宽松匹配：被截断的 "field": "partial_value（没有闭合引号）
    match = re.search(rf'"{field_name}"\s*:\s*"([^"]+)', raw_text)
    if match:
        value = match.group(1).rstrip('\\, \n\r')
        if len(value) >= 3:  # 至少3个字符才算有效
            return value
    
    return None


class Brain:
    """
    系统双层大脑：
    1. 宏观规划者 (Planner): 理解全局目标，观察当前屏幕状态，决定下一步的微观子目标。
    2. 视觉操作者 (Vision Operator): 接收微观子目标，通过带网格的屏幕截图，精准提取操作坐标。
    """
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
            
        profiles = []
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        profiles = data
                    elif isinstance(data, dict):
                        profiles = [data]
            except Exception as e:
                print(f"[Brain] 配置文件解析失败: {e}")
        else:
            print(f"[Brain] 警告: 未找到配置文件 {config_path}，建议复制 config.example.json 进行配置。")

        if not profiles:
            raise ValueError(f"请在 {config_path} 中配置有效的 API 节点组。")

        self.client = None
        
        print("\n[Brain] 开始逐个测试配置集连通性...")
        for idx, profile in enumerate(profiles):
            name = profile.get("name", f"Profile_{idx+1}")
            api_key = profile.get("api_key", "")
            base_url = profile.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            
            if not api_key or api_key == "YOUR_API_KEY_HERE" or api_key.startswith("YOUR_"):
                print(f"  [跳过] '{name}': API Key 未配置或为占位符。")
                continue
                
            test_client = OpenAI(api_key=api_key, base_url=base_url)
            try:
                test_client.chat.completions.create(
                    model=profile.get("planner_model", "qwen-plus"),
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1,
                    timeout=Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
                )
                
                self.client = test_client
                self.planner_model = profile.get("planner_model", "qwen3.5-flash-2026-02-23")
                self.operator_model = profile.get("operator_model", "qwen3-vl-flash-2026-01-22")
                print(f"  [匹配成功] 将使用高可用配置集: '{name}'")
                print(f"             - Planner: {self.planner_model}")
                print(f"             - Operator: {self.operator_model}")
                break
                
            except Exception as e:
                print(f"  [连通失败] '{name}' (URL: {base_url}): 验证请求异常 ({e})。自动降级到下一组配置。")
                
        if self.client is None:
            raise ValueError("所有提供的配置项均无法连接成功，请检查 config.json 中的 api_key、网络状态或模型名填写是否正确。")
        
        self.master_plan = []  # 全局演进路线
        self._is_first_plan = True  # 标记是否为首次规划
        self._goal_preprocessed = False  # 标记是否已预处理过目标
        self._file_in_clipboard = False  # 标记文件是否已复制到剪贴板

    def reason_macro_step(self, global_goal: str, screen_base64: str) -> Optional[str]:
        """
        [第一层] 宏观规划者：基于全局目标和当前屏幕推理下一步。
        带重试机制，返回 next_step 字符串，失败返回 None。
        """
        from src.modules.prompts.prompts import PLANNER_INITIAL_PROMPT, PLANNER_FOLLOWUP_PROMPT
        
        if self._is_first_plan:
            prompt = PLANNER_INITIAL_PROMPT.format(global_goal=global_goal)
            max_tokens = 300
            read_timeout = 60.0
            print(f"\n[Planner] 🗺️ 首次规划，生成完整路线图: '{global_goal}'...")
        else:
            master_plan_str = json.dumps(self.master_plan, ensure_ascii=False)
            prompt = PLANNER_FOLLOWUP_PROMPT.format(global_goal=global_goal, master_plan=master_plan_str)
            max_tokens = 200
            read_timeout = 20.0
            print(f"\n[Planner] ⚡ 快速视觉校验中...")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                t0 = time.time()
                response = self.client.chat.completions.create(
                    model=self.planner_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{screen_base64}",
                                        "detail": "auto"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=max_tokens,
                    temperature=0.1 if not self._is_first_plan else 0.3,
                    timeout=Timeout(connect=5.0, read=read_timeout, write=5.0, pool=5.0)
                )
                t1 = time.time()
                
                result_text = response.choices[0].message.content.strip()
                print(f"[Planner] 原始返回 ({t1-t0:.1f}s):\n{result_text[:300]}")
                
                # 多层鲁棒解析
                next_step = None
                
                # 层1: 尝试完整 JSON 解析
                result_json = robust_extract_json(result_text)
                if result_json:
                    next_step = result_json.get("next_step")
                    thought = result_json.get("thought", result_json.get("thought_process", ""))
                    
                    # 更新全局计划
                    if self._is_first_plan:
                        new_plan = result_json.get("master_plan")
                        if new_plan and isinstance(new_plan, list):
                            self.master_plan = new_plan
                            self._is_first_plan = False
                            print(f"[Planner 全局路线 ✅]: {self.master_plan}")
                    else:
                        if result_json.get("replan", False):
                            new_plan = result_json.get("master_plan")
                            if new_plan and isinstance(new_plan, list):
                                self.master_plan = new_plan
                                print(f"[Planner ⚠️ 偏航重规划]: {self.master_plan}")
                    
                    if thought:
                        print(f"[Planner 判断]: {thought}")
                
                # 层2: JSON 解析失败或无 next_step，用正则直接提取
                if not next_step:
                    next_step = robust_extract_field(result_text, "next_step")
                    if next_step:
                        print(f"[Planner 正则提取 next_step]: {next_step}")
                        # 首次规划也尝试提取 master_plan
                        if self._is_first_plan:
                            plan_match = re.search(r'"master_plan"\s*:\s*\[(.*?)\]', result_text, re.DOTALL)
                            if plan_match:
                                try:
                                    plan_items = json.loads(f"[{plan_match.group(1)}]")
                                    self.master_plan = plan_items
                                    self._is_first_plan = False
                                    print(f"[Planner 全局路线 ✅]: {self.master_plan}")
                                except json.JSONDecodeError:
                                    pass
                
                if next_step:
                    print(f"[Planner 下一步]: ---> {next_step} <---")
                    return next_step
                else:
                    print(f"[Planner] 第 {attempt+1}/{max_retries} 次未能提取 next_step")
                    
            except Exception as e:
                print(f"[Planner] 第 {attempt+1}/{max_retries} 次异常: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(1)
        
        return None

    def extract_coordinates(self, sub_goal: str, screen_base64: str, screen_size: Dict[str, int] = None) -> List[Dict[str, Any]]:
        """
        [第二层] 视觉操作者：基于具体的子目标，在有网格的屏幕上找出操作坐标。
        """
        if screen_size is None:
            screen_size = {"width": 1920, "height": 1080}
        width, height = screen_size.get("width", 1920), screen_size.get("height", 1080)
        print(f"[Vision Operator] 开始在网格中寻找子目标坐标...")
        
        from src.modules.prompts.prompts import OPERATOR_PROMPT_TEMPLATE
        prompt = OPERATOR_PROMPT_TEMPLATE.format(sub_goal=sub_goal, width=width, height=height)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.operator_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{screen_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=200,
                    temperature=0.1,
                    timeout=Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
                )
                
                result_text = response.choices[0].message.content.strip()
                print(f"[Vision Operator] 原始坐标返回 (尝试 {attempt+1}/{max_retries}):\n{result_text}")
                
                # 增强的 JSON 数组解析
                json_match = re.search(r'\[\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*\]', result_text, re.DOTALL)
                
                if not json_match:
                    # 尝试找单个字典并包裹
                    dict_match = re.search(r'\{[^{}]*"action"[^{}]*\}', result_text, re.DOTALL)
                    if dict_match:
                        json_str = f"[{dict_match.group(0)}]"
                    else:
                        raise ValueError("无法从模型返回中提取到有效的 JSON 数组或对象。")
                else:
                    json_str = json_match.group(0)
                    
                actions = json.loads(json_str)
                    
                # 转换千分位归一化坐标到真实屏幕物理像素
                for act in actions:
                    if act.get("action") in ("click", "double_click"):
                        x_val = act.get("x_norm", act.get("x"))
                        y_val = act.get("y_norm", act.get("y"))
                        
                        if isinstance(x_val, list) and len(x_val) >= 2:
                            x_val, y_val = x_val[0], x_val[1]
                        elif isinstance(y_val, list) and len(y_val) >= 2:
                            x_val, y_val = y_val[0], y_val[1]
                            
                        if x_val is not None and y_val is not None:
                            if float(x_val) <= 1000 and float(y_val) <= 1000:
                                act["x"] = int(float(x_val) / 1000.0 * width)
                                act["y"] = int(float(y_val) / 1000.0 * height)
                                print(f"[Vision Operator 转换归一化]: ({x_val}, {y_val}) -> 绝对物理像素 ({act['x']}, {act['y']})")
                            else:
                                act["x"], act["y"] = int(x_val), int(y_val)

                return actions
                
            except Exception as e:
                print(f"[Vision Operator] 寻址时发生异常 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    return []
        return []

    
    def _preprocess_file_task(self, goal: str) -> str:
        """
        预处理：检测目标中是否包含文件发送任务。
        如果检测到文件路径，自动通过 PowerShell 将文件复制到系统剪贴板，
        并修改目标描述以引导 Planner 使用 Ctrl+V 粘贴而非文件对话框。
        """
        # 检测 Windows 文件路径，支持包含空格的路径 (如 C:\Users\...\xxx.png 或 E:\xxx\yyy.docx)
        file_pattern = re.search(
            r'([A-Za-z]:\\[^、。，）\)]+\.\w{1,10})',
            goal
        )
        
        if not file_pattern:
            return goal
        
        file_path = file_pattern.group(1)
        print(f"\n[📁 文件任务检测] 发现文件路径: {file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"[📁 警告] 文件不存在: {file_path}，跳过剪贴板预处理")
            return goal
        
        # 通过系统控件将文件复制到剪贴板
        from src.modules.system_control.clipboard import copy_file_to_clipboard
        if copy_file_to_clipboard(file_path):
            self._file_in_clipboard = True
            print(f"[📁 剪贴板就绪] 文件已复制到系统剪贴板 ✅")
            
            # 重写目标：告诉 Planner 文件已在剪贴板，直接 Ctrl+V
            new_goal = goal.replace(
                file_path,
                f"【文件已在剪贴板中】"
            )
            new_goal += "（重要：文件已经被复制到系统剪贴板，不需要点发送文件按钮，直接在聊天输入框中 Ctrl+V 粘贴即可发送）"
            print(f"[📁 目标重写]: {new_goal}")
            return new_goal
        else:
            print(f"[📁 剪贴板失败] 复制到剪贴板失败")
        
        return goal

    def plan_next_action(self, global_goal: str, screen_base64: str, screen_size: Dict[str, int] = None) -> List[Dict[str, Any]]:
        """
        对外的统一入口，调度双脑模式。
        """
        if screen_size is None:
            screen_size = {"width": 1920, "height": 1080}
        
        # 0. 首次调用时预处理目标（检测文件发送任务）
        if not self._goal_preprocessed:
            global_goal = self._preprocess_file_task(global_goal)
            self._preprocessed_goal = global_goal  # 缓存重写后的目标
            self._goal_preprocessed = True
        else:
            global_goal = getattr(self, '_preprocessed_goal', global_goal)
        
        # 1. Planner 推理下一步
        sub_task = self.reason_macro_step(global_goal, screen_base64)
        
        if sub_task is None:
            return []
        if sub_task.lower() == "done":
            return [{"action": "done"}]
            
        # 2. Operator 提取坐标
        actions = self.extract_coordinates(sub_task, screen_base64, screen_size)
        return actions
