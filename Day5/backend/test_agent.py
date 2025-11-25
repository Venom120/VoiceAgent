#!/usr/bin/env python3
"""
Quick test script for Day 5 Ericsson SDR Agent
Tests FAQ loading, search, and lead capture functionality
"""

import json
from pathlib import Path

# Test paths
FAQ_PATH = Path(__file__).resolve().parents[1] / "data" / "ericsson_details.json"
LEADS_PATH = Path(__file__).resolve().parents[1] / "data" / "user_responses.json"

def test_faq_loading():
    """Test that FAQ data loads correctly"""
    print("🔍 Testing FAQ data loading...")
    try:
        with open(FAQ_PATH, 'r') as f:
            data = json.load(f)
        
        assert "company" in data, "Missing 'company' key"
        assert "faqs" in data, "Missing 'faqs' key"
        assert len(data["faqs"]) > 0, "No FAQs found"
        
        print(f"✅ FAQ data loaded successfully!")
        print(f"   - Company: {data['company']['name']}")
        print(f"   - FAQs: {len(data['faqs'])} questions")
        print(f"   - Use Cases: {len(data.get('use_cases', []))}")
        return True
    except Exception as e:
        print(f"❌ FAQ loading failed: {e}")
        return False

def test_faq_categories():
    """Test FAQ organization"""
    print("\n📂 Testing FAQ categories...")
    try:
        with open(FAQ_PATH, 'r') as f:
            data = json.load(f)
        
        categories = set()
        for faq in data["faqs"]:
            categories.add(faq.get("category", "uncategorized"))
        
        print(f"✅ Found {len(categories)} categories:")
        for cat in sorted(categories):
            count = sum(1 for faq in data["faqs"] if faq.get("category") == cat)
            print(f"   - {cat}: {count} questions")
        return True
    except Exception as e:
        print(f"❌ Category test failed: {e}")
        return False

def test_lead_storage():
    """Test lead storage file"""
    print("\n💾 Testing lead storage...")
    try:
        with open(LEADS_PATH, 'r') as f:
            data = json.load(f)
        
        assert "leads" in data, "Missing 'leads' key"
        assert isinstance(data["leads"], list), "'leads' should be a list"
        
        print(f"✅ Lead storage valid!")
        print(f"   - Current leads: {len(data['leads'])}")
        return True
    except Exception as e:
        print(f"❌ Lead storage test failed: {e}")
        return False

def test_search_simulation():
    """Simulate FAQ search"""
    print("\n🔎 Testing FAQ search simulation...")
    try:
        with open(FAQ_PATH, 'r') as f:
            data = json.load(f)
        
        # Test queries
        test_queries = [
            "private 5g",
            "pricing",
            "what does ericsson do",
            "security",
            "iot"
        ]
        
        for query in test_queries:
            query_lower = query.lower()
            results = []
            
            for faq in data["faqs"]:
                question = faq.get("question", "").lower()
                if query_lower in question or any(word in question for word in query_lower.split()):
                    results.append(faq["question"])
            
            print(f"   Query: '{query}' -> {len(results)} results")
            if results:
                print(f"      Best match: {results[0][:60]}...")
        
        print("✅ Search simulation complete!")
        return True
    except Exception as e:
        print(f"❌ Search simulation failed: {e}")
        return False

def test_sample_faq_questions():
    """Display sample FAQs"""
    print("\n📋 Sample FAQs:")
    try:
        with open(FAQ_PATH, 'r') as f:
            data = json.load(f)
        
        for i, faq in enumerate(data["faqs"][:5], 1):
            print(f"\n   {i}. Q: {faq['question']}")
            answer = faq['answer'][:100]
            print(f"      A: {answer}...")
            print(f"      Category: {faq['category']}")
        
        print(f"\n   ... and {len(data['faqs']) - 5} more FAQs")
        return True
    except Exception as e:
        print(f"❌ Sample display failed: {e}")
        return False

def main():
    print("=" * 70)
    print("Day 5 Ericsson SDR Agent - Quick Test Suite")
    print("=" * 70)
    
    tests = [
        test_faq_loading,
        test_faq_categories,
        test_lead_storage,
        test_search_simulation,
        test_sample_faq_questions
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 70)
    print(f"Test Results: {sum(results)}/{len(results)} passed")
    print("=" * 70)
    
    if all(results):
        print("✅ All tests passed! Agent is ready to use.")
        print("\n🚀 To start the agent:")
        print("   1. cd Day5")
        print("   2. ./start_app.sh")
        print("   3. Open http://localhost:3000")
    else:
        print("❌ Some tests failed. Check the errors above.")
    
    return all(results)

if __name__ == "__main__":
    exit(0 if main() else 1)
