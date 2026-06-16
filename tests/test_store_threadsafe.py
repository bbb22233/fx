"""Store 跨线程安全：连接须可在 threadpool 子线程使用（FastAPI 同步路由场景）。"""

from concurrent.futures import ThreadPoolExecutor

from fx.output.store import Store


def test_store_used_from_worker_thread(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    payload = {"as_of": "2026-06-16T00:00:00+00:00", "lists": {"top": ["BTCUSDT"]}}

    # 在不同于建连接的线程里读写，不应抛 "SQLite objects created in a thread..."
    with ThreadPoolExecutor(max_workers=4) as pool:
        pool.submit(s.save_result, payload).result()
        loaded = pool.submit(s.load_result).result()
        pool.submit(s.add_subscription, "u1", "top").result()
        subs = pool.submit(s.list_subscriptions, "u1").result()

    assert loaded["lists"]["top"] == ["BTCUSDT"]
    assert subs == ["top"]
    s.close()


def test_store_concurrent_writes_serialized(tmp_path):
    """多线程并发写订阅，全部落库且无异常（锁串行化）。"""
    s = Store(str(tmp_path / "t.db"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(s.add_subscription, "u1", f"SYM{i}") for i in range(20)]
        assert all(f.result() for f in futs)
    assert len(s.list_subscriptions("u1")) == 20
    s.close()
