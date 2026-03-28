#!/usr/bin/env python3
"""错误恢复测试 CLI 脚本

用于测试指定流水线的错误恢复功能，支持主动注入 error 或 EOS 事件，
验证 pipeline 是否能够成功自动恢复。

使用方法:
    python scripts/test_error_recovery.py -c configs/example.yaml -p input0 -t error -d 10
    python scripts/test_error_recovery.py -c configs/example.yaml -p comp0 -t eos --interval 3
"""

import sys
import os

# 添加 src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import argparse
import json
import signal
import time
import threading
import logging
from pathlib import Path
from typing import Optional

import yaml

# 确保 GStreamer 初始化
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

Gst.init(None)

from pymediamixer.engine import MixerEngine


class ErrorRecoveryTester:
    """错误恢复测试器
    
    管理测试流程，包括：
    - 启动引擎和指定 pipeline
    - 监控 pipeline 状态变化
    - 注入 error 或 EOS 事件
    - 验证自动恢复是否成功
    """
    
    def __init__(self, engine: MixerEngine, pipeline_name: str, inject_type: str):
        """初始化测试器
        
        Args:
            engine: MixerEngine 实例
            pipeline_name: 要测试的 pipeline 名称
            inject_type: 注入类型，'error' 或 'eos'
        """
        self._engine = engine
        self._pipeline_name = pipeline_name
        self._inject_type = inject_type
        self._logger = logging.getLogger("test_error_recovery")
        
        # 获取目标 pipeline
        self._pipeline = self._get_pipeline(pipeline_name)
        if not self._pipeline:
            raise ValueError(f"Pipeline '{pipeline_name}' not found in engine")
        
        # 测试状态追踪
        self._test_events: list[dict] = []
        self._lock = threading.Lock()
        self._running = False
        
        # 注册回调
        self._setup_callbacks()
    
    def _get_pipeline(self, name: str):
        """根据名称获取 pipeline 对象"""
        if name in self._engine.inputs:
            return self._engine.inputs[name]
        if name in self._engine.compositors:
            return self._engine.compositors[name]
        if name in self._engine.outputs:
            return self._engine.outputs[name]
        return None
    
    def _setup_callbacks(self):
        """设置 pipeline 状态回调"""
        self._pipeline.on_state_changed = self._on_state_changed
        self._pipeline.on_error = self._on_error
        self._pipeline.on_eos = self._on_eos
        self._pipeline.on_restarted = self._on_restarted
    
    def _on_state_changed(self, name: str, old: str, new: str):
        """状态变化回调"""
        event = {
            "time": time.strftime("%H:%M:%S"),
            "type": "state_changed",
            "name": name,
            "old": old,
            "new": new
        }
        with self._lock:
            self._test_events.append(event)
        self._logger.info(f"[{name}] State: {old} -> {new}")
    
    def _on_error(self, name: str, error_msg: str, debug: Optional[str]):
        """错误回调"""
        event = {
            "time": time.strftime("%H:%M:%S"),
            "type": "error",
            "name": name,
            "message": error_msg,
            "debug": debug
        }
        with self._lock:
            self._test_events.append(event)
        self._logger.warning(f"[{name}] ERROR: {error_msg}")
    
    def _on_eos(self, name: str):
        """EOS 回调"""
        event = {
            "time": time.strftime("%H:%M:%S"),
            "type": "eos",
            "name": name
        }
        with self._lock:
            self._test_events.append(event)
        self._logger.info(f"[{name}] EOS received")
    
    def _on_restarted(self, name: str):
        """重启成功回调"""
        event = {
            "time": time.strftime("%H:%M:%S"),
            "type": "restarted",
            "name": name
        }
        with self._lock:
            self._test_events.append(event)
        self._logger.info(f"[{name}] RESTARTED successfully")
    
    def inject_error(self) -> bool:
        """向 pipeline 注入错误事件

        通过向 pipeline 的 bus 发送错误消息来模拟错误。
        这会触发 pipeline 的 error 消息回调，验证自动重启功能。

        Returns:
            bool: 是否成功触发
        """
        pipeline_obj = self._pipeline.pipeline
        if not pipeline_obj:
            self._logger.error("Pipeline object not available")
            return False

        try:
            self._logger.info(f"Injecting ERROR into pipeline '{self._pipeline_name}'")

            # 获取 pipeline 的 bus 并发送错误消息
            # 这会触发 pipeline 的 error 回调和自动重启
            bus = pipeline_obj.get_bus()
            if not bus:
                self._logger.error("Failed to get pipeline bus")
                return False

            # 创建测试错误消息
            error = GLib.Error.new_literal(
                GLib.quark_from_string("test-error-quark"),
                "Injected test error for error recovery testing",
                1  # error code
            )
            msg = Gst.Message.new_error(pipeline_obj, error, "Test error injection - simulating pipeline failure")
            bus.post(msg)

            self._logger.info("Posted error message to pipeline bus")
            return True

        except Exception as e:
            self._logger.exception(f"Failed to inject error: {e}")
            return False
    
    def inject_eos(self) -> bool:
        """向 pipeline 注入 EOS 事件
        
        通过向 pipeline 发送 EOS 事件来模拟流结束。
        
        Returns:
            bool: 是否成功触发
        """
        pipeline_obj = self._pipeline.pipeline
        if not pipeline_obj:
            self._logger.error("Pipeline object not available")
            return False
        
        try:
            self._logger.info(f"Injecting EOS into pipeline '{self._pipeline_name}'")
            
            # 找到 pipeline 中的第一个 src pad 并发送 EOS
            elements = pipeline_obj.iterate_elements()
            for elem in elements:
                pads = elem.iterate_src_pads()
                for pad in pads:
                    if pad and not pad.is_linked():
                        # 向未连接的 src pad 发送 EOS
                        pad.send_event(Gst.Event.new_eos())
                        self._logger.info(f"Sent EOS on pad '{pad.get_name()}' of element '{elem.get_name()}'")
                        return True
            
            # 备选：向 pipeline 本身发送 EOS
            event = Gst.Event.new_eos()
            result = pipeline_obj.send_event(event)
            self._logger.info(f"Sent EOS to pipeline (result: {result})")
            return result
            
        except Exception as e:
            self._logger.exception(f"Failed to inject EOS: {e}")
            return False
    
    def inject(self) -> bool:
        """根据配置注入事件
        
        Returns:
            bool: 是否成功
        """
        if self._inject_type == "error":
            return self.inject_error()
        elif self._inject_type == "eos":
            return self.inject_eos()
        else:
            self._logger.error(f"Unknown inject type: {self._inject_type}")
            return False
    
    def get_events(self) -> list[dict]:
        """获取所有记录的测试事件"""
        with self._lock:
            return list(self._test_events)
    
    def get_summary(self) -> dict:
        """获取测试摘要"""
        events = self.get_events()
        
        error_count = sum(1 for e in events if e["type"] == "error")
        eos_count = sum(1 for e in events if e["type"] == "eos")
        restart_count = sum(1 for e in events if e["type"] == "restarted")
        
        # 检查恢复是否成功
        recovered = restart_count > 0
        
        return {
            "pipeline": self._pipeline_name,
            "inject_type": self._inject_type,
            "total_events": len(events),
            "error_events": error_count,
            "eos_events": eos_count,
            "restart_events": restart_count,
            "recovered": recovered,
            "final_state": self._pipeline.get_state()
        }


def run_single_test(engine: MixerEngine, args) -> dict:
    """运行单次测试
    
    Args:
        engine: MixerEngine 实例
        args: 命令行参数
        
    Returns:
        dict: 测试结果摘要
    """
    logger = logging.getLogger("test_error_recovery")
    
    # 创建测试器
    tester = ErrorRecoveryTester(engine, args.pipeline, args.type)
    
    logger.info(f"Starting error recovery test for pipeline '{args.pipeline}'")
    logger.info(f"Inject type: {args.type}, Delay: {args.delay}s")
    
    # 等待初始稳定
    logger.info("Waiting for pipeline to stabilize...")
    time.sleep(2)
    
    # 记录初始状态
    initial_state = tester._pipeline.get_state()
    logger.info(f"Initial state: {initial_state}")
    
    # 注入事件
    logger.info(f"Injecting {args.type} in {args.delay} seconds...")
    time.sleep(args.delay)
    
    success = tester.inject()
    if not success:
        logger.error("Failed to inject event!")
        return tester.get_summary()
    
    # 等待恢复
    logger.info(f"Waiting for recovery (max {args.wait_time}s)...")
    start_time = time.time()
    recovered = False
    recovery_time = None
    
    while time.time() - start_time < args.wait_time:
        time.sleep(0.5)
        
        # 检查是否已恢复
        summary = tester.get_summary()
        if summary["recovered"] and not recovered:
            recovered = True
            recovery_time = time.time() - start_time
            logger.info(f"Pipeline recovered successfully! (took {recovery_time:.1f}s)")
        
        # 显示当前状态
        if int(time.time() - start_time) % 2 == 0:
            current_state = tester._pipeline.get_state()
            logger.debug(f"Current state: {current_state}")
    
    # 恢复后继续观察直到 duration
    if recovered and args.duration > args.wait_time:
        observe_time = args.duration - args.wait_time
        logger.info(f"Recovery confirmed. Observing for additional {observe_time:.1f}s...")
        time.sleep(observe_time)
    
    # 最终检查
    final_summary = tester.get_summary()
    
    if final_summary["recovered"]:
        logger.info("TEST PASSED: Pipeline recovered from failure")
    else:
        logger.warning("TEST FAILED: Pipeline did not recover")
    
    return final_summary


def run_continuous_test(engine: MixerEngine, args):
    """运行持续测试（多次注入）
    
    Args:
        engine: MixerEngine 实例
        args: 命令行参数
    """
    logger = logging.getLogger("test_error_recovery")
    
    tester = ErrorRecoveryTester(engine, args.pipeline, args.type)
    
    logger.info(f"Starting continuous test for pipeline '{args.pipeline}'")
    logger.info(f"Inject interval: {args.interval}s, Duration: {args.duration}s")
    
    running = True
    inject_count = 0
    recover_count = 0
    
    def signal_handler(sig, frame):
        nonlocal running
        running = False
        logger.info("Received interrupt, stopping test...")
    
    signal.signal(signal.SIGINT, signal_handler)
    
    start_time = time.time()
    last_inject_time = start_time
    
    # 等待初始稳定
    time.sleep(2)
    
    while running:
        current_time = time.time()
        elapsed = current_time - start_time
        
        # 检查是否超时
        if args.duration > 0 and elapsed >= args.duration:
            logger.info(f"Test duration {args.duration}s reached")
            break
        
        # 检查是否需要注入
        if current_time - last_inject_time >= args.interval:
            inject_count += 1
            logger.info(f"\n--- Injection #{inject_count} ---")
            
            if tester.inject():
                # 等待恢复
                recover_start = time.time()
                recovered = False
                
                while time.time() - recover_start < args.wait_time:
                    summary = tester.get_summary()
                    if summary["restart_events"] > recover_count:
                        recover_count = summary["restart_events"]
                        recovered = True
                        logger.info(f"Recovered! (total recoveries: {recover_count})")
                        break
                    time.sleep(0.2)
                
                if not recovered:
                    logger.warning("Did not recover within wait time")
            else:
                logger.error("Injection failed")
            
            last_inject_time = current_time
        
        # 显示状态
        if int(elapsed) % 5 == 0:
            state = tester._pipeline.get_state()
            logger.debug(f"[{int(elapsed)}s] State: {state}")
        
        time.sleep(0.5)
    
    # 最终报告
    summary = tester.get_summary()
    logger.info("\n" + "="*50)
    logger.info("TEST SUMMARY")
    logger.info("="*50)
    logger.info(f"Total injections: {inject_count}")
    logger.info(f"Total recoveries: {recover_count}")
    logger.info(f"Recovery rate: {recover_count/max(inject_count,1)*100:.1f}%")
    logger.info(f"Final state: {summary['final_state']}")


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="test_error_recovery",
        description="测试 Pipeline 错误恢复功能"
    )
    
    # 配置文件
    parser.add_argument(
        "-c", "--config",
        required=True,
        help="YAML/JSON 配置文件路径"
    )
    
    # 目标 pipeline
    parser.add_argument(
        "-p", "--pipeline",
        required=True,
        help="要测试的 pipeline 名称"
    )
    
    # 注入类型
    parser.add_argument(
        "-t", "--type",
        choices=["error", "eos"],
        default="error",
        help="注入类型: error 或 eos (默认: error)"
    )
    
    # 延迟设置
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=3.0,
        help="首次注入前的延迟秒数 (默认: 3)"
    )
    
    # 等待恢复时间
    parser.add_argument(
        "-w", "--wait-time",
        type=float,
        default=10.0,
        help="等待恢复的最大秒数 (默认: 10)"
    )
    
    # 持续测试模式
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=0,
        help="持续测试模式: 每次注入间隔秒数 (0=单次测试, 默认: 0)"
    )
    
    # 测试总时长
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="持续测试总时长秒数 (默认: 60)"
    )
    
    # 日志级别
    parser.add_argument(
        "-l", "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别 (默认: INFO)"
    )
    
    # 输出格式
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果"
    )
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("test_error_recovery")
    
    # 加载配置
    try:
        with open(args.config, encoding='utf-8') as f:
            if args.config.endswith(('.yaml', '.yml')):
                config = yaml.safe_load(f)
            else:
                config = json.load(f)
    except FileNotFoundError:
        logger.error(f"配置文件不存在: {args.config}")
        sys.exit(1)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        logger.error(f"配置文件格式错误: {e}")
        sys.exit(1)
    
    # 创建引擎
    try:
        engine = MixerEngine.from_config(config)
    except Exception as e:
        logger.exception(f"创建引擎失败: {e}")
        sys.exit(1)
    
    # 启动引擎
    logger.info("Starting engine...")
    engine.start_all()
    time.sleep(0.5)
    
    # 验证 pipeline 存在
    if args.pipeline not in engine.inputs and \
       args.pipeline not in engine.compositors and \
       args.pipeline not in engine.outputs:
        logger.error(f"Pipeline '{args.pipeline}' not found!")
        logger.info(f"Available inputs: {list(engine.inputs.keys())}")
        logger.info(f"Available compositors: {list(engine.compositors.keys())}")
        logger.info(f"Available outputs: {list(engine.outputs.keys())}")
        engine.stop_all()
        sys.exit(1)
    
    try:
        # 运行测试
        if args.interval > 0:
            run_continuous_test(engine, args)
        else:
            result = run_single_test(engine, args)
            
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                logger.info("\n" + "="*50)
                logger.info("TEST RESULT")
                logger.info("="*50)
                for key, value in result.items():
                    logger.info(f"  {key}: {value}")
                
                if result["recovered"]:
                    logger.info("\n✓ TEST PASSED")
                else:
                    logger.info("\n✗ TEST FAILED")
    
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    
    finally:
        logger.info("Stopping engine...")
        engine.stop_all()
        logger.info("Done.")


if __name__ == "__main__":
    main()
