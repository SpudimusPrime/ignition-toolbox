"""
Browser step handlers

Handles all browser automation step types using Strategy Pattern.
"""

import logging
from datetime import datetime
from typing import Any

from ignition_toolkit.browser import BrowserManager
from ignition_toolkit.core.timeouts import TimeoutDefaults
from ignition_toolkit.playbook.exceptions import StepExecutionError
from ignition_toolkit.playbook.executors.base import StepHandler

logger = logging.getLogger(__name__)


class BrowserNavigateHandler(StepHandler):
    """Handle browser.navigate step"""

    def __init__(self, manager: BrowserManager):
        self.manager = manager

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        url = params.get("url")
        wait_until = params.get("wait_until", "load")
        await self.manager.navigate(url, wait_until=wait_until)
        return {"url": url, "status": "navigated"}


class BrowserClickHandler(StepHandler):
    """Handle browser.click step"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_ACTION):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("selector")
        timeout = params.get("timeout", self.default_timeout)
        force = params.get("force", False)
        await self.manager.click(selector, timeout=timeout, force=force)
        return {"selector": selector, "status": "clicked", "force": force}


class BrowserFillHandler(StepHandler):
    """Handle browser.fill step"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_ACTION):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("selector")
        value = params.get("value")
        timeout = params.get("timeout", self.default_timeout)
        fill_mode = params.get("fill_mode", "fill")
        await self.manager.fill(selector, value, timeout=timeout, fill_mode=fill_mode)
        return {"selector": selector, "status": "filled", "fill_mode": fill_mode}


class BrowserScreenshotHandler(StepHandler):
    """Handle browser.screenshot step"""

    def __init__(self, manager: BrowserManager):
        self.manager = manager

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", f"screenshot_{datetime.now().timestamp()}")
        full_page = params.get("full_page", False)
        screenshot_path = await self.manager.screenshot(name, full_page=full_page)
        return {"screenshot": str(screenshot_path), "status": "captured"}


class BrowserWaitHandler(StepHandler):
    """Handle browser.wait step"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_ACTION):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("selector")
        timeout = params.get("timeout", self.default_timeout)
        await self.manager.wait_for_selector(selector, timeout=timeout)
        return {"selector": selector, "status": "found"}


class BrowserVerifyHandler(StepHandler):
    """Handle browser.verify step"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_VERIFY):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("selector")
        exists = params.get("exists", True)  # Default: verify element exists
        timeout = params.get("timeout", self.default_timeout)  # Shorter timeout for verification

        try:
            # Try to find the element
            await self.manager.wait_for_selector(selector, timeout=timeout)
            element_found = True
        except TimeoutError:
            element_found = False

        # Check if result matches expectation
        if exists and not element_found:
            raise StepExecutionError(
                "browser",
                f"Verification failed: Expected element '{selector}' to exist, but it was not found",
            )
        elif not exists and element_found:
            raise StepExecutionError(
                "browser",
                f"Verification failed: Expected element '{selector}' to NOT exist, but it was found",
            )

        # Verification passed
        verification_result = "exists" if exists else "does not exist"
        return {
            "selector": selector,
            "exists": element_found,
            "expected": exists,
            "status": "verified",
            "message": f"Element '{selector}' {verification_result} as expected",
        }


class BrowserFileUploadHandler(StepHandler):
    """Handle browser.file_upload step"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_ACTION):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("selector")
        file_path = params.get("file_path")
        timeout = params.get("timeout", self.default_timeout)
        await self.manager.set_input_files(selector, file_path, timeout=timeout)
        return {"selector": selector, "file_path": file_path, "status": "uploaded"}


class BrowserVerifyTextHandler(StepHandler):
    """Handle browser.verify_text step"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_VERIFY):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        import re

        selector = params.get("selector")
        text = params.get("text")
        match_type = params.get("match", "exact")  # exact, contains, regex
        timeout = params.get("timeout", self.default_timeout)

        # Get element handle
        try:
            page = await self.manager.get_page()
            element = await page.wait_for_selector(selector, timeout=timeout)
            if not element:
                raise StepExecutionError(
                    "browser",
                    f"Verification failed: Element '{selector}' not found",
                )

            # Get text content
            actual_text = await element.text_content()
            if actual_text is None:
                actual_text = ""

            # Perform text matching based on match_type
            matches = False
            if match_type == "exact":
                matches = actual_text == text
            elif match_type == "contains":
                matches = text in actual_text
            elif match_type == "regex":
                matches = bool(re.search(text, actual_text))
            else:
                raise StepExecutionError(
                    "browser",
                    f"Invalid match type '{match_type}'. Must be one of: exact, contains, regex",
                )

            if not matches:
                raise StepExecutionError(
                    "browser",
                    f"Text verification failed: Expected text {match_type} match for '{text}', but found '{actual_text}'",
                )

            return {
                "selector": selector,
                "expected_text": text,
                "actual_text": actual_text,
                "match_type": match_type,
                "status": "verified",
                "message": f"Text verification passed: '{actual_text}' {match_type} matches '{text}'",
            }

        except Exception as e:
            if isinstance(e, StepExecutionError):
                raise
            raise StepExecutionError("browser", f"Text verification failed: {str(e)}")


class BrowserVerifyAttributeHandler(StepHandler):
    """Handle browser.verify_attribute step"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_VERIFY):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("selector")
        attribute = params.get("attribute")
        value = params.get("value")
        timeout = params.get("timeout", self.default_timeout)

        # Get element handle
        try:
            page = await self.manager.get_page()
            element = await page.wait_for_selector(selector, timeout=timeout)
            if not element:
                raise StepExecutionError(
                    "browser",
                    f"Verification failed: Element '{selector}' not found",
                )

            # Get attribute value
            actual_value = await element.get_attribute(attribute)

            # Compare attribute value
            if actual_value != value:
                raise StepExecutionError(
                    "browser",
                    f"Attribute verification failed: Expected {attribute}='{value}', but found '{actual_value}'",
                )

            return {
                "selector": selector,
                "attribute": attribute,
                "expected_value": value,
                "actual_value": actual_value,
                "status": "verified",
                "message": f"Attribute verification passed: {attribute}='{actual_value}'",
            }

        except Exception as e:
            if isinstance(e, StepExecutionError):
                raise
            raise StepExecutionError("browser", f"Attribute verification failed: {str(e)}")


class BrowserVerifyStateHandler(StepHandler):
    """Handle browser.verify_state step"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_VERIFY):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("selector")
        state = params.get("state")  # visible, hidden, enabled, disabled
        timeout = params.get("timeout", self.default_timeout)

        # Get element handle
        try:
            page = await self.manager.get_page()

            # Different handling based on state type
            if state == "visible":
                element = await page.wait_for_selector(selector, state="visible", timeout=timeout)
                if not element:
                    raise StepExecutionError(
                        "browser",
                        f"State verification failed: Element '{selector}' is not visible",
                    )

            elif state == "hidden":
                element = await page.wait_for_selector(selector, state="hidden", timeout=timeout)
                if not element:
                    raise StepExecutionError(
                        "browser",
                        f"State verification failed: Element '{selector}' is not hidden",
                    )

            elif state == "enabled":
                element = await page.wait_for_selector(selector, timeout=timeout)
                if not element:
                    raise StepExecutionError(
                        "browser",
                        f"Verification failed: Element '{selector}' not found",
                    )
                is_disabled = await element.is_disabled()
                if is_disabled:
                    raise StepExecutionError(
                        "browser",
                        f"State verification failed: Element '{selector}' is disabled, expected enabled",
                    )

            elif state == "disabled":
                element = await page.wait_for_selector(selector, timeout=timeout)
                if not element:
                    raise StepExecutionError(
                        "browser",
                        f"Verification failed: Element '{selector}' not found",
                    )
                is_disabled = await element.is_disabled()
                if not is_disabled:
                    raise StepExecutionError(
                        "browser",
                        f"State verification failed: Element '{selector}' is enabled, expected disabled",
                    )

            else:
                raise StepExecutionError(
                    "browser",
                    f"Invalid state '{state}'. Must be one of: visible, hidden, enabled, disabled",
                )

            return {
                "selector": selector,
                "expected_state": state,
                "status": "verified",
                "message": f"State verification passed: Element '{selector}' is {state}",
            }

        except Exception as e:
            if isinstance(e, StepExecutionError):
                raise
            raise StepExecutionError("browser", f"State verification failed: {str(e)}")


class BrowserKeyboardHandler(StepHandler):
    """Handle browser.keyboard step - send keyboard input to the page"""

    def __init__(self, manager: BrowserManager):
        self.manager = manager

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        key = params.get("key")
        if not key:
            raise StepExecutionError("browser", "Key parameter is required")

        try:
            await self.manager.press_key(key)
            return {"key": key, "status": "pressed"}
        except Exception as e:
            if isinstance(e, StepExecutionError):
                raise
            raise StepExecutionError("browser", f"Keyboard press failed: {str(e)}")


class BrowserGetTextHandler(StepHandler):
    """Handle browser.get_text step - extract text content from an element"""

    def __init__(self, manager: BrowserManager, default_timeout: int = TimeoutDefaults.BROWSER_ACTION):
        self.manager = manager
        self.default_timeout = default_timeout

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("selector")
        timeout = params.get("timeout", self.default_timeout)

        try:
            page = await self.manager.get_page()
            element = await page.wait_for_selector(selector, timeout=timeout)
            if not element:
                raise StepExecutionError(
                    "browser",
                    f"Element not found: '{selector}'",
                )

            # For input/textarea elements, get the value attribute instead of text content
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            if tag in ("input", "textarea"):
                text = await element.evaluate("el => el.value") or ""
            else:
                text = await element.text_content() or ""

            return {"selector": selector, "text": text.strip(), "status": "extracted"}

        except Exception as e:
            if isinstance(e, StepExecutionError):
                raise
            raise StepExecutionError("browser", f"Text extraction failed: {str(e)}")
