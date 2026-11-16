from livekit.plugins import google

from voice_agent.config import AgentSettings


def build_realtime_model(s: AgentSettings) -> google.realtime.RealtimeModel:
    """Gemini Live: audio in, audio out, with server-side turn detection and transcripts for the recorder."""
    kw = {"language": s.live_language} if s.live_language else {}
    return google.realtime.RealtimeModel(
        model=s.live_model,
        voice=s.live_voice,
        api_key=s.gemini_api_key,
        temperature=s.llm_temperature,
        **kw,
    )
