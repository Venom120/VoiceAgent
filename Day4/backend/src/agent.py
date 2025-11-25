import json
import logging
import random
from pathlib import Path

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
    RunContext
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation # type: ignore
from livekit.plugins.turn_detector.multilingual import MultilingualModel # type: ignore

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Load content file
CONTENT_PATH = Path(__file__).resolve().parents[1] / "shared-data" / "day4_tutor_content.json"

def load_content():
    """Load the tutor content from JSON file."""
    try:
        with open(CONTENT_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load content: {e}")
        return []

# Global content cache
TUTOR_CONTENT = load_content()


class GreeterAgent(Agent):
    """Initial agent that greets user and helps them choose a learning mode."""
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a friendly educational assistant helping students learn programming concepts through active recall.
            
            Your role is to greet the user warmly and explain the three learning modes available:
            1. LEARN mode - where I explain programming concepts to you
            2. QUIZ mode - where I ask you questions to test your knowledge
            3. TEACH BACK mode - where you explain concepts back to me and I give you feedback
            
            Ask the user which mode they'd like to start with. Once they choose, use the switch_mode tool to connect them to the appropriate learning agent.
            
            Keep your responses concise and friendly. Avoid complex formatting, emojis, or symbols.
            The user is interacting via voice.""",
        )

    @function_tool
    async def switch_mode(self, context: RunContext, mode: str):
        """Switch to a different learning mode.
        
        Args:
            mode: The learning mode to switch to. Must be one of: 'learn', 'quiz', or 'teach_back'
        """
        mode = mode.lower().strip()
        if mode not in ['learn', 'quiz', 'teach_back']:
            return f"Invalid mode '{mode}'. Please choose 'learn', 'quiz', or 'teach_back'."
        
        logger.info(f"Switching to {mode} mode")
        
        # Get the session and perform handoff
        if mode == 'learn':
            await context.session.handoff_to(LearnAgent())
            return f"Switching you to Learn mode with Matthew."
        elif mode == 'quiz':
            await context.session.handoff_to(QuizAgent())
            return f"Switching you to Quiz mode with Alicia."
        elif mode == 'teach_back':
            await context.session.handoff_to(TeachBackAgent())
            return f"Switching you to Teach Back mode with Ken."


class LearnAgent(Agent):
    """Agent that explains concepts to the user."""
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are Matthew, an enthusiastic programming teacher in LEARN mode.
            
            Your job is to explain programming concepts clearly and engagingly. Use the get_concept tool to retrieve 
            information about specific concepts, then explain them in a conversational, easy-to-understand way.
            
            When the user asks about a concept or you need to teach something, use get_concept to load the material.
            After explaining, ask if they'd like to hear about another concept or switch to a different mode.
            
            Available concepts: variables, loops, functions, conditionals, data_types
            
            If the user wants to switch modes, use the switch_mode tool to connect them to quiz or teach_back mode.
            
            Keep explanations clear but not too long. Avoid complex formatting, emojis, or symbols.
            You're speaking via voice, so be natural and conversational.""",
        )
    
    @function_tool
    async def get_concept(self, context: RunContext, concept_id: str):
        """Get information about a programming concept.
        
        Args:
            concept_id: The ID of the concept to retrieve (e.g., 'variables', 'loops', 'functions', 'conditionals', 'data_types')
        """
        concept_id = concept_id.lower().strip()
        for concept in TUTOR_CONTENT:
            if concept['id'] == concept_id:
                logger.info(f"Retrieved concept: {concept_id}")
                return json.dumps({
                    'title': concept['title'],
                    'summary': concept['summary']
                })
        
        available = [c['id'] for c in TUTOR_CONTENT]
        return json.dumps({
            'error': f"Concept '{concept_id}' not found. Available concepts: {', '.join(available)}"
        })
    
    @function_tool
    async def list_concepts(self, context: RunContext):
        """List all available programming concepts."""
        concepts = [{'id': c['id'], 'title': c['title']} for c in TUTOR_CONTENT]
        return json.dumps(concepts)
    
    @function_tool
    async def switch_mode(self, context: RunContext, mode: str):
        """Switch to a different learning mode.
        
        Args:
            mode: The learning mode to switch to. Must be 'quiz' or 'teach_back'
        """
        mode = mode.lower().strip()
        if mode not in ['quiz', 'teach_back']:
            return f"Invalid mode '{mode}'. From Learn mode, you can switch to 'quiz' or 'teach_back'."
        
        logger.info(f"Switching from learn to {mode} mode")
        
        if mode == 'quiz':
            await context.session.handoff_to(QuizAgent())
            return "Switching you to Quiz mode with Alicia."
        else:
            await context.session.handoff_to(TeachBackAgent())
            return "Switching you to Teach Back mode with Ken."


class QuizAgent(Agent):
    """Agent that quizzes the user on concepts."""
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are Alicia, an encouraging programming quiz master in QUIZ mode.
            
            Your job is to ask the user questions about programming concepts to test their knowledge.
            Use the get_quiz_question tool to get sample questions, then ask them in an engaging way.
            
            After the user answers, provide constructive feedback - praise correct answers and gently correct 
            misunderstandings. Ask follow-up questions to probe deeper understanding.
            
            Available concepts to quiz on: variables, loops, functions, conditionals, data_types
            
            If the user wants to switch modes, use the switch_mode tool to connect them to learn or teach_back mode.
            
            Be encouraging and supportive. Avoid complex formatting, emojis, or symbols.
            You're speaking via voice, so keep it conversational.""",
        )
    
    @function_tool
    async def get_quiz_question(self, context: RunContext, concept_id: str):
        """Get a quiz question for a specific concept.
        
        Args:
            concept_id: The ID of the concept to quiz on (e.g., 'variables', 'loops', 'functions', 'conditionals', 'data_types')
        """
        concept_id = concept_id.lower().strip()
        for concept in TUTOR_CONTENT:
            if concept['id'] == concept_id:
                logger.info(f"Retrieved quiz question for: {concept_id}")
                return json.dumps({
                    'title': concept['title'],
                    'question': concept['sample_question']
                })
        
        available = [c['id'] for c in TUTOR_CONTENT]
        return json.dumps({
            'error': f"Concept '{concept_id}' not found. Available concepts: {', '.join(available)}"
        })
    
    @function_tool
    async def get_random_question(self, context: RunContext):
        """Get a random quiz question from any concept."""
        if not TUTOR_CONTENT:
            return json.dumps({'error': 'No content available'})
        
        concept = random.choice(TUTOR_CONTENT)
        logger.info(f"Retrieved random quiz question: {concept['id']}")
        return json.dumps({
            'title': concept['title'],
            'question': concept['sample_question'],
            'concept_id': concept['id']
        })
    
    @function_tool
    async def list_concepts(self, context: RunContext):
        """List all available programming concepts."""
        concepts = [{'id': c['id'], 'title': c['title']} for c in TUTOR_CONTENT]
        return json.dumps(concepts)
    
    @function_tool
    async def switch_mode(self, context: RunContext, mode: str):
        """Switch to a different learning mode.
        
        Args:
            mode: The learning mode to switch to. Must be 'learn' or 'teach_back'
        """
        mode = mode.lower().strip()
        if mode not in ['learn', 'teach_back']:
            return f"Invalid mode '{mode}'. From Quiz mode, you can switch to 'learn' or 'teach_back'."
        
        logger.info(f"Switching from quiz to {mode} mode")
        
        if mode == 'learn':
            await context.session.handoff_to(LearnAgent())
            return "Switching you to Learn mode with Matthew."
        else:
            await context.session.handoff_to(TeachBackAgent())
            return "Switching you to Teach Back mode with Ken."


class TeachBackAgent(Agent):
    """Agent that asks user to teach concepts back and provides feedback."""
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are Ken, a patient and insightful programming mentor in TEACH BACK mode.
            
            Your role is to ask the user to explain programming concepts back to you, then provide thoughtful feedback.
            Use the get_concept_for_teaching tool to select a concept, then ask the user to explain it in their own words.
            
            When the user explains, listen carefully and provide qualitative feedback:
            - Point out what they got right
            - Gently identify any gaps or misconceptions
            - Ask clarifying questions to help them think deeper
            - Encourage them to relate concepts to real examples
            
            Available concepts: variables, loops, functions, conditionals, data_types
            
            If the user wants to switch modes, use the switch_mode tool to connect them to learn or quiz mode.
            
            Be supportive and constructive. Avoid complex formatting, emojis, or symbols.
            You're speaking via voice, so be warm and encouraging.""",
        )
    
    @function_tool
    async def get_concept_for_teaching(self, context: RunContext, concept_id: str):
        """Get a concept that the user should teach back.
        
        Args:
            concept_id: The ID of the concept for the user to explain (e.g., 'variables', 'loops', 'functions', 'conditionals', 'data_types')
        """
        concept_id = concept_id.lower().strip()
        for concept in TUTOR_CONTENT:
            if concept['id'] == concept_id:
                logger.info(f"Retrieved concept for teaching back: {concept_id}")
                # Return both the prompt and the reference summary for evaluation
                return json.dumps({
                    'title': concept['title'],
                    'prompt': f"Please explain {concept['title']} to me in your own words.",
                    'reference_summary': concept['summary']
                })
        
        available = [c['id'] for c in TUTOR_CONTENT]
        return json.dumps({
            'error': f"Concept '{concept_id}' not found. Available concepts: {', '.join(available)}"
        })
    
    @function_tool
    async def get_random_concept(self, context: RunContext):
        """Get a random concept for the user to teach back."""
        if not TUTOR_CONTENT:
            return json.dumps({'error': 'No content available'})
        
        concept = random.choice(TUTOR_CONTENT)
        logger.info(f"Retrieved random concept for teaching: {concept['id']}")
        return json.dumps({
            'title': concept['title'],
            'prompt': f"Please explain {concept['title']} to me in your own words.",
            'reference_summary': concept['summary'],
            'concept_id': concept['id']
        })
    
    @function_tool
    async def list_concepts(self, context: RunContext):
        """List all available programming concepts."""
        concepts = [{'id': c['id'], 'title': c['title']} for c in TUTOR_CONTENT]
        return json.dumps(concepts)
    
    @function_tool
    async def switch_mode(self, context: RunContext, mode: str):
        """Switch to a different learning mode.
        
        Args:
            mode: The learning mode to switch to. Must be 'learn' or 'quiz'
        """
        mode = mode.lower().strip()
        if mode not in ['learn', 'quiz']:
            return f"Invalid mode '{mode}'. From Teach Back mode, you can switch to 'learn' or 'quiz'."
        
        logger.info(f"Switching from teach_back to {mode} mode")
        
        if mode == 'learn':
            await context.session.handoff_to(LearnAgent())
            return "Switching you to Learn mode with Matthew."
        else:
            await context.session.handoff_to(QuizAgent())
            return "Switching you to Quiz mode with Alicia."


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up the initial greeter session with default voice (Matthew)
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-matthew",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
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
    
    # Handle agent handoffs - update TTS voice when switching agents
    @session.on("agent_handoff")
    async def _on_agent_handoff(event):
        logger.info(f"Agent handoff to: {type(event.new_agent).__name__}")
        
        # Update TTS voice based on the new agent type
        if isinstance(event.new_agent, LearnAgent):
            # Matthew for Learn mode
            new_tts = murf.TTS(
                voice="en-US-matthew",
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True
            )
        elif isinstance(event.new_agent, QuizAgent):
            # Alicia for Quiz mode
            new_tts = murf.TTS(
                voice="en-US-alicia",
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True
            )
        elif isinstance(event.new_agent, TeachBackAgent):
            # Ken for Teach Back mode
            new_tts = murf.TTS(
                voice="en-US-ken",
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True
            )
        else:
            # Default voice for GreeterAgent
            new_tts = murf.TTS(
                voice="en-US-matthew",
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True
            )
        
        # Update the session's TTS
        session._tts = new_tts

    # Start the session with the GreeterAgent
    await session.start(
        agent=GreeterAgent(),
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
