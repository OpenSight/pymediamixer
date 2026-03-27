#!/usr/bin/env python3
"""AutoVideoSinkOutput 单元测试 CLI"""

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
from gi.repository import Gst
Gst.init(None)

from pymediamixer.outputs.autovideosink_output import AutoVideoSinkOutput
from pymediamixer.inputs.videotestsrc_input import VideoTestSrcInput
from pymediamixer.compositors.video_compositor import VideoCompositor
from pymediamixer.core.constants import MediaType
from pymediamixer.core.config import VideoTestSrcConfig, VideoCompositorConfig, AutoVideoSinkConfig


def main():
    parser = argparse.ArgumentParser(description="AutoVideoSinkOutput 测试")
    parser.add_argument("--source", default="test",
                        help="'test' 自动创建测试源，或指定 producer-name")
    parser.add_argument("--duration", type=int, default=10,
                        help="运行秒数, 0=无限 (default: 10)")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )
    
    compositor = None
    input_pipe = None
    
    if args.source == "test":
        # 自动创建测试输入源和合成器
        input_pipe = VideoTestSrcInput(
            "test_src",
            media_types=[MediaType.VIDEO],
            config=VideoTestSrcConfig(
                pattern="smpte",
                width=1280,
                height=720
            )
        )
        compositor = VideoCompositor(
            "test_comp",
            inputs=[input_pipe],
            output_caps={"width": 1280, "height": 720}
        )
        # 启动输入源和合成器
        input_pipe.start()
        compositor.start()
        time.sleep(0.5)  # 等待就绪
        print(f"Auto-created test compositor: {compositor.output_channel}")
    else:
        print(f"Using external source: {args.source}")
    
    # 创建输出
    if compositor:
        output = AutoVideoSinkOutput(
            "test_output",
            sources={MediaType.VIDEO: compositor}
        )
    else:
        output = AutoVideoSinkOutput(
            "test_output",
            sources={MediaType.VIDEO: None}
        )
        if args.source != "test":
            # 外部源模式：使用调试方法设置 source
            output.switch_source_by_name(MediaType.VIDEO, args.source)
    
    # 设置回调
    output.on_error = lambda name, err, dbg: print(f"[{name}] ERROR: {err}")
    
    # 启动
    output.start()
    
    print(f"AutoVideoSinkOutput test: source={compositor.output_channel if compositor else args.source}")
    
    # 等待
    running = True
    
    def sig_handler(sig, frame):
        nonlocal running
        running = False
    
    signal.signal(signal.SIGINT, sig_handler)
    
    if args.duration > 0:
        print(f"Running for {args.duration}s... (Ctrl+C to stop)")
        start = time.time()
        while running and (time.time() - start) < args.duration:
            time.sleep(0.5)
    else:
        print("Running... (Ctrl+C to stop)")
        while running:
            time.sleep(0.5)
    
    print("Stopping...")
    output.stop()
    if compositor:
        compositor.stop()
    if input_pipe:
        input_pipe.stop()
    print("Done.")


if __name__ == "__main__":
    main()
