"""tools/market_data.py 단위 테스트.

실제 네트워크 호출을 하지 않는다 — yfinance를 unittest.mock으로 모킹해서
파싱/에러 처리 로직만 검증한다 (CI를 네트워크 의존적으로 만들지 않기 위함).

표준 라이브러리만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_market_data.py
"""

from __future__ import annotations

import os
import sys
import unittest
from decimal import DecimalException
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import market_data  # noqa: E402


class _FakeSeries:
    """yfinance의 Close 컬럼을 흉내내는 최소 스텁 (date -> price)."""

    def __init__(self, data: dict):
        self._data = data

    def items(self):
        return self._data.items()


class _FakeDate:
    def __init__(self, s: str):
        self._s = s

    def strftime(self, _fmt):
        return self._s


class _FakeDataFrame:
    """yfinance.download()의 반환값을 흉내내는 최소 스텁."""

    def __init__(self, close_data: dict, empty: bool = False):
        self.empty = empty
        self._close = _FakeSeries(close_data)

    def __getitem__(self, key):
        assert key == "Close"
        return self._close


class _FakeClose:
    """`.squeeze()`를 지원하는 Close 컬럼 스텁."""

    def __init__(self, data: dict):
        self._data = data

    def squeeze(self):
        return _FakeSeries(self._data)

    def __getitem__(self, key):
        return self


class TestGetQuote(unittest.TestCase):
    @patch("market_data.yf")
    def test_returns_quantized_price(self, mock_yf):
        mock_yf.Ticker.return_value.fast_info = {"lastPrice": 123.4567}
        result = market_data.get_quote("aapl")  # 소문자로 넣어도 대문자로 정규화
        self.assertEqual(result["ticker"], "AAPL")
        self.assertEqual(result["price"], "123.46")
        self.assertIn("as_of", result)

    @patch("market_data.yf")
    def test_missing_price_raises(self, mock_yf):
        mock_yf.Ticker.return_value.fast_info = {"lastPrice": None}
        with self.assertRaises(ValueError):
            market_data.get_quote("FAKE")

    @patch("market_data.yf")
    def test_yfinance_exception_becomes_value_error(self, mock_yf):
        mock_yf.Ticker.side_effect = RuntimeError("network down")
        with self.assertRaises(ValueError):
            market_data.get_quote("AAPL")

    def test_empty_ticker_raises(self):
        with self.assertRaises(ValueError):
            market_data.get_quote("   ")

    @patch("market_data.yf", None)
    def test_yfinance_not_installed_raises(self):
        with self.assertRaises(RuntimeError):
            market_data.get_quote("AAPL")


class TestGetHistory(unittest.TestCase):
    @patch("market_data.yf")
    def test_returns_sorted_quantized_rows(self, mock_yf):
        close_data = {_FakeDate("2023-01-03"): 122.876, _FakeDate("2023-01-04"): 124.144}
        fake_df = MagicMock()
        fake_df.empty = False
        fake_df.__getitem__.return_value = _FakeClose(close_data)
        mock_yf.download.return_value = fake_df

        rows = market_data.get_history("aapl", "2023-01-01", "2023-01-05")
        self.assertEqual(rows[0], {"date": "2023-01-03", "close": "122.88"})
        self.assertEqual(rows[1], {"date": "2023-01-04", "close": "124.14"})

    @patch("market_data.yf")
    def test_nan_close_row_is_skipped_not_raised(self, mock_yf):
        # yfinance가 특정 날짜에 결측치(NaN)를 반환하는 경우 — 예전에는
        # Decimal("NaN").quantize()가 decimal.InvalidOperation으로 죽었다.
        close_data = {
            _FakeDate("2023-01-03"): 122.876,
            _FakeDate("2023-01-04"): float("nan"),
            _FakeDate("2023-01-05"): 124.144,
        }
        fake_df = MagicMock()
        fake_df.empty = False
        fake_df.__getitem__.return_value = _FakeClose(close_data)
        mock_yf.download.return_value = fake_df

        rows = market_data.get_history("aapl", "2023-01-01", "2023-01-06")
        self.assertEqual(rows, [{"date": "2023-01-03", "close": "122.88"}, {"date": "2023-01-05", "close": "124.14"}])

    @patch("market_data.yf")
    def test_infinite_close_row_is_skipped_not_raised(self, mock_yf):
        # NaN과 같은 이유로 +Inf/-Inf도 그대로 두면 Decimal("Infinity").quantize()가
        # decimal.InvalidOperation으로 죽는다 — NaN과 동일하게 결측치로 취급해 건너뛴다.
        close_data = {
            _FakeDate("2023-01-03"): 122.876,
            _FakeDate("2023-01-04"): float("inf"),
            _FakeDate("2023-01-05"): float("-inf"),
            _FakeDate("2023-01-06"): 124.144,
        }
        fake_df = MagicMock()
        fake_df.empty = False
        fake_df.__getitem__.return_value = _FakeClose(close_data)
        mock_yf.download.return_value = fake_df

        rows = market_data.get_history("aapl", "2023-01-01", "2023-01-07")
        self.assertEqual(rows, [{"date": "2023-01-03", "close": "122.88"}, {"date": "2023-01-06", "close": "124.14"}])

    @patch("market_data.yf")
    def test_empty_dataframe_raises(self, mock_yf):
        fake_df = MagicMock()
        fake_df.empty = True
        mock_yf.download.return_value = fake_df
        with self.assertRaises(ValueError):
            market_data.get_history("FAKE", "2023-01-01", "2023-01-05")

    @patch("market_data.yf")
    def test_none_dataframe_raises(self, mock_yf):
        mock_yf.download.return_value = None
        with self.assertRaises(ValueError):
            market_data.get_history("FAKE", "2023-01-01", "2023-01-05")


class TestMainDecimalExceptionHandling(unittest.TestCase):
    @patch("market_data.get_history", side_effect=DecimalException("boom"))
    def test_stray_decimal_exception_is_reported_cleanly_not_raised(self, mock_get_history):
        # get_quote/get_history 자체는 이미 알려진 엣지케이스(NaN/무한대)를 방어하지만,
        # 앞으로 나올 수 있는 예상 못한 Decimal 예외에 대비해 CLI가 DecimalException을
        # 잡아 명확한 "오류: ..." 메시지 + 종료코드 1로 처리하는지(트레이스백으로 죽지
        # 않는지) 확인한다.
        code = market_data.main(["history", "--ticker", "AAPL", "--start", "2024-01-01", "--end", "2024-02-01"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
