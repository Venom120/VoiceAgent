import json
import asyncio
import sys
from pathlib import Path

# Ensure src path is importable when running tests directly
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from agent import EricssonSDRAgent, TaritasSDRAgent, InnogativeSDRAgent

# Helper coroutine to extract full sequence of next_lead_question fields
async def _collect_sequence(agent_cls):
    agent = agent_cls()
    seq = []
    # Allow up to 10 iterations (should complete sooner)
    for _ in range(10):
        resp = await agent.next_lead_question(None)
        data = json.loads(resp)
        if data.get("status") == "complete":
            break
        field = data["field"]
        seq.append(field)
        # Simulate user providing the field
        agent.lead_data[field] = f"dummy_{field}"  # mark as filled
    return seq, agent

def test_lead_question_sequence_all_agents():
    loop = asyncio.get_event_loop()
    expected = ["name", "company", "role", "email", "use_case", "team_size", "timeline"]
    for agent_cls in (EricssonSDRAgent, TaritasSDRAgent, InnogativeSDRAgent):
        seq, _agent = loop.run_until_complete(_collect_sequence(agent_cls))
        assert seq == expected, f"Sequence mismatch for {agent_cls.__name__}: {seq}"

def test_finalize_guard_and_success():
    loop = asyncio.get_event_loop()
    for agent_cls in (EricssonSDRAgent, TaritasSDRAgent, InnogativeSDRAgent):
        agent = agent_cls()
        # Attempt premature finalize
        premature = loop.run_until_complete(agent.finalize_lead(None))
        premature_data = json.loads(premature)
        assert premature_data.get("status") == "error", f"Finalize should error when mandatory missing for {agent_cls.__name__}"
        assert "missing" in premature_data
        # Provide mandatory fields
        agent.lead_data["name"] = "Alice"
        agent.lead_data["email"] = "alice@example.com"
        success = loop.run_until_complete(agent.finalize_lead(None))
        success_data = json.loads(success)
        assert success_data.get("status") == "saved", f"Finalize should succeed after mandatory fields for {agent_cls.__name__}"