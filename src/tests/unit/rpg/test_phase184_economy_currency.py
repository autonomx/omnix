from app.rpg.economy.currency import (
    add_currency,
    can_afford,
    currency_from_copper,
    currency_to_copper_value,
    format_currency,
    normalize_currency,
    subtract_currency_cost,
)


class TestCurrencyNormalization:
    def test_normalize_currency_from_overflow(self):
        out = normalize_currency({"gold": 1, "silver": 15, "copper": 27})
        assert out == {"gold": 2, "silver": 7, "copper": 7}

    def test_currency_to_copper_value(self):
        assert currency_to_copper_value({"gold": 2, "silver": 3, "copper": 4}) == 234

    def test_currency_from_copper(self):
        assert currency_from_copper(234) == {"gold": 2, "silver": 3, "copper": 4}


class TestCurrencySpend:
    def test_can_afford_with_auto_conversion(self):
        wallet = {"gold": 1, "silver": 0, "copper": 0}
        cost = {"gold": 0, "silver": 9, "copper": 5}
        assert can_afford(wallet, cost) is True

    def test_subtract_currency_cost_auto_converts(self):
        wallet = {"gold": 1, "silver": 0, "copper": 0}
        cost = {"gold": 0, "silver": 9, "copper": 5}
        out = subtract_currency_cost(wallet, cost)
        assert out == {"gold": 0, "silver": 0, "copper": 5}

    def test_subtract_currency_cost_raises_when_insufficient(self):
        wallet = {"gold": 0, "silver": 4, "copper": 0}
        cost = {"gold": 0, "silver": 4, "copper": 1}
        try:
            subtract_currency_cost(wallet, cost)
            assert False, "expected ValueError"
        except ValueError:
            assert True

    def test_add_currency_normalizes_result(self):
        out = add_currency({"gold": 0, "silver": 9, "copper": 9}, {"gold": 0, "silver": 0, "copper": 5})
        assert out == {"gold": 1, "silver": 0, "copper": 4}


class TestCurrencyFormatting:
    def test_format_currency(self):
        assert format_currency({"gold": 2, "silver": 0, "copper": 3}) == "2g 3c"
        assert format_currency({"gold": 0, "silver": 4, "copper": 0}) == "4s"
        assert format_currency({"gold": 0, "silver": 0, "copper": 0}) == "0c"
