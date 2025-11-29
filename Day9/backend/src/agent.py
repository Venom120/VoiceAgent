import logging
import json
import asyncio
from typing import Optional
from copy import deepcopy

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
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Import our catalog and order management
import catalog

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self, room=None) -> None:
        super().__init__(
            instructions="""You are a friendly, helpful voice shopping assistant. The user is interacting with you via voice.

                Your role is to help users discover products, answer questions about our catalog, and assist them in placing orders.

                Available Products:
                We have a curated selection of products including:
                - Coffee mugs (ceramic and travel mugs)
                - Clothing (t-shirts and hoodies in various sizes)
                - Accessories (water bottles and caps)

                Key behavioral rules (follow exactly):
                1) Always call the `list_products(filters)` tool whenever the user expresses browsing or searching intent. Do not attempt to guess inventory—use the tool.
                2) Do NOT call `create_order` unless the user explicitly confirms a purchase. Before creating an order, confirm product, quantity, and (if applicable) size and color.
                3) After returning product results to the user, call `update_shopping_state` with `current_products` set to the list you showed. This drives the frontend product panel.
                4) Only set or broadcast `last_order` after an order has actually been created via `create_order`.
                5) When you produce multi-paragraph outputs, include explicit "\n" characters to mark paragraph breaks for frontend rendering. Example:
                    "We have two coffee mugs.\n1) A white stoneware coffee mug for 800 rupees\n2) A black travel coffee mug for 1200 rupees."

                Conversation style:
                - Keep responses short (1-3 sentences) and voice-friendly.
                - Avoid code blocks, lists, emojis, or special formatting—speak plainly.
                - When presenting multiple products, summarize 2-3 items with clear ordinal references ("first", "second").
                - If the product list is empty, say "I couldn't find any matching items" and offer alternatives; do not create or display an order.

                Tools you should use:
                - list_products(filters)
                - create_order(line_items, customer_info)
                - get_last_order()
                - update_shopping_state(state)
                - update_cart(line_items, mode)

                Data guidance:
                - When you call `update_shopping_state`, include `current_products` (list of shown products) and optionally `cart` if the user indicates intent to buy later.
                - Ensure `last_order.items` is a non-empty array when returning orders.

                Failure modes:
                - If a requested product cannot be found, ask a follow-up (e.g., "I couldn't find that color—would you like a different color or size?").
                - If the user asks to buy but hasn't confirmed size/quantity, ask for those details first.

                Remember: Use tools for catalog and orders. Don't create orders unless explicitly asked and confirmed. Keep the user informed and confirm before finalizing.""",
        )
        # Store room reference for broadcasting
        self._room = room
        
        # Shopping session state
        self.shopping_state = {
            "current_products": [],  # Products currently shown to user
            "cart": [],  # Items user is considering
            "last_order": None,  # Most recent order
        }
    
    def broadcast_shopping_state(self):
        """Send the current shopping_state to frontend via LiveKit data channel."""
        try:
            if not hasattr(self, '_room') or self._room is None:
                logger.debug("No room available to broadcast shopping_state")
                return
            
            payload = json.dumps(self.shopping_state).encode('utf-8')
            asyncio.create_task(
                self._room.local_participant.publish_data(
                    payload=payload,
                    topic="shopping_state",
                    reliable=True
                )
            )
            logger.info(f"Broadcasted shopping_state to frontend (size={len(payload)} bytes)")
        except Exception as e:
            logger.exception(f"Failed to broadcast shopping_state: {e}")

    @function_tool
    async def list_products(self, filters: Optional[dict] = None):
        """
        Browse or search the product catalog with optional filters.
        
        Args:
            filters: Optional dict with keys:
                - category: str (e.g., "mug", "clothing", "accessories")
                - max_price: int (in INR)
                - color: str (e.g., "black", "white", "blue")
                - search: str (search term for name/description)
        
        Returns:
            List of product dictionaries with id, name, description, price, etc.
        """
        logger.info(f"list_products called with filters: {filters}")
        products = catalog.list_products(filters)
        
        # Update shopping state with current products
        self.shopping_state["current_products"] = products
        self.broadcast_shopping_state()
        
        return {"products": products, "count": len(products)}

    @function_tool
    async def create_order(self, line_items: list[dict], customer_info: Optional[dict] = None):
        """
        Create an order for the user.
        
        Args:
            line_items: List of items to order, each with:
                - product_id: str (required)
                - quantity: int (default 1)
                - size: str (optional, for clothing items)
            customer_info: Optional customer details
        
        Returns:
            Order object with id, items, total, currency, created_at
        """
        # If no explicit line_items passed, try to use the current cart
        items_to_use = line_items or self.shopping_state.get("cart", [])
        logger.info(f"create_order called with {len(items_to_use)} items (cart fallback)")

        # If there's an existing last_order that matches a stored order, update it instead of creating a new one
        existing_order = self.shopping_state.get("last_order")
        if existing_order and catalog.get_order_by_id(existing_order.get("id")):
            logger.info(f"Updating existing order {existing_order.get('id')} instead of creating new one")
            updated = catalog.update_order(existing_order.get("id"), items_to_use, customer_info)
            if updated:
                self.shopping_state["last_order"] = updated
                self.shopping_state["cart"] = []
                self.broadcast_shopping_state()
                return {"order": updated, "status": "updated"}
            else:
                return {"error": "failed_to_update_order"}

        # Otherwise create a new order
        if not items_to_use:
            return {"error": "no_items_to_order"}

        order = catalog.create_order(items_to_use, customer_info)

        # Update shopping state (finalized order)
        self.shopping_state["last_order"] = order
        self.shopping_state["cart"] = []  # Clear cart after order
        self.broadcast_shopping_state()

        return {"order": order, "status": "created"}

    @function_tool
    async def get_last_order(self):
        """
        Get the most recent order placed by the user.
        
        Returns:
            The last order object or None if no orders exist
        """
        logger.info("get_last_order called")
        order = catalog.get_last_order()
        return {"order": order}

    @function_tool
    async def update_cart(self, line_items: Optional[list[dict]] = None, mode: str = "replace"):
        """
        Update the in-session shopping cart displayed to the user.

        Args:
            line_items: List of items to add or replace in the cart
            mode: 'replace' (default) to replace the cart, 'add' to append/merge quantities, 'remove' to remove items by product_id
        """
        logger.info(f"update_cart called mode={mode} items={len(line_items or [])}")
        if line_items is None:
            return {"cart": deepcopy(self.shopping_state.get("cart", []))}

        if mode == "replace":
            self.shopping_state["cart"] = line_items
        elif mode == "add":
            # naive merge: add quantities for same product_id
            existing = {it["product_id"]: it for it in self.shopping_state.get("cart", [])}
            for it in line_items:
                pid = it.get("product_id")
                if not pid:
                    continue
                if pid in existing:
                    existing[pid]["quantity"] = existing[pid].get("quantity", 1) + it.get("quantity", 1)
                else:
                    existing[pid] = it
            self.shopping_state["cart"] = list(existing.values())
        elif mode == "remove":
            to_remove = {it.get("product_id") for it in line_items if it.get("product_id")}
            self.shopping_state["cart"] = [it for it in self.shopping_state.get("cart", []) if it.get("product_id") not in to_remove]
        else:
            return {"error": "unknown_mode"}

        self.broadcast_shopping_state()
        return {"status": "ok", "cart": deepcopy(self.shopping_state.get("cart", []))}

    @function_tool
    async def get_cart(self):
        """Return the current in-session cart."""
        return {"cart": deepcopy(self.shopping_state.get("cart", []))}

    @function_tool
    async def update_order(self, order_id: str, line_items: list[dict], customer_info: Optional[dict] = None):
        """Update an existing stored order (merchant-side) and broadcast the updated order."""
        logger.info(f"update_order called for {order_id} with {len(line_items)} items")
        updated = catalog.update_order(order_id, line_items, customer_info)
        if not updated:
            return {"error": "order_not_found"}

        # Update session state if this is the last order
        if self.shopping_state.get("last_order") and self.shopping_state["last_order"].get("id") == order_id:
            self.shopping_state["last_order"] = updated
        self.broadcast_shopping_state()
        return {"order": updated, "status": "updated"}

    @function_tool
    async def update_shopping_state(self, state: dict):
        """
        Update the shopping state that's displayed on the frontend.
        
        Args:
            state: Dict with keys like current_products, cart, etc.
        
        Returns:
            Updated shopping state
        """
        logger.info(f"update_shopping_state called with: {state}")
        
        # Merge state updates
        for key, value in state.items():
            if key in self.shopping_state:
                self.shopping_state[key] = value
        
        self.broadcast_shopping_state()
        
        return {"status": "success", "state": self.shopping_state}


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
    # Pass the room to the Assistant so it can broadcast shopping state
    await session.start(
        agent=Assistant(room=ctx.room),
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
