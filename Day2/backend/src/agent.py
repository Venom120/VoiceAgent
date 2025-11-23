import logging
import json
import sqlite3
import uuid
from typing import Optional
from pathlib import Path
from datetime import datetime

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
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are "Venom" a friendly barista of `Venom's Coffee` shop .
                The user interacts by voice. Your job is to take a coffee order, ask clarifying questions until the order is complete, and then save the order.

                Order state must follow this JSON shape exactly:
                {
                    "drinkType": "string",
                    "size": "string",
                    "milk": "string",
                    "extras": ["string"],
                    "name": "string"
                }

                Behavior:
                - If the user only greets (for example: "hi", "hello", "hey"), respond with a short friendly salutation and then immediately ask for the order. Example salutation: "Hi there. Welcome to Venom's Coffee. What can I get started for you today?" Then proceed by asking the first clarifying question such as "What drink would you like?"
                - Ask concise, friendly clarifying questions until every field is filled.
                - Do not use emojis or extra punctuation.
                - When the order is complete, call the function tool `save_order` with the full order JSON (exact shape above).
                - If the customer asks to repeat a previous order, ask for their name and call the function tool `load_orders` with that name; read back the most recent matching order.
                - After the tool confirms saving, speak a short, neat text summary of the saved order for the customer (one or two sentences).

                Example Qs: What drink would you like?; What size? small, medium, or large?; Any milk preference?; Any extras (vanilla, caramel, extra shot)?; What's the name for the order?""",
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
    async def save_order(context: RunContext, order: dict):
        """
        Save a finalized order into a single SQLite database and return a short text summary
        along with the record id.

        Schema (table `orders`):
        id TEXT PRIMARY KEY,
        name TEXT,
        orders TEXT  -- JSON mapping date -> [order objects]

        Behavior:
        - If a row with the same name exists, append to the most recently-updated row for that name.
        - If not, create a new row with a generated UUID id.
        - Orders are grouped under a date key (ISO date). If the date key exists, append to its list.

        Returns: dict {"id": <id>, "summary": <text>} on success, or an error string on failure.
        """
        # Validate minimal shape
        required = ["drinkType", "size", "milk", "extras", "name"]
        for k in required:
            if k not in order:
                return f"Error: missing field {k} in order"

        db_path = Path(__file__).resolve().parent.parent / "orders.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        def ensure_db(conn: sqlite3.Connection):
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    orders TEXT
                )
                """
            )

        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            ensure_db(conn)
            cur = conn.cursor()

            name = (order.get("name") or "").strip()
            # find most recent row for this name (by rowid desc)
            cur.execute("SELECT id, orders FROM orders WHERE lower(name)=? ORDER BY rowid DESC LIMIT 1", (name.lower(),))
            row = cur.fetchone()

            date_key = datetime.utcnow().date().isoformat()

            if row:
                rec_id, orders_json = row[0], row[1]
                try:
                    orders_obj = json.loads(orders_json) if orders_json else {}
                except Exception:
                    orders_obj = {}

                if date_key in orders_obj:
                    orders_obj[date_key].append(order)
                else:
                    orders_obj[date_key] = [order]

                cur.execute("UPDATE orders SET orders=? WHERE id=?", (json.dumps(orders_obj), rec_id))
                conn.commit()
                summary = (
                    f"Saved order for {name}: {order.get('size')} {order.get('drinkType')} ({order.get('milk')})"
                    + (" with " + ", ".join(order.get("extras") or [] ) if (order.get("extras")) else "")
                    + "."
                )
                return {"id": rec_id, "summary": summary}

            # no existing record, create one
            rec_id = uuid.uuid4().hex
            orders_obj = {date_key: [order]}
            cur.execute("INSERT INTO orders (id, name, orders) VALUES (?, ?, ?)", (rec_id, name, json.dumps(orders_obj)))
            conn.commit()

            summary = (
                f"Saved order for {name}: {order.get('size')} {order.get('drinkType')} ({order.get('milk')})"
                + (" with " + ", ".join(order.get("extras") or [] ) if (order.get("extras")) else "")
                + "."
            )

            return {"id": rec_id, "summary": summary}
        except Exception as e:
            logger.exception("Failed saving order")
            return f"Error saving order: {e}"
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass


    @function_tool
    async def load_orders(context: RunContext, name: Optional[str] = None, most_recent: bool = True):
        """
        Load orders by name or list most-recent orders per name.

        Args:
        name: If provided, returns the most recent order for that name (and the record id).
              If multiple records exist for that name, returns the most recent one.
        If name is None or empty, returns a list of most-recent orders for all names with their ids.

        Returns:
        If most_recent True and name provided: dict {"id": id, "name": name, "order": <order dict>}
        If name is None: list of {"id": id, "name": name, "most_recent_order": {...}}
        Or an error string if nothing found.
        """
        db_path = Path(__file__).resolve().parent.parent / "orders.db"
        if not db_path.exists():
            return "No orders database found."

        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()

            if not name:
                # list most recent order for each name
                cur.execute("SELECT id, name, orders FROM orders")
                rows = cur.fetchall()
                if not rows:
                    return "No orders in database."

                result = []
                for rec_id, rec_name, orders_json in rows:
                    try:
                        orders_obj = json.loads(orders_json) if orders_json else {}
                    except Exception:
                        continue

                    # find most recent date key
                    if not orders_obj:
                        continue
                    latest_date = sorted(orders_obj.keys(), reverse=True)[0]
                    latest_order = orders_obj[latest_date][-1]
                    result.append({"id": rec_id, "name": rec_name, "most_recent_order": latest_order})

                if not result:
                    return "No valid orders found."
                return result

            # name provided: find rows matching this name (case-insensitive)
            search = (name or "").strip()
            cur.execute("SELECT id, name, orders FROM orders WHERE lower(name)=? ORDER BY rowid DESC", (search.lower(),))
            rows = cur.fetchall()
            if not rows:
                return f"No orders found for {name}."

            # pick most recent record (first row)
            rec_id, rec_name, orders_json = rows[0]
            try:
                orders_obj = json.loads(orders_json) if orders_json else {}
            except Exception:
                return f"Orders for {name} are corrupted."

            if not orders_obj:
                return f"No orders found for {name}."

            latest_date = sorted(orders_obj.keys(), reverse=True)[0]
            latest_order = orders_obj[latest_date][-1]

            return {"id": rec_id, "name": rec_name, "order": latest_order}
        except Exception as e:
            logger.exception("Failed loading orders")
            return f"Error loading orders: {e}"
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass


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
            text_pacing=True,
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
