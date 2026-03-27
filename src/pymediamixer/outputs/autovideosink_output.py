"""AutoVideoSinkOutput - 基于 autovideosink 的本地视频预览输出"""

from dataclasses import dataclass

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from typing import Optional, TYPE_CHECKING

from ..core.output_pipeline import OutputPipeline
from ..core.constants import MediaType
from ..core.pipeline_base import PipelineConfig

if TYPE_CHECKING:
    from ..core.compositing_pipeline import CompositingPipeline


# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)


@dataclass
class AutoVideoSinkConfig(PipelineConfig):
    """AutoVideoSinkOutput 配置类"""
    pass  # 当前无特有配置项，预留扩展


class AutoVideoSinkOutput(OutputPipeline):
    """基于 autovideosink 的本地视频预览输出
    
    使用 GStreamer 的 autovideosink 元素自动选择系统可用的视频输出方式，
    适用于本地预览和调试。
    
    输入：单个视频通道（通过 intersrc 接收）
    """
    
    _SUPPORTED_MEDIA_TYPES = frozenset({MediaType.VIDEO})
    
    def __init__(self, name: str,
                 sources: dict[MediaType, Optional['CompositingPipeline']],
                 config: Optional[AutoVideoSinkConfig] = None):
        """初始化 AutoVideoSinkOutput
        
        Args:
            name: 管线名称
            sources: 媒体类型到合成管线的映射，值为 None 表示暂不设置源
            config: 管线配置对象，默认使用 AutoVideoSinkConfig()
        """
        # 媒体类型适配检查
        unsupported = set(sources.keys()) - self._SUPPORTED_MEDIA_TYPES
        if unsupported:
            raise ValueError(
                f"{self.__class__.__name__} 不支持媒体类型: {unsupported}，"
                f"仅支持: {self._SUPPORTED_MEDIA_TYPES}"
            )
        
        config = config or AutoVideoSinkConfig()
        super().__init__(name, sources, config)
    
    def _build(self) -> Gst.Pipeline:
        """完整构建 autovideosink 输出管线"""
        pipeline = Gst.Pipeline.new(self._name)
        
        # 创建 intersrc
        intersrc = Gst.ElementFactory.make("intersrc", f"{self._name}_video_intersrc")
        
        # 设置已配置的 producer-name
        if MediaType.VIDEO in self._sources:
            intersrc.set_property("producer-name", self._sources[MediaType.VIDEO])
        
        self._intersrcs[MediaType.VIDEO] = intersrc
        
        # 处理链
        convert = Gst.ElementFactory.make("videoconvert", f"{self._name}_convert")
        
        # 输出 sink
        sink = Gst.ElementFactory.make("autovideosink", f"{self._name}_sink")
        
        # 添加到 pipeline
        for elem in [intersrc, convert, sink]:
            pipeline.add(elem)
        
        # 连接
        intersrc.link(convert)
        convert.link(sink)
        
        return pipeline
