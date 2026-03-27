"""常量定义和 Caps 构建工具"""

from enum import Enum
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)


class MediaType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


# 默认视频参数
DEFAULT_VIDEO_WIDTH = 1920
DEFAULT_VIDEO_HEIGHT = 1080
DEFAULT_VIDEO_FRAMERATE = "30/1"
DEFAULT_VIDEO_FORMAT = "I420"

# 默认音频参数
DEFAULT_AUDIO_RATE = 48000
DEFAULT_AUDIO_CHANNELS = 2
DEFAULT_AUDIO_FORMAT = "S16LE"


def make_video_caps(width=None, height=None, framerate=None, fmt=None) -> Gst.Caps:
    """构建标准化的视频 caps
    
    Args:
        width: 视频宽度，默认使用 DEFAULT_VIDEO_WIDTH
        height: 视频高度，默认使用 DEFAULT_VIDEO_HEIGHT
        framerate: 帧率字符串 (如 "30/1")，默认使用 DEFAULT_VIDEO_FRAMERATE
        fmt: 视频格式 (如 "I420")，默认使用 DEFAULT_VIDEO_FORMAT
    
    Returns:
        Gst.Caps: 构建的视频 caps 对象
    """
    w = width if width is not None else DEFAULT_VIDEO_WIDTH
    h = height if height is not None else DEFAULT_VIDEO_HEIGHT
    fr = framerate if framerate is not None else DEFAULT_VIDEO_FRAMERATE
    f = fmt if fmt is not None else DEFAULT_VIDEO_FORMAT
    
    caps_str = f"video/x-raw,format={f},width={w},height={h},framerate={fr}"
    return Gst.Caps.from_string(caps_str)


def make_audio_caps(rate=None, channels=None, fmt=None) -> Gst.Caps:
    """构建标准化的音频 caps
    
    Args:
        rate: 采样率，默认使用 DEFAULT_AUDIO_RATE
        channels: 声道数，默认使用 DEFAULT_AUDIO_CHANNELS
        fmt: 音频格式 (如 "S16LE")，默认使用 DEFAULT_AUDIO_FORMAT
    
    Returns:
        Gst.Caps: 构建的音频 caps 对象
    """
    r = rate if rate is not None else DEFAULT_AUDIO_RATE
    ch = channels if channels is not None else DEFAULT_AUDIO_CHANNELS
    f = fmt if fmt is not None else DEFAULT_AUDIO_FORMAT
    
    caps_str = f"audio/x-raw,format={f},rate={r},channels={ch}"
    return Gst.Caps.from_string(caps_str)
