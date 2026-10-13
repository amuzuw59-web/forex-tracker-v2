import asyncio
import unittest

from backend.account_execution_lock import (
    acquire_account_execution_lock,
    release_account_execution_lock,
)


class TestAccountExecutionLock(unittest.IsolatedAsyncioTestCase):

    async def test_same_account_lock_serializes_tasks(self):
        first_lock = await acquire_account_execution_lock(
            "test-account-serial"
        )
        second_acquired = asyncio.Event()

        async def acquire_second():
            lock = await acquire_account_execution_lock(
                "test-account-serial"
            )
            second_acquired.set()
            await release_account_execution_lock(lock)

        task = asyncio.create_task(acquire_second())

        try:
            await asyncio.sleep(0.15)
            self.assertFalse(
                second_acquired.is_set(),
                "Second task acquired the lock before the first released it.",
            )

            await release_account_execution_lock(first_lock)
            first_lock = None

            await asyncio.wait_for(task, timeout=3)
            self.assertTrue(second_acquired.is_set())
        finally:
            if first_lock is not None:
                await release_account_execution_lock(first_lock)

            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_different_accounts_use_different_locks(self):
        first_lock = await acquire_account_execution_lock(
            "test-account-one"
        )
        second_lock = None

        try:
            second_lock = await asyncio.wait_for(
                acquire_account_execution_lock("test-account-two"),
                timeout=3,
            )
            self.assertIsNotNone(second_lock)
        finally:
            if second_lock is not None:
                await release_account_execution_lock(second_lock)
            await release_account_execution_lock(first_lock)

    async def test_empty_account_id_is_rejected(self):
        with self.assertRaises(ValueError):
            await acquire_account_execution_lock(" ")

    async def test_non_string_account_id_is_rejected(self):
        with self.assertRaises(ValueError):
            await acquire_account_execution_lock(None)


if __name__ == "__main__":
    unittest.main()
