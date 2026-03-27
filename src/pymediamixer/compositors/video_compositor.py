"""VideoCompositor - 基于 GStreamer compositor 的视频合成器"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from dataclasses import dataclass, field
from typing import Optional, Dict, TYPE_CHECKING

from ..core.compositing_pipeline import CompositingPipeline
from ..core.pipeline_base import PipelineConfig
from ..core.constants import (
    MediaType,
    DEFAULT_VIDEO_WIDTH,
    DEFAULT_VIDEO_HEIGHT,
    DEFAULT_VIDEO_FRAMERATE,
    make_video_caps
)

if TYPE_CHECKING:
    from ..core.input_pipeline import InputPipeline

# 确保 Gst 已初始化
if not Gst.is_initialized():
    Gst.init(None)


@dataclass
class VideoCompositorConfig(PipelineConfig):
    """VideoCompositor 配置类
    
    注意：输出规格（width/height/framerate）通过基类 output_caps 参数传递，
    不在此配置类中重复定义。
    """
    # 每个 channel 的布局参数，key 为 channel_index，value 为布局字典
    # 布局字典支持的参数（GStreamer compositor sink pad 属性）：
    #   - xpos (int, 可选): 水平位置（像素），默认 0
    #   - ypos (int, 可选): 垂直位置（像素），默认 0
    #   - width (int, 可选): 显示宽度（像素），默认输入视频宽度
    #   - height (int, 可选): 显示高度（像素），默认输入视频高度
    #   - zorder (int, 可选): 层级顺序，数值越大越在上层，默认 0
    #   - alpha (float, 可选): 透明度，范围 0.0~1.0，默认 1.0（不透明）
    channel_layouts: dict[int, dict] = field(default_factory=dict)


class VideoCompositor(CompositingPipeline):
    """基于 GStreamer compositor 的视频合成器
    
    使用 GStreamer 的 compositor 元素将多个视频输入合成为单一输出。
    支持设置每个输入通道的位置、大小、层级和透明度。
    
    输出：单个视频通道（通过 intersink），producer-name 为 `{name}_video`
    """
    
    def __init__(self, name: str,
                 inputs: list[Optional['InputPipeline']],
                 output_caps: Optional[dict] = None,
                 config: Optional[VideoCompositorConfig] = None):
        """初始化 VideoCompositor
        
        Args:
            name: 管线名称
            inputs: 输入管线列表，每个元素对应一个 channel，None 表示未连接
            output_caps: 输出规格配置字典，支持的 key 如下：
                - width (int, 可选): 输出视频宽度（像素），如 1920
                - height (int, 可选): 输出视频高度（像素），如 1080
                - framerate (str, 可选): 输出帧率，格式为 "num/den"，如 "30/1"、"60/1"
                若未提供，使用默认值：width=1920, height=1080, framerate="30/1"
            config: VideoCompositor 配置对象（仅包含 channel_layouts 等特有配置）
        """
        config = config or VideoCompositorConfig()
        
        # output_caps 由调用方传入，遵循基类规范
        # 如果未提供，使用默认视频规格
        if output_caps is None:
            output_caps = {
                "width": DEFAULT_VIDEO_WIDTH,
                "height": DEFAULT_VIDEO_HEIGHT,
                "framerate": DEFAULT_VIDEO_FRAMERATE
            }
        
        super().__init__(
            name,
            inputs=inputs,
            output_caps=output_caps,
            config=config
        )
        self._compositor: Optional[Gst.Element] = None
        self._channel_layouts: Dict[int, dict] = {}  # channel_index -> layout 映射
        
        # 从 config.channel_layouts 读取布局，自动调用 set_channel_layout
        for idx, layout in config.channel_layouts.items():
            if 0 <= idx < self._num_channels:
                self.set_channel_layout(idx, layout)

    @property
    def media_type(self) -> MediaType:
        """返回该合成管线处理的媒体类型"""
        return MediaType.VIDEO

    @property
    def width(self) -> int:
        """获取输出视频宽度"""
        return self._output_caps.get("width", DEFAULT_VIDEO_WIDTH)

    @property
    def height(self) -> int:
        """获取输出视频高度"""
        return self._output_caps.get("height", DEFAULT_VIDEO_HEIGHT)

    @property
    def framerate(self) -> str:
        """获取输出帧率"""
        return self._output_caps.get("framerate", DEFAULT_VIDEO_FRAMERATE)

    def _build(self) -> Gst.Pipeline:
        """完整构建视频合成管线"""
        pipeline = Gst.Pipeline.new(self._name)
        self._intersrcs = []
        
        # 创建 compositor（force-live 只能在构造函数中设置）
        self._compositor = Gst.ElementFactory.make_with_properties(
            "compositor",
            ["name", "background", "force-live"],
            [f"{self._name}_compositor", 1, True]
        )
        pipeline.add(self._compositor)
        
        # 为每个 channel 创建 intersrc -> videoconvert -> videoscale -> compositor
        for i in range(self._num_channels):
            intersrc = Gst.ElementFactory.make("intersrc", f"{self._name}_ch{i}_intersrc")
            self._intersrcs.append(intersrc)
            
            # 如果 _channel_sources 中有配置，则应用（start() 前设置或重建场景）
            if i in self._channel_sources:
                producer_name = self._channel_sources[i]
                intersrc.set_property("producer-name", producer_name)
                self._logger.info(f"Channel {i} set to '{producer_name}' (from _channel_sources)")
            
            convert = Gst.ElementFactory.make("videoconvert", f"{self._name}_ch{i}_convert")
            scale = Gst.ElementFactory.make("videoscale", f"{self._name}_ch{i}_scale")

            for elem in [intersrc, convert, scale]:
                pipeline.add(elem)

            intersrc.link(convert)
            convert.link(scale)

            # 连接到 compositor 请求 pad
            comp_pad = self._compositor.request_pad_simple(f"sink_{i}")
            src_pad = scale.get_static_pad("src")
            src_pad.link(comp_pad)

        # 恢复之前保存的 channel 布局配置
        for channel_index, layout in self._channel_layouts.items():
            if 0 <= channel_index < self._num_channels:
                pads = list(self._compositor.sinkpads)
                if channel_index < len(pads):
                    pad = pads[channel_index]
                    for key, value in layout.items():
                        try:
                            pad.set_property(key, value)
                        except Exception as e:
                            self._logger.warning(f"Failed to restore pad property {key}={value}: {e}")
        
        # compositor 输出 -> videoconvert -> capsfilter -> intersink
        out_convert = Gst.ElementFactory.make("videoconvert", f"{self._name}_out_convert")
        out_caps = Gst.ElementFactory.make("capsfilter", f"{self._name}_out_caps")
        if self._output_caps:
            caps = make_video_caps(
                width=self._output_caps.get("width"),
                height=self._output_caps.get("height"),
                framerate=self._output_caps.get("framerate")
            )
            out_caps.set_property("caps", caps)
        
        intersink = Gst.ElementFactory.make("intersink", f"{self._name}_output_intersink")
        intersink.set_property("producer-name", self.output_channel)
        
        for elem in [out_convert, out_caps, intersink]:
            pipeline.add(elem)
        
        self._compositor.link(out_convert)
        out_convert.link(out_caps)
        out_caps.link(intersink)
        
        return pipeline

    def set_channel_layout(self, channel_index: int, layout: dict):
        """设置 channel 的布局参数

        通过 compositor 的 sink pad 属性设置（如视频合成时的 xpos/ypos/width/height/zorder/alpha）。
        可在 start() 前或后调用：
        - start() 前：仅保存配置，在 _build() 时应用
        - start() 后：保存配置并动态修改运行中的 pad 属性

        Args:
            channel_index: channel 索引 (0 ~ num_channels-1)
            layout: 布局参数字典

        Raises:
            IndexError: channel_index 超出范围
        """
        if channel_index < 0 or channel_index >= self._num_channels:
            raise IndexError(f"Channel index {channel_index} out of range")

        # 保存配置（用于重建时恢复或 start() 前设置）
        if channel_index in self._channel_layouts:
            self._channel_layouts[channel_index].update(layout)
        else:
            self._channel_layouts[channel_index] = layout.copy()

        # 如果管线已构建，动态应用到 pad
        if self._compositor:
            pads = list(self._compositor.sinkpads)
            if channel_index < len(pads):
                pad = pads[channel_index]
                for key, value in layout.items():
                    try:
                        pad.set_property(key, value)
                    except Exception as e:
                        self._logger.warning(f"Failed to set pad property {key}={value}: {e}")
            else:
                self._logger.error(f"Cannot find pad for channel {channel_index}")