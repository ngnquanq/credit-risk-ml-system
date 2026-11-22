"""E15 regression: a dead warehouse must not stall document checks or submissions.

Locally (no ClickHouse) every case view leaked a thread forever: the warehouse pool was left
half-built after the first failed connection, later borrows blocked, and once the default thread
pool was full the document check of POST /applications waited forever.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from infrastructure.external import dwh_client_ch
from infrastructure.storage.documents import DocumentStore


@pytest.fixture
def fresh_pool(monkeypatch):
    monkeypatch.setattr(dwh_client_ch, "_pool", None)
    return monkeypatch


def test_failed_warehouse_connection_leaves_no_half_built_pool(fresh_pool):
    calls = []

    def refuse(**kwargs):
        calls.append(kwargs)
        raise ConnectionRefusedError("warehouse down")

    fresh_pool.setattr(dwh_client_ch.clickhouse_connect, "get_client", refuse)
    for _ in range(2):
        with pytest.raises(ConnectionRefusedError):
            dwh_client_ch._query("SELECT 1")
    assert dwh_client_ch._pool is None  # the second call tried again instead of waiting forever
    assert calls[0]["connect_timeout"] > 0 and calls[0]["send_receive_timeout"] > 0


def test_borrowing_from_an_exhausted_pool_times_out(fresh_pool):
    import queue

    fresh_pool.setattr(dwh_client_ch, "_pool", queue.Queue())
    fresh_pool.setattr(dwh_client_ch, "BORROW_TIMEOUT_S", 0.1)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        dwh_client_ch._query("SELECT 1")
    assert time.monotonic() - started < 2


class _Client:
    def stat_object(self, bucket, key):
        return object()


async def test_document_checks_do_not_need_the_default_thread_pool():
    loop = asyncio.get_running_loop()
    stuck = threading.Event()
    default = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(default)
    blocker = loop.run_in_executor(None, stuck.wait)  # the only default worker is now busy
    try:
        store = DocumentStore(_Client(), "loan-documents", "http://storage.test", timedelta(minutes=5))
        assert await asyncio.wait_for(store.exists("k"), timeout=2) is True
    finally:
        stuck.set()
        await blocker
        default.shutdown()


async def test_warehouse_calls_do_not_use_the_default_thread_pool():
    loop = asyncio.get_running_loop()
    stuck = threading.Event()
    default = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(default)
    blocker = loop.run_in_executor(None, stuck.wait)
    try:
        assert await asyncio.wait_for(dwh_client_ch.run(lambda: 42), timeout=2) == 42
    finally:
        stuck.set()
        await blocker
        default.shutdown()
