#!/usr/bin/env python3
"""VideoTestSrcInput 单元测试 CLI - 独立运行验证

用法:
    python test/test_videotestsrc_input.py [options]
    
示例:
    python test/test_videotestsrc_input.py --pattern ball --duration 5
    python test/test_videotestsrc_input.py --width 640 --height 480 --framerate 25/1
    python test/test_videotestsrc_input.py --duration 0  # 无限运行
"""

import sys
import os
import argparse
import signal
import time
import logging

# 确保能找到 src 目录
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

Gst.init(None)

from pymediamixer.inputs.videotestsrc_input import VideoTestSrcInput
from pymediamixer.core.pipeline_base import PipelineBase
from pymediamixer.core.clock import apply_clock
from pymediamixer.core.constants import MediaType
from pymediamixer.core.config import VideoTestSrcConfig


class PreviewPipeline(PipelineBase):
    """临时预览管线：intersrc -> videoconvert -> autovideosink
    
    用于接收 VideoTestSrcInput 的输出并显示到屏幕上。
    """
    
    def __init__(self, name: str, producer_name: str):
        """初始化预览管线
        
        Args:
            name: 管线名称
            producer_name: 输入管线的 producer-name（来自 VideoTestSrcInput.get_channel）
        """
        super().__init__(name, auto_restart=False)
        self._producer_name = producer_name
    
    def _build(self) -> Gst.Pipeline:
        """构建预览管线元素"""
        pipeline = Gst.Pipeline.new(self._name)
        
        # 创建 intersrc，连接到输入管线的 intersink
        intersrc = Gst.ElementFactory.make("intersrc", f"{self._name}_intersrc")
        if not intersrc:
            raise RuntimeError(f"Failed to create intersrc for {self._name}")
        intersrc.set_property("producer-name", self._producer_name)
        
        # videoconvert 用于格式转换（确保与 sink 兼容）
        convert = Gst.ElementFactory.make("videoconvert", f"{self._name}_convert")
        if not convert:
            raise RuntimeError(f"Failed to create videoconvert for {self._name}")
        
        # autovideosink 自动选择合适的视频输出
        sink = Gst.ElementFactory.make("autovideosink", f"{self._name}_sink")
        if not sink:
            raise RuntimeError(f"Failed to create autovideosink for {self._name}")
        
        # 添加元素到管线
        for elem in [intersrc, convert, sink]:
            pipeline.add(elem)
        
        # 连接元素
        if not intersrc.link(convert):
            raise RuntimeError(f"Failed to link intersrc -> convert in {self._name}")
        if not convert.link(sink):
            raise RuntimeError(f"Failed to link convert -> sink in {self._name}")
        
        return pipeline


def main():
    parser = argparse.ArgumentParser(
        description="VideoTestSrcInput 测试 - 验证视频测试源输入管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
常用 pattern 值:
  smpte       - SMPTE 测试图案 (默认)
  snow        - 雪花噪声
  black       - 黑色
  white       - 白色
  red         - 红色
  green       - 绿色
  blue        - 蓝色
  checkers-1  - 棋盘格
  ball        - 移动的球
  circular    - 圆形图案
"""
    )
    parser.add_argument("--pattern", default="smpte",
                        help="videotestsrc 图案 (default: smpte)")
    parser.add_argument("--width", type=int, default=1280,
                        help="视频宽度 (default: 1280)")
    parser.add_argument("--height", type=int, default=720,
                        help="视频高度 (default: 720)")
    parser.add_argument("--framerate", default="30/1",
                        help="帧率 (default: 30/1)")
    parser.add_argument("--duration", type=int, default=10,
                        help="运行秒数, 0=无限 (default: 10)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细日志")
    args = parser.parse_args()
    
    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )
    logger = logging.getLogger("test_videotestsrc")
    
    # 创建输入管线
    logger.info(f"Creating VideoTestSrcInput: pattern={args.pattern}, "
                f"{args.width}x{args.height}@{args.framerate}")
    
    input_pipe = VideoTestSrcInput(
        "test_input",
        media_types=[MediaType.VIDEO],
        config=VideoTestSrcConfig(
            pattern=args.pattern,
            width=args.width,
            height=args.height,
            framerate=args.framerate
        )
    )
    
    # 获取输出通道名
    producer_name = input_pipe.get_channel(MediaType.VIDEO)
    logger.info(f"Producer name: {producer_name}")
    
    # 创建预览管线
    preview = PreviewPipeline("preview", producer_name)
    
    # 设置错误回调
    def on_error(name, err, dbg):
        logger.error(f"[{name}] ERROR: {err}")
        if dbg:
            logger.debug(f"[{name}] Debug: {dbg}")
    
    def on_eos(name):
        logger.info(f"[{name}] EOS received")
    
    def on_state_changed(name, old, new):
        logger.debug(f"[{name}] State: {old} -> {new}")
    
    input_pipe.on_error = on_error
    input_pipe.on_eos = on_eos
    input_pipe.on_state_changed = on_state_changed
    
    preview.on_error = on_error
    preview.on_eos = on_eos
    preview.on_state_changed = on_state_changed
    
    # 启动管线
    print(f"\n{'='*60}")
    print(f"VideoTestSrcInput 测试")
    print(f"{'='*60}")
    print(f"图案:       {args.pattern}")
    print(f"分辨率:     {args.width}x{args.height}")
    print(f"帧率:       {args.framerate}")
    print(f"Producer:   {producer_name}")
    print(f"{'='*60}\n")
    
    logger.info("Starting input pipeline...")
    input_pipe.start()
    
    # 稍等输入管线就绪
    time.sleep(0.5)
    
    logger.info("Starting preview pipeline...")
    preview.start()
    
    # 设置信号处理
    running = True
    
    def signal_handler(sig, frame):
        nonlocal running
        print("\n收到中断信号，正在停止...")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 等待运行
    if args.duration > 0:
        print(f"运行 {args.duration} 秒... (Ctrl+C 停止)")
        start_time = time.time()
        while running and (time.time() - start_time) < args.duration:
            time.sleep(0.5)
            # 周期性输出状态
            elapsed = int(time.time() - start_time)
            if elapsed > 0 and elapsed % 5 == 0:
                input_state = input_pipe.get_state()
                preview_state = preview.get_state()
                logger.info(f"状态: input={input_state}, preview={preview_state}, "
                           f"已运行 {elapsed}s")
    else:
        print("无限运行... (Ctrl+C 停止)")
        while running:
            time.sleep(0.5)
    
    # 停止管线
    print("\n正在停止管线...")
    
    logger.info("Stopping preview pipeline...")
    preview.stop()
    
    logger.info("Stopping input pipeline...")
    input_pipe.stop()
    
    print("测试完成。")


if __name__ == "__main__":
    main()
