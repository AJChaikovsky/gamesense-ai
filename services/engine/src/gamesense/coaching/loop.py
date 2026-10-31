"""The live coaching loop: frames -> fast path -> trigger -> model -> checks -> tip."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import cv2
from gamesense_contracts import CoachingDecision, CoachingStatus, StatusEvent, TipEvent
from gamesense_contracts.events import ControlMessage, FeedbackMessage

from ..capture import Frame, FrameRingBuffer
from ..capture.replay import downscale
from ..games import GENERIC, GameProfile, detect_game
from ..games.foreground import WindowInfo, foreground_window
from ..knowledge import KnowledgeBase
from ..perception import FastPath, Signals
from ..providers import AnalysisRequest, AnalysisResult, ProviderError, VisionModelProvider
from ..providers.prompt import context_block, system_prompt
from ..telemetry import TelemetryFeed
from .budget import SpendMeter
from .convert import to_contracts
from .cooldown import Cooldown
from .feedback import FeedbackLog
from .trigger import TriggerPolicy
from .validator import first_failed

log = logging.getLogger(__name__)

Publish = Callable[[TipEvent | StatusEvent], None]


@dataclass(slots=True)
class CoachingConfig:
    tick_hz: float = 4.0
    frames_per_call: int = 2
    model_frame_width: int = 1024
    jpeg_quality: int = 80
    min_confidence: float = 0.55
    max_situation_change: float = 0.5  # summed scene change since the request
    error_backoff_s: float = 10.0  # doubles per consecutive failure, up to max_backoff_s
    max_backoff_s: float = 300.0
    detect_interval_s: float = 2.0
    hourly_budget_usd: float = 0.50
    hold_max_s: float = 30.0  # how long a next_lull tip may wait for a lull
    max_held: int = 3
    combat_memory_s: float = 15.0  # a model "combat" reading counts for this long
    combat_words: tuple[str, ...] = ("combat", "fight", "boss", "battle", "duel")
    trigger: TriggerPolicy = field(default_factory=TriggerPolicy)
    cooldown: Cooldown = field(default_factory=Cooldown)


@dataclass(slots=True)
class _InFlight:
    task: asyncio.Task[AnalysisResult]
    started: float
    frame_ids: list[str]
    reason: str
    change_since: float = 0.0


@dataclass(slots=True)
class _Held:
    """A tip waiting for a lull (``next_lull`` delivery)."""

    decision: CoachingDecision
    deadline: float
    local: bool


_PRIORITY_RANK = {"urgent": 0, "important": 1, "info": 2}


def encode_jpeg(frame: Frame, width: int, quality: int) -> bytes:
    ok, buf = cv2.imencode(
        ".jpg", downscale(frame.image, width), [cv2.IMWRITE_JPEG_QUALITY, quality]
    )
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return bytes(buf.tobytes())


class CoachingLoop:
    def __init__(
        self,
        buffer: FrameRingBuffer,
        provider: VisionModelProvider,
        publish: Publish,
        *,
        config: CoachingConfig | None = None,
        fixed_game: GameProfile | None = None,
        detect_foreground: Callable[[], WindowInfo | None] = foreground_window,
        session_id: str | None = None,
        feedback_log: FeedbackLog | None = None,
        knowledge: KnowledgeBase | None = None,
    ) -> None:
        self.buffer = buffer
        self.provider = provider
        self.publish = publish
        self.config = config or CoachingConfig()
        self.session_id = session_id or f"session_{uuid.uuid4().hex[:10]}"
        self.fast_path = FastPath()
        self.spend = SpendMeter(self.config.hourly_budget_usd)
        self.paused = False
        self.tips_delivered = 0
        self.local_tips = 0
        self.telemetry: TelemetryFeed | None = None
        self.feedback: list[FeedbackMessage] = []
        self.feedback_log = feedback_log
        self.knowledge = knowledge
        self.suppressed: dict[str, int] = {}
        self._fixed_game = fixed_game
        self._detect = detect_foreground
        self._game: GameProfile = fixed_game or GENERIC
        self._last_detect = 0.0
        self._last_frame_id: str | None = None
        self._in_flight: _InFlight | None = None
        self._backoff_until = 0.0
        self._last_latency_ms: int | None = None
        self._last_activity: str | None = None
        self._last_activity_at = 0.0
        self._last_observations: list[str] = []
        self._last_obs_values: dict[str, str] = {}
        self._held: list[_Held] = []
        self._consecutive_errors = 0
        self._fallback: Literal["provider_error", "budget"] | None = None

    @property
    def game(self) -> GameProfile:
        return self._game

    # -- control ------------------------------------------------------------------
    def handle_client_message(self, msg: FeedbackMessage | ControlMessage) -> None:
        if isinstance(msg, ControlMessage):
            self.paused = msg.action == "pause"
            log.info("coaching %s", "paused" if self.paused else "resumed")
        else:
            self.feedback.append(msg)
            log.info("tip feedback: %s %s", msg.tip_id, msg.rating)
            if self.feedback_log is not None:
                self.feedback_log.record(
                    msg,
                    session_id=self.session_id,
                    game_id=self._game.game_id,
                    provider=self.provider.name,
                    model=self.provider.model,
                )

    def status(self) -> CoachingStatus:
        now = time.monotonic()
        return CoachingStatus(
            provider=self.provider.name,
            model=self.provider.model,
            paused=self.paused,
            game_id=self._game.game_id,
            game_name=self._game.name,
            live_allowed=self._game.live_allowed,
            policy_reason=self._game.policy_reason,
            in_flight=self._in_flight is not None,
            calls=self.spend.calls,
            tips_delivered=self.tips_delivered,
            spend_usd=round(self.spend.total_usd, 5),
            spend_usd_last_hour=round(self.spend.last_hour(now), 5),
            hourly_budget_usd=self.spend.hourly_budget_usd,
            last_latency_ms=self._last_latency_ms,
            telemetry=(
                self.telemetry.source
                if self.telemetry is not None and self.telemetry.connected()
                else None
            ),
            local_tips=self.local_tips,
            held_tips=len(self._held),
            fallback_reason=self._fallback,
        )

    # -- main loop ----------------------------------------------------------------
    async def run(self) -> None:
        interval = 1.0 / self.config.tick_hz
        try:
            while True:
                await self.tick(time.monotonic())
                await asyncio.sleep(interval)
        finally:
            if self._in_flight is not None:
                self._in_flight.task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._in_flight.task

    async def tick(self, now: float) -> None:
        self._update_game(now)
        if self._in_flight is not None and self._in_flight.task.done():
            await self._finish(self._in_flight, now)
            self._in_flight = None
        if self._fallback == "budget" and self.spend.allows_call(now):
            self._leave_fallback("Budget available again. Model tips resumed.")
        self._release_held(now)

        frame = self.buffer.latest()
        if frame is None or frame.id == self._last_frame_id:
            return
        self._last_frame_id = frame.id
        signals = self.fast_path.update(frame)
        if self._in_flight is not None:
            self._in_flight.change_since += signals.scene_change
            return
        if self.paused or not self._game.live_allowed or now < self._backoff_until:
            return
        reason = self.config.trigger.should_analyze(signals, now)
        if reason is None:
            return
        if not self.spend.allows_call(now):
            self._suppress("budget")
            self._enter_fallback("budget", "Hourly model budget reached; model tips are paused.")
            return
        self.config.trigger.mark_called(now)
        await self._start_request(signals, reason, now)

    async def _start_request(self, signals: Signals, reason: str, now: float) -> None:
        frames = self.buffer.last(self.config.frames_per_call)
        jpegs = await asyncio.to_thread(
            lambda: [
                encode_jpeg(f, self.config.model_frame_width, self.config.jpeg_quality)
                for f in frames
            ]
        )
        last_tip = self.config.cooldown.last_tip_time()
        game_id = self._game.game_id
        snippets: list[str] = []
        if self.knowledge is not None:
            snippets = self.knowledge.for_situation(game_id, self._situation())
        request = AnalysisRequest(
            system_prompt=system_prompt(
                self._game, self.knowledge.core(game_id) if self.knowledge else ""
            ),
            context=context_block(
                recent_tips=self.config.cooldown.recent_messages(now),
                last_activity=self._last_activity,
                last_observations=self._last_observations,
                seconds_since_last_tip=(now - last_tip) if last_tip else None,
                telemetry=self.telemetry.facts() if self.telemetry is not None else (),
                knowledge=snippets,
            ),
            frames_jpeg=jpegs,
            request_id=uuid.uuid4().hex,
            game_id=self._game.game_id,
            hints={"scene_change": signals.scene_change, "activity": signals.activity},
        )
        task = asyncio.create_task(self.provider.analyze(request), name="model-analyze")
        self._in_flight = _InFlight(task, now, [f.id for f in frames], reason)
        log.debug("analysis started (%s)", reason)

    async def _finish(self, job: _InFlight, now: float) -> None:
        try:
            result = job.task.result()
        except ProviderError as exc:
            self._on_error(str(exc), now)
            return
        except Exception as exc:
            log.exception("provider crashed")
            self._on_error(f"{type(exc).__name__}: {exc}", now)
            return

        self.spend.record(result.cost_usd, now)
        self._last_latency_ms = result.latency_ms
        self._consecutive_errors = 0
        if self._fallback == "provider_error":
            self._leave_fallback("Coach is back online.")
        log.info(
            "analysis done in %d ms (%s), in=%d out=%d cost=$%.5f tip=%s",
            result.latency_ms,
            job.reason,
            result.usage.input_tokens,
            result.usage.output_tokens,
            result.cost_usd,
            result.analysis.tip.message if result.analysis.tip else None,
        )
        state, decision = to_contracts(
            result.analysis, game=self._game, session_id=self.session_id, frame_ids=job.frame_ids
        )
        self._last_activity = state.activity
        self._last_activity_at = now
        self._last_observations = [f"{o.type}={o.value}" for o in state.observations]
        self._last_obs_values = {o.type: str(o.value) for o in state.observations}
        if decision is not None:
            self._deliver(decision, job, now)

    def _deliver(self, decision: CoachingDecision, job: _InFlight, now: float) -> None:
        age = now - job.started
        if decision.confidence < self.config.min_confidence:
            return self._suppress("low_confidence")
        if age >= decision.expires_in_seconds:
            return self._suppress("expired")
        if job.change_since > self.config.max_situation_change and decision.priority != "urgent":
            return self._suppress("situation_changed")
        remaining = max(2, int(decision.expires_in_seconds - age))
        self._route(decision.model_copy(update={"expires_in_seconds": remaining}), now)

    def submit_local(self, decision: CoachingDecision, now: float | None = None) -> bool:
        """Deliver a tip from a local rule (no model call).

        True when it was shown or queued for the next lull. Local rules work
        without the model, so they keep coaching while the provider is down or
        the budget is spent (fallback mode).
        """
        now = time.monotonic() if now is None else now
        return self._route(decision, now, local=True)

    def _situation(self) -> list[str]:
        """What is going on right now, as text for knowledge retrieval."""
        parts = [self._last_activity or ""]
        parts += [f"{k} {v}" for k, v in self._last_obs_values.items()]
        if self.telemetry is not None:
            parts += self.telemetry.topics()
        return parts

    # -- delivery -------------------------------------------------------------------
    def facts(self) -> dict[str, object]:
        """Freshest known observation values: telemetry wins over model readings."""
        telemetry = self.telemetry.observations() if self.telemetry is not None else {}
        return {**self._last_obs_values, **telemetry}

    def in_combat(self, now: float) -> bool:
        if self.telemetry is not None and self.telemetry.connected():
            exact = self.telemetry.in_combat()
            if exact is not None:
                return exact
        activity = (self._last_activity or "").lower()
        recent = now - self._last_activity_at <= self.config.combat_memory_s
        return recent and any(word in activity for word in self.config.combat_words)

    def _wants_lull(self, decision: CoachingDecision, local: bool) -> bool:
        # Model "info" tips are never time-critical, so they wait out fights. Local
        # rules know their timing and ask for next_lull explicitly when they want it.
        return decision.delivery == "next_lull" or (not local and decision.priority == "info")

    def _route(self, decision: CoachingDecision, now: float, *, local: bool = False) -> bool:
        if self.paused or not self._game.live_allowed:
            self._suppress("paused_or_blocked")
            return False
        if first_failed(decision.valid_while, self.facts()) is not None:
            self._suppress("stale")
            return False
        if self._wants_lull(decision, local) and self.in_combat(now):
            return self._hold(decision, now, local)
        return self._publish_tip(decision, now, local=local)

    def _hold(self, decision: CoachingDecision, now: float, local: bool) -> bool:
        if any(h.decision.action == decision.action for h in self._held):
            self._suppress("repeat")
            return False
        wait = max(decision.expires_in_seconds, self.config.hold_max_s)
        self._held.append(_Held(decision, now + wait, local))
        self._held.sort(key=lambda h: (_PRIORITY_RANK[h.decision.priority], h.deadline))
        while len(self._held) > self.config.max_held:
            self._held.pop()
            self._suppress("held_overflow")
        log.debug("tip held for the next lull: %s", decision.message)
        return True

    def _release_held(self, now: float) -> None:
        if not self._held:
            return
        for held in [h for h in self._held if h.deadline <= now]:
            self._held.remove(held)
            self._suppress("expired")
        if not self._held or self.paused or self.in_combat(now):
            return
        facts = self.facts()
        for held in list(self._held):
            if first_failed(held.decision.valid_while, facts) is not None:
                self._held.remove(held)
                self._suppress("stale")
        if not self._held:
            return
        best = self._held[0]
        d = best.decision
        if self.config.cooldown.allows(d.action, d.message, d.priority, now) is None:
            self._held.pop(0)
            self._publish_tip(d, now, local=best.local)

    def _publish_tip(self, decision: CoachingDecision, now: float, *, local: bool = False) -> bool:
        if self.paused or not self._game.live_allowed:
            self._suppress("paused_or_blocked")
            return False
        cooldown = self.config.cooldown
        blocked = cooldown.allows(decision.action, decision.message, decision.priority, now)
        if blocked:
            self._suppress(blocked)
            return False
        cooldown.record(decision.action, decision.message, now)
        self.tips_delivered += 1
        self.local_tips += local
        if self.feedback_log is not None:
            self.feedback_log.remember_tip(decision)
        self.publish(TipEvent(timestamp=_utcnow(), decision=decision))
        return True

    def _on_error(self, message: str, now: float) -> None:
        self._consecutive_errors += 1
        backoff = min(
            self.config.error_backoff_s * 2 ** (self._consecutive_errors - 1),
            self.config.max_backoff_s,
        )
        log.warning("model call failed (%d in a row, retry in %.0f s): %s",
                    self._consecutive_errors, backoff, message)  # fmt: skip
        self._backoff_until = now + backoff
        self._enter_fallback("provider_error", f"Coach unavailable, retrying: {message[:160]}")

    # -- fallback mode -----------------------------------------------------------------
    def _enter_fallback(self, reason: Literal["provider_error", "budget"], message: str) -> None:
        if self._fallback == reason:
            return
        self._fallback = reason
        if self.telemetry is not None and self.telemetry.connected():
            message += " Tips from live game data keep working."
        log.info("fallback mode (%s)", reason)
        self.publish(StatusEvent(timestamp=_utcnow(), level="degraded", message=message))

    def _leave_fallback(self, message: str) -> None:
        self._fallback = None
        self.publish(StatusEvent(timestamp=_utcnow(), level="ok", message=message))

    def _suppress(self, reason: str) -> None:
        self.suppressed[reason] = self.suppressed.get(reason, 0) + 1
        log.debug("tip suppressed: %s", reason)

    def _update_game(self, now: float) -> None:
        if self._fixed_game is not None or now - self._last_detect < self.config.detect_interval_s:
            return
        self._last_detect = now
        info = self._detect()
        if info is None:
            return
        game = detect_game(info.process_name, info.title)
        if game.game_id != self._game.game_id:
            log.info("game detected: %s (%s)", game.name, info.process_name)
            self._game = game
            self.fast_path.reset()


def _utcnow() -> datetime:
    return datetime.now(UTC)
