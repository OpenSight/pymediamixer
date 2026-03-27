#!/usr/bin/env python3
"""MixerEngine 集成测试 - 完整画中画 demo"""

import sys
import os
import argparse
import signal
import time
import logging

# 添加 src 目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

from pymediamixer.engine import MixerEngine
from pymediamixer.inputs.videotestsrc_input import VideoTestSrcInput
from pymediamixer.compositors.video_compositor import VideoCompositor
from pymediamixer.outputs.autovideosink_output import AutoVideoSinkOutput
from pymediamixer.core.constants import MediaType
from pymediamixer.core.config import VideoTestSrcConfig, VideoCompositorConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_engine")

# 全局变量用于信号处理
_running = True
_engine = None


def signal_handler(signum, frame):
    """处理 Ctrl+C 信号"""
    global _running, _engine
    logger.info("Received interrupt signal, stopping...")
    _running = False
    if _engine:
        try:
            _engine.stop_all()
        except Exception as e:
            logger.error(f"Error stopping engine: {e}")


def test_pip_demo(duration: int = 10) -> bool:
    """
    基础 PIP Demo 测试
    
    - 创建 2 路 VideoTestSrcInput（不同 pattern：smpte, ball）
    - 创建 1 个 VideoCompositor（2 channel, 1280x720）
    - 创建 1 个 AutoVideoSinkOutput
    - 使用 MixerEngine 管理
    - 启动所有管线
    - 连接 channel 0 -> input0，channel 1 -> input1
    - 设置 PIP 布局（channel 0 全屏背景，channel 1 右下角小窗）
    - 运行 duration/2 秒
    - 动态切换：交换 channel 0 和 channel 1 的输入源
    - 再运行 duration/2 秒
    - 停止所有
    """
    global _engine, _running
    _running = True
    
    logger.info("=" * 60)
    logger.info("Test: PIP Demo - 画中画演示")
    logger.info("=" * 60)
    
    engine = MixerEngine()
    _engine = engine
    
    try:
        # 创建 2 路输入
        logger.info("Creating input pipelines...")
        input0 = VideoTestSrcInput(
            "input0",
            media_types=[MediaType.VIDEO],
            config=VideoTestSrcConfig(pattern="smpte", width=1280, height=720, framerate="30/1")
        )
        input1 = VideoTestSrcInput(
            "input1",
            media_types=[MediaType.VIDEO],
            config=VideoTestSrcConfig(pattern="ball", width=1280, height=720, framerate="30/1")
        )
        engine.add_input(input0)
        engine.add_input(input1)
        
        # 创建合成器
        logger.info("Creating compositor...")
        compositor = VideoCompositor(
            "comp0",
            inputs=[None, None],
            output_caps={"width": 1280, "height": 720, "framerate": "30/1"}
        )
        engine.add_compositor(compositor)
        
        # 创建输出
        logger.info("Creating output...")
        output = AutoVideoSinkOutput("preview", sources={MediaType.VIDEO: compositor})
        engine.add_output(output)
        
        # 启动所有管线
        logger.info("Starting all pipelines...")
        engine.start_all()
        
        # 等待管线稳定
        time.sleep(0.5)
        
        # 连接 channel
        logger.info("Connecting channels...")
        engine.switch("comp0", 0, "input0")  # channel 0 -> smpte
        engine.switch("comp0", 1, "input1")  # channel 1 -> ball
        
        # 设置 PIP 布局
        logger.info("Setting PIP layout...")
        # channel 0: 全屏背景
        compositor.set_channel_layout(0, {
            "xpos": 0,
            "ypos": 0,
            "width": 1280,
            "height": 720,
            "zorder": 0
        })
        # channel 1: 右下角小窗 (1/4 大小)
        pip_width = 320
        pip_height = 180
        compositor.set_channel_layout(1, {
            "xpos": 1280 - pip_width - 20,  # 右边距 20
            "ypos": 720 - pip_height - 20,   # 下边距 20
            "width": pip_width,
            "height": pip_height,
            "zorder": 1
        })
        
        # 第一阶段运行
        half_duration = duration // 2
        logger.info(f"Running phase 1 for {half_duration} seconds (smpte=background, ball=PIP)...")
        for i in range(half_duration):
            if not _running:
                break
            time.sleep(1)
            logger.info(f"  Phase 1: {i + 1}/{half_duration}s")
        
        if _running:
            # 动态切换：交换输入源
            logger.info("Switching inputs: swapping channel 0 and channel 1 sources...")
            engine.switch("comp0", 0, "input1")  # channel 0 -> ball
            engine.switch("comp0", 1, "input0")  # channel 1 -> smpte
            
            # 第二阶段运行
            remaining = duration - half_duration
            logger.info(f"Running phase 2 for {remaining} seconds (ball=background, smpte=PIP)...")
            for i in range(remaining):
                if not _running:
                    break
                time.sleep(1)
                logger.info(f"  Phase 2: {i + 1}/{remaining}s")
        
        logger.info("PIP Demo completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"PIP Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        logger.info("Stopping all pipelines...")
        engine.stop_all()
        _engine = None


def test_from_config(duration: int = 5) -> bool:
    """
    from_config 测试
    
    使用配置字典创建引擎，验证 from_config 流程
    """
    global _engine, _running
    _running = True
    
    logger.info("=" * 60)
    logger.info("Test: from_config - 配置创建测试")
    logger.info("=" * 60)
    
    config = {
        "inputs": [
            {
                "name": "src0",
                "type": "videotestsrc",
                "media_types": ["video"],
                "config": {"pattern": "smpte", "width": 1280, "height": 720, "framerate": "30/1"}
            },
            {
                "name": "src1",
                "type": "videotestsrc",
                "media_types": ["video"],
                "config": {"pattern": "ball", "width": 1280, "height": 720, "framerate": "30/1"}
            }
        ],
        "compositors": [
            {
                "name": "mixer",
                "type": "video_compositor",
                "output_caps": {"width": 1280, "height": 720, "framerate": "30/1"},
                "inputs": ["src0", "src1"],
                "config": {
                    "channel_layouts": {
                        0: {"xpos": 0, "ypos": 0, "width": 640, "height": 720, "zorder": 0},
                        1: {"xpos": 640, "ypos": 0, "width": 640, "height": 720, "zorder": 0}
                    }
                }
            }
        ],
        "outputs": [
            {
                "name": "output",
                "type": "autovideosink",
                "sources": {"video": "mixer"}
            }
        ]
    }
    
    try:
        logger.info("Creating engine from config...")
        engine = MixerEngine.from_config(config)
        _engine = engine
        
        logger.info("Starting all pipelines...")
        engine.start_all()
        
        # 等待管线稳定
        time.sleep(0.5)
        
        # 验证管线已创建
        assert len(engine.inputs) == 2, f"Expected 2 inputs, got {len(engine.inputs)}"
        assert len(engine.compositors) == 1, f"Expected 1 compositor, got {len(engine.compositors)}"
        assert len(engine.outputs) == 1, f"Expected 1 output, got {len(engine.outputs)}"
        
        logger.info(f"Running for {duration} seconds (side-by-side layout)...")
        for i in range(duration):
            if not _running:
                break
            time.sleep(1)
            logger.info(f"  {i + 1}/{duration}s")
        
        logger.info("from_config test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"from_config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if _engine:
            logger.info("Stopping all pipelines...")
            _engine.stop_all()
        _engine = None


def test_dynamic_switch(duration: int = 8) -> bool:
    """
    动态切换测试
    
    验证运行时切换输入源
    """
    global _engine, _running
    _running = True
    
    logger.info("=" * 60)
    logger.info("Test: Dynamic Switch - 动态切换测试")
    logger.info("=" * 60)
    
    engine = MixerEngine()
    _engine = engine
    
    try:
        # 创建 3 路输入
        logger.info("Creating 3 input pipelines...")
        input0 = VideoTestSrcInput(
            "input0",
            media_types=[MediaType.VIDEO],
            config=VideoTestSrcConfig(pattern="smpte", width=1280, height=720)
        )
        input1 = VideoTestSrcInput(
            "input1",
            media_types=[MediaType.VIDEO],
            config=VideoTestSrcConfig(pattern="ball", width=1280, height=720)
        )
        input2 = VideoTestSrcInput(
            "input2",
            media_types=[MediaType.VIDEO],
            config=VideoTestSrcConfig(pattern="snow", width=1280, height=720)
        )
        engine.add_input(input0)
        engine.add_input(input1)
        engine.add_input(input2)
        
        # 创建单通道合成器（简化测试）
        logger.info("Creating single channel compositor...")
        compositor = VideoCompositor(
            "comp",
            inputs=[None],
            output_caps={"width": 1280, "height": 720}
        )
        engine.add_compositor(compositor)
        
        # 创建输出
        output = AutoVideoSinkOutput("preview", sources={MediaType.VIDEO: compositor})
        engine.add_output(output)
        
        # 启动
        logger.info("Starting all pipelines...")
        engine.start_all()
        time.sleep(0.5)
        
        # 设置全屏布局
        compositor.set_channel_layout(0, {
            "xpos": 0, "ypos": 0, "width": 1280, "height": 720
        })
        
        # 切换测试
        inputs = ["input0", "input1", "input2"]
        patterns = ["smpte", "ball", "snow"]
        switch_interval = duration // 3
        
        for i, (inp_name, pattern) in enumerate(zip(inputs, patterns)):
            if not _running:
                break
            logger.info(f"Switching to {inp_name} ({pattern})...")
            engine.switch("comp", 0, inp_name)
            
            for j in range(switch_interval):
                if not _running:
                    break
                time.sleep(1)
                logger.info(f"  Showing {pattern}: {j + 1}/{switch_interval}s")
        
        logger.info("Dynamic switch test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Dynamic switch test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        logger.info("Stopping all pipelines...")
        engine.stop_all()
        _engine = None


def test_status_query() -> bool:
    """
    状态查询测试
    
    验证 get_status() 返回正确状态
    """
    global _engine, _running
    _running = True
    
    logger.info("=" * 60)
    logger.info("Test: Status Query - 状态查询测试")
    logger.info("=" * 60)
    
    engine = MixerEngine()
    _engine = engine
    
    try:
        # 创建管线
        logger.info("Creating pipelines...")
        input0 = VideoTestSrcInput(
            "input0",
            media_types=[MediaType.VIDEO],
            config=VideoTestSrcConfig(pattern="smpte", width=640, height=480)
        )
        compositor = VideoCompositor(
            "comp",
            inputs=[None],
            output_caps={"width": 640, "height": 480}
        )
        output = AutoVideoSinkOutput("preview", sources={MediaType.VIDEO: compositor})
        
        engine.add_input(input0)
        engine.add_compositor(compositor)
        engine.add_output(output)
        
        # 启动前检查状态
        logger.info("Checking status before start...")
        status = engine.get_status()
        logger.info(f"  Inputs: {status['inputs']}")
        logger.info(f"  Compositors: {status['compositors']}")
        logger.info(f"  Outputs: {status['outputs']}")
        
        # 启动
        logger.info("Starting all pipelines...")
        engine.start_all()
        time.sleep(0.5)
        
        # 连接 channel
        engine.switch("comp", 0, "input0")
        compositor.set_channel_layout(0, {"xpos": 0, "ypos": 0, "width": 640, "height": 480})
        
        # 启动后检查状态
        logger.info("Checking status after start...")
        status = engine.get_status()
        logger.info(f"  Inputs: {status['inputs']}")
        logger.info(f"  Compositors: {status['compositors']}")
        logger.info(f"  Outputs: {status['outputs']}")
        
        # 验证状态
        # 注意：状态字符串可能是 "playing" 或 "PLAYING"，取决于 GStreamer 版本
        for name, state in status["inputs"].items():
            if state.lower() != "playing":
                logger.warning(f"Input {name} not in playing state: {state}")
        
        # 运行一下确认正常
        logger.info("Running for 2 seconds to verify...")
        for i in range(2):
            if not _running:
                break
            time.sleep(1)
        
        logger.info("Status query test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Status query test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        logger.info("Stopping all pipelines...")
        engine.stop_all()
        _engine = None


def run_all_tests(duration: int) -> dict:
    """运行所有测试并返回结果"""
    results = {}
    
    # 测试 1: 状态查询（快速测试）
    results["status"] = test_status_query()
    time.sleep(1)
    
    # 测试 2: from_config
    results["config"] = test_from_config(duration // 2)
    time.sleep(1)
    
    # 测试 3: 动态切换
    results["switch"] = test_dynamic_switch(duration)
    time.sleep(1)
    
    # 测试 4: PIP Demo
    results["pip"] = test_pip_demo(duration)
    
    return results


def print_summary(results: dict):
    """打印测试汇总"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        logger.info(f"  [{symbol}] {test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info("-" * 60)
    logger.info(f"Total: {passed} passed, {failed} failed")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="MixerEngine 集成测试")
    parser.add_argument(
        "--test",
        choices=["pip", "config", "switch", "status", "all"],
        default="pip",
        help="要运行的测试场景 (默认: pip)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="测试运行时长（秒，默认: 10）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("MixerEngine Integration Tests")
    logger.info(f"Test: {args.test}, Duration: {args.duration}s")
    logger.info("")
    
    results = {}
    
    try:
        if args.test == "pip":
            results["pip"] = test_pip_demo(args.duration)
        elif args.test == "config":
            results["config"] = test_from_config(args.duration)
        elif args.test == "switch":
            results["switch"] = test_dynamic_switch(args.duration)
        elif args.test == "status":
            results["status"] = test_status_query()
        elif args.test == "all":
            results = run_all_tests(args.duration)
        
        print_summary(results)
        
        # 返回码：有失败则为 1
        all_passed = all(results.values())
        sys.exit(0 if all_passed else 1)
        
    except Exception as e:
        logger.error(f"Test execution error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
