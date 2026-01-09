# K-Robot (For Lucy) 

K-Robot 是一个为 Lucy 打造的智能伴侣机器人项目。它通过多模态交互（视、听、说、读、想）和实时 Live2D 表现，提供温暖、智能的陪伴体验。

## 🏗 项目架构

项目采用三层逻辑架构，确保表现层、逻辑层与基础服务层解耦，方便后期维护与技术迭代。

### 1. Appearance (表现层) - `src/appearance/`
负责机器人的**实时视觉展示**。
- **Live2D / 3D 动画驱动**：管理机器人的面部表情、眼神跟随及肢体动作。
- **实时性**：与 `modules/speaking` 同步，实现口型对齐 (Lip-sync)。

### 2. Modules (功能层) - `src/modules/`
负责机器人的**核心感官与认知能力**。
- **听 (Hearing)**: 处理音频输入流，管理 ASR 逻辑。
- **说 (Speaking)**: 管理语音输出逻辑，驱动嘴部动画协调。
- **想 (Thinking)**: 负责对话状态、情感分析与逻辑决策。
- **看 (Watching/Vision)**: 结合 YOLO 等模型，识别环境与人脸。
- **读 (Reading)**: 处理文本输入或视觉文字识别 (OCR)。
- **记 (Memory)**: 管理对话历史、上下文和长期记忆。

### 3. Service (基础服务层) - `src/service/`
负责**底层技术实现与外部 API 适配**。
- **LLM**: 大语言模型 API 接入。
- **TTS**: 语音合成服务接口。
- **API**: 统一的网络请求与基础数据交互。

---

## 🚀 核心逻辑流

1. **输入端**：`modules/hearing` 或 `modules/watching` 获取传感器数据。
2. **处理端**：`modules/thinking` 调用 `service/llm` 进行认知处理。
3. **输出端**：`modules/speaking` 调用 `service/tts` 生成声音，并触发 `appearance/act/mouth` 的口型动画。

---

## 🛠 模型训练 `src/` 根目录
- `training.py`: 主训练逻辑，用于模型微调或参数更新。
- `preprocessing.py`: 数据清洗与特征提取。
- `reasoning.py`: 模型推理逻辑封装。

---

## 📦 依赖管理
项目使用 `uv` 进行依赖管理。
```bash
uv sync
```
