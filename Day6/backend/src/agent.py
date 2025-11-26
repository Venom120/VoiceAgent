import logging

from dotenv import load_dotenv
from livekit.agents import (
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
try:
    # If this file is used as a module within a package, use relative import
    from . import db
except Exception:
    # If the file is executed as a script (no package), fall back to absolute import
    import db
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
                You are a calm, professional fraud-detection representative for a leovash bank. The user is interacting with you via voice. Use reassuring language and do not ask for or request any sensitive data such as full card numbers, PINs, passwords, or CVV.
                When interacting with the user for the first time you will introduce yourself.

                Your mission for a fraud-alert call:
                - Ask for the customer's name (first name is sufficient).
                - Use the provided tool `get_case(username)` to load the customer's fraud case. If no case is found, inform the user and end the call politely.
                - Ask a single non-sensitive verification question from the case (the `securityQuestion` field). Do not pressure the user for secrets.
                - If verification passes, read the suspicious transaction details (merchant, amount, masked card ending, approximate time/location) from the case and ask the user whether they made this transaction (expect a yes/no answer).
                - If verification fails, say you cannot proceed and end the call. Mark the case with status `verification_failed` using the `update_case(username, status, note)` tool.
                - If the user confirms the transaction, call `update_case(username, "confirmed_safe", "Customer confirmed transaction as legitimate.")` and tell the user the case is closed.
                - If the user denies the transaction, call `update_case(username, "confirmed_fraud", "Customer reported transaction as fraudulent; card blocked and dispute opened (mock).")` and explain the mock remediation (card blocked, dispute opened).
                - If the case is already closed then ask whether they want to update it or get details on the status or get details of the transaction and tell them.

                When using tools, call them with the exact field names described. Keep spoken responses short and clear.
                """,
        )

    # To add tools, use the @function_tool decorator.
    # Here's an example that adds a simple weather tool.
    # You also have to add `from livekit.agents import function_tool, RunContext` to the top of this file
    # @function_tool
    # async def lookup_weather(self, context: RunContext, location: str):
    #     """Use this tool to look up current weather information in the given location.
    #
    #     If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.
    #
    #     Args:
    #         location: The location to look up weather information for (e.g. city name)
    #     """
    #
    #     logger.info(f"Looking up weather for {location}")
    #
    #     return "sunny with a temperature of 70 degrees."

    
    @function_tool
    async def get_case(self, context: RunContext, username: str):
        """Tool: get_case(username)

        Returns the fraud case for the provided username (or an informative message if none).
        """
        logger.info(f"Tool get_case called for username={username}")
        case = db.find_case_by_username(username)
        if not case:
            return {"found": False, "message": "No pending fraud case found for that user."}

        # Remove the (private) security answer from the data returned to the LLM; reveal only the question.
        safe_copy = dict(case)
        safe_copy.pop("securityAnswer", None)
        return {"found": True, "case": safe_copy}


    @function_tool
    async def update_case(self, context: RunContext, username: str, status: str, note: str):
        """Tool: update_case(username, status, note)

        Persists status and a short note to the JSON DB for the user's case.
        """
        logger.info(f"Tool update_case called for username={username}, status={status}")
        ok = db.update_case(username, status, note)
        if not ok:
            return {"updated": False, "message": "Failed to update case - user not found."}
        return {"updated": True, "message": "Case updated."}


    @function_tool
    async def verify_answer(self, context: RunContext, username: str, answer: str):
        """Tool: verify_answer(username, answer)

        Compares the provided answer to the stored security answer for the user's case.
        Comparison is case-insensitive. Returns a verification result and a message.
        """
        logger.info(f"Tool verify_answer called for username={username}")
        case = db.find_case_by_username(username)
        if not case:
            return {"verified": False, "message": "No case found for that user."}

        expected = (case.get("securityAnswer") or "").strip().lower()
        provided = (answer or "").strip().lower()
        if expected == provided and expected != "":
            return {"verified": True, "message": "Verification passed."}

        # record a soft failure so operators can review later
        db.update_case(username, "verification_failed", "Customer provided incorrect answer to security question.")
        return {"verified": False, "message": "Verification failed."}



def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

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
        tts="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
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
        agent=Assistant(),
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
