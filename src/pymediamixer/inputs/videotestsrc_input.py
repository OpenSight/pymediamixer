"""VideoTestSrcInput - 基于 videotestsrc 的测试视频输入"""

from dataclasses import dataclass
from typing import List, Optional

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

from ..core.input_pipeline import InputPipeline
from ..core.pipeline_base import PipelineConfig
from ..core.constants import (
    MediaType,
    DEFAULT_VIDEO_WIDTH,
    DEFAULT_VIDEO_HEIGHT,
    DEFAULT_VIDEO_FRAMERATE,
    make_video_caps
)

# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)


@dataclass
class VideoTestSrcConfig(PipelineConfig):
    """VideoTestSrcInput 配置类"""
    pattern: str = "smpte"
    width: int = DEFAULT_VIDEO_WIDTH
    height: int = DEFAULT_VIDEO_HEIGHT
    framerate: str = DEFAULT_VIDEO_FRAMERATE


class VideoTestSrcInput(InputPipeline):
    """基于 videotestsrc 的测试视频输入
    
    使用 GStreamer 的 videotestsrc 元素生成测试视频信号，
    支持多种测试图案（pattern）。
    
    输出：单个视频通道（通过 intersink）
    """
    
    _SUPPORTED_MEDIA_TYPES = frozenset({MediaType.VIDEO})

    def __init__(self, name: str, media_types: List[MediaType], config: Optional[VideoTestSrcConfig] = None):
        """初始化 VideoTestSrcInput
        
        Args:
            name: 管线名称
            media_types: 输出端媒体类型列表，必须是 _SUPPORTED_MEDIA_TYPES 的子集
            config: VideoTestSrcInput 配置对象，默认使用 VideoTestSrcConfig()
        """
        # 校验 media_types 必须是支持的媒体类型的子集
        if not frozenset(media_types).issubset(self._SUPPORTED_MEDIA_TYPES):
            raise ValueError(
                f"VideoTestSrcInput only supports {self._SUPPORTED_MEDIA_TYPES}, got {media_types}"
            )
        
        config = config or VideoTestSrcConfig()
        super().__init__(name, media_types, config)
    
    def _build(self) -> Gst.Pipeline:
        """完整构建 videotestsrc 输入管线"""
        pipeline = Gst.Pipeline.new(self._name)
        
        # 创建源
        src = Gst.ElementFactory.make("videotestsrc", f"{self._name}_src")
        src.set_property("pattern", self._config.pattern)
        src.set_property("is-live", True)
        
        # 处理链：videoconvert -> capsfilter（保持原始分辨率配置）
        convert = Gst.ElementFactory.make("videoconvert", f"{self._name}_convert")
        capsfilter = Gst.ElementFactory.make("capsfilter", f"{self._name}_caps")
        capsfilter.set_property("caps", make_video_caps(
            width=self._config.width, height=self._config.height, framerate=self._config.framerate
        ))
        
        # 创建 intersink（使用基类工具方法）
        intersink = self._create_intersink(MediaType.VIDEO)
        
        # 添加到 pipeline
        for elem in [src, convert, capsfilter, intersink]:
            pipeline.add(elem)
        
        # 连接
        src.link(convert)
        convert.link(capsfilter)
        capsfilter.link(intersink)
        
        return pipeline
    
    @property
    def pattern(self) -> str:
        """获取当前图案名称"""
        return self._config.pattern
    
    @property
    def width(self) -> int:
        """获取视频宽度"""
        return self._config.width
    
    @property
    def height(self) -> int:
        """获取视频高度"""
        return self._config.height
    
    @property
    def framerate(self) -> str:
        """获取帧率"""
        return self._config.framerate
