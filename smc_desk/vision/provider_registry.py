from typing import Dict
from smc_desk.vision.provider_interface import VisionProviderInterface

class ProviderRegistry:
    def __init__(self):
        self._providers: Dict[str, VisionProviderInterface] = {}

    def register(self, name: str, provider: VisionProviderInterface):
        self._providers[name] = provider

    def get(self, name: str) -> VisionProviderInterface:
        if name not in self._providers:
            raise ValueError(f"Provider {name} not registered")
        return self._providers[name]

registry = ProviderRegistry()
