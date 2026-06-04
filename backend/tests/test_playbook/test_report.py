"""
Tests for the report language feature in perspective.execute_test_manifest

Covers: ReportBlock/ReportEntry models, polarity logic, skip-to trigger
conditions, and executor integration with mocked Playwright page.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestReportBlockModel:
    def test_defaults(self):
        from ignition_toolkit.playbook.models import ReportBlock

        rb = ReportBlock(selector=".my-class", result="pass")
        assert rb.selector == ".my-class"
        assert rb.result == "pass"
        assert rb.skip_to is None

    def test_with_skip_to(self):
        from ignition_toolkit.playbook.models import ReportBlock

        rb = ReportBlock(selector=".cls", result="fail", skip_to="end")
        assert rb.skip_to == "end"


class TestReportEntryModel:
    def test_fields(self):
        from ignition_toolkit.playbook.models import ReportEntry

        entry = ReportEntry(
            component_id="comp_1",
            label="State Card Selected",
            selector=".active",
            declared_result="pass",
            actual_result="pass",
            matched=True,
            skip_to_fired=False,
            timestamp="2026-01-01T00:00:00",
        )
        assert entry.matched is True
        assert entry.skip_to_fired is False


class TestReportPolarity:
    """Polarity: result='pass' means found=good; result='fail' means found=bad."""

    def _polarity(self, declared: str, found: bool) -> str:
        if declared == "pass":
            return "pass" if found else "fail"
        return "fail" if found else "pass"

    def test_pass_declared_found(self):
        assert self._polarity("pass", True) == "pass"

    def test_pass_declared_not_found(self):
        assert self._polarity("pass", False) == "fail"

    def test_fail_declared_found(self):
        assert self._polarity("fail", True) == "fail"

    def test_fail_declared_not_found(self):
        """Negative/deletion test: element absent = success."""
        assert self._polarity("fail", False) == "pass"


class TestSkipToTrigger:
    """skip-to fires only when actual_result != declared_result (mismatch)."""

    @pytest.mark.parametrize("declared,actual,should_fire", [
        ("pass", "pass", False),
        ("pass", "fail", True),
        ("fail", "fail", False),
        ("fail", "pass", True),
    ])
    def test_skip_to_trigger(self, declared, actual, should_fire):
        matched = actual == declared
        skip_to_fired = not matched
        assert skip_to_fired == should_fire


class TestExecutorReportBlock:
    """Integration tests for report block evaluation inside execute()."""

    def _make_handler(self):
        from ignition_toolkit.playbook.executors.perspective_executor import (
            PerspectiveExecuteTestManifestHandler,
        )

        manager = MagicMock()
        manager.get_page = AsyncMock()
        manager.screenshot = AsyncMock(return_value="/tmp/shot.png")
        manager.fill = AsyncMock()
        return PerspectiveExecuteTestManifestHandler(manager=manager)

    def _make_page(self, selector_found: bool):
        page = AsyncMock()
        page.click = AsyncMock()
        page.query_selector = AsyncMock(
            return_value=MagicMock() if selector_found else None
        )
        return page

    @pytest.mark.asyncio
    async def test_report_entry_recorded_on_pass(self):
        handler = self._make_handler()
        page = self._make_page(selector_found=True)
        handler.manager.get_page = AsyncMock(return_value=page)

        manifest = [
            {
                "component_id": "c1",
                "action": "click",
                "selector": ".btn",
                "expected": "Button clicked",
                "report": {"selector": ".active", "result": "pass"},
            }
        ]
        result = await handler.execute({"manifest": manifest, "capture_screenshots": False})

        assert "report_entries" in result
        assert len(result["report_entries"]) == 1
        entry = result["report_entries"][0]
        assert entry["declared_result"] == "pass"
        assert entry["actual_result"] == "pass"
        assert entry["matched"] is True
        assert entry["skip_to_fired"] is False

    @pytest.mark.asyncio
    async def test_negative_test_element_absent_records_pass(self):
        """result='fail' + element not found = actual 'pass' (deletion confirmed)."""
        handler = self._make_handler()
        page = self._make_page(selector_found=False)
        handler.manager.get_page = AsyncMock(return_value=page)

        manifest = [
            {
                "component_id": "c1",
                "action": "click",
                "selector": ".btn",
                "expected": "Item deleted",
                "report": {"selector": ".item-row", "result": "fail"},
            }
        ]
        result = await handler.execute({"manifest": manifest, "capture_screenshots": False})

        entry = result["report_entries"][0]
        assert entry["declared_result"] == "fail"
        assert entry["actual_result"] == "pass"
        assert entry["matched"] is True

    @pytest.mark.asyncio
    async def test_skip_to_end_stops_manifest(self):
        handler = self._make_handler()
        page = self._make_page(selector_found=False)  # declared pass, not found → fail → mismatch
        handler.manager.get_page = AsyncMock(return_value=page)

        manifest = [
            {
                "component_id": "c1",
                "action": "click",
                "selector": ".btn",
                "expected": "Popup opens",
                "report": {"selector": ".popup", "result": "pass", "skip-to": "end"},
            },
            {
                "component_id": "c2",
                "action": "click",
                "selector": ".close",
                "expected": "Popup closed",
            },
        ]
        result = await handler.execute({"manifest": manifest, "capture_screenshots": False})

        # c2 should not have been executed
        executed_ids = [r["component_id"] for r in result["results"]]
        assert "c1" in executed_ids
        assert "c2" not in executed_ids
        assert result["report_entries"][0]["skip_to_fired"] is True
        assert result.get("abort_requested") is None

    @pytest.mark.asyncio
    async def test_skip_to_abort_sets_flag(self):
        handler = self._make_handler()
        page = self._make_page(selector_found=False)  # mismatch → skip-to abort fires
        handler.manager.get_page = AsyncMock(return_value=page)

        manifest = [
            {
                "component_id": "c1",
                "action": "click",
                "selector": ".btn",
                "expected": "Popup opens",
                "report": {"selector": ".popup", "result": "pass", "skip-to": "abort"},
            },
        ]
        result = await handler.execute({"manifest": manifest, "capture_screenshots": False})

        assert result.get("abort_requested") is True
        assert "abort_message" in result

    @pytest.mark.asyncio
    async def test_skip_to_component_id_jumps(self):
        """skip-to a named component_id skips intermediate items."""
        call_order = []

        async def mock_click(selector, **kwargs):
            call_order.append(selector)

        handler = self._make_handler()
        page = AsyncMock()
        page.click = AsyncMock(side_effect=mock_click)
        # c1 report: selector not found (mismatch with pass) → skip-to c3
        page.query_selector = AsyncMock(return_value=None)
        handler.manager.get_page = AsyncMock(return_value=page)

        manifest = [
            {
                "component_id": "c1",
                "action": "click",
                "selector": ".btn1",
                "expected": "Step 1",
                "report": {"selector": ".result1", "result": "pass", "skip-to": "c3"},
            },
            {
                "component_id": "c2",
                "action": "click",
                "selector": ".btn2",
                "expected": "Step 2",
            },
            {
                "component_id": "c3",
                "action": "click",
                "selector": ".btn3",
                "expected": "Step 3",
            },
        ]
        result = await handler.execute({"manifest": manifest, "capture_screenshots": False})

        executed_ids = [r["component_id"] for r in result["results"]]
        assert "c1" in executed_ids
        assert "c2" not in executed_ids
        assert "c3" in executed_ids

    @pytest.mark.asyncio
    async def test_no_report_block_produces_no_entries(self):
        handler = self._make_handler()
        page = self._make_page(selector_found=True)
        handler.manager.get_page = AsyncMock(return_value=page)

        manifest = [
            {"component_id": "c1", "action": "click", "selector": ".btn", "expected": "Clicked"},
        ]
        result = await handler.execute({"manifest": manifest, "capture_screenshots": False})

        assert "report_entries" not in result
