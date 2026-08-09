# TradingView MCP — setup and what we emit

Status: **not connected in this environment.** The compiler produces and
validates payloads, but nothing has been dispatched to a live chart yet.

## Why this document exists

The compiler was written before the server's API was checked, and it emitted
four shapes that do not exist: `horizontal_ray`, `path`, `long_position` and
`short_position`. Those payloads passed local validation and would have drawn
**nothing** — the run reports success and the chart stays empty, which is
worse than an error because it looks like it worked.

`SUPPORTED_SHAPES` now mirrors the server exactly and
`_assert_server_can_draw` refuses anything outside it, so that class of
failure cannot return silently.

## The server

[tradesdontlie/tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp)
— drives TradingView Desktop over the Chrome DevTools Protocol and exposes
chart reading, drawing, replay and screenshot tools.

### Prerequisites

- TradingView **Desktop** app with a paid subscription
- Node.js 18+
- TradingView launched with remote debugging enabled

### Install

```bash
git clone https://github.com/tradesdontlie/tradingview-mcp.git
cd tradingview-mcp
npm install
```

### Connect to Claude Code

Add to `~/.claude/.mcp.json` (or the project's `.mcp.json`):

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "node",
      "args": ["/absolute/path/to/tradingview-mcp/src/server.js"]
    }
  }
}
```

### Launch TradingView with debugging on

```bash
./scripts/launch_tv_debug_mac.sh
```

Then confirm the connection by asking for `tv_health_check`. Nothing below
works until that passes.

## The drawing API

One tool, `draw_shape`, accepting exactly four shapes:

| Shape | Used for |
|---|---|
| `rectangle` | order blocks, FVGs, HTF zones, dealing ranges |
| `horizontal_line` | liquidity levels, EQH/EQL, protected highs and lows |
| `trend_line` | BOS and CHoCH, drawn from the broken swing to the breaking candle |
| `text` | short labels |

Companions: `draw_list`, `draw_remove_one`, `draw_clear`. **Clear before
re-annotating**, or drawings stack on every run.

## How our concepts map

Most map straight through. Three have no native shape and are decomposed
rather than dropped:

| Concept | Emitted as |
|---|---|
| Order block / FVG / HTF zone / dealing range | `rectangle` |
| Liquidity, EQH/EQL, protected level | `horizontal_line` |
| BOS / CHoCH | `trend_line` |
| Conditional path | connected dashed `trend_line` segments |
| Long / short position | two `rectangle`s (risk from entry to stop, reward from entry to target) plus a `text` label |

The position decomposition loses TradingView's own risk/reward arithmetic, so
the compiler computes the figure itself and records it as `risk_reward` on the
payload — a reader can then tell the number came from us rather than the
platform.

## Using it

```python
from smc_desk.rendering.tradingview_hcn_profile import (
    compile_hcn_native_markup, flatten_draw_calls,
)

plan = compile_hcn_native_markup(marks, watch_only=True)
for call in flatten_draw_calls(plan):
    ...  # one draw_shape MCP call per entry
```

`flatten_draw_calls` expands composites, so a caller issues one call per entry
without needing to know which concepts happen to be native.

## Authority

Position tools stay refused while `watch_only=True`, and decomposing a
position into rectangles is **not** a way around that gate — the refusal
happens before compilation. Nothing here creates signal, paper or live
execution authority; it only draws already-certified geometry.

## Visual grammar

Styling comes from `smc_desk/rendering/smc_visual_grammar.py`, shared with the
matplotlib renderer so both produce the same-looking chart from the same
evidence. Internal structure is dashed and light; swing structure is solid and
heavy. That distinction is the first thing an SMC reader uses.
