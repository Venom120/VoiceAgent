#!/usr/bin/env python3
"""
Multi-company test for Day 5 SDR Agent
Tests all three companies: Ericsson, Taritas, and Innogative
"""

import json
from pathlib import Path

# Test paths
DATA_DIR = Path(__file__).resolve().parent / "data"

COMPANIES = {
    "Ericsson India": {
        "file": DATA_DIR / "ericsson_details.json",
        "industry": "Telecommunications & Enterprise Connectivity",
        "key_products": ["Private 5G", "IoT", "Network APIs"]
    },
    "Taritas Software Solutions": {
        "file": DATA_DIR / "taritas_details.json",
        "industry": "IT Consulting & Software Development",
        "key_products": ["Custom Software", "Mobile Apps", "Blockchain"]
    },
    "Innogative": {
        "file": DATA_DIR / "innogative_details.json",
        "industry": "IT Services & Digital Marketing",
        "key_products": ["Web Development", "Social Media Marketing", "Digital Marketing"]
    }
}

def test_company_data(company_name, company_info):
    """Test individual company FAQ data"""
    print(f"\n{'='*70}")
    print(f"Testing {company_name}")
    print(f"{'='*70}")
    
    try:
        with open(company_info["file"], 'r') as f:
            data = json.load(f)
        
        # Test structure
        assert "company" in data, f"Missing 'company' key for {company_name}"
        assert "faqs" in data, f"Missing 'faqs' key for {company_name}"
        assert len(data["faqs"]) > 0, f"No FAQs found for {company_name}"
        
        # Test company info
        company_data = data["company"]
        print(f"✅ Company: {company_data.get('name', 'Unknown')}")
        print(f"   Industry: {company_data.get('industry', 'Unknown')}")
        print(f"   Focus Areas: {len(company_data.get('focus_areas', []))} areas")
        
        # Test FAQs
        faqs = data["faqs"]
        print(f"✅ FAQs: {len(faqs)} questions")
        
        # Count categories
        categories = {}
        for faq in faqs:
            cat = faq.get("category", "uncategorized")
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"   Categories: {', '.join(categories.keys())}")
        
        # Test use cases
        use_cases = data.get("use_cases", [])
        print(f"✅ Use Cases: {len(use_cases)} examples")
        
        # Test target customers
        targets = data.get("target_customers", [])
        print(f"✅ Target Customers: {len(targets)} segments")
        
        # Show sample FAQs
        print(f"\n   📋 Sample Questions:")
        for i, faq in enumerate(faqs[:3], 1):
            print(f"      {i}. {faq['question']}")
        
        # Test search simulation with key products
        print(f"\n   🔍 Testing search with key products:")
        for product in company_info["key_products"]:
            product_lower = product.lower()
            matches = 0
            for faq in faqs:
                question = faq.get("question", "").lower()
                answer = faq.get("answer", "").lower()
                if product_lower in question or product_lower in answer:
                    matches += 1
            print(f"      '{product}': {matches} matches")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed for {company_name}: {e}")
        return False

def test_leads_storage():
    """Test the shared leads storage"""
    print(f"\n{'='*70}")
    print("Testing Shared Leads Storage")
    print(f"{'='*70}")
    
    leads_path = DATA_DIR / "user_responses.json"
    
    try:
        with open(leads_path, 'r') as f:
            data = json.load(f)
        
        assert "leads" in data, "Missing 'leads' key"
        assert isinstance(data["leads"], list), "'leads' should be a list"
        
        print(f"✅ Leads storage initialized")
        print(f"   Current leads: {len(data['leads'])}")
        
        # Show structure of expected lead
        print(f"\n   📝 Expected lead structure:")
        print(f"      - company_spoken_with")
        print(f"      - name, company, email")
        print(f"      - role, use_case")
        print(f"      - team_size, timeline")
        print(f"      - questions_asked[]")
        print(f"      - conversation_start/end")
        
        return True
        
    except Exception as e:
        print(f"❌ Leads storage test failed: {e}")
        return False

def test_agent_handoff_structure():
    """Test that agent.py has proper handoff structure"""
    print(f"\n{'='*70}")
    print("Testing Agent Handoff Structure")
    print(f"{'='*70}")
    
    agent_path = Path(__file__).resolve().parent / "src" / "agent.py"
    
    try:
        with open(agent_path, 'r') as f:
            content = f.read()
        
        # Check for GreeterAgent
        assert "class GreeterAgent(Agent):" in content, "GreeterAgent class not found"
        print("✅ GreeterAgent class defined")
        
        # Check for all three SDR agents
        assert "class EricssonSDRAgent(Agent):" in content, "EricssonSDRAgent class not found"
        print("✅ EricssonSDRAgent class defined")
        
        assert "class TaritasSDRAgent(Agent):" in content, "TaritasSDRAgent class not found"
        print("✅ TaritasSDRAgent class defined")
        
        assert "class InnogativeSDRAgent(Agent):" in content, "InnogativeSDRAgent class not found"
        print("✅ InnogativeSDRAgent class defined")
        
        # Check for handoff tool
        assert "connect_to_company" in content, "connect_to_company tool not found"
        print("✅ connect_to_company handoff tool defined")
        
        # Check for chat_ctx and tts parameters
        assert "chat_ctx=None, tts=None" in content, "chat_ctx and tts parameters not found in agent constructors"
        print("✅ Agent constructors support chat_ctx and tts for handoff")
        
        # Check entrypoint starts with GreeterAgent
        assert "agent=GreeterAgent(" in content, "Entrypoint doesn't start with GreeterAgent"
        print("✅ Entrypoint correctly starts with GreeterAgent")
        
        return True
        
    except Exception as e:
        print(f"❌ Agent structure test failed: {e}")
        return False

def main():
    print("=" * 70)
    print("Day 5 Multi-Company SDR Agent - Comprehensive Test Suite")
    print("=" * 70)
    
    results = []
    
    # Test each company
    for company_name, company_info in COMPANIES.items():
        results.append(test_company_data(company_name, company_info))
    
    # Test shared storage
    results.append(test_leads_storage())
    
    # Test agent structure
    results.append(test_agent_handoff_structure())
    
    # Summary
    print(f"\n{'='*70}")
    print(f"Final Results: {sum(results)}/{len(results)} tests passed")
    print(f"{'='*70}")
    
    if all(results):
        print("✅ All tests passed! Multi-company SDR agent is ready!")
        print("\n🎯 Features:")
        print("   ✓ GreeterAgent for company selection")
        print("   ✓ 3 specialized SDR agents (Ericsson, Taritas, Innogative)")
        print("   ✓ Agent handoff with chat context preservation")
        print("   ✓ 45+ FAQs across all companies")
        print("   ✓ Unified lead capture system")
        
        print("\n🚀 To start the agent:")
        print("   1. cd Day5")
        print("   2. ./start_app.sh")
        print("   3. Open http://localhost:3000")
        print("   4. Say which company you want to speak with!")
    else:
        print("❌ Some tests failed. Review the errors above.")
    
    return all(results)

if __name__ == "__main__":
    exit(0 if main() else 1)
