from livekit.agents import tts
from livekit.plugins import deepgram

from voice_agent.config import AgentSettings


def build_tts(s: AgentSettings, speaking_rate: float = 1.0, voice_id: str = "") -> tts.TTS:
    """`voice_id` is the call's own voice (the one its agent was created with); TTS_MODEL is only the fallback."""
    if s.tts_provider == "deepgram":
        kw = {} if speaking_rate == 1.0 else {"speed": speaking_rate}
        return deepgram.TTS(model=voice_id.strip() or s.tts_model, api_key=s.deepgram_api_key, **kw)
    raise ValueError(f"unsupported TTS provider {s.tts_provider}")
