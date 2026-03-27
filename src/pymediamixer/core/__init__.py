"""Core module - 核心基类和工具"""

from .constants import (
    MediaType,
    DEFAULT_VIDEO_WIDTH,
    DEFAULT_VIDEO_HEIGHT,
    DEFAULT_VIDEO_FRAMERATE,
    DEFAULT_VIDEO_FORMAT,
    DEFAULT_AUDIO_RATE,
    DEFAULT_AUDIO_CHANNELS,
    DEFAULT_AUDIO_FORMAT,
    make_video_caps,
    make_audio_caps,
)
from .clock import apply_clock, get_clock, get_base_time
from .pipeline_base import PipelineBase, PipelineConfig
from .input_pipeline import InputPipeline
from .compositing_pipeline import CompositingPipeline
from .output_pipeline import OutputPipeline

__all__ = [
    # constants
    "MediaType",
    "DEFAULT_VIDEO_WIDTH",
    "DEFAULT_VIDEO_HEIGHT",
    "DEFAULT_VIDEO_FRAMERATE",
    "DEFAULT_VIDEO_FORMAT",
    "DEFAULT_AUDIO_RATE",
    "DEFAULT_AUDIO_CHANNELS",
    "DEFAULT_AUDIO_FORMAT",
    "make_video_caps",
    "make_audio_caps",
    # clock
    "apply_clock",
    "get_clock",
    "get_base_time",
    # pipeline_base
    "PipelineBase",
    "PipelineConfig",
    # input_pipeline
    "InputPipeline",
    # compositing_pipeline
    "CompositingPipeline",
    # output_pipeline
    "OutputPipeline",
]
