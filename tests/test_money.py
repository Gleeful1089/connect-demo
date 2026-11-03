import ast
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

import config
from money import fee, ledger, pricing, vcard
from money.rounding import pct_of, round_cents

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {"llm", "anthropic", "openai", "mapping", "triage", "detect", "evaluation", "pipeline", "search", "buyer"}


def _imports(path):
    names = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            names.add(n.module.split(".")[0])
    return names


# ---- enforcement: money code must not import or call any LLM ----
def test_money_modules_do_not_import_llm_or_model_code():
    for p in list((ROOT / "money").glob("*.py")) + [ROOT / "config.py"]:
        assert not _imports(p) & FORBIDDEN, p


def test_importing_money_does_not_load_llm_at_runtime():
    code = ("import sys; sys.path.insert(0, %r); import money.ledger, money.fee, money.pricing, money.vcard; "
            "bad = [m for m in ('llm','anthropic','openai') if m in sys.modules]; sys.exit(1 if bad else 0)") % str(ROOT)
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_no_float_literals_or_float_calls_in_money():
    for p in (ROOT / "money").glob("*.py"):
        for n in ast.walk(ast.parse(p.read_text())):
            assert not (isinstance(n, ast.Constant) and isinstance(n.value, float)), (p, n.lineno)
            assert not (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "float"), (p, n.lineno)


def test_floats_rejected_at_runtime():
    with pytest.raises(TypeError):
        round_cents(10.5)
    with pytest.raises(TypeError):
        pct_of(1050.0, config.FEE_RATE)
    with pytest.raises(ValueError):
        fee.platform_fee_cents("USD", "completed", 100.5)


# ---- rounding edge cases ----
def test_round_half_up_not_bankers():
    assert round_cents(Decimal("0.5")) == 1
    assert round_cents(Decimal("1.5")) == 2
    assert round_cents(Decimal("2.5")) == 3   # banker's rounding would give 2
    assert round_cents(Decimal("2.4999")) == 2


def test_fee_rounds_half_up_at_boundary():
    # 3% of 10_50x: 1,050,00 cents * 0.03 = 3150 exactly; use a base that lands on .5
    # 16,650 cents * 0.03 = 499.5 -> 500 (half up), floor is 500 so check pct directly
    assert fee.platform_fee_cents("USD", "completed", 16650)["pct_cents"] == 500
    assert pct_of(1050, config.FEE_RATE) == 32      # 31.5 -> 32
    assert pct_of(1049, config.FEE_RATE) == 31      # 31.47 -> 31
    assert pct_of(1, config.FEE_RATE) == 0


# ---- fee: completed, floor, cap ----
def test_completed_stay_three_percent():
    f = fee.platform_fee_cents("USD", "completed", 68000)
    assert f["fee_cents"] == 2040 and f["rule"] == "3% of base"


def test_floor_applies_when_percent_is_below_floor():
    f = fee.platform_fee_cents("USD", "completed", 10000)  # 3% = 300 < 500
    assert f["fee_cents"] == 500 and f["rule"] == "floor applied"


def test_floor_boundary_exact():
    assert fee.platform_fee_cents("USD", "completed", 16667)["fee_cents"] == 500   # 500.01 -> 500
    assert fee.platform_fee_cents("USD", "completed", 16700)["fee_cents"] == 501   # 501


def test_fee_never_exceeds_the_amount_it_is_charged_on():
    f = fee.platform_fee_cents("USD", "completed", 300)
    assert f["fee_cents"] == 300 and f["rule"] == "capped at base"


# ---- fee: cancellation scenarios ----
def test_cancelled_no_charge_fee_is_zero_even_with_floor():
    assert fee.platform_fee_cents("USD", "cancelled_no_charge", 68000)["fee_cents"] == 0


def test_cancelled_with_retained_charge_fee_applies_to_retained_amount():
    f = fee.platform_fee_cents("USD", "cancelled_retained", 68000, retained_cents=34000)
    assert f["base_cents"] == 34000 and f["fee_cents"] == 1020


def test_retained_charge_small_amount_uses_floor_then_cap():
    assert fee.platform_fee_cents("USD", "cancelled_retained", 68000, retained_cents=10000)["fee_cents"] == 500
    assert fee.platform_fee_cents("USD", "cancelled_retained", 68000, retained_cents=400)["fee_cents"] == 400


def test_retained_charge_must_be_valid():
    for bad in (0, 68001):
        with pytest.raises(ValueError):
            fee.platform_fee_cents("USD", "cancelled_retained", 68000, retained_cents=bad)


def test_unknown_scenario_rejected():
    with pytest.raises(ValueError):
        fee.platform_fee_cents("USD", "no_show", 100)


# ---- pricing and FX ----
def test_same_currency_has_no_fx_line():
    q = pricing.quote_stay(34000, 2, "USD", "USD")
    assert [l["kind"] for l in q["lines"]] == ["contracted", "total"] and q["total_cents"] == 68000


def test_cross_currency_itemizes_fx_margin_paid_by_buyer():
    q = pricing.quote_stay(28000, 2, "EUR", "USD")
    kinds = [l["kind"] for l in q["lines"]]
    assert kinds == ["contracted", "converted", "fx_margin", "total"]
    by = {l["kind"]: l["amount_cents"] for l in q["lines"]}
    assert by["contracted"] == 56000
    assert by["converted"] == 61040                 # 56000 * 1.09
    assert by["fx_margin"] == 916                   # 1.5% of 61040 = 915.6 -> 916
    assert q["total_cents"] == 61040 + 916


def test_fx_margin_rounding_edge():
    # 1.5% of 1,000 converted cents = 15 exactly; of 1,033 = 15.495 -> 15; of 1,034 = 15.51 -> 16
    assert pct_of(1033, config.FX_MARGIN) == 15 and pct_of(1034, config.FX_MARGIN) == 16
    assert pct_of(100, config.FX_MARGIN) == 2        # 1.5 -> 2 half up


def test_zero_nights_rejected():
    with pytest.raises(ValueError):
        pricing.quote_stay(100, 0, "USD", "USD")


# ---- virtual card and statements ----
def test_virtual_card_is_single_use_for_exact_total_and_simulated():
    q = pricing.quote_stay(28000, 2, "EUR", "USD")
    card = vcard.issue("BK-1", q["total_cents"], "USD")
    assert card["limit_cents"] == q["total_cents"] and card["single_use"] and "simulated" in card["display"]
    with pytest.raises(ValueError):
        vcard.settle(card, card["limit_cents"] + 1)


def test_statement_completed_stay():
    s = ledger.build_statement("BK-1", 34000, 2, "USD", "USD", "completed")
    assert s["fee"]["fee_cents"] == 2040 and s["hotel_net_payout_cents"] == 68000 - 2040
    assert s["virtual_card"]["captured_cents"] == 68000


def test_statement_cancelled_no_charge():
    s = ledger.build_statement("BK-2", 34000, 2, "USD", "USD", "cancelled_no_charge")
    assert s["fee"]["fee_cents"] == 0 and s["hotel_net_payout_cents"] == 0
    assert s["virtual_card"]["status"] == "VOIDED_SIMULATED" and s["virtual_card"]["captured_cents"] == 0


def test_statement_cancelled_retained_defaults_to_first_night():
    s = ledger.build_statement("BK-3", 34000, 2, "USD", "USD", "cancelled_retained")
    assert s["retained_cents"] == 34000 and s["fee"]["fee_cents"] == 1020
    assert s["virtual_card"]["captured_cents"] == 34000


def test_statement_cross_currency():
    s = ledger.build_statement("BK-4", 28000, 2, "EUR", "USD", "completed")
    assert s["fee"]["fee_cents"] == 1680 and s["hotel_net_payout_cents"] == 56000 - 1680
    led = {e["account"]: e for e in s["ledger"]}
    assert led["buyer_card_captured"]["currency"] == "USD" and led["hotel_net_payout"]["currency"] == "EUR"
    assert led["platform_fx_margin"]["amount_cents"] == 916


def test_statement_cross_currency_retained_converts_only_retained_amount():
    s = ledger.build_statement("BK-5", 28000, 2, "EUR", "USD", "cancelled_retained")
    assert s["buyer_charge"]["total_cents"] == 30520 + 458   # 28000*1.09 = 30520; 1.5% = 457.8 -> 458


def test_ledger_amounts_are_all_integers():
    s = ledger.build_statement("BK-6", 28000, 3, "EUR", "USD", "completed")
    assert all(isinstance(e["amount_cents"], int) for e in s["ledger"])
