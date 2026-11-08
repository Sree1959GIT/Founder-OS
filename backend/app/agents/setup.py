"""Build the agent stack (router, decision service, event bus, orchestrator) from settings."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.tools import ToolContext
from app.config import Settings
from app.conversation.classifier import TurnClassifier
from app.conversation.contexts import GlobalContext
from app.conversation.manager import ConversationManager
from app.decision.base import DecisionLog, DecisionProvider, DecisionService, FakeDecisionProvider, LLMDecisionProvider
from app.decision.jev import JevProvider
from app.decision.laya import LayaProvider
from app.llm.names import name_sources
from app.llm.privacy import NameIndex
from app.llm.router import LLMRouter, build_fast_provider, build_router


def build_decisions(settings: Settings, router: LLMRouter) -> DecisionService:
    """`DECISION_PROVIDER` picks the model. Laya and Jev fall back to the LLM on low confidence or failure (PRD F7)."""
    log = DecisionLog(settings.workspace_data_dir() / "decision_log.jsonl")
    llm = LLMDecisionProvider(router)
    provider: DecisionProvider = llm
    fallback: DecisionProvider | None = None
    if settings.decision_provider == "fake":
        provider = FakeDecisionProvider()
    elif settings.decision_provider == "laya":
        provider, fallback = LayaProvider(settings.laya_checkpoint, settings.laya_device), llm
    elif settings.decision_provider == "jev":
        if not settings.cloud_allowed:  # Jev is a cloud service: "cloud off" means nothing leaves the PC
            logger.warning("DECISION_PROVIDER=jev but CLOUD_ALLOWED is false: using the LLM for decisions")
        elif settings.jev_api_key:
            provider, fallback = JevProvider(settings.jev_api_key, model=settings.jev_model, names=router.names), llm
        else:
            logger.warning("DECISION_PROVIDER=jev but JEV_API_KEY is empty: using the LLM for decisions")
    return DecisionService(provider, log, fallback=fallback, min_confidence=settings.decision_min_confidence)


def build_conversation(settings: Settings, orchestrator: AgentOrchestrator, finance: Any) -> ConversationManager:
    def global_context() -> GlobalContext:
        months: list[str] = []
        try:
            months = finance.metrics.available_months()
        except Exception as exc:  # no data yet is a normal state, not an error
            logger.debug("No month range for the conversation lane: {}", exc)
        return GlobalContext(
            workspace_id=settings.workspace_id,
            currency=settings.currency,
            first_month=months[0] if months else None,
            latest_month=months[-1] if months else None,
            cloud_allowed=orchestrator.router.cloud_allowed,
        )

    return ConversationManager(
        orchestrator,
        classifier=TurnClassifier(orchestrator.decisions, settings.fast_lane_timeout_s),
        fast=build_fast_provider(settings),
        fast_timeout_s=settings.fast_lane_timeout_s,
        global_context=global_context,
        quiet=settings.conversation_quiet,
    )


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
    router.names = NameIndex(name_sources(finance, vault))  # before the decision service: Jev is filtered too
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
        cash_risk_warn_at=settings.cash_risk_warn_at,
    )
