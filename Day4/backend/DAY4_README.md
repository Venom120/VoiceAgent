# Day 4: Teach-the-Tutor - Active Recall Coach

## Overview

Day 4 introduces a "Teach-the-Tutor" experience with three distinct learning modes, each with its own personality and voice. The system helps users learn programming concepts through active recall by explaining, quizzing, and having users teach back concepts.

## Features

### Three Learning Modes

1. **LEARN Mode** (Voice: Matthew)
   - The agent explains programming concepts clearly
   - Uses the content file to provide detailed explanations
   - Perfect for first-time learning or refreshing knowledge

2. **QUIZ Mode** (Voice: Alicia)
   - The agent asks questions to test your knowledge
   - Provides constructive feedback on answers
   - Helps reinforce learning through active recall

3. **TEACH BACK Mode** (Voice: Ken)
   - You explain concepts back to the agent
   - Receive qualitative feedback on your explanations
   - The best way to learn is to teach!

### Content System

The agent uses a JSON content file (`shared-data/day4_tutor_content.json`) containing programming concepts:
- Variables
- Loops
- Functions
- Conditionals
- Data Types

Each concept includes:
- A detailed summary for learning
- Sample questions for quizzing and teaching back

### Dynamic Voice Switching

- **Matthew** (Greeter & Learn): Enthusiastic teacher voice
- **Alicia** (Quiz): Encouraging quiz master voice
- **Ken** (Teach Back): Patient mentor voice

Voices automatically change when you switch between modes!

## How It Works

### Architecture

The system uses **agent handoffs** to seamlessly switch between different learning modes:

1. **GreeterAgent**: Welcomes users and helps them choose a mode
2. **LearnAgent**: Explains concepts using the content file
3. **QuizAgent**: Asks questions and evaluates answers
4. **TeachBackAgent**: Prompts users to explain and provides feedback

Each agent has its own:
- Personality and instruction set
- Set of tools (function calls)
- Voice configuration

### Agent Tools

**GreeterAgent**:
- `switch_mode(mode)` - Switch to learn, quiz, or teach_back mode

**LearnAgent**:
- `get_concept(concept_id)` - Retrieve concept information
- `list_concepts()` - List all available concepts
- `switch_mode(mode)` - Switch to quiz or teach_back mode

**QuizAgent**:
- `get_quiz_question(concept_id)` - Get a quiz question for a concept
- `get_random_question()` - Get a random quiz question
- `list_concepts()` - List all available concepts
- `switch_mode(mode)` - Switch to learn or teach_back mode

**TeachBackAgent**:
- `get_concept_for_teaching(concept_id)` - Get a concept for user to explain
- `get_random_concept()` - Get a random concept to teach back
- `list_concepts()` - List all available concepts
- `switch_mode(mode)` - Switch to learn or quiz mode

## Usage Examples

### Starting a Session

1. Connect to the voice agent
2. The GreeterAgent will welcome you and explain the modes
3. Say which mode you want (e.g., "I'd like to try learn mode")
4. The agent switches to that mode with the appropriate voice

### Learn Mode Example

**You**: "Tell me about variables"
**Agent (Matthew)**: *Uses get_concept tool and explains variables*
**You**: "Can you explain loops now?"
**Agent**: *Retrieves and explains loops*

### Quiz Mode Example

**You**: "Quiz me on functions"
**Agent (Alicia)**: *Uses get_quiz_question and asks a question*
**You**: *Provides answer*
**Agent**: *Gives feedback and follow-up questions*

### Teach Back Mode Example

**You**: "I want to explain variables"
**Agent (Ken)**: *Uses get_concept_for_teaching and asks you to explain*
**You**: *Explains the concept in your own words*
**Agent**: *Provides qualitative feedback on your explanation*

### Switching Modes

You can switch modes at any time by simply asking:
- "Switch to quiz mode"
- "I want to go to teach back mode"
- "Let's do learn mode"

The agent will use the `switch_mode` tool to transfer you to the appropriate agent with the right voice!

## Technical Implementation

### Content Loading

```python
CONTENT_PATH = Path(__file__).resolve().parents[1] / "shared-data" / "day4_tutor_content.json"
TUTOR_CONTENT = load_content()
```

### Agent Handoff

```python
await context.session.handoff_to(LearnAgent())
```

### Voice Configuration

```python
@session.on("agent_handoff")
async def _on_agent_handoff(event):
    if isinstance(event.new_agent, QuizAgent):
        new_tts = murf.TTS(voice="en-US-alicia", ...)
    # ... update session TTS
```

## Running the Application

### From Day4 Root Directory

```bash
# Start all services
./start_app.sh
```

### Or Run Individually

```bash
# Terminal 1 - LiveKit Server
livekit-server --dev

# Terminal 2 - Backend Agent
cd backend
uv run python src/agent.py dev

# Terminal 3 - Frontend
cd frontend
pnpm dev
```

Then open http://localhost:3000 in your browser!

## Completion Criteria

✅ The agent greets users and asks for their preferred learning mode
✅ All three modes (learn, quiz, teach_back) are fully supported
✅ Each mode uses content from the JSON file appropriately
✅ Users can switch between modes at any time by asking
✅ Different voices are used for each mode (Matthew, Alicia, Ken)

## Advanced Ideas (Optional)

- Add a mastery tracking system to store user progress
- Implement a teach-back evaluator tool that scores explanations
- Add more concepts and learning paths
- Create a spaced repetition system
- Track weak concepts and suggest practice plans

## Resources

- [LiveKit Agent Handoffs](https://docs.livekit.io/agents/build/agents-handoffs/)
- [Context Preservation](https://docs.livekit.io/agents/build/agents-handoffs/#context-preservation)
- [Murf Falcon TTS Documentation](https://murf.ai/api/docs/text-to-speech/streaming)
- [Complex Agent Example](https://github.com/livekit-examples/python-agents-examples/blob/main/complex-agents/medical_office_triage/triage.py)

## Next Steps

1. Test all three learning modes
2. Try switching between modes during a session
3. Record a demo video
4. Share your progress on LinkedIn with #MurfAIVoiceAgentsChallenge

Happy Learning! 📚🎓
