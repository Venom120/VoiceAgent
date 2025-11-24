# Persistence helpers
import json
from datetime import datetime
from pathlib import Path

import logging
from dotenv import load_dotenv
from livekit.agents import ( # type: ignore
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    tokenize,
    function_tool,
    RunContext,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation # type: ignore
from livekit.plugins.turn_detector.multilingual import MultilingualModel # type: ignore

logger = logging.getLogger("agent")

load_dotenv(".env.local")


LOG_PATH = Path(__file__).resolve().parents[1] / "wellness_log.json"

def ensure_log_exists():
    try:
        if not LOG_PATH.exists():
            LOG_PATH.write_text("[]", encoding="utf-8")
    except Exception:
        logger.exception("Failed to ensure wellness log exists")


class Assistant(Agent):
    def __init__(self, previous_summary: str | None = None) -> None:
        # Improved system prompt for a grounded health & wellness companion
        base_instructions = (
            "You are a supportive, non-clinical health & wellness voice companion. "
            "Your role is to run a short daily check-in: ask about mood, energy, current stressors, and 1–3 practical intentions for the day. "
            "Always avoid medical diagnoses, clinical recommendations, or mental health treatment language — you are a friendly companion, not a clinician."
        )

        # Conversation guidance and explicit advice style (required block from user)
        advice_block = (
            "Offer simple, realistic advice or reflections\n\n"
            "Suggestions should be:\n"
            "Small, actionable, and grounded.\n"
            "Non-medical, non-diagnostic.\n"
            "Examples of advice style:\n"
            "Break large goals into smaller steps.\n"
            "Encourage short breaks.\n"
            "Offer simple grounding ideas (e.g., \"take a 5-minute walk\").\n"
        )

        behavior_notes = (
            "Ask concise, open questions (examples: 'How are you feeling today?', 'What is your energy like?', "
            "'Anything stressing you out right now?', 'What are 1–3 things you'd like to get done today?'). "
            "When the user shares mood, energy, and intentions, offer small practical suggestions as shown above. "
            "Finish each check-in with a brief recap that repeats today's mood and the 1–3 objectives and asks 'Does this sound right?'."
        )

        # Notes about persistence and tool usage
        tools_notes = (
            "You have two tools available: 'read_wellness_log' and 'append_wellness_entry'. "
            "Use 'read_wellness_log' to reference past entries when appropriate. "
            "When the user confirms mood, energy, and objectives by replying to your question of `Does this sound right?`, call 'append_wellness_entry' with those values and a short one-sentence summary of the check-in."
        )

        if previous_summary:
            tools_notes += f"\nPrevious check-in reference: {previous_summary}"

        full_instructions = "\n\n".join([base_instructions, behavior_notes, advice_block, tools_notes])

        super().__init__(instructions=full_instructions)

    @function_tool
    async def read_wellness_log(self, context: RunContext) -> str:
        """Return the full wellness log as a JSON string."""
        ensure_log_exists()
        try:
            data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
            logger.info(f"Reading wellness log: {len(data)} entries found")
            return json.dumps(data)
        except Exception as e:
            logger.exception("Error reading wellness log")
            return json.dumps({"error": str(e)})

    @function_tool
    async def append_wellness_entry(
        self, context: RunContext, mood: str, energy: str, objectives: str, summary: str = ""
    ) -> str:
        """Append a wellness entry to the JSON log after gathering user's mood, energy, and objectives.

        Args:
            mood: The user's reported mood (e.g., "good", "stressed", "tired")
            energy: The user's reported energy level (e.g., "high", "low", "medium")
            objectives: The user's 1-3 goals or intentions for the day
            summary: Optional brief summary of the check-in

        Returns:
            Status message indicating success or error
        """
        ensure_log_exists()
        try:
            raw = LOG_PATH.read_text(encoding="utf-8")
            arr = json.loads(raw or "[]")
            entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "mood": mood,
                "energy": energy,
                "objectives": objectives,
                "summary": summary,
            }
            arr.append(entry)
            LOG_PATH.write_text(json.dumps(arr, indent=2), encoding="utf-8")
            logger.info(f"Wellness entry saved: mood={mood}, energy={energy}")
            return "Wellness entry saved successfully"
        except Exception as e:
            logger.exception("Error appending wellness entry")
            return f"Error saving entry: {e}"


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Load previous wellness log to provide context to the agent
    ensure_log_exists()
    previous_summary = None
    try:
        log_data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        if log_data:
            last_entry = log_data[-1]
            previous_summary = (
                f"Last check-in on {last_entry.get('timestamp', 'unknown')}: "
                f"mood was '{last_entry.get('mood', 'not recorded')}', "
                f"energy was '{last_entry.get('energy', 'not recorded')}', "
                f"objectives: {last_entry.get('objectives', 'none')}."
            )
    except Exception as e:
        logger.warning(f"Could not load previous wellness log: {e}")

    # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=deepgram.STT(model="nova-3"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=google.LLM(
                model="gemini-2.5-flash",
            ),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=murf.TTS(
                voice="en-US-matthew", 
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True
            ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(previous_summary=previous_summary),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
