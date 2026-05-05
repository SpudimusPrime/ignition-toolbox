"""
Browser manager - Playwright browser automation

Handles browser lifecycle and basic operations with screenshot streaming.
"""

# Import config first to set environment variables before Playwright import
from ignition_toolkit.config import setup_environment

setup_environment()

import asyncio
import base64
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ignition_toolkit.core.paths import get_data_dir, get_screenshots_dir

logger = logging.getLogger(__name__)

# Screenshot streaming configuration
SCREENSHOT_FPS = int(os.getenv("SCREENSHOT_FPS", "2"))  # 2 frames per second
SCREENSHOT_QUALITY = int(os.getenv("SCREENSHOT_QUALITY", "80"))  # JPEG quality 0-100
SCREENSHOT_ENABLED = os.getenv("SCREENSHOT_STREAMING", "true").lower() == "true"
# Screenshot format for saved files: "webp" (smaller, better compression) or "png" (lossless, universal)
SCREENSHOT_FORMAT = os.getenv("SCREENSHOT_FORMAT", "webp").lower()
SCREENSHOT_WEBP_QUALITY = int(os.getenv("SCREENSHOT_WEBP_QUALITY", "85"))  # WebP quality 0-100


class BrowserManager:
    """
    Manage Playwright browser instances

    Example:
        async with BrowserManager() as manager:
            page = await manager.get_page()
            await page.goto("https://example.com")
            await page.screenshot(path="screenshot.png")
    """

    def __init__(
        self,
        headless: bool = False,
        slow_mo: int = 0,
        screenshots_dir: Path | None = None,
        downloads_dir: Path | None = None,
        screenshot_callback: Callable[[str], Awaitable[None]] | None = None,
    ):
        """
        Initialize browser manager

        Args:
            headless: Run browser in headless mode
            slow_mo: Slow down operations by milliseconds
            screenshots_dir: Directory for saving screenshots
            downloads_dir: Directory for saving downloads
            screenshot_callback: Async function to call with base64 screenshot data
        """
        self.headless = headless
        self.slow_mo = slow_mo
        self.screenshots_dir = screenshots_dir or get_screenshots_dir()
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir = downloads_dir or (get_data_dir() / "downloads")
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_callback = screenshot_callback

        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

        # Screenshot streaming state
        self._streaming_task: asyncio.Task | None = None
        self._streaming_active = False
        self._streaming_paused = False

        # Download tracking
        self._active_downloads: list[asyncio.Task] = []

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()

    async def start(self) -> None:
        """Start browser instance"""
        if self._browser is not None:
            logger.warning("Browser already started")
            return

        logger.info("[BROWSER] Starting Playwright browser...")
        logger.debug("Starting Playwright initialization")

        # CRITICAL FIX: Run browser initialization without await to avoid event loop conflicts
        # This prevents deadlocks with FastAPI's event loop
        self._playwright = await async_playwright().start()
        logger.debug("Playwright started")

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )
        logger.debug("Browser launched")

        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
            accept_downloads=True,
        )
        logger.debug("Context created")

        # WORKAROUND: new_page() hangs in FastAPI - create page synchronously then await
        # This avoids the asyncio event loop deadlock issue
        logger.debug("Creating page (working around FastAPI deadlock)")
        page_task = self._context.new_page()
        self._page = await page_task
        logger.debug("Page created successfully")

        # Set up download handler
        self._page.on("download", self._download_started)

        logger.info("[BROWSER] Browser started successfully")

    async def stop(self) -> None:
        """Stop browser instance"""
        # Wait for any pending downloads to complete before closing browser
        await self.await_downloads()

        if self._page:
            await self._page.close()
            self._page = None

        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Browser stopped")

    async def get_page(self) -> Page:
        """
        Get current page

        Returns:
            Playwright Page object

        Raises:
            RuntimeError: If browser not started
        """
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def navigate(self, url: str, wait_until: str = "load") -> None:
        """
        Navigate to URL

        Args:
            url: URL to navigate to
            wait_until: When to consider navigation successful
                       (load, domcontentloaded, networkidle)
        """
        page = await self.get_page()
        logger.info(f"Navigating to: {url}")
        await page.goto(url, wait_until=wait_until)

    async def click(self, selector: str, timeout: int = 30000, force: bool = False, wait_until: str | None = None) -> None:
        """
        Click element

        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds
            force: Force click even if element is behind another element
            wait_until: If set, wait for this load state after clicking (e.g. "networkidle", "load")
        """
        page = await self.get_page()
        logger.info(f"Clicking: {selector} (force={force}, wait_until={wait_until})")
        await page.click(selector, timeout=timeout, force=force)
        if wait_until:
            await page.wait_for_load_state(wait_until, timeout=timeout)

    async def click_at_coordinates(self, x: int, y: int) -> None:
        """
        Click at specific coordinates

        Args:
            x: X coordinate (pixels from left)
            y: Y coordinate (pixels from top)
        """
        page = await self.get_page()
        logger.info(f"Clicking at coordinates: ({x}, {y})")
        await page.mouse.click(x, y)

    async def press_key(self, key: str) -> None:
        """
        Press a key or key combination on the page.

        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'End', 'PageDown', 'Control+A')
        """
        page = await self.get_page()
        logger.info(f"Pressing key: {key}")
        await page.keyboard.press(key)

    async def fill(self, selector: str, value: str, timeout: int = 30000, fill_mode: str = "fill") -> None:
        """
        Fill input field

        Args:
            selector: CSS selector
            value: Value to fill
            timeout: Timeout in milliseconds
            fill_mode: "fill" (default) uses page.fill(); "type" types character-by-character
                       via press_sequentially, which fires React synthetic events correctly
                       and prevents Perspective controlled inputs from reverting on blur
        """
        page = await self.get_page()
        logger.info(f"Filling {selector} with: {value} (mode={fill_mode})")
        if fill_mode == "type":
            locator = page.locator(selector)
            await locator.wait_for(timeout=timeout)

            # Perspective wraps <input> inside a container div — drill down to the
            # actual editable element so key events land in the right place.
            tag = await locator.evaluate("el => el.tagName.toLowerCase()")
            if tag not in ("input", "textarea"):
                inner = locator.locator("input, textarea")
                if await inner.count() > 0:
                    locator = inner.first

            await locator.click()
            await page.keyboard.press("Control+A")
            await locator.press_sequentially(value)
            # Tab triggers blur → Perspective commits the value to its binding system
            # before the next fill step moves focus elsewhere.
            await page.keyboard.press("Tab")
        else:
            await page.fill(selector, value, timeout=timeout)

    async def set_input_files(self, selector: str, file_path: str, timeout: int = 30000) -> None:
        """
        Upload file to file input element

        Args:
            selector: CSS selector for file input
            file_path: Path to file to upload
            timeout: Timeout in milliseconds
        """
        page = await self.get_page()
        logger.info(f"Uploading file {file_path} to {selector}")
        await page.set_input_files(selector, file_path, timeout=timeout)

    async def wait_for_selector(self, selector: str, timeout: int = 30000) -> None:
        """
        Wait for selector to appear

        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds
        """
        page = await self.get_page()
        logger.info(f"Waiting for selector: {selector}")
        await page.wait_for_selector(selector, timeout=timeout)

    async def screenshot(self, name: str, full_page: bool = False, format: str | None = None) -> Path:
        """
        Take screenshot

        Args:
            name: Screenshot name (without extension)
            full_page: Capture full scrollable page
            format: Override default format ("webp" or "png")

        Returns:
            Path to screenshot file
        """
        page = await self.get_page()

        # Determine format (use override or default from config)
        use_format = format.lower() if format else SCREENSHOT_FORMAT

        if use_format == "webp":
            screenshot_path = self.screenshots_dir / f"{name}.webp"
            logger.info(f"Taking WebP screenshot: {screenshot_path}")
            # Playwright supports type="jpeg" for lossy, but we can save as webp via Pillow
            # Actually, let's use JPEG with good quality, then convert to WebP for best compression
            # Simpler approach: Take PNG first, then convert to WebP using Pillow
            import io
            try:
                from PIL import Image
                screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
                img = Image.open(io.BytesIO(screenshot_bytes))
                img.save(str(screenshot_path), "WEBP", quality=SCREENSHOT_WEBP_QUALITY)
            except ImportError:
                # Pillow not available, fall back to PNG
                logger.warning("Pillow not installed, falling back to PNG format")
                screenshot_path = self.screenshots_dir / f"{name}.png"
                await page.screenshot(path=str(screenshot_path), full_page=full_page)
        else:
            # Default to PNG (lossless, universal compatibility)
            screenshot_path = self.screenshots_dir / f"{name}.png"
            logger.info(f"Taking PNG screenshot: {screenshot_path}")
            await page.screenshot(path=str(screenshot_path), full_page=full_page)

        return screenshot_path

    async def get_text(self, selector: str) -> str:
        """
        Get element text content

        Args:
            selector: CSS selector

        Returns:
            Text content
        """
        page = await self.get_page()
        element = await page.query_selector(selector)
        if element is None:
            raise ValueError(f"Element not found: {selector}")
        return await element.text_content() or ""

    async def get_page_html(self) -> str:
        """
        Get full page HTML content

        Returns:
            HTML content as string
        """
        page = await self.get_page()
        return await page.content()

    async def get_screenshot_base64(self) -> str:
        """
        Get screenshot as base64-encoded string

        Returns:
            Base64-encoded PNG screenshot
        """
        page = await self.get_page()
        screenshot_bytes = await page.screenshot(type="png")
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def get_element_screenshot_base64(self, selector: str) -> str:
        """
        Get screenshot of a specific element as base64-encoded string

        Args:
            selector: CSS selector for the element to screenshot

        Returns:
            Base64-encoded PNG screenshot of the element

        Raises:
            ValueError: If element not found
        """
        page = await self.get_page()
        element = await page.query_selector(selector)
        if element is None:
            raise ValueError(f"Element not found for screenshot: {selector}")
        screenshot_bytes = await element.screenshot(type="png")
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def evaluate(self, script: str) -> Any:
        """
        Execute JavaScript

        Args:
            script: JavaScript code

        Returns:
            Script result
        """
        page = await self.get_page()
        return await page.evaluate(script)

    async def start_screenshot_streaming(self) -> None:
        """
        Start streaming screenshots to callback function

        Captures screenshots at configured FPS and sends base64-encoded
        JPEG data to the callback function.
        """
        if not SCREENSHOT_ENABLED:
            logger.info("Screenshot streaming disabled by configuration")
            return

        if not self.screenshot_callback:
            logger.warning("No screenshot callback configured, streaming disabled")
            return

        if self._streaming_task is not None:
            logger.warning("Screenshot streaming already active")
            return

        self._streaming_active = True
        self._streaming_paused = False
        self._streaming_task = asyncio.create_task(self._screenshot_streaming_loop())
        logger.info(f"Screenshot streaming started at {SCREENSHOT_FPS} FPS")

    async def stop_screenshot_streaming(self) -> None:
        """Stop screenshot streaming"""
        if self._streaming_task is None:
            return

        self._streaming_active = False
        self._streaming_task.cancel()

        try:
            await self._streaming_task
        except asyncio.CancelledError:
            pass

        self._streaming_task = None
        logger.info("Screenshot streaming stopped")

    def pause_screenshot_streaming(self) -> None:
        """Pause screenshot streaming (freeze current frame)"""
        self._streaming_paused = True
        logger.info("Screenshot streaming paused")

    def resume_screenshot_streaming(self) -> None:
        """Resume screenshot streaming"""
        self._streaming_paused = False
        logger.info("Screenshot streaming resumed")

    async def _screenshot_streaming_loop(self) -> None:
        """
        Internal loop for capturing and streaming screenshots

        Runs continuously at configured FPS until stopped.
        """
        page = await self.get_page()
        frame_interval = 1.0 / SCREENSHOT_FPS

        logger.info(f"Screenshot streaming loop started (interval: {frame_interval:.3f}s)")

        while self._streaming_active:
            try:
                frame_start = asyncio.get_event_loop().time()

                # Only capture if not paused
                if not self._streaming_paused:
                    # Capture screenshot
                    screenshot_bytes = await page.screenshot(
                        type="jpeg",
                        quality=SCREENSHOT_QUALITY,
                        full_page=False,  # Viewport only for performance
                    )

                    # Encode to base64
                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

                    # Send to callback
                    if self.screenshot_callback:
                        await self.screenshot_callback(screenshot_b64)

                # Calculate sleep time to maintain FPS
                frame_elapsed = asyncio.get_event_loop().time() - frame_start
                sleep_time = max(0, frame_interval - frame_elapsed)

                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                logger.info("Screenshot streaming loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in screenshot streaming: {e}")
                # Continue streaming despite errors
                await asyncio.sleep(frame_interval)

    def _download_started(self, download) -> None:
        """
        Called when download event is fired - creates tracked async task

        Args:
            download: Playwright Download object
        """
        task = asyncio.create_task(self._handle_download(download))
        self._active_downloads.append(task)
        logger.info(f"Download started: {download.suggested_filename}")

    async def await_downloads(self, timeout: float = 30.0) -> None:
        """
        Wait for all active downloads to complete

        Args:
            timeout: Maximum time to wait for downloads in seconds
        """
        if not self._active_downloads:
            return

        logger.info(f"Waiting for {len(self._active_downloads)} download(s) to complete...")

        try:
            await asyncio.wait_for(
                asyncio.gather(*self._active_downloads, return_exceptions=True),
                timeout=timeout
            )
            logger.info("All downloads completed")
        except asyncio.TimeoutError:
            logger.warning(f"Download timeout after {timeout}s - some downloads may not have completed")
        finally:
            # Clear completed tasks
            self._active_downloads.clear()

    async def _handle_download(self, download) -> None:
        """
        Handle download events and save to custom downloads directory

        Args:
            download: Playwright Download object
        """
        try:
            # Get suggested filename
            filename = download.suggested_filename
            save_path = self.downloads_dir / filename

            # Save download to custom location
            await download.save_as(str(save_path))
            logger.info(f"Download saved to: {save_path}")
        except Exception as e:
            logger.error(f"Error saving download: {e}")
