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

# Load FAQ and company data paths
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ERICSSON_FAQ_PATH = DATA_DIR / "ericsson_details.json"
TARITAS_FAQ_PATH = DATA_DIR / "taritas_details.json"
INNOGATIVE_FAQ_PATH = DATA_DIR / "innogative_details.json"
LEADS_PATH = DATA_DIR / "user_responses.json"


def load_faq_data(company: str = "ericsson"):
    """Load FAQ and company information from JSON file for specified company.
    
    Args:
        company: Company name - 'ericsson', 'taritas', or 'innogative'
    """
    faq_paths = {
        "ericsson": ERICSSON_FAQ_PATH,
        "taritas": TARITAS_FAQ_PATH,
        "innogative": INNOGATIVE_FAQ_PATH
    }
    
    faq_path = faq_paths.get(company.lower(), ERICSSON_FAQ_PATH)
    
    try:
        with open(faq_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"FAQ file not found at {faq_path}")
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


class GreeterAgent(Agent):
    """Initial agent that greets user and helps them choose which company to speak with."""
    
    def __init__(self, chat_ctx=None, tts=None) -> None:
        super().__init__(
            instructions="""You are a friendly receptionist helping visitors connect with the right Sales Development Representative.
            
            You work with three companies:
            1. Ericsson India - Enterprise 5G solutions, Private 5G networks, IoT, and telecommunications
            2. Taritas Software Solutions - Custom software development, mobile apps, blockchain consulting  
            3. Innogative - Web development, digital marketing, social media marketing
            
            Your role is to:
            - Greet visitors warmly and professionally
            - Ask which company they'd like to speak with
            - Use the connect_to_company tool to transfer them to the appropriate SDR
            
            Keep your responses concise and friendly. Avoid complex formatting, emojis, or symbols.
            The user is interacting via voice.""",
            chat_ctx=chat_ctx,
            tts=tts,
        )
    
    async def on_enter(self) -> None:
        """Greet the user when the agent becomes active."""
        await self.session.generate_reply(
            instructions=(
                "Greet the visitor warmly and introduce yourself as a receptionist. "
                "Let them know you can connect them with SDRs from Ericsson India, Taritas Software Solutions, or Innogative. "
                "Ask which company they'd like to speak with."
            )
        )
    
    @function_tool
    async def connect_to_company(self, context: RunContext, company: str):
        """Connect the user to a specific company's SDR agent.
        
        Args:
            company: The company name - must be 'ericsson', 'taritas', or 'innogative'
        """
        company = company.lower().strip()
        
        if company not in ['ericsson', 'taritas', 'innogative']:
            return f"Sorry, I don't recognize '{company}'. Please choose 'Ericsson', 'Taritas', or 'Innogative'."
        
        logger.info(f"Connecting to {company} SDR agent")
        
        # Return the appropriate SDR agent based on company selection
        if company == 'ericsson':
            return (
                EricssonSDRAgent(chat_ctx=self.chat_ctx, tts=self.tts),
                f"Connecting you to an Ericsson India representative.",
            )
        elif company == 'taritas':
            return (
                TaritasSDRAgent(chat_ctx=self.chat_ctx, tts=self.tts),
                f"Connecting you to a Taritas Software Solutions representative.",
            )
        elif company == 'innogative':
            return (
                InnogativeSDRAgent(chat_ctx=self.chat_ctx, tts=self.tts),
                f"Connecting you to an Innogative representative.",
            )


class EricssonSDRAgent(Agent):
    """Sales Development Representative agent for Ericsson India."""
    
    def __init__(self, lead_data: Optional[dict] = None, chat_ctx=None, tts=None) -> None:
        # Initialize or load lead data
        if lead_data is None:
            self.lead_data = {
                "company_spoken_with": "Ericsson India",
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
        self.faq_data = load_faq_data("ericsson")
        
        super().__init__(
            instructions="""You are a professional and friendly Sales Development Representative (SDR) for Ericsson India, 
            a global leader in telecommunications and enterprise 5G solutions.

            Core flow:
            1. Warm greeting + brief positioning (Ericsson + enterprise 5G / IoT)
            2. Ask an open question about their context or problem
            3. Ask if they have any question about company or any queries from the faq list
            4. Provide value (answer / clarify) using search_faq, get_company_info, or get_use_cases as needed
            5. Immediately after providing value, if NAME or EMAIL are not yet captured, ask for the next missing field via the next_lead_question tool.
            6. Progressively capture fields in this order: name, company, role, email, use_case, team_size, timeline (one at a time, naturally woven into conversation)
            7. Before calling finalize_lead ensure at minimum name and email are collected. If they aren't, collect them first.
            8. At wrap-up: call get_lead_summary, confirm details, then finalize_lead.

            Mandatory capture before finalization: name and email.

            Tools usage rules:
            - search_faq when user asks product/pricing/capability questions.
            - save_lead_field whenever user gives a lead detail.
            - next_lead_question to know the next field to request; call it before ending or after any substantial answer until all fields complete.
            - finalize_lead ONLY after name & email present.

            Tone & style:
            - Conversational, professional, concise (voice context)
            - NEVER ask for multiple fields in one sentence; one gentle question at a time.
            - If user seems rushed, prioritize name & email first.
            - Avoid emojis or complex formatting.

            If user signals they want to end and mandatory fields are missing, quickly obtain name & email, summarize, then finalize.
            """,
            chat_ctx=chat_ctx,
            tts=tts,
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
    async def next_lead_question(self, context: RunContext):
        """Return the next missing lead field and a suggested question prompt.

        Field order: name, company, role, email, use_case, team_size, timeline
        If all collected returns status=complete.
        """
        order = ["name", "company", "role", "email", "use_case", "team_size", "timeline"]
        prompts = {
            "name": "Could I get your name so I can personalize next steps?",
            "company": "Which organization or company are you with?",
            "role": "What is your role there?",
            "email": "What's the best email to send a brief follow-up summary to?",
            "use_case": "Could you briefly describe the primary use case or problem you're exploring?",
            "team_size": "About how large is the team that would benefit from this solution?",
            "timeline": "Do you have a target timeline for evaluation or deployment?"
        }
        for field in order:
            if not self.lead_data.get(field):
                return json.dumps({"field": field, "prompt": prompts[field]})
        return json.dumps({"status": "complete"})
    
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
        # Guard: ensure mandatory fields present
        mandatory = ["name", "email"]
        missing = [f for f in mandatory if not self.lead_data.get(f)]
        if missing:
            return json.dumps({"status": "error", "message": "Cannot finalize yet; mandatory fields missing.", "missing": missing})

        # Add end timestamp
        self.lead_data["conversation_end"] = datetime.now().isoformat()

        leads_db = load_leads()
        leads_db["leads"].append(self.lead_data)
        success = save_leads(leads_db)

        if success:
            logger.info(f"Lead saved successfully: {self.lead_data.get('name', 'Unknown')}")
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
        logger.error("Failed to save lead")
        return json.dumps({"status": "error", "message": "Failed to save lead information"})


class TaritasSDRAgent(Agent):
    """Sales Development Representative agent for Taritas Software Solutions."""
    
    def __init__(self, lead_data: Optional[dict] = None, chat_ctx=None, tts=None) -> None:
        # Initialize or load lead data
        if lead_data is None:
            self.lead_data = {
                "company_spoken_with": "Taritas Software Solutions",
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
        self.faq_data = load_faq_data("taritas")
        
        super().__init__(
            instructions="""You are a professional and friendly Sales Development Representative (SDR) for Taritas Software Solutions.

            Conversational protocol:
            1. Warm greeting + positioning (custom software / mobile / blockchain)
            2. Explore their project or challenge.
            3. Provide value (answer / clarify) using FAQ tools.
            4. Ask if they have any question about company or any queries from the faq list
            5. After providing value, if name or email not yet collected, call next_lead_question and ask that single field.
            6. Capture fields in order: name, company, role, email, use_case, team_size, timeline.
            7. Do NOT finalize before name & email are saved.
            8. At close: summarize (get_lead_summary) then finalize_lead.

            Tool guidance:
            - search_faq for service/pricing/capability questions.
            - save_lead_field immediately when user supplies a detail.
            - next_lead_question for deciding the next field to request (once per turn max until complete).
            - finalize_lead only after mandatory fields captured.

            Style:
            - Natural, one question at a time, concise (voice).
            - If user seems hesitant, reassure and focus on value before asking next detail.
            - Avoid multiple field requests in one utterance.

            Mandatory before finalization: name & email.
            """,
            chat_ctx=chat_ctx,
            tts=tts,
        )
    
    async def on_enter(self) -> None:
        """Greet the user when the agent becomes active."""
        await self.session.generate_reply(
            instructions=(
                "Greet the visitor warmly, introduce yourself as an SDR from Taritas Software Solutions, "
                "and ask what brought them here today or what kind of software project they're looking for. Be friendly and professional."
            )
        )
    
    @function_tool
    async def search_faq(self, context: RunContext, query: str):
        """Search the Taritas FAQ database for relevant information.
        
        Args:
            query: The question or topic to search for (e.g., 'mobile app', 'pricing', 'blockchain', 'what does Taritas do')
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
            return json.dumps(results[:3])
        else:
            logger.info(f"No FAQ results found for query: {query}")
            return json.dumps({
                "message": "I don't have specific information on that, but I can connect you with our technical team for detailed information."
            })
    
    @function_tool
    async def get_company_info(self, context: RunContext):
        """Get general information about Taritas - what they do, technologies, focus areas."""
        company_data = self.faq_data.get("company", {})
        return json.dumps(company_data)
    
    @function_tool
    async def get_use_cases(self, context: RunContext, industry: Optional[str] = None):
        """Get real-world use cases and success stories.
        
        Args:
            industry: Optional specific industry to filter by (e.g., 'healthcare', 'fintech', 'e-commerce')
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
    async def next_lead_question(self, context: RunContext):
        """Return next missing lead field and prompt for Taritas lead capture."""
        order = ["name", "company", "role", "email", "use_case", "team_size", "timeline"]
        prompts = {
            "name": "Could I get your name to personalize our follow-up?",
            "company": "Which company or organization are you with?",
            "role": "What role do you hold there?",
            "email": "What's the best email to send a brief follow-up or proposal?",
            "use_case": "Could you describe the core use case or problem you're solving?",
            "team_size": "Roughly how large is the team that will use this solution?",
            "timeline": "Do you have an expected timeline for starting this project?"
        }
        for field in order:
            if not self.lead_data.get(field):
                return json.dumps({"field": field, "prompt": prompts[field]})
        return json.dumps({"status": "complete"})
    
    @function_tool
    async def get_lead_summary(self, context: RunContext):
        """Get a summary of collected lead information. Use this when the conversation is ending."""
        return json.dumps(self.lead_data)
    
    @function_tool
    async def finalize_lead(self, context: RunContext):
        """Finalize and save the lead. Requires mandatory fields name & email first."""
        mandatory = ["name", "email"]
        missing = [f for f in mandatory if not self.lead_data.get(f)]
        if missing:
            return json.dumps({"status": "error", "message": "Cannot finalize yet; mandatory fields missing.", "missing": missing})
        self.lead_data["conversation_end"] = datetime.now().isoformat()
        leads_db = load_leads()
        leads_db["leads"].append(self.lead_data)
        success = save_leads(leads_db)
        if success:
            logger.info(f"Lead saved successfully: {self.lead_data.get('name', 'Unknown')}")
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
        logger.error("Failed to save lead")
        return json.dumps({"status": "error", "message": "Failed to save lead information"})


class InnogativeSDRAgent(Agent):
    """Sales Development Representative agent for Innogative."""
    
    def __init__(self, lead_data: Optional[dict] = None, chat_ctx=None, tts=None) -> None:
        # Initialize or load lead data
        if lead_data is None:
            self.lead_data = {
                "company_spoken_with": "Innogative",
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
        self.faq_data = load_faq_data("innogative")
        
        super().__init__(
            instructions="""You are a professional and friendly Sales Development Representative (SDR) for Innogative.

            Flow:
            1. Greet + position (digital agency: web/mobile/digital marketing).
            2. Explore their digital goals or challenges.
            3. Use FAQ tools for answers.
            4. Ask if they have any question about company or any queries from the faq list
            5. After each substantive answer, call next_lead_question until all lead fields captured (one per turn).
            6. Capture order: name, company, role, email, use_case, team_size, timeline.
            7. Mandatory before finalize: name & email.
            8. Summarize (get_lead_summary) then finalize_lead.

            Tools:
            - search_faq, get_company_info, get_use_cases for info.
            - save_lead_field to record details as user gives them.
            - next_lead_question to know next field to politely request.
            - finalize_lead only after mandatory fields.

            Style:
            - Friendly, concise, one question at a time.
            - Avoid stacking multiple data requests.
            - Voice context: no emojis or heavy formatting.

            If user tries to end early and mandatory fields missing: quickly obtain name & email, confirm summary, then close.
            """,
            chat_ctx=chat_ctx,
            tts=tts,
        )
    
    async def on_enter(self) -> None:
        """Greet the user when the agent becomes active."""
        await self.session.generate_reply(
            instructions=(
                "Greet the visitor warmly, introduce yourself as an SDR from Innogative, "
                "and ask what brought them here today or what digital services they're interested in. Be friendly and professional."
            )
        )
    
    @function_tool
    async def search_faq(self, context: RunContext, query: str):
        """Search the Innogative FAQ database for relevant information.
        
        Args:
            query: The question or topic to search for (e.g., 'web development', 'pricing', 'social media', 'what does Innogative do')
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
            return json.dumps(results[:3])
        else:
            logger.info(f"No FAQ results found for query: {query}")
            return json.dumps({
                "message": "I don't have specific information on that, but I can connect you with our team for detailed information."
            })
    
    @function_tool
    async def get_company_info(self, context: RunContext):
        """Get general information about Innogative - what they do, services, focus areas."""
        company_data = self.faq_data.get("company", {})
        return json.dumps(company_data)
    
    @function_tool
    async def get_use_cases(self, context: RunContext, industry: Optional[str] = None):
        """Get real-world use cases and success stories.
        
        Args:
            industry: Optional specific industry to filter by (e.g., 'startups', 'local businesses', 'e-commerce')
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
    async def next_lead_question(self, context: RunContext):
        """Return next missing lead field and prompt for Innogative lead capture."""
        order = ["name", "company", "role", "email", "use_case", "team_size", "timeline"]
        prompts = {
            "name": "May I have your name so I can personalize the follow-up?",
            "company": "Which company or brand are you representing?",
            "role": "What's your role there?",
            "email": "What's a good email to send a concise summary to?",
            "use_case": "What digital goal or use case are you primarily exploring?",
            "team_size": "About how large is the team involved?",
            "timeline": "Is there a timeline you're targeting for this initiative?"
        }
        for field in order:
            if not self.lead_data.get(field):
                return json.dumps({"field": field, "prompt": prompts[field]})
        return json.dumps({"status": "complete"})
    
    @function_tool
    async def get_lead_summary(self, context: RunContext):
        """Get a summary of collected lead information. Use this when the conversation is ending."""
        return json.dumps(self.lead_data)
    
    @function_tool
    async def finalize_lead(self, context: RunContext):
        """Finalize and save the lead. Requires mandatory fields name & email first."""
        mandatory = ["name", "email"]
        missing = [f for f in mandatory if not self.lead_data.get(f)]
        if missing:
            return json.dumps({"status": "error", "message": "Cannot finalize yet; mandatory fields missing.", "missing": missing})
        self.lead_data["conversation_end"] = datetime.now().isoformat()
        leads_db = load_leads()
        leads_db["leads"].append(self.lead_data)
        success = save_leads(leads_db)
        if success:
            logger.info(f"Lead saved successfully: {self.lead_data.get('name', 'Unknown')}")
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
        agent=GreeterAgent(
            tts=murf.TTS(
                voice="en-US-matthew",
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True,
            )
        ),
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
