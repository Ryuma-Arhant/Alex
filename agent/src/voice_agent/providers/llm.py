from livekit.agents import APIConnectOptions, llm
from livekit.plugins import google

from voice_agent.config import AgentSettings

# Gemini rejects request deadlines under 10s with HTTP 400 (found the hard way), so never go below this.
ATTEMPT_TIMEOUT_S = 15.0

# Connection options for the call LLM. The Gemini plugin turns `timeout` into the server deadline for the *whole*
# streamed reply, not just its first token. The framework default (10s, 3 retries) cut replies off mid-sentence with
# 504 DEADLINE_EXCEEDED whenever Gemini was slow to start, then kept the caller in silence through the retries, and
# three such failures in a row ended the call. A generous deadline lets a slow reply finish; one quick retry covers
# a transient error without a long silence.
CALL_LLM_CONN_OPTIONS = APIConnectOptions(max_retry=1, retry_interval=1.0, timeout=30.0)


def model_chain(primary: str, fallbacks: str) -> list[str]:
    return list(dict.fromkeys([primary, *[m.strip() for m in fallbacks.split(",") if m.strip()]]))


def build_llm(s: AgentSettings) -> llm.LLM:
    """The call model (gemini-3.5-flash-lite by default), with failover only if AGENT_LLM_FALLBACK_MODELS is set."""
    llms = [
        google.LLM(model=m, api_key=s.gemini_api_key, temperature=s.llm_temperature)
        for m in model_chain(s.agent_llm_model, s.agent_llm_fallback_models)
    ]
    return (
        llms[0] if len(llms) == 1 else llm.FallbackAdapter(llms, attempt_timeout=ATTEMPT_TIMEOUT_S, max_retry_per_llm=0)
    )
