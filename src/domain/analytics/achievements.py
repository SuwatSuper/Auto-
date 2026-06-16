# Layer 1 — Domain (analytics/achievements)
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class Achievement(StrEnum):
    FIRST_WIN = "FIRST_WIN"
    TEN_WINS = "TEN_WINS"
    HUNDRED_WINS = "HUNDRED_WINS"
    STREAK_5 = "STREAK_5"
    STREAK_10 = "STREAK_10"
    DRAWDOWN_SURVIVED = "DRAWDOWN_SURVIVED"
    PROFITABLE_MONTH = "PROFITABLE_MONTH"


def check_achievements(
    wins: int,
    current_streak: int,
    monthly_pnl: Decimal,
    survived_drawdown: bool,
) -> list[Achievement]:
    earned: list[Achievement] = []
    if wins >= 1:
        earned.append(Achievement.FIRST_WIN)
    if wins >= 10:
        earned.append(Achievement.TEN_WINS)
    if wins >= 100:
        earned.append(Achievement.HUNDRED_WINS)
    if current_streak >= 5:
        earned.append(Achievement.STREAK_5)
    if current_streak >= 10:
        earned.append(Achievement.STREAK_10)
    if survived_drawdown:
        earned.append(Achievement.DRAWDOWN_SURVIVED)
    if monthly_pnl > Decimal("0"):
        earned.append(Achievement.PROFITABLE_MONTH)
    return earned
