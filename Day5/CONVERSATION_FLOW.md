# Multi-Company SDR Agent - Conversation Flow Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER CONNECTS                           │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
                   ┌──────────────────┐
                   │  GreeterAgent    │
                   │  (Receptionist)  │
                   └──────────────────┘
                             │
          "Which company would you like to speak with?"
                             │
                    ┌────────┴────────┬─────────────────────────┐
                    ↓                 ↓                         ↓
         ┌─────────────────┐  ┌────────────────┐         ┌──────────────┐
         │  "Ericsson"     │  │  "Taritas"     │         │ "Innogative" │
         └────────┬────────┘  └────────┬───────┘         └──────┬───────┘
                  ↓                    ↓                        ↓
     ┌──────────────────────┐ ┌─────────────────────┐ ┌────────────────────┐
     │ EricssonSDRAgent     │ │ TaritasSDRAgent     │ │ InnogativeSDRAgent │
     │ Enterprise 5G        │ │ Software Dev        │ │ Digital Marketing  │
     └──────────────────────┘ └─────────────────────┘ └────────────────────┘
                  │                    │                  │
                  └────────────────────┴──────────────────┘
                                       ↓
                          ┌────────────────────────┐
                          │  Unified Lead Storage  │
                          │  user_responses.json   │
                          └────────────────────────┘
```

## Conversation Flow Example

### Phase 1: Company Selection

```
┌──────────────────────────────────────────────────────────────────┐
│ GreeterAgent: "Hello! I can connect you with:                    │
│               - Ericsson India (Enterprise 5G)                   │
│               - Taritas Software Solutions (Software Dev)        │
│               - Innogative (Digital Marketing)                   │
│               Which company would you like to speak with?"       │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│ User: "I'd like to speak with Taritas"                           │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│ GreeterAgent: [Calls connect_to_company("taritas")]              │
│               [Hands off to TaritasSDRAgent]                     │
│               "Connecting you to Taritas representative..."      │
└──────────────────────────────────────────────────────────────────┘
```

### Phase 2: SDR Conversation (Example: Taritas)

```
┌──────────────────────────────────────────────────────────────────┐
│ TaritasSDRAgent: "Hi! I'm from Taritas Software Solutions in     │
│                  Jabalpur. We specialize in custom software      │
│                  and mobile app development. What brings you     │
│                  here today?"                                    │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│ User: "I need a mobile app for my business"                      │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│ TaritasSDRAgent: [Uses search_faq("mobile app")]                 │
│                  "We do cross-platform mobile app development    │
│                  using Xamarin, React Native, and Flutter.       │
│                  May I get your name?"                           │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│ User: "I'm Raj Kumar"                                            │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│ TaritasSDRAgent: [Calls save_lead_field("name", "Raj Kumar")]    │
│                  "Great to meet you, Raj! Which company are      │
│                  you with?"                                      │
└──────────────────────────────────────────────────────────────────┘
                                ↓
                   [Continues conversation...]
```

### Phase 3: Lead Capture

```
Fields Collected During Natural Conversation:
┌────────────────┬──────────────────────────────────────┐
│ Field          │ Value                                │
├────────────────┼──────────────────────────────────────┤
│ Name           │ Raj Kumar                            │
│ Company        │ TechVentures Pvt Ltd                 │
│ Email          │ raj@techventures.com                 │
│ Role           │ Technical Director                   │
│ Use Case       │ E-commerce mobile app                │
│ Team Size      │ 10-50                                │
│ Timeline       │ Next 3 months                        │
│ Questions      │ ["mobile app", "pricing", "timeline"]│
└────────────────┴──────────────────────────────────────┘
```

### Phase 4: Call Summary & Finalization

```
┌──────────────────────────────────────────────────────────────────┐
│ User: "Thanks, that's all I needed"                              │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│ TaritasSDRAgent: [Calls finalize_lead()]                         │
│                  "Thank you, Raj! Let me summarize:              │
│                  - Name: Raj Kumar                               │
│                  - Company: TechVentures Pvt Ltd                 │
│                  - Role: Technical Director                      │
│                  - Need: E-commerce mobile app                   │
│                  - Timeline: Next 3 months                       │
│                                                                  │
│                  I've saved your information and our team        │
│                  will contact you at raj@techventures.com.       │
│                  Have a great day!"                              │
└──────────────────────────────────────────────────────────────────┘
                                ↓
                    [Lead saved to database]
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     FAQ Data (Read)                             │
├─────────────────────────────────────────────────────────────────┤
│ ericsson_details.json ──→ EricssonSDRAgent.faq_data             │
│ taritas_details.json  ──→ TaritasSDRAgent.faq_data              │
│ innogative_details.json → InnogativeSDRAgent.faq_data           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  Lead Data (Write)                              │
├─────────────────────────────────────────────────────────────────┤
│ All SDR Agents ──→ user_responses.json                          │
│                    {                                            │
│                      "leads": [                                 │
│                        {                                        │
│                          "company_spoken_with": "Taritas...",   │
│                          "name": "Raj Kumar",                   │
│                          ...                                    │
│                        }                                        │
│                      ]                                          │
│                    }                                            │
└─────────────────────────────────────────────────────────────────┘
```

## Agent Handoff Mechanism

```
┌────────────────────────────────────────────────────────────────┐
│ 1. User in GreeterAgent                                        │
│    ↓                                                           │
│ 2. GreeterAgent.connect_to_company("taritas")                  │
│    ↓                                                           │
│ 3. Return tuple:                                               │
│    (TaritasSDRAgent(chat_ctx=self.chat_ctx,                    │
│                     tts=self.tts),                             │
│     "Connecting message...")                                   │
│    ↓                                                           │
│ 4. Framework performs handoff:                                 │
│    - Stops GreeterAgent                                        │
│    - Preserves chat history (chat_ctx)                         │
│    - Starts TaritasSDRAgent                                    │
│    - Maintains same TTS voice                                  │
│    ↓                                                           │
│ 5. TaritasSDRAgent.on_enter() executes                         │
│    - Greets user in new context                                │
│    - Continues conversation seamlessly                         │
└────────────────────────────────────────────────────────────────┘
```

## Tool Functions Per Agent

### GreeterAgent Tools
```
└─ connect_to_company(company: str)
   → Returns appropriate SDR agent instance
```

### All SDR Agent Tools (Identical structure, company-specific data)
```
├─ search_faq(query: str)
│  → Searches company-specific FAQ database
│
├─ get_company_info()
│  → Returns company overview
│
├─ get_use_cases(industry: Optional[str])
│  → Returns success stories
│
├─ save_lead_field(field: str, value: str)
│  → Stores individual lead field
│
├─ get_lead_summary()
│  → Reviews collected information
│
└─ finalize_lead()
   → Saves to unified database
```

## Multi-Company Comparison

```
┌──────────────┬───────────────┬─────────────────┬──────────────────┐
│ Aspect       │ Ericsson      │ Taritas         │ Innogative       │
├──────────────┼───────────────┼─────────────────┼──────────────────┤
│ Location     │ Global        │ Jabalpur/UK     │ Jabalpur         │
│ Industry     │ Telecom/5G    │ IT Consulting   │ Digital Mkt      │
│ Founded      │ 1876          │ 2012            │ 2022             │
│ Team Size    │ 100,000+      │ 50-249          │ 2-10             │
│ Target       │ Enterprises   │ Startups/SMEs   │ Local Business   │
│ Pricing      │ Enterprise    │ $1,000+         │ ₹5,000/month+    │
│ FAQs         │ 15            │ 15              │ 15               │
│ Focus        │ Private 5G    │ Mobile Apps     │ Social Media     │
└──────────────┴───────────────┴─────────────────┴──────────────────┘
```

## Success Metrics

```
✅ 3 Companies Supported
✅ 45 Total FAQs
✅ 4 Agents (1 Greeter + 3 SDR)
✅ Unified Lead Storage
✅ Context-Preserving Handoff
✅ Company-Specific Knowledge
✅ Natural Lead Capture
✅ 100% Test Coverage
```

---

**Ready to Handle Multiple Companies with Seamless Agent Handoff!**
