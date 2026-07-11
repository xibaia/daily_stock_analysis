# -*- coding: utf-8 -*-
"""
Tests for fundamental adapter helpers.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import data_provider.fundamental_adapter as fundamental_adapter_module

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.fundamental_adapter import (
    AkshareFundamentalAdapter,
    _build_dividend_payload,
    _extract_latest_row,
    _parse_dividend_plan_to_per_share,
)


class TestFundamentalAdapter(unittest.TestCase):
    def test_candidate_probe_skips_dataframe_rejected_by_validator(self) -> None:
        adapter = AkshareFundamentalAdapter()
        fake_akshare = SimpleNamespace(
            first=lambda: pd.DataFrame({"股票代码": ["000001"]}),
            second=lambda: pd.DataFrame({"股票代码": ["600519"]}),
        )

        with patch.dict(sys.modules, {"akshare": fake_akshare}):
            frame, source, errors = adapter._call_df_candidates(
                [("first", {}), ("second", {})],
                validator=lambda df: "600519" in df["股票代码"].tolist(),
            )

        self.assertEqual(source, "second")
        self.assertEqual(frame.iloc[0]["股票代码"], "600519")
        self.assertEqual(errors, [])

    def test_fundamental_bundle_uses_supported_earnings_signatures(self) -> None:
        adapter = AkshareFundamentalAdapter()
        calls = []

        def record_candidates(candidates, validator=None):
            calls.append((candidates, validator))
            return None, None, []

        with patch.object(adapter, "_call_df_candidates", side_effect=record_candidates):
            adapter.get_fundamental_bundle("600519")

        forecast_candidates, forecast_validator = calls[1]
        quick_candidates, quick_validator = calls[2]
        top10_candidates, top10_validator = calls[5]

        self.assertEqual(
            forecast_candidates,
            [("stock_yjyg_em", {}), ("stock_yjbb_em", {})],
        )
        self.assertEqual(quick_candidates, [("stock_yjkb_em", {})])
        self.assertNotIn("stock_gdfx_top_10_em", [name for name, _ in top10_candidates])
        self.assertIsNotNone(forecast_validator)
        self.assertIsNotNone(quick_validator)
        self.assertIsNotNone(top10_validator)

    def test_capital_flow_uses_direct_single_stock_history_and_normalizes_units(self) -> None:
        adapter = AkshareFundamentalAdapter()
        flow_frame = pd.DataFrame(
            {
                "日期": [f"2026-06-{day:02d}" for day in range(1, 11)],
                "主力净流入-净额": [f"{day * 100}万" for day in range(1, 11)],
            }
        )

        with patch(
            "data_provider.fundamental_adapter._fetch_eastmoney_stock_fund_flow",
            return_value=flow_frame,
        ) as fetch_flow, patch.object(
            adapter,
            "_call_df_candidates",
            side_effect=AssertionError("market-wide fallback must not run"),
        ):
            payload = adapter.get_capital_flow("300925")

        fetch_flow.assert_called_once_with("300925", "sz")
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["stock_flow"]["main_net_inflow"], 10_000_000.0)
        self.assertEqual(payload["stock_flow"]["inflow_5d"], 40_000_000.0)
        self.assertEqual(payload["stock_flow"]["inflow_10d"], 55_000_000.0)

    def test_capital_flow_direct_request_failure_is_explicit_without_fallback(self) -> None:
        adapter = AkshareFundamentalAdapter()

        with patch(
            "data_provider.fundamental_adapter._fetch_eastmoney_stock_fund_flow",
            side_effect=ConnectionError("upstream closed"),
        ), patch.object(
            adapter,
            "_call_df_candidates",
            side_effect=AssertionError("market-wide fallback must not run"),
        ):
            payload = adapter.get_capital_flow("603602")

        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["stock_flow"], {})
        self.assertIn("eastmoney_stock_fflow:ConnectionError", payload["errors"])

    def test_eastmoney_flow_request_is_single_stock_and_bounded(self) -> None:
        response = unittest.mock.Mock()
        response.json.return_value = {
            "data": {"klines": ["2026-06-01,100,0,0,0,0,0,0,0,0,0,10.0,1.2"]}
        }
        response.raise_for_status.return_value = None

        with patch.object(
            fundamental_adapter_module.requests,
            "get",
            return_value=response,
        ) as request_get:
            frame = fundamental_adapter_module._fetch_eastmoney_stock_fund_flow(
                "600519",
                "sh",
                timeout_seconds=1.25,
            )

        self.assertEqual(frame.iloc[0]["主力净流入-净额"], "100")
        _, kwargs = request_get.call_args
        self.assertEqual(kwargs["timeout"], 1.25)
        self.assertEqual(kwargs["params"]["secid"], "1.600519")
        self.assertEqual(request_get.call_count, 1)

    def test_parse_dividend_plan_to_per_share_supports_cn_patterns(self) -> None:
        self.assertAlmostEqual(_parse_dividend_plan_to_per_share("10派3元(含税)"), 0.3, places=6)
        self.assertAlmostEqual(_parse_dividend_plan_to_per_share("每10股派发2.5元"), 0.25, places=6)
        self.assertAlmostEqual(_parse_dividend_plan_to_per_share("每股派0.8元"), 0.8, places=6)
        self.assertIsNone(_parse_dividend_plan_to_per_share("仅送股，不现金分红"))

    def test_extract_latest_row_returns_none_when_code_mismatch(self) -> None:
        df = pd.DataFrame(
            {
                "股票代码": ["600000", "000001"],
                "值": [1, 2],
            }
        )
        row = _extract_latest_row(df, "600519")
        self.assertIsNone(row)

    def test_extract_latest_row_fallback_when_no_code_column(self) -> None:
        df = pd.DataFrame({"值": [1, 2]})
        row = _extract_latest_row(df, "600519")
        self.assertIsNotNone(row)
        self.assertEqual(row["值"], 1)

    def test_dragon_tiger_no_match_with_code_column_is_ok(self) -> None:
        adapter = AkshareFundamentalAdapter()
        df = pd.DataFrame(
            {
                "股票代码": ["600000"],
                "日期": ["2026-01-01"],
            }
        )
        with patch.object(adapter, "_call_df_candidates", return_value=(df, "stock_lhb_stock_statistic_em", [])):
            result = adapter.get_dragon_tiger_flag("600519")
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["is_on_list"])
        self.assertEqual(result["recent_count"], 0)

    def test_dragon_tiger_match_is_ok(self) -> None:
        adapter = AkshareFundamentalAdapter()
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        df = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "日期": [today],
            }
        )
        with patch.object(adapter, "_call_df_candidates", return_value=(df, "stock_lhb_stock_statistic_em", [])):
            result = adapter.get_dragon_tiger_flag("600519")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["is_on_list"])
        self.assertGreaterEqual(result["recent_count"], 1)

    def test_fundamental_bundle_includes_financial_report_and_dividend_payload(self) -> None:
        adapter = AkshareFundamentalAdapter()
        now = datetime.now()
        within_ttm = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        future_day = (now + timedelta(days=10)).strftime("%Y-%m-%d")
        old_day = (now - timedelta(days=500)).strftime("%Y-%m-%d")
        fin_df = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "报告期": [within_ttm],
                "营业总收入": [1000.0],
                "归母净利润": [300.0],
                "经营活动产生的现金流量净额": [500.0],
                "净资产收益率": [18.2],
                "营业收入同比": [12.0],
                "净利润同比": [9.5],
            }
        )
        forecast_df = pd.DataFrame({"股票代码": ["600519"], "预告": ["预增"]})
        quick_df = pd.DataFrame({"股票代码": ["600519"], "快报": ["快报摘要"]})
        dividend_df = pd.DataFrame(
            {
                "股票代码": ["600519", "600519", "600519", "600519"],
                "除息日": [within_ttm, within_ttm, future_day, old_day],
                "分配方案": ["10派3元(含税)", "10派3元(含税)", "10派5元", "10派1元"],
            }
        )

        with patch.object(
            adapter,
            "_call_df_candidates",
            side_effect=[
                (fin_df, "stock_financial_abstract", []),
                (forecast_df, "stock_yjyg_em", []),
                (quick_df, "stock_yjkb_em", []),
                (dividend_df, "stock_fhps_detail_em", []),
                (None, None, []),
                (None, None, []),
            ],
        ):
            result = adapter.get_fundamental_bundle("600519")

        financial_report = result["earnings"].get("financial_report", {})
        self.assertEqual(financial_report.get("report_date"), within_ttm)
        self.assertEqual(financial_report.get("revenue"), 1000.0)
        self.assertEqual(financial_report.get("net_profit_parent"), 300.0)
        self.assertEqual(financial_report.get("operating_cash_flow"), 500.0)
        self.assertEqual(financial_report.get("roe"), 18.2)

        dividend_payload = result["earnings"].get("dividend", {})
        events = dividend_payload.get("events", [])
        self.assertEqual(len(events), 2)  # duplicate + future day filtered
        self.assertEqual(dividend_payload.get("ttm_event_count"), 1)
        self.assertAlmostEqual(dividend_payload.get("ttm_cash_dividend_per_share"), 0.3, places=6)

    def test_build_dividend_payload_returns_empty_when_code_not_matched(self) -> None:
        now = datetime.now().strftime("%Y-%m-%d")
        df = pd.DataFrame(
            {
                "股票代码": ["000001"],
                "除息日": [now],
                "分配方案": ["10派3元(含税)"],
            }
        )

        payload = _build_dividend_payload(df, stock_code="600519")
        self.assertEqual(payload, {})

    def test_build_dividend_payload_skips_after_tax_plan(self) -> None:
        now = datetime.now().strftime("%Y-%m-%d")
        df = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "除息日": [now],
                "分配方案": ["10派3元(税后)"],
            }
        )

        payload = _build_dividend_payload(df, stock_code="600519")
        self.assertEqual(payload, {})

    def test_build_dividend_payload_ttm_window_boundary(self) -> None:
        now = datetime.now()
        day_365 = (now - timedelta(days=365)).strftime("%Y-%m-%d")
        day_366 = (now - timedelta(days=366)).strftime("%Y-%m-%d")
        df = pd.DataFrame(
            {
                "股票代码": ["600519", "600519"],
                "除息日": [day_365, day_366],
                "分配方案": ["10派3元(含税)", "10派5元(含税)"],
            }
        )

        payload = _build_dividend_payload(df, stock_code="600519")
        self.assertEqual(payload.get("ttm_event_count"), 1)
        self.assertAlmostEqual(payload.get("ttm_cash_dividend_per_share"), 0.3, places=6)


if __name__ == "__main__":
    unittest.main()
