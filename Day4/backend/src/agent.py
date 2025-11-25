import json
import logging
import random
from pathlib import Path

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
import asyncio
import tempfile
import shutil
from typing import cast, Any
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Load content file
CONTENT_PATH = Path(__file__).resolve().parents[1] / "shared-data" / "day4_tutor_content.json"

def normalize_mode(mode_str: str) -> str:
    """Normalize a user-provided mode string into the canonical mode ids.

    Accepts natural language variants like 'teach back', 'teach-back', 'teachback',
    'quiz mode', 'learn mode', etc., and returns one of: 'learn', 'quiz', 'teach_back'.
    """
    if not mode_str:
        return ""
    s = mode_str.strip().lower()
    # remove trailing 'mode' word
    if s.endswith(' mode'):
        s = s[: -len(' mode')]
    # replace hyphens and spaces with underscore for canonicalization
    s = s.replace('-', ' ').replace('_', ' ').strip()
    s = s.replace(' ', '_')
    # map common synonyms
    if s in ('teachback', 'teach_back', 'teach-back'):
        return 'teach_back'
    if s in ('teach_back',):
        return 'teach_back'
    if s in ('learn', 'learn'):
        return 'learn'
    if s in ('quiz', 'quiz'):
        return 'quiz'
    # fallback: return normalized token
    return s

def load_content():
    """Load the tutor content from JSON file at runtime.

    This reads the file each time to ensure the latest changes (for example,
    when the user teaches back and updates or creates a topic) are visible to
    agents immediately.
    """
    try:
        with open(CONTENT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.exception("Failed to load content: %s", e)
        return []


def save_content(content_list):
    """Atomically save the content list back to the JSON file.

    Uses a temporary file and atomic replace to avoid partial writes.
    """
    try:
        dirpath = CONTENT_PATH.parent
        with tempfile.NamedTemporaryFile('w', delete=False, dir=str(dirpath), encoding='utf-8') as tf:
            json.dump(content_list, tf, indent=2, ensure_ascii=False)
            temp_name = tf.name
        shutil.move(temp_name, str(CONTENT_PATH))
        return True
    except Exception as e:
        logger.exception("Failed to save content: %s", e)
        return False


class GreeterAgent(Agent):
    """Initial agent that greets user and helps them choose a learning mode."""
    def __init__(self, chat_ctx=None, tts=None) -> None:
        super().__init__(
            instructions="""You are a friendly educational assistant helping students learn programming concepts through active recall.
            
            Your role is to greet the user warmly and explain the three learning modes available:
            1. LEARN mode - where I explain programming concepts to you
            2. QUIZ mode - where I ask you questions to test your knowledge
            3. TEACH BACK mode - where you explain concepts back to me and I give you feedback
            
            Ask the user which mode they'd like to start with. Once they choose, use the switch_mode tool to connect them to the appropriate learning agent.
            
            Keep your responses concise and friendly. Avoid complex formatting, emojis, or symbols.
            The user is interacting via voice.""",
            chat_ctx=chat_ctx,
            tts=tts,
        )

    @function_tool
    async def switch_mode(self, context: RunContext, mode: str):
        """Switch to a different learning mode.
        
        Args:
            mode: The learning mode to switch to. Must be one of: 'learn', 'quiz', or 'teach_back'
        """
        mode = normalize_mode(mode)
        if mode not in ['learn', 'quiz', 'teach_back']:
            return f"Invalid mode '{mode}'. Please choose 'learn', 'quiz', or 'teach_back'."
        
        logger.info(f"Switching to {mode} mode")
        
        # Get the session and perform handoff
        # Return a new agent instance to trigger a framework handoff.
        # Preserve the current chat context so the new agent retains prior conversation history.
        if mode == 'learn':
            # Return the agent and a short switching announcement so the framework
            # performs a clean handoff and the new agent's on_enter runs afterwards.
            return (
                LearnAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-matthew",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Learn mode with Matthew.",
            )
        elif mode == 'quiz':
            return (
                QuizAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-alicia",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Quiz mode with Alicia.",
            )
        elif mode == 'teach_back':
            return (
                TeachBackAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-ken",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Teach Back mode with Ken.",
            )


class LearnAgent(Agent):
    """Agent that explains concepts to the user."""
    def __init__(self, chat_ctx=None, tts=None) -> None:
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
            chat_ctx=chat_ctx,
            tts=tts,
        )

    async def on_enter(self) -> None:
        # Greet the user when LearnAgent becomes active
        await self.session.generate_reply(
            instructions=(
                "Hi — I'm Matthew. I'll explain programming concepts clearly and concisely. "
                "Tell me which concept you'd like to learn about, or say 'list concepts' to hear options."
            )
        )
    
    @function_tool
    async def get_concept(self, context: RunContext, concept_id: str):
        """Get information about a programming concept.
        
        Args:
            concept_id: The ID of the concept to retrieve (e.g., 'variables', 'loops', 'functions', 'conditionals', 'data_types')
        """
        concept_id = concept_id.lower().strip()
        content = load_content()
        for concept in content:
            if concept['id'] == concept_id:
                logger.info(f"Retrieved concept: {concept_id}")
                return json.dumps({
                    'title': concept['title'],
                    'summary': concept['summary']
                })
        
        available = [c['id'] for c in content]
        return json.dumps({
            'error': f"Concept '{concept_id}' not found. Available concepts: {', '.join(available)}"
        })
    
    @function_tool
    async def list_concepts(self, context: RunContext):
        """List all available programming concepts."""
        content = load_content()
        concepts = [{'id': c['id'], 'title': c['title']} for c in content]
        return json.dumps(concepts)
    
    @function_tool
    async def switch_mode(self, context: RunContext, mode: str):
        """Switch to a different learning mode.
        
        Args:
            mode: The learning mode to switch to. Must be 'quiz' or 'teach_back'
        """
        mode = normalize_mode(mode)
        if mode not in ['quiz', 'teach_back']:
            return f"Invalid mode '{mode}'. From Learn mode, you can switch to 'quiz' or 'teach_back'."
        
        logger.info(f"Switching from learn to {mode} mode")

        if mode == 'quiz':
            return (
                QuizAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-alicia",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Quiz mode with Alicia.",
            )
        else:
            return (
                TeachBackAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-ken",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Teach Back mode with Ken.",
            )


class QuizAgent(Agent):
    """Agent that quizzes the user on concepts."""
    def __init__(self, chat_ctx=None, tts=None) -> None:
        super().__init__(
            instructions="""You are Alicia, an encouraging programming quiz master in QUIZ mode.
            
            Your job is to present multiple-choice questions (MCQs) about programming concepts to test the user's knowledge.
            Use the get_quiz_question tool to retrieve a question, then present it as an MCQ with four labeled choices: A, B, C, D.
            Exactly one choice should be correct.

            After the user answers:
            - State whether they were correct or incorrect.
            - Reveal the correct choice and give a brief (1-2 sentence) explanation.
            - Offer a short follow-up question or a hint to deepen understanding.
            
            If the user asks for a hint before answering, provide a concise clue without giving away the answer.
            If the user wants to switch modes, use the switch_mode tool to connect them to learn or teach_back mode.

            Available concepts to quiz on: variables, loops, functions, conditionals, data_types

            Be encouraging and supportive. Keep responses concise and conversational for voice interaction.
            Avoid complex formatting, emojis, or symbols.""",
            chat_ctx=chat_ctx,
            tts=tts,
        )

    async def on_enter(self) -> None:
        # Greet the user when QuizAgent becomes active
        # Build a dynamic list of available concepts from the shared content file
        try:
            content = load_content()
            topics = [c.get('title') for c in content]
            topics_str = ", ".join(topics) if topics else "variables, loops, functions, conditionals, data types"
        except Exception:
            topics_str = "variables, loops, functions, conditionals, data types"

        await self.session.generate_reply(
            instructions=(
                f"Hi — I'm Alicia, your quiz master. I'll ask you questions to test your knowledge. "
                f"I can quiz you on: {topics_str}. Say a concept name to get a question on it, or ask for a random question."
            )
        )
    
    @function_tool
    async def get_quiz_question(self, context: RunContext, concept_id: str):
        """Get a quiz question for a specific concept.
        
        Args:
            concept_id: The ID of the concept to quiz on (e.g., 'variables', 'loops', 'functions', 'conditionals', 'data_types')
        """
        concept_id = concept_id.lower().strip()
        content = load_content()
        for concept in content:
            if concept['id'] == concept_id:
                logger.info(f"Retrieved quiz question for: {concept_id}")
                return json.dumps({
                    'title': concept['title'],
                    'question': concept['sample_question']
                })
        
        available = [c['id'] for c in content]
        return json.dumps({
            'error': f"Concept '{concept_id}' not found. Available concepts: {', '.join(available)}"
        })
    
    @function_tool
    async def get_random_question(self, context: RunContext):
        """Get a random quiz question from any concept."""
        content = load_content()
        if not content:
            return json.dumps({'error': 'No content available'})

        concept = random.choice(content)
        logger.info(f"Retrieved random quiz question: {concept['id']}")
        return json.dumps({
            'title': concept['title'],
            'question': concept['sample_question'],
            'concept_id': concept['id']
        })
    
    @function_tool
    async def list_concepts(self, context: RunContext):
        """List all available programming concepts."""
        content = load_content()
        concepts = [{'id': c['id'], 'title': c['title']} for c in content]
        return json.dumps(concepts)
    
    @function_tool
    async def switch_mode(self, context: RunContext, mode: str):
        """Switch to a different learning mode.
        
        Args:
            mode: The learning mode to switch to. Must be 'learn' or 'teach_back'
        """
        mode = normalize_mode(mode)
        if mode not in ['learn', 'teach_back']:
            return f"Invalid mode '{mode}'. From Quiz mode, you can switch to 'learn' or 'teach_back'."
        
        logger.info(f"Switching from quiz to {mode} mode")

        if mode == 'learn':
            return (
                LearnAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-matthew",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Learn mode with Matthew.",
            )
        else:
            return (
                TeachBackAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-ken",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Teach Back mode with Ken.",
            )


class TeachBackAgent(Agent):
    """Agent that asks user to teach concepts back and provides feedback."""
    def __init__(self, chat_ctx=None, tts=None) -> None:
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
            chat_ctx=chat_ctx,
            tts=tts,
        )

    async def on_enter(self) -> None:
        # Greet the user when TeachBackAgent becomes active
        await self.session.generate_reply(
            instructions=(
                "Hi — I'm Ken. I'll ask you to explain concepts back to me and provide helpful feedback. "
                "Tell me which concept you'd like to teach back, or ask for a random one."
            )
        )
    
    @function_tool
    async def get_concept_for_teaching(self, context: RunContext, concept_id: str):
        """Get a concept that the user should teach back.
        
        Args:
            concept_id: The ID of the concept for the user to explain (e.g., 'variables', 'loops', 'functions', 'conditionals', 'data_types')
        """
        concept_id = concept_id.lower().strip()
        content = load_content()
        for concept in content:
            if concept['id'] == concept_id:
                logger.info(f"Retrieved concept for teaching back: {concept_id}")
                # Return both the prompt and the reference summary for evaluation
                return json.dumps({
                    'title': concept['title'],
                    'prompt': f"Please explain {concept['title']} to me in your own words.",
                    'reference_summary': concept['summary']
                })
        
        available = [c['id'] for c in content]
        return json.dumps({
            'error': f"Concept '{concept_id}' not found. Available concepts: {', '.join(available)}"
        })
    
    @function_tool
    async def get_random_concept(self, context: RunContext):
        """Get a random concept for the user to teach back."""
        content = load_content()
        if not content:
            return json.dumps({'error': 'No content available'})

        concept = random.choice(content)
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
        content = load_content()
        concepts = [{'id': c['id'], 'title': c['title']} for c in content]
        return json.dumps(concepts)

    @function_tool
    async def save_concept(self, context: RunContext, concept_id: str, title: str | None = None, summary: str | None = None, sample_question: str | None = None):
        """Create or update a concept in the shared content file.

        - If the concept exists, update provided fields.
        - If it does not exist, create a new entry.

        Returns a confirmation message.
        """
        concept_id = concept_id.lower().strip()
        content = load_content()

        # find existing concept
        found = None
        for c in content:
            if c.get('id') == concept_id:
                found = c
                break

        if found is not None:
            if title is not None:
                found['title'] = title
            if summary is not None:
                found['summary'] = summary
            if sample_question is not None:
                found['sample_question'] = sample_question
            saved = save_content(content)
            if saved:
                return json.dumps({'status': 'updated', 'id': concept_id})
            else:
                return json.dumps({'error': 'failed to save updated content'})
        else:
            # create new concept entry
            new_entry = {
                'id': concept_id,
                'title': title or concept_id.capitalize(),
                'summary': summary or "",
                'sample_question': sample_question or ""
            }
            content.append(new_entry)
            saved = save_content(content)
            if saved:
                return json.dumps({'status': 'created', 'id': concept_id})
            else:
                return json.dumps({'error': 'failed to save new content'})
    
    @function_tool
    async def switch_mode(self, context: RunContext, mode: str):
        """Switch to a different learning mode.
        
        Args:
            mode: The learning mode to switch to. Must be 'learn' or 'quiz'
        """
        mode = normalize_mode(mode)
        if mode not in ['learn', 'quiz']:
            return f"Invalid mode '{mode}'. From Teach Back mode, you can switch to 'learn' or 'quiz'."
        
        logger.info(f"Switching from teach_back to {mode} mode")

        if mode == 'learn':
            return (
                LearnAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-matthew",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Learn mode with Matthew.",
            )
        else:
            return (
                QuizAgent(
                    chat_ctx=self.chat_ctx,
                    tts=murf.TTS(
                        voice="en-US-alicia",
                        style="Conversation",
                        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                        text_pacing=True,
                    ),
                ),
                "Switching you to Quiz mode with Alicia.",
            )


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
    # The event emitter requires a synchronous callback. Create a sync wrapper
    @session.on(cast(Any, "agent_handoff"))
    def _on_agent_handoff(event):
        """Synchronous handler for agent handoff events.

        The event emitter requires sync callbacks. Build the desired Murf TTS
        object synchronously and assign it to session._tts immediately so the
        voice pipeline has a TTS node available without waiting for an async
        task to run.
        """
        try:
            logger.info(f"Agent handoff to: {type(event.new_agent).__name__}")

            # Select voice based on the new agent type
            if isinstance(event.new_agent, LearnAgent):
                voice_name = "en-US-matthew"
            elif isinstance(event.new_agent, QuizAgent):
                voice_name = "en-US-alicia"
            elif isinstance(event.new_agent, TeachBackAgent):
                voice_name = "en-US-ken"
            else:
                voice_name = "en-US-matthew"

            new_tts = murf.TTS(
                voice=voice_name,
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True,
            )

            # Immediately set the session TTS so downstream tts_nodes see a valid
            # TTS object. This is a best-effort fallback; agent-level tts overrides
            # are preferred when supported by the framework version.
            # assign to internal and public attributes when available
            try:
                session._tts = new_tts
            except Exception:
                logger.debug("session._tts assignment failed")

            try:
                # some versions expose a public 'tts' attribute; use setattr on Any
                setattr(cast(Any, session), "tts", new_tts)
            except Exception:
                logger.debug("session.tts assignment failed or not present")

            # Also set the new agent's tts attribute so agent-level activity can
            # see it immediately (best-effort).
            try:
                if hasattr(event, "new_agent") and event.new_agent is not None:
                    setattr(event.new_agent, "tts", new_tts)
            except Exception:
                logger.debug("failed to set new_agent.tts (non-fatal)")
        except Exception as e:
            logger.exception("Error handling agent_handoff event (non-fatal): %s", e)

    # Start the session with the GreeterAgent
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
