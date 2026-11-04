"""Build the agent stack (router, decision service, event bus, orchestrator) from settings."""

from __future__ import annotations

from typing import Any

from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.tools import ToolContext
from app.config import Settings
from app.decision.base import DecisionLog, DecisionProvider, DecisionService, FakeDecisionProvider, LLMDecisionProvider
from app.llm.router import LLMRouter, build_router


def build_decisions(settings: Settings, router: LLMRouter) -> DecisionService:
    provider: DecisionProvider = (
        FakeDecisionProvider() if settings.decision_provider == "fake" else LLMDecisionProvider(router)
    )
    log = DecisionLog(settings.workspace_data_dir() / "decision_log.jsonl")
    return DecisionService(provider, log, min_confidence=settings.decision_min_confidence)


def build_orchestrator(
    settings: Settings,
    finance: Any,
    vault: Any,
    *,
    bus: EventBus | None = None,
    router: LLMRouter | None = None,
    decisions: DecisionService | None = None,
) -> AgentOrchestrator:
    router = router or build_router(settings)
    return AgentOrchestrator(
        router,
        decisions or build_decisions(settings, router),
        bus or EventBus(),
        lambda agent_id: ToolContext(finance=finance, vault=vault, agent_id=agent_id),
        approval_policy=settings.team_approval,
        approval_timeout_s=settings.team_approval_timeout_s,
        max_local=settings.max_local_agents,
        max_cloud=settings.max_cloud_agents,
        max_steps=settings.agent_max_steps,
    )
