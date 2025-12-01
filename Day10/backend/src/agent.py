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
import json
from livekit import rtc
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Predefined scenario templates for the Improv Battle
SCENARIOS = [
    "You are a barista who must explain to a customer that their latte is actually a portal to another dimension. Show surprise, then try to stay calm.",
    "You are a time-travelling tour guide explaining modern smartphones to someone from the 1800s. Be excited and slightly condescending.",
    "You are a restaurant waiter who must calmly tell a customer that their order has escaped the kitchen. Keep a straight face while the situation escalates.",
    "You are a customer trying to return an obviously cursed object to a very skeptical shop owner. Be persuasive and a little dramatic.",
    "You are an anxious stage magician whose trick keeps failing in increasingly absurd ways. Convince the audience it's all part of the act.",
]


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=self._get_instructions(),
        )
        
        # Initialize improv game state
        self.improv_state = {
            "current_round": 0,
            "max_rounds": 3,
            "rounds": [],
            "phase": "intro",
        }
    
    def _get_instructions(self) -> str:
        """Generate instructions for the Improv Battle host."""
        return """You are the charismatic host of 'Improv Battle', a fast-paced TV improv game show.

Start by asking the player for their name in a friendly, energetic way, then remember and use it throughout the show.

PERSONA:
- High-energy, quick-witted, and theatrical like a game show host
- You're encouraging but honest - not afraid to playfully roast weak performances
- Think of yourself as a mix between a supportive acting coach and a cheeky comedy club MC
- Keep your language conversational and natural for voice interaction - no emojis, asterisks, or complex formatting

YOUR ROLE:
1. GREETING: When the show starts, warmly welcome the player and ask their name. Briefly explain the format: "Welcome to Improv Battle! Here's how it works - I'll give you 3 improv scenarios. You act them out. I react. Simple as that. Ready to see what you've got?"

2. SCENARIO SETUP: For each round, clearly describe the improv scenario and the character the player should embody. Paint a vivid picture in 2-3 sentences, then prompt them with "Action! Show me what you've got."

3. LISTENING: Let the player perform. Stay silent and attentive. Wait for them to signal they're done (by saying "End scene", "End", or when there's a natural pause).

4. REACTION: After each scene, give immediate, authentic feedback:
- Point out specific moments that stood out (good or awkward)
- Vary your tone: sometimes impressed, sometimes amused, sometimes constructively critical
- Keep reactions to 2-3 sentences maximum
- Be playful and conversational: "Okay that portal explanation was wild, I loved the panic in your voice!" or "Hmm, felt a bit rushed there - I wanted more commitment to the absurdity"

5. CLOSING: After all rounds, give a fun character-style summary: "Alright [player name], that's a wrap! You've got [describe their style - e.g., 'great comedic timing' or 'bold character choices' or 'fearless commitment to the weird']. Thanks for playing Improv Battle!"

GUIDELINES:
- Always address the player by name when you know it
- Keep all responses brief and punchy (2-4 sentences max per turn)
- Vary your feedback tone each round to keep it dynamic
- Use function tools to track game progress (start_game, next_scenario, end_scene)
- Never speak for the player or write their lines - only narrate as the host
- Make it feel like a real TV show: energetic, fun, slightly unpredictable"""
    
    def _short(self, s: str, n: int = 30):
        """Helper to truncate long strings."""
        return (s[:n] + "...") if len(s) > n else s
    
    @function_tool
    async def start_game(self, max_rounds: int = 3):
        """Start a new Improv Battle game for the player.
        
        Args:
            max_rounds: Number of improv rounds to play (default: 3)
        """
        self.improv_state["max_rounds"] = max_rounds
        self.improv_state["current_round"] = 0
        self.improv_state["rounds"] = []
        self.improv_state["phase"] = "intro"
        
        logger.info(f"Game started with {max_rounds} rounds")
        
        return {
            "message": f"Welcome to Improv Battle! Get ready for {self.improv_state['max_rounds']} wild improv scenarios.",
            "state": self.improv_state,
        }

    @function_tool
    async def next_scenario(self):
        """Advance to the next scenario and return it.
        
        Returns the next improv scenario for the player to perform.
        """
        if self.improv_state["current_round"] >= self.improv_state["max_rounds"]:
            self.improv_state["phase"] = "done"
            logger.info("All rounds complete")
            return {"message": "All rounds complete.", "state": self.improv_state}

        # choose scenario deterministically from list for variety
        idx = self.improv_state["current_round"] % len(SCENARIOS)
        scenario = SCENARIOS[idx]
        self.improv_state["current_round"] += 1
        self.improv_state["phase"] = "awaiting_improv"
        self.improv_state["rounds"].append({"scenario": scenario, "host_reaction": None, "player_lines": []})
        logger.info(f"Starting round {self.improv_state['current_round']}: {scenario[:50]}...")
        return {"scenario": scenario, "round": self.improv_state["current_round"], "state": self.improv_state}

    @function_tool
    async def submit_player_line(self, player_line: str):
        """Store a player utterance for the current round.
        
        Args:
            player_line: What the player said during their improv
        
        Returns current phase and stored content.
        """
        if not self.improv_state["rounds"]:
            return {"error": "No active round."}
        self.improv_state["rounds"][-1]["player_lines"].append(player_line)
        return {"ok": True, "last_line": player_line, "state": self.improv_state}

    @function_tool
    async def end_scene(self, cue: str = "End scene"):
        """Mark the current scene as ended and generate a host reaction.
        
        Args:
            cue: The end scene cue (e.g., "End scene", "End")
        
        Generates varied host feedback (positive, neutral, or mildly critical).
        """
        import random
        
        if not self.improv_state["rounds"]:
            return {"error": "No active round to end."}

        # simple heuristics for reaction: look at last player line if present
        last_lines = self.improv_state["rounds"][-1].get("player_lines", [])
        last = last_lines[-1] if last_lines else ""

        # Craft a short, varied reaction using rules: positive / neutral / mild critique
        tone = random.choices(["positive", "neutral", "critical"], weights=[0.45, 0.3, 0.25])[0]
        if tone == "positive":
            reaction = f"That was great — I loved how you handled the bit about '{self._short(last)}'. Really committed!"
        elif tone == "neutral":
            reaction = f"Solid work. The idea was clear; you might tighten the pacing next time."
        else:
            reaction = f"Not bad, but that felt a touch rushed. Try leaning more into the character's motivation next round."

        self.improv_state["rounds"][-1]["host_reaction"] = reaction
        self.improv_state["phase"] = "reacting"
        logger.info(f"Scene ended with {tone} reaction")
        return {"reaction": reaction, "state": self.improv_state}

    @function_tool
    async def stop_game(self, confirm: bool = True):
        """Gracefully end the game early if the player requests it.
        
        Args:
            confirm: Whether to confirm ending the game (default: True)
        """
        if confirm:
            self.improv_state["phase"] = "done"
            logger.info("Game stopped by player request")
            return {"message": "Game ended by player.", "state": self.improv_state}
        return {"message": "Stop cancelled.", "state": self.improv_state}


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Initialize agent instance that will handle the game
    assistant = Assistant()
    logger.info("Assistant instance created")

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
        agent=assistant,
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
