# pymediamixer

基于 GStreamer 的媒体导播混流应用，支持多路音视频流的合成（混流、画中画、音频混音）与实时处理。

## 功能特性

- **多路输入**：支持视频测试源（videotestsrc）等多种输入类型
- **视频合成**：支持多通道视频合成、画中画（PiP）布局
- **实时输出**：支持本地预览窗口（autovideosink）输出
- **动态切换**：运行时动态切换输入源，无需重启
- **配置驱动**：通过 YAML 配置文件定义媒体处理流程

## 项目结构

```
pymediamixer/
├── src/pymediamixer/       # 核心源码
│   ├── core/               # 核心管线基类
│   │   ├── pipeline_base.py        # 管线基类
│   │   ├── input_pipeline.py       # 输入管线
│   │   ├── compositing_pipeline.py # 合成管线
│   │   └── output_pipeline.py      # 输出管线
│   ├── inputs/             # 输入实现
│   │   └── videotestsrc_input.py   # 视频测试源
│   ├── compositors/        # 合成器实现
│   │   └── video_compositor.py     # 视频合成器
│   ├── outputs/            # 输出实现
│   │   └── autovideosink_output.py # 本地预览输出
│   └── engine.py           # 媒体引擎主类
├── configs/                # 配置示例
│   └── example.yaml        # 双输入画中画示例
├── scripts/                # CLI 脚本
│   └── mediamixer.py       # 命令行入口
├── test/                   # 单元测试
└── conda/                  # Conda 虚拟环境（本地）
```

## 环境要求

- Python >= 3.10
- GStreamer 1.0
- PyGObject >= 3.42.0

## 安装

### 1. 创建 Conda 环境

```bash
conda env create -f environment.yml
conda activate pymediamixer
```

### 2. 安装项目

```bash
pip install -e .
```

## 使用方式

### 命令行工具

```bash
# 使用配置文件启动
python scripts/mediamixer.py configs/example.yaml

# 指定运行时长（秒）
python scripts/mediamixer.py configs/example.yaml --duration 30

# 非交互模式
python scripts/mediamixer.py configs/example.yaml --no-interactive

# 查看帮助
python scripts/mediamixer.py --help
```

### 交互式命令

启动后进入交互模式，支持以下命令：

```
> help                           # 显示帮助
> status                         # 查看管线状态
> switch <合成器> <通道> <输入>   # 切换输入源
> quit / exit                    # 退出程序
```

### 配置文件示例

```yaml
# 输入源配置
inputs:
  - name: input0
    type: videotestsrc
    media_types: ["video"]
    config:
      pattern: smpte
      width: 1280
      height: 720

  - name: input1
    type: videotestsrc
    media_types: ["video"]
    config:
      pattern: ball
      width: 640
      height: 480

# 合成器配置
compositors:
  - name: comp0
    type: video_compositor
    output_caps:
      width: 1280
      height: 720
    inputs: [input0, input1]
    config:
      channel_layouts:
        0:
          xpos: 0
          ypos: 0
          width: 1280
          height: 720
          zorder: 0
        1:
          xpos: 960
          ypos: 540
          width: 320
          height: 180
          zorder: 1

# 输出配置
outputs:
  - name: preview
    type: autovideosink
    sources:
      video: comp0
```

### Python API

```python
from pymediamixer.engine import MixerEngine
import yaml

# 从配置文件加载
with open("configs/example.yaml") as f:
    config = yaml.safe_load(f)

engine = MixerEngine.from_config(config)
engine.start_all()

# 动态切换输入源
engine.switch("comp0", 1, "input1")

# 查看状态
print(engine.get_status())

# 停止
engine.stop_all()
```

## 开发

### 运行测试

```bash
pytest test/
```

### 项目本地环境

项目使用位于 `conda/` 目录下的本地 Conda 环境：

```bash
conda activate d:\git\pymediamixer\conda
```

VSCode 已配置自动激活该环境。

## 许可证

GPL
