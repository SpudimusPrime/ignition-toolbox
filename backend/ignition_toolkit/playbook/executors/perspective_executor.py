"""
Perspective FAT testing step handlers

Handles Perspective-specific Factory Acceptance Testing (FAT) operations
including component discovery, test execution, and verification.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ignition_toolkit.browser import BrowserManager
from ignition_toolkit.playbook.exceptions import StepExecutionError
from ignition_toolkit.playbook.executors.base import StepHandler

logger = logging.getLogger(__name__)


class PerspectiveDiscoverPageHandler(StepHandler):
    """Handle perspective.discover_page step - Discover interactive components"""

    def __init__(self, manager: BrowserManager):
        self.manager = manager

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"PerspectiveDiscoverPageHandler.execute() called with params: {params}")
        logger.info(f"Browser manager instance: {self.manager}")

        selector = params.get("selector", "body")
        types = params.get("types", [])
        exclude_selectors = params.get("exclude_selectors", [])

        logger.info(f"Discovery parameters - selector: {selector}, types: {types}, exclude: {exclude_selectors}")

        # Load discovery script
        script_path = Path(__file__).parent.parent.parent / "browser" / "component_discovery.js"
        logger.info(f"Component discovery script path: {script_path}")

        if not script_path.exists():
            logger.error(f"Component discovery script NOT FOUND at: {script_path}")
            raise StepExecutionError(
                "perspective",
                f"Component discovery script not found: {script_path}"
            )

        logger.info("Reading component discovery script...")
        with open(script_path, encoding='utf-8') as f:
            discovery_script = f.read()
        logger.info(f"Discovery script loaded ({len(discovery_script)} characters)")

        logger.info("Getting browser page...")
        page = await self.manager.get_page()
        logger.info(f"Browser page obtained: {page}")

        # Inject discovery script
        logger.info("Injecting discovery script into page...")
        try:
            inject_result = await page.evaluate(discovery_script)
            logger.info(f"Discovery script injected successfully. Result: {inject_result}")
        except Exception as e:
            logger.error(f"Failed to inject discovery script: {e}")
            raise StepExecutionError("perspective", f"Failed to inject discovery script: {e}")

        # Execute discovery
        options = {
            "types": types,
            "excludeSelectors": exclude_selectors
        }

        logger.info(f"Executing discoverPerspectiveComponents with selector='{selector}', options={options}")
        try:
            result = await page.evaluate(
                f"discoverPerspectiveComponents('{selector}', {json.dumps(options)})"
            )
            logger.info(f"Discovery executed. Result: {result}")
        except Exception as e:
            logger.error(f"Failed to execute discovery: {e}")
            raise StepExecutionError("perspective", f"Failed to execute discovery: {e}")

        if not result.get("success"):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Component discovery reported failure: {error_msg}")
            raise StepExecutionError(
                "perspective",
                f"Component discovery failed: {error_msg}"
            )

        component_count = result.get('count', 0)
        logger.info(
            f"Discovered {component_count} components "
            f"(types: {types or 'all'})"
        )

        output = {
            "status": "discovered",
            "count": component_count,
            "inventory": result.get("components", []),
            "timestamp": result.get("timestamp"),
            "root_selector": selector
        }
        logger.info(f"Returning discovery output: count={component_count}, inventory_length={len(output['inventory'])}")
        return output


class PerspectiveExtractMetadataHandler(StepHandler):
    """Handle perspective.extract_component_metadata step - Enrich component metadata"""

    def __init__(self, manager: BrowserManager):
        self.manager = manager

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        components = params.get("components", [])

        if not components:
            logger.warning("No components provided for metadata extraction")
            return {
                "status": "skipped",
                "enriched_inventory": [],
                "count": 0
            }

        # Enrich each component with additional metadata
        enriched = []

        for component in components:
            enriched_component = {
                **component,
                "metadata": {
                    "analyzed_at": datetime.now().isoformat(),
                    "has_label": bool(component.get("label") or component.get("ariaLabel")),
                    "has_id": bool(component.get("id")),
                    "is_perspective_component": bool(component.get("componentPath")),
                    "selector_reliability": self._assess_selector_reliability(component)
                }
            }

            enriched.append(enriched_component)

        logger.info(f"Enriched metadata for {len(enriched)} components")

        return {
            "status": "enriched",
            "enriched_inventory": enriched,
            "count": len(enriched)
        }

    def _assess_selector_reliability(self, component: dict) -> str:
        """Assess reliability of component selectors"""
        if component.get("id"):
            return "high"  # ID is most reliable
        if component.get("componentPath"):
            return "high"  # Perspective component path is reliable
        if component.get("dataAttributes"):
            return "medium"  # Data attributes are fairly reliable
        return "low"  # CSS path only


class PerspectiveExecuteTestManifestHandler(StepHandler):
    """Handle perspective.execute_test_manifest step - Execute test plan"""

    def __init__(self, manager: BrowserManager, parameter_resolver: Any = None):
        self.manager = manager
        self.parameter_resolver = parameter_resolver
        # Injected by PlaybookRunHandler before each execute() call; cleared after.
        self._progress_callback: Any = None

    async def _broadcast(self, live_items: list[dict]) -> None:
        if self._progress_callback:
            try:
                await self._progress_callback(live_items)
            except Exception as e:
                logger.warning(f"Failed to broadcast test manifest progress: {e}")

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        manifest = params.get("manifest", [])
        capture_screenshots = params.get("capture_screenshots", True)
        on_failure = params.get("on_failure", "continue")
        return_to_baseline = params.get("return_to_baseline", True)
        baseline_url = params.get("baseline_url")

        # Guard: if manifest was stored as a raw string try to parse it.
        if isinstance(manifest, str):
            import json as _json
            try:
                manifest = _json.loads(manifest)
            except Exception:
                raise StepExecutionError(
                    "perspective",
                    "manifest parameter must be a list of test items, got a string. "
                    "Use the Form editor's 'Add Test Item' button to build the manifest."
                )

        if not manifest:
            raise StepExecutionError("perspective", "No test manifest provided")

        page = await self.manager.get_page()
        results = []
        live_items: list[dict] = []
        passed = 0
        failed = 0
        skipped = 0

        logger.info(f"Executing test manifest with {len(manifest)} tests")

        for test in manifest:
            component_id = test.get("component_id", "unknown")
            action = test.get("action", "click")
            expected = test.get("expected", "No error")
            started_at = datetime.now().isoformat()

            logger.info(f"Testing component: {component_id} (action: {action})")

            # Evaluate skip_if before running
            skip_if = test.get("skip_if")
            if skip_if and self.parameter_resolver:
                if self.parameter_resolver.resolve_skip_if(skip_if):
                    logger.info(f"Skipping manifest item '{component_id}' — skip_if: {skip_if}")
                    live_items.append({
                        "step_id": component_id,
                        "step_name": f"{action}: {component_id}",
                        "status": "skipped",
                        "started_at": started_at,
                        "completed_at": started_at,
                        "error": None,
                        "output": {"skipped": True, "reason": f"skip_if: {skip_if}"},
                    })
                    await self._broadcast(live_items)
                    skipped += 1
                    results.append({"component_id": component_id, "action": action, "status": "skipped", "started_at": started_at})
                    continue

            # Broadcast item as running before executing
            live_items.append({
                "step_id": component_id,
                "step_name": f"{action}: {component_id}",
                "status": "running",
                "started_at": started_at,
                "completed_at": None,
                "error": None,
                "output": {"expected": expected},
            })
            await self._broadcast(live_items)

            test_result = {
                "component_id": component_id,
                "action": action,
                "expected": expected,
                "started_at": started_at,
            }

            try:
                if action == "click":
                    selector = test.get("selector")
                    if not selector:
                        raise ValueError("No selector provided for click action")
                    await page.click(selector, timeout=5000)
                    await asyncio.sleep(0.5)

                elif action == "fill":
                    selector = test.get("selector")
                    value = test.get("value", "Test")
                    fill_mode = test.get("fill_mode", "type")
                    if not selector:
                        raise ValueError("No selector provided for fill action")
                    await self.manager.fill(selector, value, timeout=5000, fill_mode=fill_mode)

                elif action == "keyboard":
                    key = test.get("key")
                    text = test.get("text")
                    if text:
                        await page.keyboard.type(str(text))
                    elif key:
                        await page.keyboard.press(key)
                    else:
                        raise ValueError("No key or text provided for keyboard action")

                else:
                    raise ValueError(f"Unsupported test action: {action}")

                if capture_screenshots:
                    screenshot_name = test.get("screenshot_name") or f"test_{component_id}_{datetime.now().timestamp()}"
                    screenshot_path = await self.manager.screenshot(screenshot_name)
                    test_result["screenshot"] = str(screenshot_path)

                completed_at = datetime.now().isoformat()
                test_result.update({"status": "passed", "actual": "Action completed successfully", "completed_at": completed_at})
                live_items[-1].update({"status": "completed", "completed_at": completed_at})
                passed += 1

            except Exception as e:
                logger.warning(f"Test failed for {component_id}: {e}")
                completed_at = datetime.now().isoformat()
                test_result.update({"status": "failed", "error": str(e), "actual": f"Error: {e}", "completed_at": completed_at})
                live_items[-1].update({"status": "failed", "error": str(e), "completed_at": completed_at})
                failed += 1

            await self._broadcast(live_items)
            results.append(test_result)

            if test_result["status"] == "failed" and on_failure == "abort":
                break

            if return_to_baseline and baseline_url:
                try:
                    await page.goto(baseline_url, wait_until="networkidle", timeout=10000)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Failed to return to baseline: {e}")

        logger.info(
            f"Test execution complete: {passed} passed, {failed} failed, "
            f"{skipped} skipped (total: {len(results)})"
        )

        return {
            "status": "completed",
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "results": results,
        }


class PerspectiveVerifyNavigationHandler(StepHandler):
    """Handle perspective.verify_navigation step - Verify navigation occurred"""

    def __init__(self, manager: BrowserManager):
        self.manager = manager

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        expected_url_pattern = params.get("expected_url_pattern")
        expected_title_pattern = params.get("expected_title_pattern")
        timeout = params.get("timeout", 5000)

        page = await self.manager.get_page()

        try:
            # Wait for navigation
            await page.wait_for_load_state("networkidle", timeout=timeout)

            current_url = page.url
            current_title = await page.title()

            # Verify URL if pattern provided
            if expected_url_pattern:
                if expected_url_pattern not in current_url:
                    raise StepExecutionError(
                        "perspective",
                        f"URL verification failed. Expected pattern: '{expected_url_pattern}', "
                        f"Actual URL: '{current_url}'"
                    )

            # Verify title if pattern provided
            if expected_title_pattern:
                if expected_title_pattern not in current_title:
                    raise StepExecutionError(
                        "perspective",
                        f"Title verification failed. Expected pattern: '{expected_title_pattern}', "
                        f"Actual title: '{current_title}'"
                    )

            return {
                "status": "verified",
                "url": current_url,
                "title": current_title,
                "message": "Navigation verified successfully"
            }

        except TimeoutError:
            raise StepExecutionError(
                "perspective",
                f"Navigation verification timed out after {timeout}ms"
            )


class PerspectiveVerifyDockHandler(StepHandler):
    """Handle perspective.verify_dock_opened step - Verify dock opened"""

    def __init__(self, manager: BrowserManager):
        self.manager = manager

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        dock_selector = params.get("dock_selector")
        timeout = params.get("timeout", 3000)

        if not dock_selector:
            raise StepExecutionError(
                "perspective",
                "No dock_selector provided"
            )

        page = await self.manager.get_page()

        try:
            # Wait for dock element to appear
            await page.wait_for_selector(dock_selector, timeout=timeout, state="visible")

            # Verify dock is visible
            is_visible = await page.is_visible(dock_selector)

            if not is_visible:
                raise StepExecutionError(
                    "perspective",
                    f"Dock element found but not visible: {dock_selector}"
                )

            return {
                "status": "verified",
                "dock_selector": dock_selector,
                "message": "Dock opened and visible"
            }

        except TimeoutError:
            raise StepExecutionError(
                "perspective",
                f"Dock did not open within {timeout}ms: {dock_selector}"
            )
