"""Reusability proof: a different domain profile runs through the same factory with no code changes."""

from livekit.agents import AgentSession

from voice_agent.config import AgentSettings, get_settings
from voice_agent.profile.prompt_composer import RuntimeContext
from voice_agent.profile.schema import AgentProfileSpec
from voice_agent.session_factory import build_agent, build_session, build_turn_handling
from voice_agent.tools.base import CallState, ToolContext
from voice_agent.tools.registry import build_tools

REMINDER = AgentProfileSpec.model_validate(
    {
        "identity": {"agent_name": "Remi", "role_summary": "appointment reminders"},
        "context_prompt": "Remind the patient of their appointment. Do nothing else.",
        "voice_behavior": {"latency_profile": "aggressive", "greeting": "Hi, this is Remi."},
    }
)


def test_latency_profiles_map_to_distinct_tuning():
    s = get_settings()
    ag = build_turn_handling(REMINDER, s, "vad")
    cons = build_turn_handling(
        REMINDER.model_copy(
            update={"voice_behavior": REMINDER.voice_behavior.model_copy(update={"latency_profile": "conservative"})}
        ),
        s,
        "vad",
    )
    assert ag["endpointing"]["min_delay"] < cons["endpointing"]["min_delay"]
    assert ag["preemptive_generation"]["enabled"] and not cons["preemptive_generation"]["enabled"]


async def test_second_profile_builds_real_session_and_agent():
    s = get_settings()
    state = CallState("c", "k")
    session = build_session(REMINDER, s, vad=None, userdata=state)
    assert isinstance(session, AgentSession)
    agent = build_agent(REMINDER, RuntimeContext("OUTBOUND", "now"), build_tools([], ToolContext(state, None)))
    assert "Remind the patient" in agent.instructions


def test_pipeline_is_the_default_voice_mode():
    """The Manager's STT -> LLM -> TTS pipeline is what calls use unless AGENT_VOICE_MODE says otherwise."""
    assert AgentSettings.model_fields["agent_voice_mode"].default == "pipeline"


async def test_realtime_mode_builds_a_gemini_live_session_without_stt_or_tts():
    s = get_settings().model_copy(update={"agent_voice_mode": "realtime"})
    session = build_session(REMINDER, s, vad=None, userdata=CallState("c", "k"))
    assert type(session.llm).__name__ == "RealtimeModel" and session.llm.model == s.live_model
    assert session.stt is None and session.tts is None


async def test_pipeline_mode_is_still_available():
    s = get_settings().model_copy(update={"agent_voice_mode": "pipeline"})
    session = build_session(REMINDER, s, vad=None, userdata=CallState("c", "k"))
    assert session.stt is not None and session.tts is not None


def test_one_prewarmed_process_in_production(monkeypatch):
    """Each pre-warmed process holds its own models; the framework default (one per CPU) overflowed a 1 GB host."""
    from livekit.agents.worker import ServerEnvOption

    from voice_agent.worker import idle_processes

    monkeypatch.delenv("AGENT_IDLE_PROCESSES", raising=False)
    opt = idle_processes()
    assert ServerEnvOption.getvalue(opt, devmode=False) == 1 and ServerEnvOption.getvalue(opt, devmode=True) == 0
    monkeypatch.setenv("AGENT_IDLE_PROCESSES", "3")
    assert idle_processes() == 3


async def test_pipeline_llm_deadline_covers_a_slow_reply():
    """A 10s deadline (the framework default) cut Gemini replies off mid-sentence with 504 DEADLINE_EXCEEDED."""
    s = get_settings().model_copy(update={"agent_voice_mode": "pipeline"})
    session = build_session(REMINDER, s, vad=None, userdata=CallState("c", "k"))
    opts = session.conn_options.llm_conn_options
    assert opts.timeout >= 30 and opts.max_retry == 1


async def test_call_speaks_in_its_agents_voice():
    """The voice chosen for the agent (sent per call as voice_id) wins; TTS_MODEL is only the fallback."""
    s = get_settings().model_copy(update={"agent_voice_mode": "pipeline", "tts_model": "aura-2-draco-en"})
    female = REMINDER.model_copy(
        update={"voice_behavior": REMINDER.voice_behavior.model_copy(update={"voice_id": "aura-2-pandora-en"})}
    )
    assert build_session(female, s, vad=None, userdata=CallState("c", "k")).tts.model == "aura-2-pandora-en"
    assert build_session(REMINDER, s, vad=None, userdata=CallState("c", "k")).tts.model == "aura-2-draco-en"
