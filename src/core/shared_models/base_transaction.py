from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Dict, Any


@dataclass(kw_only=True)
class BaseTransaction:
    amount: float
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Dict[str, Any] = field(default_factory=dict)
