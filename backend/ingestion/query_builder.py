from __future__ import annotations

from dataclasses import dataclass


DEFAULT_RISK_KEYWORDS = ("投诉", "监管", "泄露", "召回", "食品安全", "事故", "欺诈", "停运")


@dataclass(frozen=True)
class MonitorQuery:
    provider: str
    query: str
    language: str | None
    region: str | None
    lookback_minutes: int
    max_items: int


def build_monitor_query(watchlist: dict, provider: str, lookback_minutes: int = 60, max_items: int = 10) -> MonitorQuery:
    names = [watchlist.get("entity_name", ""), *(watchlist.get("aliases") or []), *(watchlist.get("products") or [])]
    risks = watchlist.get("risk_keywords") or list(DEFAULT_RISK_KEYWORDS)
    positives = [item for item in [*names, *(watchlist.get("company_keywords") or []), *risks] if str(item).strip()]
    excludes = [item for item in (watchlist.get("exclude_keywords") or []) if str(item).strip()]
    query = " OR ".join(_quote(item) for item in positives[:20])
    if excludes:
        query = f"({query}) -" + " -".join(_quote(item) for item in excludes[:10])
    return MonitorQuery(provider, query[:500], (watchlist.get("languages") or [None])[0], (watchlist.get("regions") or [None])[0], max(1, min(10080, lookback_minutes)), max(1, min(100, max_items)))


def _quote(value: str) -> str:
    value = str(value).strip().replace('"', "")
    return f'"{value}"' if " " in value else value
