import matplotlib
matplotlib.use("Agg")  # Ensure headless mode
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Optional
import os

from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.perception.ontology import Direction, ConfirmationStatus
from smc_desk.rendering.coordinate_transform import CoordinateTransform
from smc_desk.rendering.scene_graph import SceneGraph, VisualObject, PixelGeometry, MarketGeometry, LeaderLineGeometry
from smc_desk.rendering.label_layout import LabelLayoutEngine, LabelLayoutItem

class SMCChartRenderer:
    def __init__(self, renderer_version: str = "2.0.0"):
        self.renderer_version = renderer_version

    def render(
        self,
        df: pd.DataFrame,
        snapshot: PerceptionSnapshot,
        mode: str, # "clean", "live", "audit", "review"
        config: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> Tuple[bytes, SceneGraph, CoordinateTransform]:
        """
        Renders an SMC chart based on the mode and returns the image bytes,
        semantic scene graph, and coordinate transform model.
        """
        n = len(df)
        if n == 0:
            raise ValueError("Dataframe cannot be empty for rendering")

        # Establish price and time bounds
        o = df["open"].to_numpy(float)
        h = df["high"].to_numpy(float)
        l = df["low"].to_numpy(float)
        c = df["close"].to_numpy(float)

        min_p = float(l.min())
        max_p = float(h.max())
        price_range = max_p - min_p if max_p != min_p else 1.0
        
        # 10% vertical margins
        margin = price_range * 0.10
        min_p_visible = Decimal(str(round(min_p - margin, 4)))
        max_p_visible = Decimal(str(round(max_p + margin, 4)))

        # Define Figure
        figsize = config.get("figsize", (18, 9))
        dpi = config.get("dpi", 120)
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        fig.patch.set_facecolor("#0e1117")
        ax.set_facecolor("#0e1117")
        ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.6)
        
        # Plot candles
        up_color = config.get("up_color", "#26a69a")
        dn_color = config.get("dn_color", "#ef5350")
        body_floor = (max_p - min_p) * 1e-3
        
        for i in range(n):
            col = up_color if c[i] >= o[i] else dn_color
            ax.plot([i, i], [l[i], h[i]], color=col, linewidth=0.7, zorder=2)
            lo_b, hi_b = min(o[i], c[i]), max(o[i], c[i])
            ax.add_patch(Rectangle((i - 0.34, lo_b), 0.68, max(hi_b - lo_b, body_floor), color=col, zorder=3, linewidth=0))

        ax.set_xlim(-1, n)
        ax.set_ylim(float(min_p_visible), float(max_p_visible))
        
        if mode == "review":
            # Review mode: stable axes, clean candles, no annotations
            # Let's keep minimal tick styling for axes readability
            ax.tick_params(colors="gray", labelsize=8)
            ax.spines['bottom'].set_color('#2a2e39')
            ax.spines['top'].set_color('#2a2e39')
            ax.spines['left'].set_color('#2a2e39')
            ax.spines['right'].set_color('#2a2e39')
        else:
            ax.axis("off") # Default hidden axes for annotated look

        # Force a draw so window extent and transData are populated
        fig.canvas.draw()
        bbox = ax.get_window_extent()
        chart_w = fig.bbox.width
        chart_h = fig.bbox.height
        
        # Initialize CoordinateTransform
        tick_size = Decimal(str(config.get("tick_size", 0.01)))
        
        visible_start = pd.to_datetime(df.iloc[0]["timestamp"])
        if visible_start.tzinfo is None:
            visible_start = visible_start.tz_localize("UTC")
            
        visible_end = pd.to_datetime(df.iloc[-1]["timestamp"])
        if visible_end.tzinfo is None:
            visible_end = visible_end.tz_localize("UTC")

        transform = CoordinateTransform(
            chart_width_px=chart_w,
            chart_height_px=chart_h,
            plot_left_px=bbox.x0,
            plot_right_px=bbox.x1,
            plot_top_px=chart_h - bbox.y1,
            plot_bottom_px=chart_h - bbox.y0,
            visible_start_time=visible_start,
            visible_end_time=visible_end,
            visible_bar_count=n,
            minimum_visible_price=min_p_visible,
            maximum_visible_price=max_p_visible,
            tick_size=tick_size
        )
        transform.initialize_mapping(df, fig, ax)

        # Build Scene Graph
        scene_graph = SceneGraph(
            scene_graph_id=f"scene_{mode}_{datetime.now(timezone.utc).timestamp()}",
            generated_at=datetime.now(timezone.utc)
        )
        
        # Helper to find index
        def _idx(ts) -> int:
            t = pd.to_datetime(ts)
            if t.tzinfo is None:
                t = t.tz_localize("UTC")
            idx_list = df.index[df['timestamp'] == t]
            if len(idx_list) > 0:
                return idx_list[0]
            # fallback
            return n - 1

        # Render annotations if not clean/review modes
        if mode in ["live", "audit"]:
            # 1. Swings
            # We render local, internal, external
            scales = ["local", "internal", "external"] if mode == "audit" else ["local"]
            for scale in scales:
                if scale in snapshot.swings:
                    for sw in snapshot.swings[scale]:
                        ix = _idx(sw.pivot_time)
                        price = float(sw.price_low if sw.direction == Direction.BULLISH else sw.price_high)
                        col = up_color if sw.direction == Direction.BULLISH else dn_color
                        
                        # Decide marker shape / size
                        marker = "^" if sw.direction == Direction.BULLISH else "v"
                        if sw.evidence.is_external:
                            s = 50
                            alpha = 0.9
                            style_tok = "external_swing"
                        else:
                            s = 20
                            alpha = 0.5
                            style_tok = "local_swing"
                            
                        # Draw marker
                        ax.scatter([ix], [price], s=s, color=col, marker=marker, zorder=4, alpha=alpha)
                        
                        # Add scene graph entry
                        x_px = transform.candle_index_to_x(ix)
                        y_px = transform.price_to_y(Decimal(str(price)))
                        
                        scene_graph.objects.append(VisualObject(
                            visual_object_id=f"{df.iloc[0]['timestamp']}-{scale}-swing-{sw.object_id}::marker",
                            semantic_object_id=sw.object_id,
                            semantic_object_type="swing",
                            shape_type="marker",
                            z_index=4,
                            visibility_status="visible",
                            pixel_geometry=PixelGeometry(x1=x_px, y1=y_px, anchor_x=x_px, anchor_y=y_px),
                            market_geometry=MarketGeometry(
                                start_time=sw.pivot_time,
                                end_time=sw.pivot_time,
                                price_low=sw.price_low,
                                price_high=sw.price_high,
                                pivot_time=sw.pivot_time,
                                source_candle_ids=sw.source_candle_ids
                            ),
                            style_token=style_tok,
                            source_object_hash=hashlib.sha256(sw.object_id.encode()).hexdigest()[:8]
                        ))

            # 2. Fair Value Gaps
            for fvg in snapshot.fvgs:
                # In live mode, only render active/untouched/partially mitigated FVGs.
                # In audit mode, render all.
                is_active = fvg.mitigation_status != "full" and fvg.terminal_reason == "none"
                if mode == "live" and not is_active:
                    # Document omission
                    scene_graph.omitted_objects_report.append({
                        "semantic_object_id": fvg.object_id,
                        "attempted_anchor": None,
                        "collision_objects": [],
                        "decision": "OMITTED_HISTORICAL_FVG"
                    })
                    continue
                    
                ix = _idx(fvg.pivot_time)
                col = up_color if fvg.direction == Direction.BULLISH else dn_color
                low = float(fvg.price_low)
                high = float(fvg.price_high)
                
                # Visual style based on status
                alpha = 0.15
                if fvg.mitigation_status == "full":
                    alpha = 0.05
                    style_tok = "fully_mitigated_fvg"
                else:
                    style_tok = "active_fvg"
                    
                ax.add_patch(Rectangle((ix, low), (n - 1) - ix, high - low, color=col, alpha=alpha, zorder=1, linewidth=0))
                
                # Add scene graph entry
                x1_px = transform.candle_index_to_x(ix)
                x2_px = transform.candle_index_to_x(n - 1)
                y1_px = transform.price_to_y(fvg.price_high)
                y2_px = transform.price_to_y(fvg.price_low)
                
                scene_graph.objects.append(VisualObject(
                    visual_object_id=f"fvg-{fvg.object_id}::box",
                    semantic_object_id=fvg.object_id,
                    semantic_object_type="fvg",
                    shape_type="rectangle",
                    z_index=1,
                    visibility_status="visible",
                    pixel_geometry=PixelGeometry(x1=x1_px, x2=x2_px, y1=y1_px, y2=y2_px),
                    market_geometry=MarketGeometry(
                        start_time=fvg.pivot_time,
                        end_time=df.iloc[-1]["timestamp"],
                        price_low=fvg.price_low,
                        price_high=fvg.price_high,
                        pivot_time=fvg.pivot_time,
                        source_candle_ids=fvg.source_candle_ids
                    ),
                    style_token=style_tok,
                    source_object_hash=hashlib.sha256(fvg.object_id.encode()).hexdigest()[:8]
                ))

            # 3. Structure Breaks & Label Collision Handling
            label_layout_items = []
            
            for brk in snapshot.structure_breaks:
                is_confirmed = brk.confirmation_status == ConfirmationStatus.CONFIRMED
                if mode == "live" and not is_confirmed:
                    # In live mode we might only show confirmed structure events
                    continue
                    
                ix_cand = _idx(brk.candidate_at)
                level = float(brk.evidence.broken_price)
                col = up_color if brk.direction == Direction.BULLISH else dn_color
                
                # Line styling
                label_text = f"{brk.break_type}"
                if not is_confirmed:
                    label_text += " (PROBE)"
                    ls = ":"
                    end_ix = n - 1
                    style_tok = "wick_probe"
                else:
                    ls = "-"
                    end_ix = _idx(brk.confirmed_at)
                    style_tok = "confirmed_break"
                    
                # Draw the broken level line
                ax.plot([ix_cand, end_ix], [level, level], color=col, linestyle=ls, linewidth=1.5, zorder=5)
                
                # Record geometry for line
                x1_px = transform.candle_index_to_x(ix_cand)
                x2_px = transform.candle_index_to_x(end_ix)
                y_px = transform.price_to_y(brk.evidence.broken_price)
                
                scene_graph.objects.append(VisualObject(
                    visual_object_id=f"break-line-{brk.object_id}",
                    semantic_object_id=brk.object_id,
                    semantic_object_type="structure_break",
                    shape_type="horizontal_line",
                    z_index=5,
                    visibility_status="visible",
                    pixel_geometry=PixelGeometry(x1=x1_px, x2=x2_px, y1=y_px, y2=y_px),
                    market_geometry=MarketGeometry(
                        start_time=brk.candidate_at,
                        end_time=brk.confirmed_at or df.iloc[-1]["timestamp"],
                        price_low=brk.evidence.broken_price,
                        price_high=brk.evidence.broken_price,
                        pivot_time=brk.pivot_time,
                        source_candle_ids=brk.source_candle_ids
                    ),
                    style_token=style_tok,
                    source_object_hash=hashlib.sha256(brk.object_id.encode()).hexdigest()[:8]
                ))
                
                # Queue the label for layout engine
                label_layout_items.append(LabelLayoutItem(
                    semantic_id=brk.object_id,
                    text=f" {label_text}",
                    anchor_x=x1_px,
                    anchor_y=y_px,
                    width=len(label_text) * 8.0, # Approximate label width
                    height=12.0
                ))

            # Run label layout engine to solve collisions
            # Bounding box of final candle is at index n-1
            final_c_x = transform.candle_index_to_x(n - 1)
            layout_engine = LabelLayoutEngine(
                plot_left=transform.plot_left_px,
                plot_right=transform.plot_right_px,
                plot_top=transform.plot_top_px,
                plot_bottom=transform.plot_bottom_px,
                final_candle_x=final_c_x
            )
            
            layout_results = layout_engine.layout_labels(label_layout_items)
            scene_graph.omitted_objects_report.extend(layout_engine.unresolved_collisions)
            
            for item in layout_results:
                if item.omitted:
                    # Object omitted, already in report
                    continue
                    
                # Draw label
                col = up_color if "BULLISH" in item.semantic_id or "BOS" in item.text or "CHoCH" in item.text else dn_color
                # Plot in display coordinates via transData.inverted()
                inv = ax.transData.inverted()
                # y is screen y-down, so we convert back to matplotlib display coords
                disp_y = transform.chart_height_px - item.placed_y
                data_coords = inv.transform((item.placed_x, disp_y))
                
                ax.text(data_coords[0], data_coords[1], item.text, color=col, fontsize=8, fontweight="bold", va="center", zorder=9)
                
                # Draw leader line if moved significantly
                leader_geom = None
                if item.has_leader_line:
                    ax.plot([inv.transform((item.anchor_x, 0))[0], data_coords[0]], [inv.transform((0, transform.chart_height_px - item.anchor_y))[1], data_coords[1]], color=col, linestyle=":", linewidth=0.8, zorder=8)
                    leader_geom = LeaderLineGeometry(
                        x1=item.anchor_x,
                        y1=item.anchor_y,
                        x2=item.placed_x,
                        y2=item.placed_y
                    )
                    
                # Add label to scene graph
                scene_graph.objects.append(VisualObject(
                    visual_object_id=f"label-{item.semantic_id}",
                    semantic_object_id=item.semantic_id,
                    semantic_object_type="text_label",
                    shape_type="text_label",
                    z_index=9,
                    visibility_status="visible",
                    pixel_geometry=PixelGeometry(
                        x1=item.placed_x,
                        x2=item.placed_x + item.width,
                        y1=item.placed_y,
                        y2=item.placed_y + item.height,
                        anchor_x=item.anchor_x,
                        anchor_y=item.anchor_y
                    ),
                    market_geometry=MarketGeometry(
                        start_time=transform.x_to_time(item.placed_x),
                        end_time=transform.x_to_time(item.placed_x + item.width),
                        price_low=transform.y_to_price(item.placed_y + item.height),
                        price_high=transform.y_to_price(item.placed_y),
                        source_candle_ids=[]
                    ),
                    style_token="label_text",
                    label_text=item.text,
                    label_anchor="left",
                    leader_line_geometry=leader_geom,
                    source_object_hash=hashlib.sha256(item.semantic_id.encode()).hexdigest()[:8]
                ))

        # Add neutral metadata header
        symbol = config.get("symbol", "BTCUSDT")
        timeframe = config.get("timeframe", "15m")
        header_text = f"{symbol} {timeframe} | {mode.upper()} MODE"
        ax.text(0.01, 0.98, header_text, color="#ececec", transform=ax.transAxes, fontsize=10, fontweight="bold", va="top", ha="left")

        # Save/emit chart
        plt.tight_layout()
        
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            plt.savefig(output_path, dpi=dpi, facecolor="#0e1117", bbox_inches="tight")
            
        # Also return image bytes
        from io import BytesIO
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=dpi, facecolor="#0e1117", bbox_inches="tight")
        plt.close(fig)
        
        image_bytes = buf.getvalue()
        return image_bytes, scene_graph, transform
