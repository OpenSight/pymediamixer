"""合成管线基类模块

提供 CompositingPipeline 基类，一条合成管线仅处理一种媒体类型，
有多个 channel（每个 channel 对应一个 intersrc 输入），
可动态切换每个 channel 连接的输入源，合成后通过 intersink 输出。
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from abc import abstractmethod
from typing import Optional, List, Dict, TYPE_CHECKING

from .pipeline_base import PipelineBase, PipelineConfig
from .constants import MediaType

if TYPE_CHECKING:
    from .input_pipeline import InputPipeline

# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)


class CompositingPipeline(PipelineBase):
    """合成管线基类
    
    核心设计：
    - 一条合成管线仅处理一种媒体类型（如仅 VIDEO 或仅 AUDIO）
    - 拥有多个 channel，每个 channel 对应一个 intersrc
    - 可动态切换每个 channel 连接的输入源（通过修改 intersrc 的 producer-name）
    - 合成后通过 intersink 输出，output producer-name 为 `{name}_{media_type.value}`
    """

    def __init__(self, name: str,
                 inputs: list[Optional['InputPipeline']],
                 output_caps: Optional[dict] = None,
                 config: Optional[PipelineConfig] = None):
        """初始化合成管线
        
        Args:
            name: 管线名称
            inputs: 输入管线列表，每个元素对应一个 channel，None 表示未连接
            output_caps: 输出参数，如 {"width": 1920, "height": 1080, "framerate": "30/1"}
            config: 管线配置对象
        """
        super().__init__(name, config=config)
        self._num_channels = len(inputs)
        self._output_caps = output_caps or {}
        self._intersrcs: List[Gst.Element] = []  # 按 channel index 索引
        self._channel_sources: Dict[int, str] = {}  # channel_index -> producer_name 映射
        
        # 对非 None 的 input_pipeline 自动调用 switch_channel
        for idx, inp in enumerate(inputs):
            if inp is not None:
                self.switch_channel(idx, inp)

    @property
    @abstractmethod
    def media_type(self) -> MediaType:
        """由子类实现，返回该合成管线处理的媒体类型"""
        ...

    @property
    def output_channel(self) -> str:
        """输出 producer-name"""
        return f"{self._name}_{self.media_type.value}"

    @property
    def num_channels(self) -> int:
        """获取 channel 数量"""
        return self._num_channels

    def switch_channel(self, channel_index: int, input_pipeline: 'InputPipeline'):
        """将指定 channel 切换到某个输入管线
        
        自动根据 self.media_type 选择该输入管线对应媒体类型的输出端。
        
        Args:
            channel_index: channel 索引 (0 ~ num_channels-1)
            input_pipeline: InputPipeline 实例
        """
        producer_name = input_pipeline.get_channel(self.media_type)
        self.switch_channel_by_name(channel_index, producer_name)

    def switch_channel_by_name(self, channel_index: int, producer_name: str):
        """直接通过 producer-name 切换
        
        可在 start() 前或后调用：
        - start() 前：仅保存配置，在 _build() 时应用
        - start() 后：保存配置并动态修改运行中的 intersrc 属性
        
        Args:
            channel_index: channel 索引 (0 ~ num_channels-1)
            producer_name: 目标输入的 producer-name
            
        Raises:
            IndexError: channel_index 超出范围
        """
        if channel_index < 0 or channel_index >= self._num_channels:
            raise IndexError(f"Channel index {channel_index} out of range [0, {self._num_channels})")
        
        # 保存配置（用于重建时恢复或 start() 前设置）
        self._channel_sources[channel_index] = producer_name
        
        # 如果已经有对应的 intersrc 在运行，动态切换
        if self._intersrcs and channel_index < len(self._intersrcs):
            self._intersrcs[channel_index].set_property("producer-name", producer_name)
            self._logger.info(f"Channel {channel_index} switched to '{producer_name}'")

    def get_channel_source(self, channel_index: int) -> Optional[str]:
        """返回指定 channel 当前连接的 producer-name
        
        Args:
            channel_index: channel 索引 (0 ~ num_channels-1)
            
        Returns:
            当前连接的 producer-name，若管线未构建则返回 None
            
        Raises:
            IndexError: channel_index 超出范围
        """
        if channel_index < 0 or channel_index >= self._num_channels:
            raise IndexError(f"Channel index {channel_index} out of range")
        if not self._intersrcs:
            return None
        return self._intersrcs[channel_index].get_property("producer-name")



    @abstractmethod
    def _build(self) -> Gst.Pipeline:
        """子类实现：创建并返回完整的合成管线 Pipeline。
        
        子类必须在 _build() 中：
        1. 创建 Gst.Pipeline 对象
        2. 创建 N 个 intersrc 并存入 self._intersrcs 列表
        3. 创建合成器元素并赋值给 self._compositor
        4. 构建完整管线拓扑并返回 Pipeline
        
        注意：子类应在创建 intersrc 后，根据 self._channel_sources
        恢复之前的 producer-name 连接状态（用于重建场景）。
        """
        pass
