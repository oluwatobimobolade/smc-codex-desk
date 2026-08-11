# TradingView MCP — native annotation contract

Status: the compiler and the installed local MCP share a versioned drawing
contract. Offline compiler and MCP sanitisation tests pass. Live dispatch must
still fail closed unless `draw_capabilities` reports that exact contract from
the already-open, signed-in TradingView Desktop instance.

## Non-negotiable instance rule

Use only the owner's existing signed-in TradingView Desktop instance. Do not
launch TradingView, create another profile, restart the app, or create another
tab/layout merely to obtain MCP control. If the MCP is not already attached,
annotation pauses; SVG or image overlays are not a silent substitute for a
requested native TradingView markup.

The installed server is `/Users/tobimobolade/tools/tradingview-mcp`. It drives
TradingView Desktop through the Chrome DevTools Protocol. The upstream project
is [tradesdontlie/tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp),
with a local versioned multipoint extension used by this Desk.

## Capability handshake

Before drawing, call `draw_capabilities`. The compiler accepts only:

```json
{
  "schema": "tradingview_mcp_drawing_capabilities_v1",
  "server_contract": "local_tradingview_mcp_multipoint_v2",
  "draw_tool": "draw_shape",
  "update_tool": "draw_update",
  "targeted_remove_tool": "draw_remove_one",
  "overrides_encoding": "json_string",
  "options_encoding": "json_string",
  "multipoint": true,
  "shapes": [
    "horizontal_line",
    "horizontal_ray",
    "trend_line",
    "rectangle",
    "text",
    "path"
  ]
}
```

A missing shape, non-multipoint server, or incompatible JSON encoding is an
error before any chart mutation. This prevents a compiler from claiming
success for payloads the connected server cannot draw.

## Native trader-tool mapping

| SMC meaning | Native TradingView object |
|---|---|
| Order block, FVG, HTF zone, dealing range | `rectangle` |
| Liquidity, EQH/EQL, protected level | `horizontal_ray` from the evidence-bound origin |
| BOS / CHoCH travel | `trend_line` from broken swing to confirming candle |
| Conditional scenario | one native multipoint `path` |
| Short annotation | `text` |

The ray retains its origin; a full-width line would make a different temporal
claim. A structure break uses a bounded trend line because the event travelled
between two known candles. A conditional scenario uses one editable native
path, not a chain of unrelated line fragments.

Native long/short-position support has not been live-probed under this
contract. When non-watch markup is explicitly authorised, the compiler uses a
truthful composite of two rectangles plus a label and computes the displayed
risk/reward itself. Watch-only charts reject entry, stop, target and position
objects before compilation.

## Dispatch and cleanup

```python
from smc_desk.rendering.tradingview_hcn_profile import (
    compile_hcn_native_markup,
    flatten_draw_calls,
)

capabilities = ...  # result of draw_capabilities from the attached instance
plan = compile_hcn_native_markup(
    marks,
    watch_only=True,
    server_capabilities=capabilities,
)
for envelope in flatten_draw_calls(plan):
    tool_name = envelope["tool"]
    arguments = envelope["arguments"]
    ...  # dispatch tool_name with arguments and record returned entity_id
```

`flatten_draw_calls` emits schema-correct MCP envelopes. `overrides` and
`options` are JSON strings because that is what the local server accepts.
Semantic metadata stays outside the MCP argument object.

Record every returned `entity_id` under the markup workflow. To re-annotate,
remove only those IDs with `draw_remove_one`, or refine them with `draw_update`.
Never call `draw_clear` as workflow cleanup: it can delete the owner's unrelated
manual analysis. `draw_list` and `draw_get_properties` are read-only inspection
tools, not proof that a drawing belongs to this workflow.

## Visual and authority contract

Styles come from `smc_desk/rendering/smc_visual_grammar.py`, shared with the
static renderer. Internal structure is lighter and dashed; external structure
is heavier and solid; zones are muted; labels are short; and there is at most
one conditional path. This is presentation grammar, not evidence.

Every price and time must already be bound to certified chart evidence. The
compiler does not discover levels, move geometry, select a trade, or create
signal/paper/live authority. Native annotation makes the chart editable and
trader-readable; it does not make the market conclusion correct.
