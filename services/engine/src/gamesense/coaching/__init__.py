"""Trigger policy, request scheduling, stale-result checks, cooldowns and delivery."""

from .loop import CoachingConfig, CoachingLoop

__all__ = ["CoachingConfig", "CoachingLoop"]
