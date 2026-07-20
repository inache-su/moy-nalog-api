"""Offline tests for the interactive integration-test runner."""

from unittest.mock import AsyncMock

import pytest

from scripts.integration_test import IntegrationTest


async def test_full_mode_attempts_cleanup_after_unexpected_failure(tmp_path):
    runner = IntegrationTest(tmp_path)
    runner.test_authentication = AsyncMock(return_value=True)
    runner.test_user_profile = AsyncMock(return_value=True)
    runner.test_simple_receipt = AsyncMock(side_effect=RuntimeError("boom"))
    runner.test_cancel_receipts = AsyncMock(return_value=True)

    with pytest.raises(RuntimeError, match="boom"):
        await runner.run(
            auth_method="password",
            username="123456789012",
            password="password",
            test_mode="full",
        )

    runner.test_cancel_receipts.assert_awaited_once()
