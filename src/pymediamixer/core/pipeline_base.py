"""Pipeline 基类模块

提供所有 GStreamer 管线（Input/Compositing/Output）的基类，
统一管理生命周期、线程模型、Bus 消息处理和自动重启机制。
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gst, GLib
import threading
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable

from .clock import apply_clock

# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)


@dataclass
class PipelineConfig:
    """所有管线配置的基类，子类可继承扩展"""
    auto_restart: bool = True
    max_restarts_per_minute: int = 0  # 0=无限制
    restart_delay: float = 5.0 # 重启秒数


class PipelineBase(ABC):
    """所有 GStreamer 管线的基类
    
    核心职责：
    - 生命周期管理（start/stop/restart）
    - 独立线程运行（每个 Pipeline 有独立的 GLib.MainContext / GLib.MainLoop）
    - Bus 消息处理
    - 全局时钟同步
    - 错误/EOS 自动重启
    - 状态查询和回调通知
    """

    def __init__(self, name: str, config: Optional[PipelineConfig] = None):
        """初始化管线基类
        
        Args:
            name: 管线名称，用于日志和元素命名
            config: 管线配置对象，默认使用 PipelineConfig()
        """
        self._name = name
        self._config = config or PipelineConfig()
        self._auto_restart = self._config.auto_restart
        self._max_restarts_per_minute = self._config.max_restarts_per_minute
        self._restart_delay = self._config.restart_delay
        self._pipeline: Optional[Gst.Pipeline] = None
        self._context = GLib.MainContext.new()
        self._mainloop = GLib.MainLoop.new(self._context, False)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._logger = logging.getLogger(f"pymediamixer.{name}")
        
        # 重启保护
        self._restart_count = 0
        self._restart_window_start = 0.0
        
        
        # 线程同步锁
        self._lock = threading.Lock()
        
        # 回调属性（外部可注册）
        self.on_state_changed: Optional[Callable[[str, str, str], None]] = None
        self.on_error: Optional[Callable[[str, str, Optional[str]], None]] = None
        self.on_eos: Optional[Callable[[str], None]] = None
        self.on_restarted: Optional[Callable[[str], None]] = None


    @property
    def name(self) -> str:
        """获取管线名称"""
        return self._name

    @property
    def pipeline(self) -> Optional[Gst.Pipeline]:
        """获取 GStreamer pipeline 对象"""
        return self._pipeline

    @property
    def is_running(self) -> bool:
        """判断管线是否正在运行"""
        return self._running

    def start(self):
        """非阻塞启动管线
        
        执行步骤：
        1. 调用 _build() 构建 pipeline
        2. 应用全局时钟 (apply_clock)
        3. 设 pipeline 为 PLAYING 状态
        4. 启动后台线程运行 mainloop
        """
        with self._lock:
            if self._running:
                self._logger.warning(f"Pipeline {self._name} is already running")
                return
            
            try:
                # 构建 pipeline（子类负责创建并返回完整的 pipeline）
                self._pipeline = self._build()
                if not self._pipeline:
                    self._logger.error(f"Failed to create pipeline {self._name}")
                    return
                
                # 应用全局时钟
                apply_clock(self._pipeline)
                
                # 设置为 PLAYING 状态
                ret = self._pipeline.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.FAILURE:
                    self._logger.error(f"Failed to set pipeline {self._name} to PLAYING")
                    self._pipeline = None
                    return
                
                # 标记为运行中
                self._running = True
                
                # 重置重启计数
                self._restart_count = 0
                self._restart_window_start = time.monotonic()
                
                # 启动后台线程
                self._thread = threading.Thread(
                    target=self._run,
                    name=f"pipeline-{self._name}",
                    daemon=True
                )
                self._thread.start()
                
                self._logger.info(f"Pipeline {self._name} started")
                
            except Exception as e:
                self._logger.exception(f"Failed to start pipeline {self._name}: {e}")
                self._running = False
                if self._pipeline:
                    self._pipeline.set_state(Gst.State.NULL)
                    self._pipeline = None

    def stop(self):
        """停止管线
        
        执行步骤：
        1. 设置 pipeline 为 NULL 状态
        2. 退出 mainloop
        3. 等待线程结束
        """
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            pipeline_to_cleanup = self._pipeline
            self._pipeline = None
        
        # 以下操作在锁外执行，避免死锁
        try:
            # 清理 pipeline 资源
            if pipeline_to_cleanup:
                self._cleanup_pipeline(pipeline_to_cleanup)
                del pipeline_to_cleanup
            
            # 退出 mainloop
            if self._mainloop.is_running():
                self._mainloop.quit()
            
            # 等待线程结束
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
                if self._thread.is_alive():
                    self._logger.warning(f"Pipeline {self._name} thread did not exit in time")
            
            self._thread = None
            
            self._logger.info(f"Pipeline {self._name} stopped")
            
        except Exception as e:
            self._logger.exception(f"Error stopping pipeline {self._name}: {e}")

    def restart(self):
        """重启管线
        
        销毁当前 pipeline 并重新构建。
        包含重启保护：1秒延迟、5次/分钟阈值。
        
        注意：此方法应在 pipeline 线程中通过 GLib idle 调用，
        或从外部在 stop() 后再 start()。
        """
        # 重启保护逻辑
        now = time.monotonic()
        if now - self._restart_window_start > 60:
            self._restart_count = 0
            self._restart_window_start = now
        
        self._restart_count += 1
        if self._max_restarts_per_minute > 0 and self._restart_count > self._max_restarts_per_minute:
            self._logger.error(
                f"Pipeline {self._name}: restart limit exceeded "
                f"({self._max_restarts_per_minute}/min), stopping auto-restart"
            )
            self._running = False
            if self._mainloop.is_running():
                self._mainloop.quit()
            return
        
        self._logger.info(f"Pipeline {self._name}: restarting (attempt {self._restart_count})...")
        
        try:
            # 1. 将当前 pipeline 设为 NULL（锁内获取并置空，锁外操作旧对象）
            with self._lock:
                old_pipeline = self._pipeline
                self._pipeline = None
            
            # 清理旧 pipeline 资源
            if old_pipeline:
                self._cleanup_pipeline(old_pipeline)
                del old_pipeline
            
            # 2. 延迟避免快速循环
            time.sleep(self._restart_delay)
            
            # 3. 检查是否仍需运行
            if not self._running:
                return
            
            # 4. 重新构建（先在锁外创建，再在锁内赋值）
            new_pipeline = self._build()
            if not new_pipeline:
                self._logger.error(f"Pipeline {self._name}: failed to create new pipeline")
                return
            
            with self._lock:
                self._pipeline = new_pipeline
            
            apply_clock(self._pipeline)
            
            # 5. 重新添加 bus watch（在当前上下文中）
            self._setup_bus_watch()
            
            # 6. 设为 PLAYING
            ret = self._pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                self._logger.error(f"Pipeline {self._name}: failed to restart - state change failed")
                return
            
            self._logger.info(f"Pipeline {self._name}: restarted successfully")
            
            # 回调通知
            if self.on_restarted:
                try:
                    self.on_restarted(self._name)
                except Exception as e:
                    self._logger.exception(f"Error in on_restarted callback: {e}")
                    
        except Exception as e:
            self._logger.exception(f"Pipeline {self._name}: restart failed: {e}")

    def get_state(self) -> str:
        """获取当前 pipeline 状态字符串
        
        Returns:
            状态字符串（如 "playing", "paused", "null" 等）
        """
        with self._lock:
            pipeline = self._pipeline
        
        if not pipeline:
            return "NULL"
        
        # 使用短暂超时避免永久阻塞 (100ms)
        timeout = Gst.SECOND // 10
        success, state, pending = pipeline.get_state(timeout)
        
        if success == Gst.StateChangeReturn.FAILURE:
            return "UNKNOWN"
        
        return state.value_nick if state else "UNKNOWN"

    def wait(self, timeout: Optional[float] = None):
        """阻塞等待 pipeline 停止
        
        Args:
            timeout: 超时时间（秒），None 表示无限等待
        """
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    @abstractmethod
    def _build(self) -> Gst.Pipeline:
        """
        抽象方法：子类实现，创建并返回完整的 GStreamer Pipeline。
        
        子类负责：
        1. 创建 Gst.Pipeline 对象（可用 Gst.Pipeline.new() 或 Gst.parse_launch()）
        2. 创建所有需要的 element
        3. 添加 element 到 pipeline 并连接
        4. 返回构建完成的 Pipeline 对象
        
        Returns:
            Gst.Pipeline: 构建完成的 pipeline 对象
        """
        pass

    def _run(self):
        """线程入口：推入线程默认上下文，添加 bus watch，运行 mainloop"""
        self._context.push_thread_default()
        try:
            self._setup_bus_watch()
            self._mainloop.run()
        except Exception as e:
            self._logger.exception(f"Pipeline {self._name} mainloop error: {e}")
        finally:
            self._context.pop_thread_default()
            self._logger.debug(f"Pipeline {self._name} thread exited")

    def _setup_bus_watch(self):
        """在当前上下文中添加 bus signal watch 和消息回调"""
        if not self._pipeline:
            return
        
        bus = self._pipeline.get_bus()
        if not bus:
            self._logger.error(f"Pipeline {self._name}: failed to get bus")
            return
        
        bus.add_signal_watch()
        bus.connect("message::error", self._on_error)
        bus.connect("message::eos", self._on_eos)
        bus.connect("message::state-changed", self._on_state_changed)
        bus.connect("message::latency", self._on_latency)
        bus.connect("message::warning", self._on_warning)
        
        # 钩子：子类可添加额外的消息监听
        self._setup_additional_bus_handlers(bus)

    def _setup_additional_bus_handlers(self, bus: Gst.Bus):
        """子类可重写以添加额外的 bus 消息处理
        
        此方法在 mainloop 线程中被调用，确保注册的信号处理器能正常工作。
        不需要显式清理回调，bus finalize 时会自动断开所有连接。
        
        Args:
            bus: GStreamer bus 对象
            
        Example:
            def _setup_additional_bus_handlers(self, bus):
                bus.connect("message::buffering", self._on_buffering)
        """
        pass

    def _cleanup_pipeline(self, pipeline: Gst.Pipeline):
        """清理 pipeline 资源
        
        移除 signal watch，设置 NULL 状态。
        注意：不需要显式 disconnect_by_func，bus finalize 时会自动断开所有连接。
        
        Args:
            pipeline: 要清理的 GStreamer pipeline 对象
        """
        if not pipeline:
            return
        
        bus = pipeline.get_bus()
        if bus:
            # 必须调用：平衡 add_signal_watch() 的引用计数
            bus.remove_signal_watch()
        
        # 设置为 NULL 状态释放 GStreamer 内部资源
        pipeline.set_state(Gst.State.NULL)



    def _on_error(self, bus, msg):
        """错误消息处理
        
        记录日志，回调通知；若 auto_restart 则自动重启
        """
        err, debug = msg.parse_error()
        error_msg = err.message if err else "Unknown error"
        
        self._logger.error(f"Pipeline {self._name} ERROR: {error_msg}")
        if debug:
            self._logger.debug(f"Debug info: {debug}")
        
        # 回调通知
        if self.on_error:
            try:
                self.on_error(self._name, error_msg, debug)
            except Exception as e:
                self._logger.exception(f"Error in on_error callback: {e}")
        
        # 自动重启
        if self._auto_restart and self._running:
            self._context.invoke_full(GLib.PRIORITY_HIGH, self._idle_restart)

    def _on_eos(self, bus, msg):
        """EOS 消息处理
        
        记录日志，回调通知；若 auto_restart 则自动重启
        """
        self._logger.info(f"Pipeline {self._name} received EOS")
        
        # 回调通知
        if self.on_eos:
            try:
                self.on_eos(self._name)
            except Exception as e:
                self._logger.exception(f"Error in on_eos callback: {e}")
        
        # 自动重启
        if self._auto_restart and self._running:
            self._context.invoke_full(GLib.PRIORITY_HIGH, self._idle_restart)

    def _idle_restart(self):
        """通过 GLib idle 回调执行重启，确保在 mainloop 线程中
        
        Returns:
            GLib.SOURCE_REMOVE: 表示只执行一次
        """
        if self._running:
            self.restart()
        return GLib.SOURCE_REMOVE

    def _on_state_changed(self, bus, msg):
        """状态变化消息处理"""
        # 只关心 pipeline 自身的状态变化
        if msg.src != self._pipeline:
            return
        
        old, new, pending = msg.parse_state_changed()
        old_nick = old.value_nick if old else "unknown"
        new_nick = new.value_nick if new else "unknown"
        
        self._logger.debug(f"Pipeline {self._name} state: {old_nick} -> {new_nick}")
        
        # 回调通知
        if self.on_state_changed:
            try:
                self.on_state_changed(self._name, old_nick, new_nick)
            except Exception as e:
                self._logger.exception(f"Error in on_state_changed callback: {e}")

    def _on_latency(self, bus, msg):
        """延迟消息处理：重新计算延迟"""
        if self._pipeline:
            self._pipeline.recalculate_latency()
            self._logger.debug(f"Pipeline {self._name}: recalculated latency")

    def _on_warning(self, bus, msg):
        """警告消息处理"""
        warn, debug = msg.parse_warning()
        warn_msg = warn.message if warn else "Unknown warning"
        
        self._logger.warning(f"Pipeline {self._name} WARNING: {warn_msg}")
        if debug:
            self._logger.debug(f"Debug info: {debug}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self._name}, state={self.get_state()})>"
