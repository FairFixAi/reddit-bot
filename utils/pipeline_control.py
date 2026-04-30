"""Central run and OpenAI budget controls."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from utils.config import (
    OPENAI_ESTIMATED_COST_PER_RECORD_USD,
    OPENAI_RUN_BUDGET_USD,
    OPENAI_WEEKLY_BUDGET_USD,
    RUN_PIPELINE,
)


@dataclass(frozen=True)
class OpenAIBudgetCheck:
    record_count: int
    estimated_cost_usd: float
    weekly_spent_usd: float
    weekly_budget_usd: float


def ensure_pipeline_enabled() -> None:
    """Fail closed unless RUN_PIPELINE=true is explicitly set."""
    if not RUN_PIPELINE:
        raise RuntimeError("RUN_PIPELINE is not true; pipeline execution is disabled.")


def estimate_openai_cost(record_count: int) -> float:
    return round(max(0, record_count) * OPENAI_ESTIMATED_COST_PER_RECORD_USD, 6)


def _openai_budget_key() -> str:
    iso = datetime.now(timezone.utc).isocalendar()
    return f"openai_estimated_spend:{iso.year}-W{iso.week:02d}"


def check_openai_budget(record_count: int) -> OpenAIBudgetCheck:
    """Block before classification if run or weekly thresholds would be exceeded."""
    from data.db import get_job_state_value

    estimated = estimate_openai_cost(record_count)
    if OPENAI_RUN_BUDGET_USD <= 0:
        raise RuntimeError("OPENAI_RUN_BUDGET_USD must be > 0 before OpenAI classification can run.")
    if OPENAI_WEEKLY_BUDGET_USD <= 0:
        raise RuntimeError("OPENAI_WEEKLY_BUDGET_USD must be > 0 before OpenAI classification can run.")
    if estimated > OPENAI_RUN_BUDGET_USD:
        raise RuntimeError(
            f"Estimated OpenAI cost ${estimated:.6f} exceeds per-run budget "
            f"${OPENAI_RUN_BUDGET_USD:.6f}; refusing to run."
        )

    raw_spent = get_job_state_value(_openai_budget_key(), default="0")
    try:
        weekly_spent = float(raw_spent)
    except (TypeError, ValueError):
        weekly_spent = 0.0
    if weekly_spent + estimated > OPENAI_WEEKLY_BUDGET_USD:
        raise RuntimeError(
            f"Estimated weekly OpenAI spend ${weekly_spent + estimated:.6f} would exceed "
            f"weekly budget ${OPENAI_WEEKLY_BUDGET_USD:.6f}; refusing to run."
        )
    return OpenAIBudgetCheck(
        record_count=record_count,
        estimated_cost_usd=estimated,
        weekly_spent_usd=weekly_spent,
        weekly_budget_usd=OPENAI_WEEKLY_BUDGET_USD,
    )


def record_openai_estimated_spend(record_count: int) -> None:
    """Persist estimated spend after successful classifications."""
    from data.db import add_job_state_float

    amount = estimate_openai_cost(record_count)
    if amount > 0:
        add_job_state_float(_openai_budget_key(), amount)
