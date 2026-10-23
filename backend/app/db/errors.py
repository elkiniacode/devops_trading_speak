"""Trade errors. Their messages are safe to show to users."""


class TradeRejected(ValueError):
    """A trade broke a business rule; str(exc) explains why."""


class InsufficientCashError(TradeRejected):
    """A buy costs more than the available cash."""


class InsufficientSharesError(TradeRejected):
    """A sell asks for more shares than are held."""
