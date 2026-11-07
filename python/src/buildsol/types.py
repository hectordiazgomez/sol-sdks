from pathlib import Path
from typing import Any, BinaryIO, Literal, Union

from typing_extensions import Required, TypedDict

Upload = Union[str, Path, bytes, BinaryIO, tuple[str, bytes], tuple[str, bytes, str]]


class SpeechParams(TypedDict, total=False):
    text: Required[str]
    voice_id: str
    country: str
    gender: Literal["female", "male"]
    age: Literal["young", "middle_aged", "old"]
    dialect: str
    style: str
    style_position: Literal["start", "middle", "end"]
    instruction: str
    speed: float
    output_format: Literal["mp3", "wav", "pcm"]
    reference_audio: str
    reference_text: str
    reference_filename: str
    seed: int


class Voice(TypedDict):
    id: str
    name: str
    description: str
    gender: str
    age_group: str
    country: str
    kind: str
    categories: list[str]
    profile_key: str
    dialect: dict[str, Any] | None
    preview_url: str | None
    is_default: bool
    created_at: str


class VoiceList(TypedDict):
    voices: list[Voice]
    categories: list[dict[str, Any]]


class VoiceResult(TypedDict):
    voice: Voice


class Balance(TypedDict):
    characters_remaining: int
    free_remaining: int
    subscription_remaining: int
    topup_remaining: int
    free_resets_at: str | None


class Transcription(TypedDict):
    id: str
    model: str
    text: str
    segments: list[dict[str, Any]]
    language: str | None
    words: list[dict[str, Any]]
    usage: dict[str, Any]
    billing: dict[str, Any]


class Translation(TypedDict):
    id: str
    model: str
    translation: str
    source_language: str
    target_language: str
    characters: int
    usage: dict[str, Any]
    billing: dict[str, Any]


class LiveSession(TypedDict):
    id: str
    model: str
    token: str
    expires_in: int
    url: str
    audio_format: dict[str, Any]
    max_seconds: int
    billing: dict[str, Any]


class TranscriptionParams(TypedDict, total=False):
    model: str
    language: str
    diarize: bool
    transcription_style: Literal["verbatim", "clean"]


class VoiceParams(TypedDict, total=False):
    transcript: str
    dialect: str
    gender: Literal["female", "male", "neutral"]
    age_group: Literal["young", "middle_aged", "old"]
    country: str
    description: str
