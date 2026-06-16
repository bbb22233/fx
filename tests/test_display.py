"""清单展示层：同币跨所去重（一份干净的去重币清单）。"""

from fx.output.discord_bot.commands import format_scan
from fx.output.serialize import collapse_by_symbol, format_symbol_entry


def _summary(lists, metrics):
    return {"as_of": "2026-06-16T00:00:00+00:00", "lists": lists, "metrics": metrics}


def test_collapse_merges_same_symbol_across_exchanges():
    metrics = {
        "binance:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "binance"},
        "okx:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "okx"},
        "binance:ETH/USDT:USDT": {"symbol": "ETH/USDT:USDT", "exchange": "binance"},
    }
    keys = ["binance:BTC/USDT:USDT", "okx:BTC/USDT:USDT", "binance:ETH/USDT:USDT"]
    entries = collapse_by_symbol(keys, metrics)
    assert entries == [
        {"symbol": "BTC/USDT:USDT", "exchanges": ["binance", "okx"]},
        {"symbol": "ETH/USDT:USDT", "exchanges": ["binance"]},
    ]
    assert format_symbol_entry(entries[0]) == "BTC/USDT:USDT [binance, okx]"
    assert format_symbol_entry(entries[1]) == "ETH/USDT:USDT [binance]"


def test_collapse_single_exchange_is_bare_symbol():
    """单所(exchange=None)退化为裸 symbol，无标签 —— 最干净。"""
    metrics = {"BTCUSDT": {"symbol": "BTCUSDT", "exchange": None}}
    entries = collapse_by_symbol(["BTCUSDT"], metrics)
    assert entries == [{"symbol": "BTCUSDT", "exchanges": [None]}]
    assert format_symbol_entry(entries[0]) == "BTCUSDT"


def test_format_scan_dedup_count_and_text():
    metrics = {
        "binance:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "binance"},
        "okx:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "okx"},
    }
    out = format_scan(_summary({"top": ["binance:BTC/USDT:USDT", "okx:BTC/USDT:USDT"],
                                "bottom": [], "squeeze": [], "watch": []}, metrics))
    # 计数按去重后的币数(1)，不是按 key 数(2)
    assert "【顶部】(1): BTC/USDT:USDT [binance, okx]" in out
