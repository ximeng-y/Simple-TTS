"""TTS 服务接入层。

对外只暴露一个抽象方法 synthesize()，GUI 层只认这一层，
换服务商时新增一个实现类即可，UI 无需改动。
"""

from .base import TTSProvider

__all__ = ["TTSProvider"]
