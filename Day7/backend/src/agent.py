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
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from order_manager import Catalog, Cart, OrderManager, ingredients_for, save_pending_cart, load_pending_cart, delete_pending_cart
import uuid


# Global helpers (one per process)
CARTS: dict = {}
CAT = Catalog()
OM = OrderManager()

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="""
            You are a friendly food & grocery ordering assistant for a quick-commerce store. The user interacts by voice.

            Capabilities you must provide:
            - Greet the user and explain you can help order groceries and simple meal ingredients.
            - Ask clarifying questions when needed (size, brand, quantity, dietary constraints).
            - Maintain a cart during the conversation (items, quantities, options).
            - Support operations: add item, remove item, update quantity, list cart, and confirm each change.
            - Support higher-level requests like "ingredients for X" by mapping dishes to multiple catalog items and adding them to the cart.
            - Answer product detail questions (size, weight, brand, unit, description) when asked about an item.
            - Support listing ingredients by category. If a user asks to "list all ingredients" or similar, immediately present the available categories (queried from the catalog) rather than inventing or guessing categories.
            - When the user says they are done (examples: "place my order", "that's all", "i'm done"), confirm the final cart and total, then place the order by persisting it to the database and saving an order JSON file.
            - Support order tracking and history queries: return current order status and previous orders when asked.

            Behavior:
            - Keep responses concise and conversational. Ask one clarifying question at a time when ambiguous.
            - Confirm cart changes explicitly (e.g., "Added 2 x Whole Wheat Bread to your cart. Your total is $X").
            - When placing an order, collect simple customer info if needed (name/address), confirm the saved order id, and mention that the order is stored.

            Product details:
            - If the user asks about the size, weight, brand, unit, or description of a product ("What's the size and weight of pasta?"), return the item's details from the catalog when available.
            - If the catalog doesn't contain the requested detail, say you don't have that information and offer to add the item to the cart instead.

            Quantity suggestions:
            - If the user asks "Can you suggest [quantity]?" or asks for a suggested quantity, ask a clarifying follow-up: either the number of family members or what dish they are making.
            - If the user doesn't provide that context after one prompt, default to suggesting 1 unit for that item and proceed.

            Listing ingredients by category:
            - When asked to list ingredients or browse the catalog, call the `list_ingredients` tool with no category to retrieve available categories and present them to the user in one sentence (e.g. "Available categories: Produce, Groceries, Snacks...").
            - When the user selects a category, call `list_ingredients` with the provided category. Use the tool's canonical category name. If the tool returns no items, do not invent items; instead present the available categories returned by the tool and offer alternatives or ask a clarifying question.
            - Use the tool-provided responses (categories, suggestions) verbatim—don't fabricate additional categories or items.

            Implementation notes (for the agent runtime):
            - Use the provided catalog and order manager tools to read catalog items, modify the per-room cart, persist orders to SQLite/JSON, and read/advance order status.
            - If a requested item is not found, ask a clarifying question or offer alternatives.
            """,
        )
        # unique session key for pending cart persistence (falls back to room when available)
        self._session_key = str(uuid.uuid4())
        # initialize an in-memory cart for this Assistant instance
        self._cart = Cart(CAT)

    def _get_session_key(self, context: RunContext) -> str:
        """Return a deterministic session key for pending cart persistence.

        Prefer the live room name when available; fall back to the assistant UUID.
        """
        room = getattr(context, "room", None)
        if room is not None and getattr(room, "name", None):
            return room.name
        return self._session_key

    def _rehydrate_cart(self, session_key: str) -> None:
        """Load pending cart snapshot (if any) and replace the in-memory cart.

        This guarantees the Assistant uses the latest persisted cart across
        requests/workers. If the DB has an empty list, the cart will be reset.
        """
        try:
            cart_list = load_pending_cart(session_key)
        except Exception:
            logger.exception("failed to load pending cart for %s", session_key)
            return
        # If the DB has an explicit empty snapshot ([]) we still reset the cart
        if cart_list is None:
            return
        # Replace the in-memory cart with the persisted snapshot
        self._cart = Cart(CAT)
        for it in cart_list:
            try:
                item_id = it.get("id")
                qty = int(it.get("quantity", 0))
                if item_id and qty > 0:
                    # populate internal mapping directly
                    self._cart.items[item_id] = qty
            except Exception:
                logger.exception("failed to rehydrate cart item %s", it)
        logger.debug("rehydrated cart for %s -> %s", session_key, self._cart.list())

    # Cart and order tools exposed to the LLM as function tools
    @function_tool
    async def add_item(self, context: RunContext, item: str, quantity: int = 1):
        """Add an item to the current room's cart."""
        # Use a consistent session key and rehydrate the in-memory cart first
        session_key = self._get_session_key(context)
        self._rehydrate_cart(session_key)
        cart = self._cart
        ok, msg = cart.add(item, quantity)
        # persist pending cart snapshot
        try:
            save_pending_cart(session_key, cart.list())
            logger.debug("saved pending cart for %s -> %s", session_key, cart.list())
        except Exception:
            logger.exception("failed to save pending cart")
        return {"success": ok, "message": msg, "cart": cart.list(), "total": cart.total()}

    @function_tool
    async def remove_item(self, context: RunContext, item: str):
        """Remove an item from the cart."""
        session_key = self._get_session_key(context)
        self._rehydrate_cart(session_key)
        cart = self._cart
        ok, msg = cart.remove(item)
        try:
            save_pending_cart(session_key, cart.list())
            logger.debug("saved pending cart for %s -> %s", session_key, cart.list())
        except Exception:
            logger.exception("failed to save pending cart")
        return {"success": ok, "message": msg, "cart": cart.list(), "total": cart.total()}

    @function_tool
    async def update_quantity(self, context: RunContext, item: str, quantity: int):
        """Update quantity for an item in the cart."""
        session_key = self._get_session_key(context)
        self._rehydrate_cart(session_key)
        cart = self._cart
        ok, msg = cart.update(item, quantity)
        try:
            save_pending_cart(session_key, cart.list())
            logger.debug("saved pending cart for %s -> %s", session_key, cart.list())
        except Exception:
            logger.exception("failed to save pending cart")
        return {"success": ok, "message": msg, "cart": cart.list(), "total": cart.total()}

    @function_tool
    async def list_cart(self, context: RunContext):
        """Return the current cart contents."""
        session_key = self._get_session_key(context)
        self._rehydrate_cart(session_key)
        cart = self._cart
        return {"cart": cart.list(), "total": cart.total()}

    @function_tool
    async def item_details(self, context: RunContext, item: str):
        """Return product details (size, weight, brand, unit, description) for an item."""
        # Try to resolve item from catalog
        it = CAT.find_by_name(item)
        if not it:
            return {"found": False, "message": f"Item '{item}' not found in catalog."}
        details = {}
        # Use catalog-provided fields when available
        details["id"] = it.get("id")
        details["name"] = it.get("name")
        if "price" in it:
            try:
                details["price"] = float(it.get("price", 0))
            except Exception:
                details["price"] = it.get("price")
        for f in ("brand", "size", "weight", "unit", "description"):
            if f in it:
                details[f] = it.get(f)
        details["tags"] = it.get("tags", [])
        return {"found": True, "details": details}

    @function_tool
    async def suggest_quantity(self, context: RunContext, item: str):
        """Return a suggested quantity for an item or request clarifying context.

        Behavior:
        - If the assistant can infer from common units (e.g., packs, loaves), suggest 1 pack/loaf by default.
        - Otherwise ask the user: "How many people will this serve, or what are you making?" and return a prompt. If that context isn't provided, default to 1.
        """
        it = CAT.find_by_name(item)
        if not it:
            return {"found": False, "message": f"Item '{item}' not found in catalog."}

        unit = it.get("unit") or it.get("units") or "unit"
        # Simple heuristics: if unit is a pack/loaf/jar/bottle, recommend 1; if unit is count and price small, suggest 3
        if unit in ("pack", "loaf", "jar", "bottle", "cup", "bag", "container", "item", "bulb"): 
            return {"found": True, "suggested": 1, "reason": f"Typical purchase: 1 {unit}"}

        if unit in ("count",):
            # prefer to ask for clarification (servings/family size), but give a default suggestion
            return {"found": True, "needs_context": True, "prompt": "How many people will this serve, or what dish are you making? If unsure, I suggest 1.", "suggested": 1}

        # fallback default
        return {"found": True, "suggested": 1, "reason": "Default suggestion"}

    @function_tool
    async def list_ingredients(self, context: RunContext, category: str = ""):
        """List items by category. If category is empty, return available categories and ask the user to pick one."""
        # If user didn't provide a category, return categories so the assistant can ask follow-up
        if not category:
            cats = CAT.categories()
            return {"need_category": True, "categories": cats, "message": "Which category would you like to browse?"}
        # Resolve user-provided category to a canonical catalog category (supports aliases like 'fruits')
        canonical = CAT.resolve_category(category)
        suggestions = []
        if not canonical:
            # try a case-insensitive direct hit on available categories
            cats = CAT.categories()
            lc = category.lower().strip()
            for c in cats:
                if lc in c.lower() or c.lower() in lc:
                    suggestions.append(c)
            # if we have a single suggestion, use it
            if len(suggestions) == 1:
                canonical = suggestions[0]

        if not canonical:
            return {"found": False, "message": f"No items found for category '{category}'.", "categories": CAT.categories(), "suggestions": suggestions}

        items = CAT.items_by_category(canonical)
        if not items:
            return {"found": False, "message": f"No items found for category '{canonical}'.", "categories": CAT.categories(), "suggestions": suggestions}

        # Return a friendly list of items (id,name,price,size/unit)
        out = []
        for it in items:
            out.append({
                "id": it.get("id"),
                "name": it.get("name"),
                "price": it.get("price"),
                "size": it.get("size"),
                "unit": it.get("unit"),
            })
        return {"found": True, "category": canonical, "items": out}

    @function_tool
    async def ingredients_for(self, context: RunContext, dish: str, servings: int = 1):
        """Add ingredients for a named dish to the cart using recipe mapping."""
        session_key = self._get_session_key(context)
        self._rehydrate_cart(session_key)
        cart = self._cart
        parts = ingredients_for(dish, servings)
        added = []
        for item_id, qty in parts:
            it = CAT.get(item_id)
            if it:
                cart.add(it["id"], qty)
                added.append({"id": it["id"], "name": it["name"], "quantity": qty})
        # persist pending cart snapshot
        try:
            save_pending_cart(session_key, cart.list())
            logger.debug("saved pending cart for %s -> %s", session_key, cart.list())
        except Exception:
            logger.exception("failed to save pending cart")
        return {"added": added, "cart": cart.list(), "total": cart.total()}

    @function_tool
    async def place_order(self, context: RunContext, customer_name: str = "", customer_address: str = ""):
        """Place the current cart as an order and persist to DB/JSON."""
        session_key = self._get_session_key(context)
        # ensure we are operating on the persisted snapshot
        self._rehydrate_cart(session_key)
        cart = self._cart
        if not cart.list():
            return {"success": False, "message": "Cart is empty"}
        # Require customer info before finalizing the order. If missing, ask for it and do not clear the cart.
        if not customer_name or not customer_address:
            return {
                "success": False,
                "needs_customer_info": True,
                "message": "Please confirm your name and address before I place the order.",
                "cart": cart.list(),
                "total": cart.total(),
            }

        res = OM.place_order(cart, customer_name=customer_name, customer_address=customer_address)
        # clear cart after successful placing and remove pending snapshot
        try:
            delete_pending_cart(session_key)
        except Exception:
            logger.exception("failed to delete pending cart")
        # reset in-memory cart
        self._cart = Cart(CAT)
        return {"success": True, "order_id": res["order_id"], "order_path": res["path"], "order": res["order"]}

    @function_tool
    async def track_order(self, context: RunContext, order_id: int):
        """Return current status and items for an order id."""
        o = OM.get_order(order_id)
        if not o:
            return {"found": False}
        return {"found": True, "order": o}

    @function_tool
    async def advance_order(self, context: RunContext, order_id: int):
        """Advance order status to the next step (mock)."""
        new = OM.advance_status(order_id)
        if new is None:
            return {"success": False, "message": "Order not found"}
        return {"success": True, "new_status": new}

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
                model="gemini-2.0-flash",
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
