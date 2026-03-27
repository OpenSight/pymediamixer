"""全局时钟管理模块

为所有 pipeline 提供统一的时钟和 base_time，确保多个管线之间的同步。
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)

_global_clock = Gst.SystemClock.obtain()
_global_base_time = _global_clock.get_time()


def apply_clock(pipeline: Gst.Pipeline):
    """将全局时钟和 base_time 应用到指定 pipeline
    
    Args:
        pipeline: 需要应用时钟的 GStreamer pipeline
    """
    pipeline.set_clock(_global_clock)
    pipeline.set_start_time(Gst.CLOCK_TIME_NONE)
    pipeline.set_base_time(_global_base_time)


def get_clock() -> Gst.Clock:
    """获取全局时钟
    
    Returns:
        Gst.Clock: 全局系统时钟
    """
    return _global_clock


def get_base_time() -> int:
    """获取全局 base_time
    
    Returns:
        int: 全局 base_time (纳秒)
    """
    return _global_base_time
