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
)
import json
from copy import deepcopy
from typing import Optional
import asyncio
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self, room=None) -> None:
        super().__init__(
            instructions="""You are an epic Game Master running a thrilling fantasy adventure in a world of dragons, magic, and mystery.
            
            UNIVERSE & TONE:
            - Setting: A medieval fantasy realm filled with ancient ruins, mystical forests, dangerous dungeons, and magical creatures
            - Tone: Dramatic and immersive, with moments of tension, wonder, and excitement
            - Style: Cinematic storytelling that brings scenes to life
            
            YOUR ROLE AS GAME MASTER:
            - You describe vivid scenes with sensory details (sights, sounds, smells)
            - You narrate the consequences of the player's actions
            - You present challenges, encounters, and choices
            - You always end your response with a question prompting player action (e.g., "What do you do?", "How do you respond?", "Which path do you take?")
            - You keep the story moving forward with purpose
            
            STORY STRUCTURE:
            - The player is a brave adventurer who begins their journey in a small village
            - Initial quest: Strange creatures have been attacking the village at night, and the elder needs help
            - Create a mini-arc with 8-15 exchanges: investigation, discovery, a challenge or encounter, and resolution
            - Remember past player decisions and reference them naturally
            - Track named NPCs and locations the player encounters
            
            INTERACTION RULES:
            - Responses must be concise (2-4 sentences max) and conversational for voice
            - No complex formatting, emojis, asterisks, or special characters
            - Accept player creativity and improvisation - adapt the story accordingly
            - If the player's action is unclear, ask for clarification
            - CRITICAL: NEVER speak as the player or produce the player's lines. Do not write first-person player actions like "I will help the village." Your responses must ONLY contain GM narration from third-person perspective and ALWAYS end with a question prompting player action (e.g., "What do you do?", "How do you respond?", "Which path do you take?"). Do not include any player dialogue, thoughts, or actions in your responses. If you generate anything that sounds like player speech, STOP and only ask what the player does next.
            - Keep combat simple and narrative-focused (no complex dice mechanics)
            - Create meaningful choices with different consequences
            
            WORLD STATE MANAGEMENT (function-calls only):
            - When something important changes in the world (player HP, inventory, NPC introduced/updated, quest status changes), you MUST call the appropriate function tool to update the backend world state.
            - DO NOT emit WORLD_STATE or WORLD_UPDATE as text in your response — the backend will automatically send the updated world state to the frontend after function calls.
            - Available function tools (use these liberally):
                1) `update_npc(name: str, data: dict)` - Create or update an NPC. `data` must include `role` (string), `attitude` (string), and `alive` (boolean). Optionally include `location` and `description`.
                   Example: When you introduce "Elder Thistlewick", immediately call update_npc(name="Elder Thistlewick", data={"role": "village elder", "attitude": "friendly", "alive": true, "location": "Oakhaven Village", "description": "An elderly man seeking help"})
                3) `give_item(item: dict)` - Add an item to player inventory. `item` must include `name`, optional `qty`, `desc` (description), `durability` (if applicable), `weight`, `value`, etc. Provide rich details for immersive gameplay. Example: give_item(item={"name": "Iron Sword", "qty": 1, "desc": "A sturdy blade forged from iron, sharp and reliable.", "durability": 100, "weight": 5, "value": 50})
                3) `change_hp(amount: int, reason: str = "")` - Add (positive) or subtract (negative) HP from player. Backend clamps to 0 minimum.
                4) `set_player_details(details: dict)` - Set/merge player.details metadata (level, xp, bio, etc.).
                5) `apply_world_patch(patch: dict)` - Apply a generic JSON patch for multiple simultaneous changes (quests, events, locations, etc.).
                   Example: To start a quest, call apply_world_patch(patch={"quests": {"active": [{"name": "Village Creatures", "description": "Strange creatures attacking at night", "status": "active"}]}, "events": ["quest_started"]})
            - NPC identity rule: Always use the same exact name as key when updating an NPC (to avoid duplicates with different spellings).
            - Paragraphs & line breaks: When you produce multi-paragraph narration, include explicit "\n" characters to mark paragraph breaks for frontend rendering. Example:
                "You step into the clearing.\nThe moonlight makes the leaves glitter."

            REMEMBER: You're interacting via voice. Keep it immersive, dramatic, and always push the adventure forward by asking what the player does next.""",
        )
        # Store room reference for broadcasting
        self._room = room
        
        # In-memory JSON world state for this agent instance.
        # This will be modified during the session (player actions, NPCs, locations, quests, etc.)
        self.world_state = {
            "player": {
                "name": "Adventurer",
                "class": "Wanderer",
                "hp": 100,
                "status": "Healthy",
                "attributes": {"Strength": 10, "Intelligence": 10, "Luck": 10},
                "inventory": [],
            },
            "npcs": {},
            "locations": {
                "village": {"description": "A small farming village on the edge of Thornwood.", "paths": ["north_forest"]}
            },
            "events": [],
            "quests": {"active": [], "completed": []},
        }

    def log_world_state(self):
        try:
            logger.info("WORLD_STATE: %s", json.dumps(self.world_state))
        except Exception:
            logger.info("WORLD_STATE (unserializable)\n%r", self.world_state)

    def merge_state(self, patch: dict):
        # shallow recursive merge useful for small patches
        def _merge(dest, src):
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dest.get(k), dict):
                    _merge(dest[k], v)
                else:
                    dest[k] = deepcopy(v)

        _merge(self.world_state, patch)
        logger.info("Applied world state patch: %s", json.dumps(patch))
        self.log_world_state()
        # After state change, broadcast updated state to frontend
        self.broadcast_world_state()

    def broadcast_world_state(self):
        """Send the current world_state to all connected participants via LiveKit data channel."""
        try:
            if not hasattr(self, '_room') or self._room is None:
                logger.debug("No room available to broadcast world_state")
                return
            
            payload = json.dumps(self.world_state).encode('utf-8')
            # Send as a data message with topic "world_state"
            asyncio.create_task(
                self._room.local_participant.publish_data(
                    payload=payload,
                    topic="world_state",
                    reliable=True
                )
            )
            print("Broadcasted world_state to frontend (size=%d bytes)", len(payload))
        except Exception as e:
            logger.exception("Failed to broadcast world_state: %s", e)

    @function_tool
    async def apply_full_world_state(self, state: Optional[dict] = None):
        """Tool: replace the authoritative world state after validation.

        The model may return a full `WORLD_STATE:` JSON after a turn. This tool validates shape minimally and
        replaces `self.world_state` with a deep copy of the provided state.
        """
        if state is None or not isinstance(state, dict):
            return {"error": "state must be a JSON object"}

        # Basic validation: ensure at least a player key exists
        if "player" not in state or not isinstance(state.get("player"), dict):
            return {"error": "state must contain a 'player' object"}

        # Apply as authoritative replacement
        try:
            self.world_state = deepcopy(state)
            logger.info("Applied full WORLD_STATE from assistant")
            self.log_world_state()
            # broadcast authoritative state after a full replace
            self.broadcast_world_state()
            return {"status": "ok", "state": deepcopy(self.world_state)}
        except Exception as e:
            logger.exception("Failed to apply full world state: %s", e)
            return {"error": "failed to apply state"}

    @function_tool
    async def read_world_state(self):
        """Tool: returns the current world state JSON."""
        # Return serializable dict
        return deepcopy(self.world_state)

    @function_tool
    async def apply_world_patch(self, patch: Optional[dict] = None):
        """Tool: apply a JSON patch (dict) to the world state and return the new state."""
        if patch is None or not isinstance(patch, dict):
            return {"error": "patch must be a JSON object"}
        # Reuse merge_state to apply patch and log
        self.merge_state(patch)
        return {"status": "ok", "state": deepcopy(self.world_state)}

    @function_tool
    async def update_npc(self, name: Optional[str] = None, data: Optional[dict] = None):
        """Create or update an NPC in the world state.

        Args:
            name: NPC name (used as the key)
            data: dict with at least `role` (str), `attitude` (str), and `alive` (bool).
                  May include `location` and `description`.
        """
        if not name or not isinstance(name, str):
            return {"error": "name must be a non-empty string"}
        if not isinstance(data, dict):
            return {"error": "data must be an object"}

        # Basic validation
        role = data.get("role")
        attitude = data.get("attitude")
        alive = data.get("alive")
        if not isinstance(role, str) or not isinstance(attitude, str) or not isinstance(alive, bool):
            return {"error": "data must include role (str), attitude (str), and alive (bool)"}

        npcs = self.world_state.setdefault("npcs", {})
        existing = npcs.get(name, {})
        merged = deepcopy(existing)
        # merge provided fields
        for k, v in data.items():
            merged[k] = deepcopy(v)

        npcs[name] = merged
        logger.info("NPC updated: %s -> %s", name, json.dumps(merged))
        self.log_world_state()
        # broadcast change so frontends update immediately
        self.broadcast_world_state()
        return {"status": "ok", "npc": deepcopy(merged)}

    @function_tool
    async def give_item(self, item: Optional[dict] = None):
        """Add an item to the player's inventory. Item should include `name`, and optionally `qty`, `desc`, `durability`, `weight`, `value`, etc. for detailed item information."""
        if not isinstance(item, dict):
            return {"error": "item must be an object"}
        name = item.get("name")
        if not name or not isinstance(name, str):
            return {"error": "item.name must be a non-empty string"}
        qty = int(item.get("qty", 1))
        desc = item.get("desc", "")
        durability = item.get("durability")
        weight = item.get("weight")
        value = item.get("value")

        inv = self.world_state.setdefault("player", {}).setdefault("inventory", [])
        # try to find existing item by name
        for it in inv:
            if isinstance(it, dict) and it.get("name") == name:
                it["qty"] = int(it.get("qty", 1)) + qty
                logger.info("Increased inventory item %s by %s", name, qty)
                self.log_world_state()
                return {"status": "ok", "inventory": deepcopy(inv)}

        new_item = {"name": name, "qty": qty}
        if desc:
            new_item["desc"] = desc
        if durability is not None:
            new_item["durability"] = durability
        if weight is not None:
            new_item["weight"] = weight
        if value is not None:
            new_item["value"] = value
        inv.append(new_item)
        logger.info("Added inventory item %s x%s", name, qty)
        self.log_world_state()
        # broadcast inventory update
        self.broadcast_world_state()
        return {"status": "ok", "inventory": deepcopy(inv)}

    @function_tool
    async def change_hp(self, amount: int = 0, reason: str = ""):
        """Change the player's HP by `amount` (positive or negative). Clamps at 0.

        Returns the new hp and status.
        """
        try:
            amt = int(amount)
        except Exception:
            return {"error": "amount must be an integer"}

        player = self.world_state.setdefault("player", {})
        hp = int(player.get("hp", 0)) + amt
        if hp < 0:
            hp = 0
        player["hp"] = hp
        # simple status rules
        if hp <= 0:
            player["status"] = "Unconscious"
        else:
            player["status"] = "Healthy"

        logger.info("Player HP changed by %s (reason=%s). New hp=%s", amt, reason, hp)
        self.log_world_state()
        # broadcast HP change
        self.broadcast_world_state()
        return {"status": "ok", "hp": hp, "player_status": player.get("status")}

    @function_tool
    async def set_player_details(self, details: Optional[dict] = None):
        """Set or merge the `player.details` object with provided fields (level, xp, bio, etc.)."""
        if not isinstance(details, dict):
            return {"error": "details must be an object"}
        player = self.world_state.setdefault("player", {})
        cur = player.setdefault("details", {})
        for k, v in details.items():
            cur[k] = deepcopy(v)

        logger.info("Player details updated: %s", json.dumps(cur))
        self.log_world_state()
        # broadcast player detail changes
        self.broadcast_world_state()
        return {"status": "ok", "details": deepcopy(cur)}

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
        preemptive_generation=False,
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

    # Create the Assistant instance here so event handlers can reference it
    assistant = Assistant(room=ctx.room)

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
