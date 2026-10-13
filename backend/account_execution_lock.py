"""Cross-process account execution lock for a shared local filesystem."""

import asyncio
import fcntl
import hashlib
import tempfile
from pathlib import Path


def _acquire_lock_file(path):
    """Acquire an exclusive file lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = path.open("a", encoding="utf-8")

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return lock_file
    except BaseException:
        lock_file.close()
        raise


def _release_lock_file(lock_file):
    """Release the lock and close its file."""
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


async def acquire_account_execution_lock(account_id):
    """Acquire a lock identified by a hash of the account ID."""
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("A valid account ID is required.")

    digest = hashlib.sha256(account_id.strip().encode("utf-8")).hexdigest()
    path = Path(tempfile.gettempdir()) / (
        f"forex_tracker_account_{digest}.lock"
    )

    acquisition = asyncio.create_task(
        asyncio.to_thread(_acquire_lock_file, path)
    )

    try:
        return await asyncio.shield(acquisition)
    except asyncio.CancelledError:
        # If acquisition is still waiting, wait until its worker finishes,
        # then release any lock it acquired before propagating cancellation.
        try:
            lock_file = await acquisition
        except BaseException:
            pass
        else:
            await asyncio.to_thread(_release_lock_file, lock_file)
        raise


async def release_account_execution_lock(lock_file):
    """Release a previously acquired account lock."""
    if lock_file is not None:
        await asyncio.to_thread(_release_lock_file, lock_file)
