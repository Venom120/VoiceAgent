import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import tempfile
import shutil

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
    RunContext
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Load FAQ and company data
FAQ_PATH = Path(__file__).resolve().parents[1] / "data" / "ericsson_details.json"
LEADS_PATH = Path(__file__).resolve().parents[1] / "data" / "user_responses.json"


def load_faq_data():
    """Load Ericsson FAQ and company information from JSON file."""
    try:
        with open(FAQ_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"FAQ file not found at {FAQ_PATH}")
        return {"company": {}, "faqs": []}
    except Exception as e:
        logger.exception(f"Failed to load FAQ data: {e}")
        return {"company": {}, "faqs": []}


def load_leads():
    """Load existing leads from JSON file."""
    try:
        with open(LEADS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"leads": []}
    except Exception as e:
        logger.exception(f"Failed to load leads: {e}")
        return {"leads": []}


def save_leads(leads_data):
    """Atomically save leads data back to JSON file."""
    try:
        dirpath = LEADS_PATH.parent
        with tempfile.NamedTemporaryFile('w', delete=False, dir=str(dirpath), encoding='utf-8') as tf:
            json.dump(leads_data, tf, indent=2, ensure_ascii=False)
            temp_name = tf.name
        shutil.move(temp_name, str(LEADS_PATH))
        return True
    except Exception as e:
        logger.exception(f"Failed to save leads: {e}")
        return False


class EricssonSDRAgent(Agent):
    """Sales Development Representative agent for Ericsson India."""
    
    def __init__(self, lead_data: Optional[dict] = None) -> None:
        # Initialize or load lead data
        if lead_data is None:
            self.lead_data = {
                "name": None,
                "company": None,
                "email": None,
                "role": None,
                "use_case": None,
                "team_size": None,
                "timeline": None,
                "questions_asked": [],
                "conversation_start": datetime.now().isoformat(),
            }
        else:
            self.lead_data = lead_data
        
        # Preload FAQ data for faster responses
        self.faq_data = load_faq_data()
        
        super().__init__(
            instructions="""You are a professional and friendly Sales Development Representative (SDR) for Ericsson India, 
            a global leader in telecommunications and enterprise 5G solutions.

            Your main objectives are:
            1. Greet the visitor warmly and professionally
            2. Ask what brought them here and understand their business needs
            3. Answer questions about Ericsson's products, services, and solutions using the FAQ data
            4. Naturally collect lead information during the conversation (name, company, email, role, use case, team size, timeline)
            5. Keep the conversation focused on understanding the prospect's needs and qualifying them
            
            Key Ericsson offerings to highlight:
            - Private 5G networks for enterprises
            - IoT and industrial automation solutions
            - Enterprise wireless connectivity
            - Network APIs and edge computing
            
            Guidelines:
            - Be conversational and natural - don't interrogate
            - Use tools to search FAQs when prospects ask about products, pricing, or capabilities
            - Store lead information as you collect it using the save_lead_field tool
            - When you detect the conversation is ending, provide a summary and thank them
            - Keep responses concise and professional for voice interaction
            - Avoid complex formatting, emojis, or symbols
            
            The user is interacting via voice, so be warm, engaging, and professional.""",
        )
    
    async def on_enter(self) -> None:
        """Greet the user when the agent becomes active."""
        await self.session.generate_reply(
            instructions=(
                "Greet the visitor warmly, introduce yourself as an SDR from Ericsson India, "
                "and ask what brought them here today or what they're working on. Be friendly and professional."
            )
        )
    
    @function_tool
    async def search_faq(self, context: RunContext, query: str):
        """Search the Ericsson FAQ database for relevant information.
        
        Args:
            query: The question or topic to search for (e.g., 'private 5G', 'pricing', 'IoT solutions', 'what does Ericsson do')
        """
        query_lower = query.lower()
        results = []
        
        # Search through FAQs
        for faq in self.faq_data.get("faqs", []):
            question = faq.get("question", "").lower()
            answer = faq.get("answer", "")
            category = faq.get("category", "")
            
            # Simple keyword matching
            if query_lower in question or any(word in question for word in query_lower.split()):
                results.append({
                    "question": faq.get("question"),
                    "answer": answer,
                    "category": category
                })
        
        # Also search in answer text if no question matches
        if len(results) == 0:
            for faq in self.faq_data.get("faqs", []):
                answer = faq.get("answer", "").lower()
                if query_lower in answer or any(word in answer for word in query_lower.split()):
                    results.append({
                        "question": faq.get("question"),
                        "answer": faq.get("answer"),
                        "category": faq.get("category")
                    })
        
        # Track questions asked
        if query not in self.lead_data["questions_asked"]:
            self.lead_data["questions_asked"].append(query)
        
        if results:
            logger.info(f"Found {len(results)} FAQ results for query: {query}")
            return json.dumps(results[:3])  # Return top 3 results
        else:
            logger.info(f"No FAQ results found for query: {query}")
            return json.dumps({
                "message": "I don't have specific information on that, but I can connect you with our solutions team for detailed information."
            })
    
    @function_tool
    async def get_company_info(self, context: RunContext):
        """Get general information about Ericsson India - what they do, industries served, focus areas."""
        company_data = self.faq_data.get("company", {})
        return json.dumps(company_data)
    
    @function_tool
    async def get_use_cases(self, context: RunContext, industry: Optional[str] = None):
        """Get real-world use cases and success stories.
        
        Args:
            industry: Optional specific industry to filter by (e.g., 'manufacturing', 'logistics', 'ports')
        """
        use_cases = self.faq_data.get("use_cases", [])
        
        if industry:
            industry_lower = industry.lower()
            filtered = [uc for uc in use_cases if industry_lower in uc.get("industry", "").lower()]
            return json.dumps(filtered if filtered else use_cases)
        
        return json.dumps(use_cases)
    
    @function_tool
    async def save_lead_field(self, context: RunContext, field: str, value: str):
        """Save a lead information field.
        
        Args:
            field: The field name - must be one of: name, company, email, role, use_case, team_size, timeline
            value: The value to store for this field
        """
        valid_fields = ["name", "company", "email", "role", "use_case", "team_size", "timeline"]
        
        if field not in valid_fields:
            return json.dumps({"error": f"Invalid field. Must be one of: {', '.join(valid_fields)}"})
        
        self.lead_data[field] = value
        logger.info(f"Saved lead field: {field} = {value}")
        
        return json.dumps({"status": "saved", "field": field, "value": value})
    
    @function_tool
    async def get_lead_summary(self, context: RunContext):
        """Get a summary of collected lead information. Use this when the conversation is ending."""
        return json.dumps(self.lead_data)
    
    @function_tool
    async def finalize_lead(self, context: RunContext):
        """Finalize and save the lead to the database. Call this when the conversation is ending.
        
        This will:
        1. Add a timestamp
        2. Save the lead to the leads database
        3. Return a summary for the agent to communicate to the user
        """
        # Add end timestamp
        self.lead_data["conversation_end"] = datetime.now().isoformat()
        
        # Load existing leads
        leads_db = load_leads()
        
        # Add new lead
        leads_db["leads"].append(self.lead_data)
        
        # Save to file
        success = save_leads(leads_db)
        
        if success:
            logger.info(f"Lead saved successfully: {self.lead_data.get('name', 'Unknown')}")
            
            # Create summary for agent
            summary = {
                "status": "saved",
                "lead_name": self.lead_data.get("name", "Not provided"),
                "company": self.lead_data.get("company", "Not provided"),
                "email": self.lead_data.get("email", "Not provided"),
                "role": self.lead_data.get("role", "Not provided"),
                "use_case": self.lead_data.get("use_case", "Not provided"),
                "team_size": self.lead_data.get("team_size", "Not provided"),
                "timeline": self.lead_data.get("timeline", "Not provided"),
                "questions_count": len(self.lead_data["questions_asked"])
            }
            
            return json.dumps(summary)
        else:
            logger.error("Failed to save lead")
            return json.dumps({"status": "error", "message": "Failed to save lead information"})


def prewarm(proc: JobProcess):
    """Prewarm models and load FAQ data for faster response times."""
    proc.userdata["vad"] = silero.VAD.load()
    # Preload FAQ data
    proc.userdata["faq_data"] = load_faq_data()
    logger.info("FAQ data preloaded successfully")


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
    await session.start(
        agent=EricssonSDRAgent(),
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
