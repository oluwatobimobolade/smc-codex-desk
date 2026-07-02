import asyncio
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class KimiWebBridge:
    """
    KimiWebBridge captures clean, headless screenshots of external charts
    (e.g., TradingView or Binance). This is used to feed the Vision lens
    with objective, external visual representations of the market.
    """
    def __init__(self, headless: bool = True, default_timeout: int = 15000):
        self.headless = headless
        self.default_timeout = default_timeout

    async def _capture_async(self, url: str, theme: str = "dark", capture_options: Optional[Dict[str, Any]] = None) -> bytes:
        from playwright.async_api import async_playwright
        
        opts = capture_options or {}
        
        async with async_playwright() as p:
            # Prefer chromium for chart rendering fidelity
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                color_scheme=theme,
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()
            
            logger.info(f"KimiWebBridge navigating to {url}")
            await page.goto(url, timeout=self.default_timeout, wait_until="networkidle")
            
            # Wait for any specific chart elements if needed, or just let networkidle suffice
            # In a real tradingview link, we might wait for the canvas:
            # await page.wait_for_selector('canvas', timeout=self.default_timeout)
            
            # Additional logic can be injected here for theme or crop modifiers
            # E.g. hiding UI overlays if a selector is provided
            hide_selectors = opts.get("hide_selectors", [])
            for selector in hide_selectors:
                try:
                    await page.evaluate(f"document.querySelectorAll('{selector}').forEach(el => el.style.display = 'none');")
                except Exception as e:
                    logger.debug(f"Failed to hide selector {selector}: {e}")
            
            # Take screenshot
            clip = opts.get("clip") # Format: {"x": 0, "y": 0, "width": 1920, "height": 1080}
            screenshot_bytes = await page.screenshot(type="png", clip=clip)
            
            await browser.close()
            return screenshot_bytes

    def capture_chart(self, url: str, theme: str = "dark", capture_options: Optional[Dict[str, Any]] = None) -> bytes:
        """
        Synchronous wrapper for the async playwright capture.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're inside a running loop, create a new thread or use nest_asyncio. 
                # For simplicity here, we'll try running directly if safe, or raise.
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self._capture_async(url, theme, capture_options))
            else:
                return loop.run_until_complete(self._capture_async(url, theme, capture_options))
        except RuntimeError:
            # No current event loop
            return asyncio.run(self._capture_async(url, theme, capture_options))

