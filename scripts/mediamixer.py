#!/usr/bin/env python3
"""pymediamixer CLI 入口脚本

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
import sys
import logging
from pathlib import Path

import yaml


# 确保 GStreamer 初始化
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

from pymediamixer.engine import MixerEngine


def print_help():
    """打印交互式命令帮助"""
    print("""
Available commands:
  switch <compositor> <channel> <input>  - Switch compositor channel to input
  status                                 - Show all pipeline status
  help                                   - Show this help
  quit / exit                            - Exit the program
""")


def run_interactive(engine: MixerEngine, duration: int):
    """交互式命令循环
    
    Args:
        engine: MixerEngine 实例
        duration: 超时秒数，0 表示无限
    """
    running = True
    
    # 设置信号处理
    def sig_handler(sig, frame):
        nonlocal running
        running = False
        print("\nReceived interrupt, shutting down...")
    signal.signal(signal.SIGINT, sig_handler)
    
    # 超时线程
    if duration > 0:
        def timeout_handler():
            nonlocal running
            time.sleep(duration)
            if running:
                print(f"\nDuration {duration}s reached, shutting down...")
                running = False
        threading.Thread(target=timeout_handler, daemon=True).start()
    
    print("Interactive mode. Type 'help' for commands, 'quit' to exit.")
    
    while running:
        try:
            cmd = input("> ").strip()
            if not cmd:
                continue
            
            parts = cmd.split()
            command = parts[0].lower()
            
            if command in ("quit", "exit"):
                break
            elif command == "help":
                print_help()
            elif command == "status":
                status = engine.get_status()
                print(f"Inputs: {status['inputs']}")
                print(f"Compositors: {status['compositors']}")
                print(f"Outputs: {status['outputs']}")
            elif command == "switch":
                if len(parts) != 4:
                    print("Usage: switch <compositor_name> <channel_index> <input_name>")
                else:
                    try:
                        comp_name = parts[1]
                        channel_idx = int(parts[2])
                        input_name = parts[3]
                        engine.switch(comp_name, channel_idx, input_name)
                        print(f"Switched {comp_name} channel {channel_idx} to {input_name}")
                    except ValueError as e:
                        print(f"Error: Invalid channel index '{parts[2]}'")
                    except KeyError as e:
                        print(f"Error: {e}")
                    except Exception as e:
                        print(f"Error: {e}")
            else:
                print(f"Unknown command: {command}. Type 'help' for available commands.")
                
        except EOFError:
            break
        except KeyboardInterrupt:
            break


def wait_for_shutdown(engine: MixerEngine, duration: int):
    """非交互模式：等待信号或超时
    
    Args:
        engine: MixerEngine 实例
        duration: 超时秒数，0 表示无限
    """
    running = True
    
    def sig_handler(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, sig_handler)
    
    if duration > 0:
        print(f"Running for {duration}s... (Ctrl+C to stop)")
        start = time.time()
        while running and (time.time() - start) < duration:
            time.sleep(0.5)
    else:
        print("Running... (Ctrl+C to stop)")
        while running:
            time.sleep(0.5)


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="mediamixer",
        description="媒体导播应用 - 根据配置文件启动媒体混流引擎"
    )
    parser.add_argument(
        "config",
        nargs="?",
        help="YAML 配置文件路径"
    )
    parser.add_argument(
        "--config", "-c",
        dest="config_opt",
        help="YAML 配置文件路径（可选方式）"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=0,
        help="运行秒数 (0=无限，默认: 0)"
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="禁用交互模式"
    )
    parser.add_argument(
        "--log-level", "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="设置日志等级 (默认: INFO)"
    )
    
    args = parser.parse_args()
    config_path = args.config or args.config_opt
    
    # 配置日志等级
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if not config_path:
        parser.error("必须提供配置文件，例如: pymediamixer config.json")
    
    # 加载配置（支持 JSON 和 YAML 格式）
    try:
        with open(config_path, encoding='utf-8') as f:
            if config_path.endswith(('.yaml', '.yml')):
                config = yaml.safe_load(f)
            else:
                config = json.load(f)
    except FileNotFoundError:
        print(f"Error: 配置文件不存在: {config_path}")
        sys.exit(1)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        print(f"Error: 配置文件格式错误: {e}")
        sys.exit(1)
    
    # 创建引擎
    try:
        engine = MixerEngine.from_config(config)
    except Exception as e:
        print(f"Error: 创建引擎失败: {e}")
        sys.exit(1)
    
    # 启动引擎
    print(f"mediamixer starting... (配置: {config_path})")
    engine.start_all()
    time.sleep(0.5)
    
    print("mediamixer running...")
    status = engine.get_status()
    print(f"Inputs: {list(status['inputs'].keys())}")
    print(f"Compositors: {list(status['compositors'].keys())}")
    print(f"Outputs: {list(status['outputs'].keys())}")
    
    try:
        if args.no_interactive:
            # 非交互模式
            wait_for_shutdown(engine, args.duration)
        else:
            # 交互模式
            run_interactive(engine, args.duration)
    finally:
        print("Stopping...")
        engine.stop_all()
        print("Stopped.")


if __name__ == "__main__":
    main()
