"""Authentication foundation for the Basirah API layer: JWT access/
refresh tokens, API keys, and password hashing.

Deliberately scoped as a *foundation*, not a full multi-user system --
no User domain model exists in src/domain/models/ yet (only Stock/
PriceBar/MarketSnapshot/FundamentalSnapshot, all reference/market data,
per stock.py's own docstring). Building a full user table, registration
flow, and per-user API key store here would be inventing a feature this
milestone was not asked for ("Authentication foundation", not "user
management"). See jwt_handler.py, password.py, and api_key.py's own
docstrings for what is and is not in scope.
"""
