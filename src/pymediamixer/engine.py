"""MixerEngine - 媒体导播编排引擎

统一管理所有 Pipeline 的创建、连接和生命周期。
这是一个可选的便捷封装，用户也可以直接使用三种管线类自行管理。
"""

import logging
from .core.constants import MediaType
from .core.input_pipeline import InputPipeline
from .core.compositing_pipeline import CompositingPipeline
from .core.output_pipeline import OutputPipeline

# 配置类导入（用于 from_config）
from .inputs.videotestsrc_input import VideoTestSrcConfig
from .compositors.video_compositor import VideoCompositorConfig
from .outputs.autovideosink_output import AutoVideoSinkConfig


class MixerEngine:
    """媒体导播编排引擎 - 统一管理所有管线的创建、连接、生命周期"""
    
    def __init__(self):
        self._inputs: dict[str, InputPipeline] = {}
        self._compositors: dict[str, CompositingPipeline] = {}
        self._outputs: dict[str, OutputPipeline] = {}
        self._logger = logging.getLogger("pymediamixer.engine")

    # --- Pipeline 管理 ---
    def add_input(self, input_pipeline: InputPipeline):
        """添加输入管线"""
        self._inputs[input_pipeline.name] = input_pipeline
        self._logger.info(f"Added input: {input_pipeline.name}")

    def add_compositor(self, comp_pipeline: CompositingPipeline):
        """添加合成管线"""
        self._compositors[comp_pipeline.name] = comp_pipeline
        self._logger.info(f"Added compositor: {comp_pipeline.name}")

    def add_output(self, output_pipeline: OutputPipeline):
        """添加输出管线"""
        self._outputs[output_pipeline.name] = output_pipeline
        self._logger.info(f"Added output: {output_pipeline.name}")

    def remove_input(self, name: str):
        """移除输入管线（先停止再移除）"""
        if name in self._inputs:
            self._inputs[name].stop()
            del self._inputs[name]
            self._logger.info(f"Removed input: {name}")

    def remove_compositor(self, name: str):
        """移除合成管线（先停止再移除）"""
        if name in self._compositors:
            self._compositors[name].stop()
            del self._compositors[name]
            self._logger.info(f"Removed compositor: {name}")

    def remove_output(self, name: str):
        """移除输出管线（先停止再移除）"""
        if name in self._outputs:
            self._outputs[name].stop()
            del self._outputs[name]
            self._logger.info(f"Removed output: {name}")

    # --- 连接与切换 ---
    def switch(self, compositor_name: str, channel_index: int, input_name: str):
        """
        将指定合成器的 channel 切换到指定输入。
        自动根据合成器的 media_type 选择输入管线的对应输出端。
        
        Args:
            compositor_name: 合成器名称
            channel_index: channel 索引 (0 ~ num_channels-1)
            input_name: 输入管线名称
            
        Raises:
            KeyError: 如果找不到指定的 compositor 或 input
        """
        comp = self._compositors.get(compositor_name)
        if not comp:
            raise KeyError(f"Compositor '{compositor_name}' not found")
        inp = self._inputs.get(input_name)
        if not inp:
            raise KeyError(f"Input '{input_name}' not found")
        comp.switch_channel(channel_index, inp)

    # --- 生命周期（无顺序限制）---
    def start_all(self):
        """启动所有管线（无特定顺序限制）"""
        for inp in self._inputs.values():
            inp.start()
        for comp in self._compositors.values():
            comp.start()
        for out in self._outputs.values():
            out.start()
        self._logger.info("All pipelines started")

    def stop_all(self):
        """停止所有管线"""
        for out in self._outputs.values():
            out.stop()
        for comp in self._compositors.values():
            comp.stop()
        for inp in self._inputs.values():
            inp.stop()
        self._logger.info("All pipelines stopped")

    def start_input(self, name: str):
        """启动指定的输入管线"""
        if name in self._inputs:
            self._inputs[name].start()

    def stop_input(self, name: str):
        """停止指定的输入管线"""
        if name in self._inputs:
            self._inputs[name].stop()

    def start_compositor(self, name: str):
        """启动指定的合成管线"""
        if name in self._compositors:
            self._compositors[name].start()

    def stop_compositor(self, name: str):
        """停止指定的合成管线"""
        if name in self._compositors:
            self._compositors[name].stop()

    def start_output(self, name: str):
        """启动指定的输出管线"""
        if name in self._outputs:
            self._outputs[name].start()

    def stop_output(self, name: str):
        """停止指定的输出管线"""
        if name in self._outputs:
            self._outputs[name].stop()

    def get_status(self) -> dict:
        """获取所有管线的状态
        
        Returns:
            包含所有管线状态的字典，格式为：
            {
                "inputs": {name: state, ...},
                "compositors": {name: state, ...},
                "outputs": {name: state, ...}
            }
        """
        return {
            "inputs": {name: pipe.get_state() for name, pipe in self._inputs.items()},
            "compositors": {name: pipe.get_state() for name, pipe in self._compositors.items()},
            "outputs": {name: pipe.get_state() for name, pipe in self._outputs.items()},
        }

    def get_input(self, name: str) -> InputPipeline:
        """获取指定名称的输入管线"""
        return self._inputs.get(name)

    def get_compositor(self, name: str) -> CompositingPipeline:
        """获取指定名称的合成管线"""
        return self._compositors.get(name)

    def get_output(self, name: str) -> OutputPipeline:
        """获取指定名称的输出管线"""
        return self._outputs.get(name)

    @property
    def inputs(self) -> dict[str, InputPipeline]:
        """获取所有输入管线（只读副本）"""
        return dict(self._inputs)

    @property
    def compositors(self) -> dict[str, CompositingPipeline]:
        """获取所有合成管线（只读副本）"""
        return dict(self._compositors)

    @property
    def outputs(self) -> dict[str, OutputPipeline]:
        """获取所有输出管线（只读副本）"""
        return dict(self._outputs)

    # --- 便捷工厂 ---
    @classmethod
    def from_config(cls, config: dict) -> "MixerEngine":
        """
        从配置字典创建 MixerEngine。
        
        配置格式与 Pipeline 构建接口保持一致：
        {
            "inputs": [
                {"name": "input0", "type": "videotestsrc",
                 "media_types": ["video"],  # 输出媒体类型列表
                 "config": {"pattern": "smpte", "width": 1920, "height": 1080}}
            ],
            "compositors": [
                {"name": "comp0", "type": "video_compositor",
                 "output_caps": {"width": 1920, "height": 1080, "framerate": "30/1"},
                 "inputs": ["input0", "input1"],  # 输入源名称列表，顺序对应 channel 索引
                 "config": {"channel_layouts": {...}}}  # 可选：子类特有配置
            ],
            "outputs": [
                {"name": "preview", "type": "autovideosink",
                 "sources": {"video": "comp0"}}  # 与 OutputPipeline 的 sources 参数一致
            ]
        }
        
        Args:
            config: 配置字典
            
        Returns:
            MixerEngine: 配置好的引擎实例
            
        Raises:
            ValueError: 未知的管线类型
        """
        engine = cls()
        
        # 创建输入管线
        for input_cfg in config.get("inputs", []):
            input_type = input_cfg["type"]
            if input_type == "videotestsrc":
                # 延迟导入避免循环引用
                from .inputs.videotestsrc_input import VideoTestSrcInput, VideoTestSrcConfig
                cfg = input_cfg.get("config", {})
                # 从配置读取 media_types，默认 ["video"]
                media_types_str = input_cfg.get("media_types", ["video"])
                media_types = []
                for mt_str in media_types_str:
                    if mt_str == "video":
                        media_types.append(MediaType.VIDEO)
                    elif mt_str == "audio":
                        media_types.append(MediaType.AUDIO)
                    else:
                        raise ValueError(f"Unknown media type: {mt_str}")
                # 使用与 Pipeline 构造接口一致的格式
                pipe = VideoTestSrcInput(
                    input_cfg["name"],
                    media_types=media_types,
                    config=VideoTestSrcConfig(**cfg) if cfg else VideoTestSrcConfig()
                )
                engine.add_input(pipe)
            else:
                raise ValueError(f"Unknown input type: {input_type}")
        
        # 创建合成管线
        for comp_cfg in config.get("compositors", []):
            comp_type = comp_cfg["type"]
            if comp_type == "video_compositor":
                # 延迟导入避免循环引用
                from .compositors.video_compositor import VideoCompositor, VideoCompositorConfig
                output_caps = comp_cfg.get("output_caps", {})
                
                # inputs 是输入源名称列表，顺序对应 channel 索引
                input_names = comp_cfg.get("inputs", [])
                inputs: list[InputPipeline | None] = [
                    engine._inputs.get(name) for name in input_names
                ]
                
                # 提取子类特有配置
                cfg = comp_cfg.get("config", {})
                channel_layouts = cfg.get("channel_layouts", {}) if cfg else {}

                # 一步创建 VideoCompositor，使用与 Pipeline 构造接口一致的格式
                pipe = VideoCompositor(
                    comp_cfg["name"],
                    inputs=inputs,
                    output_caps=output_caps,
                    config=VideoCompositorConfig(channel_layouts=channel_layouts)
                )
                engine.add_compositor(pipe)
            else:
                raise ValueError(f"Unknown compositor type: {comp_type}")
        
        # 创建输出管线
        for out_cfg in config.get("outputs", []):
            out_type = out_cfg["type"]
            if out_type == "autovideosink":
                # 延迟导入避免循环引用
                from .outputs.autovideosink_output import AutoVideoSinkOutput, AutoVideoSinkConfig

                # 构建 sources 字典：从配置查找已创建的 compositor
                # 配置格式与 OutputPipeline 的 sources 参数一致
                sources_config = out_cfg.get("sources", {})
                sources: dict[MediaType, CompositingPipeline | None] = {}
                for media_type_str, comp_name in sources_config.items():
                    comp = engine._compositors.get(comp_name)
                    if media_type_str == "video":
                        sources[MediaType.VIDEO] = comp
                    elif media_type_str == "audio":
                        sources[MediaType.AUDIO] = comp

                # 一步创建 AutoVideoSinkOutput，使用与 Pipeline 构造接口一致的格式
                cfg = out_cfg.get("config", {})
                pipe = AutoVideoSinkOutput(
                    out_cfg["name"],
                    sources=sources,
                    config=AutoVideoSinkConfig(**cfg) if cfg else AutoVideoSinkConfig()
                )
                engine.add_output(pipe)
            else:
                raise ValueError(f"Unknown output type: {out_type}")
        
        return engine
