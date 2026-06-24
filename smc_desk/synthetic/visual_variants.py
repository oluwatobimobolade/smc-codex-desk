from typing import Dict, Any, List

class VisualVariantGenerator:
    def __init__(self):
        pass

    def generate_style_variants(self, base_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generates visual variants of the same chart scene (metamorphic variations).
        - Changes theme (light vs dark)
        - Changes grid lines configuration
        - Changes chart dimensions
        - Changes colors
        """
        variants = []
        themes = ["dark", "light"]
        dpis = [100, 150]
        fig_sizes = [(18, 9), (12, 6)]
        
        for theme in themes:
            for dpi in dpis:
                for size in fig_sizes:
                    config = base_config.copy()
                    config.update({
                        "theme": theme,
                        "dpi": dpi,
                        "figsize": size,
                        "grid_visible": theme == "light"
                    })
                    variants.append(config)
        return variants
