# POI Refinement Repair - 2026-07-02

## Trigger

The SUIUSDT review exposed a POI classification issue:

- `0.7320-0.7348` was being discussed too loosely as a retest pocket.
- The user correctly identified that this was not the order block.
- Review confirmed it was FVG/imbalance, while the nearest actual 15m bullish OB was `0.7383-0.7416` and the cleaner deeper 15m bullish OB was `0.7288-0.7316`.

## Repair

The system now separates:

- Order block authority.
- FVG / imbalance authority.
- Shallow front POI inducement risk.
- Deeper same-leg OB reaction priority.

## Code Changed

- `smc_desk/perception/poi_lifecycle.py`
  - Upgraded selection method to `ranked_active_poi_v3_protected_range_first_deeper_ob_reaction_priority`.
  - Added reaction roles and selection score adjustments.
  - FVG-only zones are secondary unless overlapping an OB.
  - Shallow/front POIs are marked `front_inducement_risk` when a deeper valid same-timeframe OB exists.
  - Deeper OBs are marked `deeper_order_block_reaction_candidate`.

- `smc_desk/engine.py`
  - Added the same deeper-OB reaction adjustment to the older `build_trade_plan` path.
  - Conditions now explicitly warn that FVG-only pockets are secondary and shallow POIs may be inducement.

- `strategies/smc/house_rules.md`
  - Added explicit doctrine on nearest OB vs deeper OB, FVG authority, and inducement in front of the POI.

- `strategies/smc/POI_REFINEMENT_DOCTRINE.md`
  - Added the full doctrine note.

## Tests Added

- Bullish case: deeper 15m OB outranks shallow OB and FVG in front.
- Bearish case: deeper supply outranks nearest shallow supply.
- Legacy engine case: older trade-plan path selects deeper OB instead of closest shallow/FVG pocket.

## Validation

Focused validation passed:

`7 passed in 0.94s`

Full project validation passed after updating the selector-version regression:

`675 passed, 1 skipped in 106.89s`

## Important Boundary

This repair improves POI selection and entry refinement. It does not claim predictive edge. Execution still requires sweep, displacement, confirmation, stop validation, target validation, and R:R validation.
