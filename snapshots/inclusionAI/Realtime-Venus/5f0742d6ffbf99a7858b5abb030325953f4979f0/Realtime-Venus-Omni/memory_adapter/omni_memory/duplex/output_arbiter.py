# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""User-visible arbitration for proactive Duplex speech."""

from __future__ import annotations
from typing import Any, Mapping

PROACTIVE_OUTPUT_POLICIES = ("official", "suppress_during_answer", "disabled")


class ProactiveOutputArbiter:
    """Mute overlapping proactive turns without changing model execution."""

    def __init__(self, policy: str) -> None:
        if policy not in PROACTIVE_OUTPUT_POLICIES:
            expected = ", ".join(PROACTIVE_OUTPUT_POLICIES)
            raise ValueError(f"proactive output policy must be one of: {expected}")
        self.policy = policy
        self._suppressing_turn = False

    @property
    def suppressing_turn(self) -> bool:
        return self._suppressing_turn

    def reset(self) -> None:
        self._suppressing_turn = False

    def apply(
        self, raw: Mapping[str, Any], *, explicit_answer_active: bool
    ) -> dict[str, Any]:
        """Return the visible result while retaining internal state."""
        result = dict(raw)
        if self.policy == "official":
            return result
        is_listen = result.get("is_listen")
        if not isinstance(is_listen, bool):
            return result
        speaking = not is_listen
        should_start = speaking and (
            self.policy == "disabled" or explicit_answer_active
        )
        should_suppress = self._suppressing_turn or should_start
        if not should_suppress:
            return result
        end_of_turn = result.get("end_of_turn") is True
        self._suppressing_turn = not end_of_turn
        result["text"] = ""
        for name in ("audio", "audio_waveform", "audio_wav", "wav"):
            if name in result:
                result[name] = None
        result["output_suppressed"] = True
        result["suppression_reason"] = (
            "proactive_output_disabled"
            if self.policy == "disabled"
            else "explicit_answer_owns_output_channel"
        )
        return result


__all__ = ["PROACTIVE_OUTPUT_POLICIES", "ProactiveOutputArbiter"]
