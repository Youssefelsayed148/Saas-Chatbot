"""PLACEHOLDER quota plans. Limits are configuration, not billing promises."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    bots: int
    seats: int
    pages_per_bot: int
    upload_file_mb: int
    monthly_messages: int
    contacts: int
    channel_connections: int
    sentiment_runs: int


# PLACEHOLDER values approved 2026-10-14. Replace through this table after
# product verification; tokens and currency spend are intentionally uncapped.
PLACEHOLDER_PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": PlanLimits(1, 2, 25, 5, 200, 100, 1, 0),
    "starter": PlanLimits(3, 5, 150, 10, 3_000, 2_000, 1, 1_000),
    "pro": PlanLimits(10, 15, 600, 20, 15_000, 20_000, 3, 5_000),
    "business": PlanLimits(30, 50, 2_000, 25, 60_000, 100_000, 10, 20_000),
}

PLAN_LABELS = tuple(PLACEHOLDER_PLAN_LIMITS)
