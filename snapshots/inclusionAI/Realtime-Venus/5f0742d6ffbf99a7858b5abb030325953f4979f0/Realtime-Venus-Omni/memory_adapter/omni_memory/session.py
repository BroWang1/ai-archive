# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Session lifecycle management for media processing and question answering.

MediaMemorySession encodes a recording and answers questions through the
selected Chat backend. MemorySession defines the shared session interface.
"""

from __future__ import annotations
from typing import Any, Iterable, Mapping, Sequence
from .config import MemoryConfig
from .schema import Answer, MainStreamOutput, MediaChunk, Question


class MemorySession:
    """Base interface for configured Chat or Duplex sessions.

    Inputs are sampled MediaChunk objects and independent Question objects.
    The run method returns final answers, while main_stream_outputs exposes
    Duplex stream results.
    """

    def __init__(
        self, *, mode: str, use_memory: bool, config: MemoryConfig, generate_audio: bool
    ) -> None:
        """Store immutable public settings for a single-use session."""
        self.mode = mode
        self.use_memory = use_memory
        self.config = config
        self.generate_audio = generate_audio
        self._main_stream_outputs: list[MainStreamOutput] = []

    @property
    def main_stream_outputs(self) -> tuple[MainStreamOutput, ...]:
        """Return visible main-stream outputs from a Duplex run."""
        return tuple(self._main_stream_outputs)

    def run(
        self, *, media_chunks: Iterable[MediaChunk], questions: Sequence[Question]
    ) -> list[Answer]:
        """Process one media stream and return one final answer per question."""
        raise NotImplementedError

    def close(self) -> None:
        """Release session-owned state and background resources."""
        raise NotImplementedError


class MediaMemorySession(MemorySession):
    """Process complete recorded media and answer independent Chat questions.

    With memory enabled, every caller-sampled visual enters PCost before the
    retained visual store is encoded and retrieved.  With memory disabled, the
    complete-media adapter uniformly caps visuals at 128 and selects local
    one-second audio blocks without constructing long-term memory.
    """

    def __init__(
        self,
        *,
        model: Any,
        processor: Any,
        use_memory: bool,
        config: MemoryConfig,
        generate_audio: bool,
        adapter: Any | None = None,
        prompt_context: Mapping[str, Any] | None = None,
    ) -> None:
        """Create the selected complete-media backend around a loaded model."""
        super().__init__(
            mode="chat",
            use_memory=use_memory,
            config=config,
            generate_audio=generate_audio,
        )
        if use_memory:
            from .chat.runtime import MemoryChatRuntime

            self.backend = MemoryChatRuntime(
                model=model,
                processor=processor,
                config=config.to_chat_engine_config(),
                generate_audio=generate_audio,
                adapter=adapter,
                prompt_context=prompt_context,
            )
        else:
            from .chat.complete_media import CompleteMediaChat

            self.backend = CompleteMediaChat(
                model=model,
                processor=processor,
                max_new_tokens=config.chat.max_new_tokens,
                visual_encoding_frames_per_batch=config.resources.chat.visual_encoding_frames_per_batch,
                max_visual_frames=128,
                adapter=adapter,
            )
        self._state = "idle"

    @property
    def last_rendered_prompt(self) -> str | None:
        """Return the rendered prompt used for the most recent answer."""
        value = getattr(self.backend, "last_rendered_prompt", None)
        return value if isinstance(value, str) else None

    def begin_media(self, media_id: str = "media") -> None:
        """Begin accepting chronological chunks for one complete recording."""
        if self._state != "idle":
            raise RuntimeError("begin_media requires an unused session")
        self.backend.begin_media(media_id=media_id)
        self._state = "receiving_media"

    def process_media_chunk(self, chunk: MediaChunk) -> None:
        """Append one validated chunk; a final chunk completes media encoding."""
        if self._state != "receiving_media":
            raise RuntimeError("process_media_chunk requires begin_media()")
        self.backend.add_media_chunk(chunk)
        if chunk.is_final:
            self._state = "ready"

    def answer_question(
        self, question: Question, *, generation_options: Mapping[str, Any] | None = None
    ) -> Answer:
        """Answer one independent question after complete media processing."""
        if self._state != "ready":
            raise RuntimeError("ask requires a completed media stream")
        _validate_chat_question(question)
        if self.use_memory:
            engine_answer = self.backend.ask(
                text=question.model_text,
                retrieval_text=question.retrieval_text,
                query_id=question.query_id,
                generation_options=generation_options,
            )
        else:
            engine_answer = self.backend.ask(
                text=question.model_text, query_id=question.query_id
            )
        answer = _public_answer(engine_answer)
        return answer

    def run(
        self,
        *,
        media_chunks: Iterable[MediaChunk],
        questions: Sequence[Question],
        generation_options: Mapping[str, Any] | None = None,
    ) -> list[Answer]:
        """Encode complete media once, then answer each independent question."""
        self.begin_media()
        saw_final = False
        for chunk in media_chunks:
            self.process_media_chunk(chunk)
            saw_final = chunk.is_final
        if not saw_final:
            raise ValueError("last MediaChunk must set is_final=true")
        return [
            self.answer_question(question, generation_options=generation_options)
            for question in questions
        ]

    def close(self) -> None:
        """Release encoded media and make this session unusable."""
        close = getattr(self.backend, "close", None)
        if callable(close):
            close()
        self._state = "closed"


def _validate_chat_question(question: Question) -> None:
    """Require a complete-media question without a stream timestamp."""
    if not isinstance(question, Question):
        raise TypeError("questions must contain Question objects")
    if question.timestamp_seconds is not None:
        raise ValueError("Chat questions must not set timestamp_seconds")


def _public_answer(value: Any) -> Answer:
    return Answer(
        query_id=str(value.query_id),
        text=str(value.text or ""),
        audio_waveform=getattr(value, "audio_waveform", None),
    )


__all__ = ["MediaMemorySession", "MemorySession"]
