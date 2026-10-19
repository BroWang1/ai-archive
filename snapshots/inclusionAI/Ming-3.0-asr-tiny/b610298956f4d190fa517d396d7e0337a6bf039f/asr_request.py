"""Build the audio request used by Ming-3.0-asr-tiny."""


# The character between the backticks is a literal tab, not a backslash and "t".
ASR_INSTRUCTION = (
    "Please recognize the language of this speech and transcribe it, "
    "placing a `\t` between the identified language and the transcribe."
)


def prepare_asr_request(
    processor, audio, *, prompt=None, language_hint=None,
    audio_chunk_frames=None, return_tensors="pt",
):
    """Prepare audio and context through the processor's single ASR entry point."""
    return processor.apply_transcription_request(
        audio, prompt=prompt, language_hint=language_hint,
        audio_chunk_frames=audio_chunk_frames, return_tensors=return_tensors,
    )


def context_chunk_frames(duration_seconds):
    """Use one encoder chunk for a ContextASR-Bench clip up to 60 seconds."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if duration_seconds > 60:
        raise ValueError("Context ASR chunk policy supports clips up to 60 seconds")
    return 6000 if duration_seconds > 30 else 3000


def decode_transcript(tokenizer, token_ids):
    """Remove the language envelope from generated text."""
    text = tokenizer.decode(token_ids, skip_special_tokens=True).strip()
    if "\t" in text:
        return text.split("\t", 1)[1].strip()
    for language in ("Chinese", "English", "Canton", "Japanese", "Korean"):
        if text.startswith(language):
            return text[len(language):].strip()
    return text
