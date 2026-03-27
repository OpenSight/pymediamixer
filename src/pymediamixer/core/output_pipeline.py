"""输出管线基类模块

提供从合成管线获取数据并输出到具体目标的基类。
使用 intersrc 接收 compositor 的输出。
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from abc import abstractmethod
from typing import Optional, TYPE_CHECKING

from .pipeline_base import PipelineBase, PipelineConfig
from .constants import MediaType

if TYPE_CHECKING:
    from .compositing_pipeline import CompositingPipeline

# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)


class OutputPipeline(PipelineBase):
    """输出管线基类
    
    从合成管线获取数据输出到具体目标。可有 1~2 个输入端（intersrc），
    每种媒体类型最多一个。
    
    使用方式：
    1. 子类继承并实现 _build() 返回完整的 Gst.Pipeline 对象
    2. 调用 set_source() 设置数据来源的 producer-name
    3. 调用 start() 启动管线
    """

    def __init__(self, name: str,
                 sources: dict[MediaType, Optional['CompositingPipeline']],
                 config: Optional[PipelineConfig] = None):
        """初始化输出管线
        
        Args:
            name: 管线名称
            sources: 媒体类型到合成管线的映射，值为 None 表示暂不设置源
            config: 管线配置对象，默认使用 PipelineConfig()
        """
        super().__init__(name, config=config)
        self._media_types = list(sources.keys())
        self._sources: dict[MediaType, str] = {}
        self._intersrcs: dict[MediaType, Optional[Gst.Element]] = {mt: None for mt in self._media_types}
        
        # 对非 None 的 compositor 自动调用 set_source
        for media_type, compositor in sources.items():
            if compositor is not None:
                self.set_source(media_type, compositor)

    @property
    def media_types(self) -> list[MediaType]:
        """获取支持的媒体类型列表"""
        return list(self._media_types)

    def set_source(self, media_type: MediaType, compositing_pipeline: "CompositingPipeline"):
        """设置指定媒体类型的来源合成管线
        
        可在 start 前或后调用：
        - start 前：保存配置，_build() 时应用
        - start 后：保存配置并动态修改运行中的 intersrc 属性
        
        Args:
            media_type: 媒体类型
            compositing_pipeline: CompositingPipeline 实例
            
        Raises:
            ValueError: 如果该管线不支持指定的媒体类型，或 media_type 不匹配
            TypeError: 如果传入的不是 CompositingPipeline 实例
        """
        if media_type not in self._media_types:
            raise ValueError(f"Pipeline {self._name} does not support {media_type} input")
        
        # 类型检查
        from .compositing_pipeline import CompositingPipeline
        if not isinstance(compositing_pipeline, CompositingPipeline):
            raise TypeError("Source must be a CompositingPipeline instance")
        
        # MediaType 匹配检查
        if compositing_pipeline.media_type != media_type:
            raise ValueError(
                f"MediaType mismatch: expected {media_type.value}, "
                f"but compositing pipeline has {compositing_pipeline.media_type.value}"
            )
        
        # 获取 producer-name
        producer_name = compositing_pipeline.output_channel
        
        # 保存配置
        self._sources[media_type] = producer_name
        
        # 如果已经有对应的 intersrc 在运行，动态切换
        if media_type in self._intersrcs and self._intersrcs[media_type]:
            self._intersrcs[media_type].set_property("producer-name", producer_name)
            self._logger.info(f"Source for {media_type.value} switched to '{producer_name}'")

    def switch_source(self, media_type: MediaType, compositing_pipeline: "CompositingPipeline"):
        """运行时切换来源
        
        等同于 set_source()，提供更语义化的接口名称。
        
        Args:
            media_type: 媒体类型
            compositing_pipeline: CompositingPipeline 实例
        """
        self.set_source(media_type, compositing_pipeline)

    def switch_source_by_name(self, media_type: MediaType, producer_name: str):
        """直接通过 producer-name 切换来源（调试用）
        
        正常调用不应使用此方法，主要用于调试场景。
        
        Args:
            media_type: 媒体类型
            producer_name: 目标 producer-name
        """
        if media_type not in self._media_types:
            raise ValueError(f"Pipeline {self._name} does not support {media_type} input")
        
        self._sources[media_type] = producer_name
        
        if media_type in self._intersrcs and self._intersrcs[media_type]:
            self._intersrcs[media_type].set_property("producer-name", producer_name)
            self._logger.info(f"Source for {media_type.value} switched to '{producer_name}' (by name)")

    @abstractmethod
    def _build(self) -> Gst.Pipeline:
        """子类实现：创建并返回完整的输出管线 Pipeline。
        
        子类必须在 _build() 中：
        1. 创建 Gst.Pipeline 对象
        2. 创建 intersrc 并存入 self._intersrcs[media_type]
        3. 使用 self._sources 中已配置的 producer-name 设置 intersrc
        4. 构建完整管线拓扑并返回 Pipeline
        """
        pass

    def get_source(self, media_type: MediaType) -> Optional[str]:
        """获取指定媒体类型当前配置的 producer-name
        
        Args:
            media_type: 媒体类型
        
        Returns:
            str or None: 配置的 producer-name，未配置则返回 None
        """
        return self._sources.get(media_type)
