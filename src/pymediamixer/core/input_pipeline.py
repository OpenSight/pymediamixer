"""输入管线基类模块

提供输入源到 intersink 的数据流管理，支持视频和/或音频输出。
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from abc import abstractmethod
from typing import List, Dict, Optional

from .pipeline_base import PipelineBase, PipelineConfig
from .constants import MediaType

# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)


class InputPipeline(PipelineBase):
    """输入管线基类
    
    管理输入源到 1~2 个 intersink 的数据流。
    
    核心设计：
    - 一个输入管线可同时输出视频和音频（各一个 intersink），也可仅输出一种
    - 同一种媒体类型最多一个 intersink
    - producer-name 命名：{pipeline_name}_{media_type.value}，如 input0_video、input0_audio
    - 输入保持原始分辨率，仅做格式转换（videoconvert/audioconvert），不做缩放
    - intersink 的 event-types 强制设置为空列表，不转发任何事件（含 EOS）
    """
    
    def __init__(self, name: str, media_types: List[MediaType], config: Optional[PipelineConfig] = None):
        """初始化输入管线
        
        Args:
            name: 管线名称
            media_types: 输出端媒体类型列表，如 [MediaType.VIDEO] 或 [MediaType.VIDEO, MediaType.AUDIO]
            config: 管线配置对象，默认使用 PipelineConfig()
        """
        super().__init__(name, config)
        self._media_types: List[MediaType] = list(media_types)
        self._intersinks: Dict[MediaType, Gst.Element] = {}
    
    def get_channel(self, media_type: MediaType) -> str:
        """返回指定媒体类型的 producer-name
        
        Args:
            media_type: 媒体类型
            
        Returns:
            producer-name 字符串，格式为 {pipeline_name}_{media_type.value}
            
        Raises:
            ValueError: 如果该管线不支持指定的媒体类型
        """
        if media_type not in self._media_types:
            raise ValueError(f"Pipeline {self._name} does not have {media_type} output")
        return f"{self._name}_{media_type.value}"
    
    @property
    def channels(self) -> Dict[MediaType, str]:
        """只读属性，返回所有通道映射
        
        Returns:
            {MediaType: producer_name} 的字典
        """
        return {mt: self.get_channel(mt) for mt in self._media_types}
    
    @property
    def media_types(self) -> List[MediaType]:
        """获取支持的媒体类型列表
        
        Returns:
            MediaType 列表的副本
        """
        return list(self._media_types)

    @abstractmethod
    def _build(self) -> Gst.Pipeline:
        """子类实现：创建并返回完整的输入管线 Pipeline。
        
        子类负责在 _build() 中完成所有管线构建工作，包括：
        1. 创建 Gst.Pipeline 对象
        2. 创建源元素、处理元素、intersink
        3. 添加所有元素并连接
        4. 将 intersink 存入 self._intersinks[media_type]
        5. 返回 Pipeline 对象
        
        可使用 self._create_intersink(media_type) 工具方法简化 intersink 创建。
        """
        pass

    def _create_intersink(self, media_type: MediaType) -> Gst.Element:
        """创建并配置好的 intersink 元素
        
        可选工具方法，子类可选择调用此方法简化代码。
        
        Args:
            media_type: 媒体类型
            
        Returns:
            配置好的 intersink 元素（已设置 producer-name 和 event-types=[]）
        """
        intersink_name = f"{self._name}_{media_type.value}_intersink"
        intersink = Gst.ElementFactory.make("intersink", intersink_name)
        if not intersink:
            raise RuntimeError(f"Failed to create intersink element: {intersink_name}")
        
        # 设置 producer-name
        intersink.set_property("producer-name", self.get_channel(media_type))
        
        # 关键：强制 event-types 为空列表，不转发任何事件（含 EOS）
        try:
            intersink.set_property("event-types", [])
            self._logger.debug(f"Set event-types=[] via list for {intersink.get_name()}")
        except Exception as e1:
            self._logger.error(f"Set event-types=[] via list for {intersink.get_name()} failed: {e1}")
        
        # 存入字典
        self._intersinks[media_type] = intersink
        
        return intersink
