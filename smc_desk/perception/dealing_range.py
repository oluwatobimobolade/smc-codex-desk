"""SMC dealing range and premium/discount model."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True)
class DealingRange:
    range_id: str
    timeframe: str
    range_high: Decimal
    range_low: Decimal
    equilibrium_50: Decimal
    premium_zone: tuple[Decimal, Decimal]
    discount_zone: tuple[Decimal, Decimal]
    current_price: Decimal
    price_location: str
    internal_range_liquidity: list[dict[str, Any]]
    external_range_liquidity: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "range_id": self.range_id,
            "timeframe": self.timeframe,
            "range_high": str(self.range_high),
            "range_low": str(self.range_low),
            "equilibrium_50": str(self.equilibrium_50),
            "premium_zone": [str(self.premium_zone[0]), str(self.premium_zone[1])],
            "discount_zone": [str(self.discount_zone[0]), str(self.discount_zone[1])],
            "current_price": str(self.current_price),
            "price_location": self.price_location,
            "internal_range_liquidity": self.internal_range_liquidity,
            "external_range_liquidity": self.external_range_liquidity,
        }


def build_dealing_range(
    *,
    timeframe: str,
    snapshot: Mapping[str, Any],
    current_price: Decimal | str | float,
    protected_high: Decimal | str | float | None = None,
    protected_low: Decimal | str | float | None = None,
    parent_context: Mapping[str, Any] | None = None,
) -> DealingRange | None:
    """Build the active dealing range from the protected external pair.

    Prefer the protected external high/low already confirmed by the structure
    detector. Fall back to the latest external swings only when protected levels
    are missing. Clip the child range to the parent range so a lower timeframe
    cannot claim a wider range than its parent leg.
    """
    external_swings = list((snapshot.get("swings", {}) or {}).get("external", []) or [])

    def _price(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    range_high = _price(protected_high)
    range_low = _price(protected_low)
    high_swing = low_swing = None

    if range_high is None or range_low is None:
        highs = [s for s in external_swings if str(s.get("direction")) == "bearish"]
        lows = [s for s in external_swings if str(s.get("direction")) == "bullish"]
        if not highs or not lows:
            return None
        high_swing = highs[-1]
        low_swing = lows[-1]
        if range_high is None:
            range_high = _price(high_swing.get("price_high"))
        if range_low is None:
            range_low = _price(low_swing.get("price_low"))
    else:
        # Try to attach source swing ids for the protected pair.
        highs = [s for s in external_swings if str(s.get("direction")) == "bearish"]
        lows = [s for s in external_swings if str(s.get("direction")) == "bullish"]
        high_swing = highs[-1] if highs else None
        low_swing = lows[-1] if lows else None

    if range_high is None or range_low is None or range_high <= range_low:
        return None

    # Clip to parent range if available.
    parent_ceiling = _price((parent_context or {}).get("protected_high") or (parent_context or {}).get("external_range_high"))
    parent_floor = _price((parent_context or {}).get("protected_low") or (parent_context or {}).get("external_range_low"))
    if parent_ceiling is not None and parent_floor is not None and parent_ceiling > parent_floor:
        range_high = min(range_high, parent_ceiling)
        range_low = max(range_low, parent_floor)
        if range_high <= range_low:
            return None

    price = _price(current_price)
    if price is None:
        return None
    equilibrium = (range_high + range_low) / Decimal("2")
    price_location = "premium" if price > equilibrium else "discount" if price < equilibrium else "equilibrium"
    range_id = f"{timeframe}:dr:{range_high}:{range_low}"
    return DealingRange(
        range_id=range_id,
        timeframe=timeframe,
        range_high=range_high,
        range_low=range_low,
        equilibrium_50=equilibrium,
        premium_zone=(equilibrium, range_high),
        discount_zone=(range_low, equilibrium),
        current_price=price,
        price_location=price_location,
        internal_range_liquidity=_internal_liquidity(external_swings, range_high, range_low),
        external_range_liquidity=[
            {"side": "buy_side", "price": str(range_high), "source_swing_id": high_swing.get("object_id") if high_swing else None},
            {"side": "sell_side", "price": str(range_low), "source_swing_id": low_swing.get("object_id") if low_swing else None},
        ],
    )


def _internal_liquidity(swings: list[Mapping[str, Any]], range_high: Decimal, range_low: Decimal) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []
    for swing in swings[-12:]:
        direction = str(swing.get("direction"))
        price = Decimal(str(swing.get("price_high") if direction == "bearish" else swing.get("price_low")))
        if range_low < price < range_high:
            levels.append(
                {
                    "side": "buy_side" if direction == "bearish" else "sell_side",
                    "price": str(price),
                    "source_swing_id": swing.get("object_id"),
                }
            )
    return levels
