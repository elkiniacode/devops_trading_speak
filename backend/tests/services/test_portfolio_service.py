from app.services.portfolio import portfolio_view, total_value
from app.services.trading import execute_trade


async def test_fresh_portfolio(ctx):
    view = portfolio_view(ctx)
    assert view == {
        "cash_balance": 10000.0,
        "positions": [],
        "positions_value": 0.0,
        "total_value": 10000.0,
        "total_pnl": 0.0,
        "total_pnl_percent": 0.0,
        "valuation_complete": True,
        "as_of": view["as_of"],
    }
    assert view["as_of"].endswith("Z")


async def test_positions_are_valued_at_cached_prices(ctx):
    await execute_trade(ctx, "MSFT", "buy", 2.5)  # @ 400 -> 1000
    await execute_trade(ctx, "AAPL", "buy", 10)  # @ 100 -> 1000
    ctx.cache.update("AAPL", 101.23)
    ctx.cache.update("MSFT", 390.0)

    view = portfolio_view(ctx)
    assert view["positions"] == [  # sorted by ticker
        {
            "ticker": "AAPL",
            "quantity": 10.0,
            "avg_cost": 100.0,
            "current_price": 101.23,
            "market_value": 1012.3,
            "unrealized_pnl": 12.3,
            "unrealized_pnl_percent": 1.23,
            "stale": False,
        },
        {
            "ticker": "MSFT",
            "quantity": 2.5,
            "avg_cost": 400.0,
            "current_price": 390.0,
            "market_value": 975.0,
            "unrealized_pnl": -25.0,
            "unrealized_pnl_percent": -2.5,
            "stale": False,
        },
    ]
    assert view["cash_balance"] == 8000.0
    assert view["positions_value"] == 1987.3
    assert view["total_value"] == 9987.3
    assert view["total_pnl"] == -12.7
    assert view["total_pnl_percent"] == -0.13
    assert view["valuation_complete"] is True
    assert total_value(ctx) == 9987.3


async def test_never_priced_position_counts_at_average_cost(ctx):
    await execute_trade(ctx, "AAPL", "buy", 10)
    ctx.cache.remove("AAPL")
    view = portfolio_view(ctx)
    assert view["positions"][0] == {
        "ticker": "AAPL",
        "quantity": 10.0,
        "avg_cost": 100.0,
        "current_price": None,
        "market_value": None,
        "unrealized_pnl": None,
        "unrealized_pnl_percent": None,
        "stale": False,
    }
    assert view["total_value"] == 10000.0
    assert view["valuation_complete"] is False


async def test_old_price_is_used_but_flagged_stale(ctx):
    await execute_trade(ctx, "AAPL", "buy", 10)
    ctx.cache.update("AAPL", 120.0)
    ctx.market.quote_age = -1
    view = portfolio_view(ctx)
    assert view["positions"][0]["stale"] is True
    assert view["positions"][0]["current_price"] == 120.0
    assert view["total_value"] == 10200.0
    assert view["valuation_complete"] is True
