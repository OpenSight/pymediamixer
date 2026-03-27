#!/usr/bin/env python3
"""VideoCompositor 单元测试 CLI

可独立运行的测试脚本，验证 VideoCompositor 的功能。

用法：
    python test/test_video_compositor.py [选项]
    
选项：
    --num-channels  输入通道数量（默认 2）
    --width         输出宽度（默认 1920）
    --height        输出高度（默认 1080）
    --layout        布局模式: pip/grid/fullscreen（默认 pip）
    --duration      运行时长秒数，0 表示无限（默认 10）
"""

import sys
import os
import argparse
import signal
import time
import logging
import math

# 确保能找到 src 目录
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

# 初始化 GStreamer
Gst.init(None)

from pymediamixer.inputs.videotestsrc_input import VideoTestSrcInput
from pymediamixer.compositors.video_compositor import VideoCompositor
from pymediamixer.core.pipeline_base import PipelineBase
from pymediamixer.core.constants import MediaType
from pymediamixer.core.config import VideoTestSrcConfig, VideoCompositorConfig

# 预设的 videotestsrc pattern 列表，用于不同通道显示不同图案
PATTERNS = ["smpte", "ball", "snow", "red", "blue", "green", "white", "checkers-1"]


class PreviewPipeline(PipelineBase):
    """临时预览管线
    
    从指定的 producer-name 接收视频并显示到窗口。
    管线结构：intersrc -> videoconvert -> autovideosink
    """
    
    def __init__(self, name: str, producer_name: str):
        """初始化预览管线
        
        Args:
            name: 管线名称
            producer_name: 输入源的 producer-name
        """
        super().__init__(name, auto_restart=False)
        self._producer_name = producer_name
    
    def _build(self) -> Gst.Pipeline:
        """构建预览管线"""
        pipeline = Gst.Pipeline.new(self._name)
        
        # 创建 intersrc 接收合成输出
        intersrc = Gst.ElementFactory.make("intersrc", f"{self._name}_intersrc")
        if not intersrc:
            raise RuntimeError(f"Failed to create intersrc for {self._name}")
        intersrc.set_property("producer-name", self._producer_name)
        
        # 创建 videoconvert 进行格式转换
        convert = Gst.ElementFactory.make("videoconvert", f"{self._name}_convert")
        if not convert:
            raise RuntimeError(f"Failed to create videoconvert for {self._name}")
        
        # 创建 autovideosink 自动选择视频输出
        sink = Gst.ElementFactory.make("autovideosink", f"{self._name}_sink")
        if not sink:
            raise RuntimeError(f"Failed to create autovideosink for {self._name}")
        
        # 添加到管线
        for elem in [intersrc, convert, sink]:
            pipeline.add(elem)
        
        # 链接元素
        if not intersrc.link(convert):
            raise RuntimeError("Failed to link intersrc -> convert")
        if not convert.link(sink):
            raise RuntimeError("Failed to link convert -> sink")
        
        return pipeline


def calculate_pip_layout(index: int, num_channels: int, width: int, height: int) -> dict:
    """计算 PIP（画中画）布局
    
    Channel 0 全屏作为背景，其他 channel 在右下角缩小叠加显示。
    
    Args:
        index: 通道索引
        num_channels: 总通道数
        width: 输出宽度
        height: 输出高度
        
    Returns:
        布局参数字典
    """
    if index == 0:
        # 主画面全屏
        return {
            "xpos": 0,
            "ypos": 0,
            "width": width,
            "height": height,
            "zorder": 0
        }
    else:
        # PIP 小窗口，位于右下角，每个错开一点位置
        pip_w = width // 4
        pip_h = height // 4
        margin = 20
        # 多个 PIP 窗口错开排列
        x = width - pip_w - margin * index
        y = height - pip_h - margin * index
        return {
            "xpos": x,
            "ypos": y,
            "width": pip_w,
            "height": pip_h,
            "zorder": index  # 后面的 channel 层级更高
        }


def calculate_grid_layout(index: int, num_channels: int, width: int, height: int) -> dict:
    """计算网格布局
    
    将所有通道等分排列在网格中。
    
    Args:
        index: 通道索引
        num_channels: 总通道数
        width: 输出宽度
        height: 输出高度
        
    Returns:
        布局参数字典
    """
    # 计算网格的行列数（尽量接近正方形）
    cols = math.ceil(math.sqrt(num_channels))
    rows = math.ceil(num_channels / cols)
    
    # 每个单元格的尺寸
    cell_w = width // cols
    cell_h = height // rows
    
    # 计算当前通道所在的行列
    col = index % cols
    row = index // cols
    
    return {
        "xpos": col * cell_w,
        "ypos": row * cell_h,
        "width": cell_w,
        "height": cell_h,
        "zorder": 0
    }


def calculate_fullscreen_layout(index: int, num_channels: int, width: int, height: int) -> dict:
    """计算全屏布局
    
    仅显示 channel 0 全屏，其他通道隐藏。
    
    Args:
        index: 通道索引
        num_channels: 总通道数
        width: 输出宽度
        height: 输出高度
        
    Returns:
        布局参数字典
    """
    if index == 0:
        return {
            "xpos": 0,
            "ypos": 0,
            "width": width,
            "height": height,
            "zorder": 0
        }
    else:
        # 隐藏其他通道（尺寸为 0，透明度为 0）
        return {
            "xpos": 0,
            "ypos": 0,
            "width": 0,
            "height": 0,
            "zorder": 0,
            "alpha": 0.0
        }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="VideoCompositor 测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
布局模式说明：
  pip        - 画中画模式，channel 0 全屏背景，其他在右下角
  grid       - 网格模式，所有通道等分排列
  fullscreen - 全屏模式，仅显示 channel 0
        """
    )
    parser.add_argument("--num-channels", type=int, default=2,
                        help="输入通道数量（默认 2）")
    parser.add_argument("--width", type=int, default=1920,
                        help="输出宽度（默认 1920）")
    parser.add_argument("--height", type=int, default=1080,
                        help="输出高度（默认 1080）")
    parser.add_argument("--layout", choices=["pip", "grid", "fullscreen"], default="pip",
                        help="布局模式（默认 pip）")
    parser.add_argument("--duration", type=int, default=10,
                        help="运行时长秒数，0 表示无限（默认 10）")
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )
    logger = logging.getLogger("test_video_compositor")
    
    logger.info(f"创建 {args.num_channels} 个输入管线...")
    
    # 创建输入管线（每个使用不同的 pattern）
    inputs = []
    for i in range(args.num_channels):
        pattern = PATTERNS[i % len(PATTERNS)]
        inp = VideoTestSrcInput(
            f"input{i}",
            media_types=[MediaType.VIDEO],
            config=VideoTestSrcConfig(
                pattern=pattern,
                width=640,  # 输入使用较小分辨率，由 compositor 统一缩放
                height=480
            )
        )
        inputs.append(inp)
        logger.info(f"  输入 {i}: pattern={pattern}")
    
    # 创建合成器
    logger.info(f"创建 VideoCompositor: {args.width}x{args.height}, {args.num_channels} channels")
    comp = VideoCompositor(
        "comp0",
        inputs=[None] * args.num_channels,
        output_caps={"width": args.width, "height": args.height}
    )
    
    # 创建预览管线
    logger.info(f"创建预览管线，producer-name: {comp.output_channel}")
    preview = PreviewPipeline("preview", comp.output_channel)
    
    # 启动所有输入管线
    logger.info("启动输入管线...")
    for inp in inputs:
        inp.start()
    
    # 启动合成器
    logger.info("启动合成器...")
    comp.start()
    
    # 等待合成器就绪
    time.sleep(0.5)
    
    # 启动预览
    logger.info("启动预览...")
    preview.start()
    
    # 连接各个 channel 到对应输入
    logger.info("连接输入通道...")
    for i, inp in enumerate(inputs):
        comp.switch_channel(i, inp)
    
    # 根据布局模式设置各通道布局
    logger.info(f"设置布局模式: {args.layout}")
    for i in range(args.num_channels):
        if args.layout == "pip":
            layout = calculate_pip_layout(i, args.num_channels, args.width, args.height)
        elif args.layout == "grid":
            layout = calculate_grid_layout(i, args.num_channels, args.width, args.height)
        else:  # fullscreen
            layout = calculate_fullscreen_layout(i, args.num_channels, args.width, args.height)
        
        comp.set_channel_layout(i, layout)
        logger.debug(f"  Channel {i} layout: {layout}")
    
    print(f"\n{'='*60}")
    print(f"VideoCompositor 测试运行中")
    print(f"  通道数: {args.num_channels}")
    print(f"  分辨率: {args.width}x{args.height}")
    print(f"  布局: {args.layout}")
    print(f"{'='*60}\n")
    
    # 设置信号处理，支持 Ctrl+C 停止
    running = True
    def signal_handler(sig, frame):
        nonlocal running
        print("\n收到停止信号...")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # 运行指定时间
    if args.duration > 0:
        print(f"运行 {args.duration} 秒后自动停止... (Ctrl+C 可提前停止)")
        start_time = time.time()
        while running and (time.time() - start_time) < args.duration:
            time.sleep(0.5)
    else:
        print("持续运行中... (Ctrl+C 停止)")
        while running:
            time.sleep(0.5)
    
    # 停止所有管线
    print("停止所有管线...")
    preview.stop()
    comp.stop()
    for inp in inputs:
        inp.stop()
    
    print("测试完成。")


if __name__ == "__main__":
    main()
