import pandas as pd
from smc_desk.synthetic.market_scene_generator import _baseline, _cdl, _df

class AdversarialCaseGenerator:
    def __init__(self):
        pass

    def generate_one_tick_fvg(self, base_price: float = 100.0, seed: int = 42, tick_size: float = 0.05) -> pd.DataFrame:
        """
        Generates an FVG that is exactly 1 tick in size to challenge edge case detectors.
        """
        rows, p = _baseline(base_price, 10, seed)
        # c1
        rows.append(_cdl(p, p * 1.001))
        c1_hi = p * 1.001
        
        # c2 impulse
        p = c1_hi
        rows.append(_cdl(p, p + 10 * tick_size))
        c2_hi = p + 10 * tick_size
        
        # c3 low is exactly 1 tick above c1 high
        c3_lo = c1_hi + tick_size
        rows.append((c3_lo, c3_lo + 2 * tick_size, c3_lo, c3_lo + tick_size))
        
        return _df(rows)

    def generate_spurious_equal_highs(self, base_price: float = 100.0, seed: int = 42, tolerance: float = 0.1) -> pd.DataFrame:
        """
        Generates two peaks that are close but fall just OUTSIDE the equal highs tolerance.
        """
        rows, p = _baseline(base_price, 10, seed)
        level = p * 1.010
        rows.append(_cdl(p, level)) # Peak 1
        
        # Pullback
        p = level
        for f in (0.995, 0.992):
            rows.append(_cdl(p, level * f))
            p = level * f
            
        # Peak 2 is level + 2 * tolerance (clearly outside equal high threshold)
        rows.append(_cdl(p, level + 2 * tolerance))
        
        return _df(rows)
