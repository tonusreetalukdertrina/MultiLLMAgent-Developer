import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import autogen

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("devqa")

REQUIRED_ENV_VARS = ["GROQ_API_KEY", "GOOGLE_API_KEY"]


def check_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Set them before calling ask() -- see the module docstring for how."
        )

def make_llm_config(provider: str, model: str, max_tokens: int = 600) -> dict:
    if provider == "groq":
        return {"config_list": [{
            "model": model,
            "api_key": os.environ["GROQ_API_KEY"],
            "api_type": "groq",
            "max_tokens": max_tokens,
        }]}
    if provider == "google":
        return {"config_list": [{
            "model": model,
            "api_key": os.environ["GOOGLE_API_KEY"],
            "api_type": "google",
            "max_tokens": max_tokens,
        }]}
    raise ValueError(f"Unknown provider: {provider}")

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_SMALL_MODEL = "openai/gpt-oss-20b"
GOOGLE_MODEL = "gemini-3.6-flash"

MEETING_STYLE = (
    "\n\nYou're in a live discussion with other experts, not writing a report. "
    "Speak like you're actually in the room: address colleagues by name when "
    "responding to them ('Building on what Backend said...', 'I'd push back on "
    "that a bit, DBMS...'), and react to what was just said instead of restating "
    "the whole question from scratch. You can go into real depth -- explain your "
    "reasoning, walk through a trade-off, include a short code example if it "
    "helps -- but stay conversational in tone rather than switching into "
    "formal report mode (avoid markdown tables and section headers here; save "
    "that structure for the final summary). Roughly one solid paragraph per "
    "turn is the right length -- enough to actually say something substantive, "
    "not so much that it reads like documentation."
)

EXPERT_CONFIG = {
    "Moderator": {
        "provider": "groq", "model": GROQ_SMALL_MODEL,
        "system_message": (
            "You are chairing a roundtable discussion between software experts. "
            "Open the meeting by briefly framing the question in one or two sentences "
            "and inviting the most relevant expert to start. During the discussion, "
            "if things stall or go in circles, redirect with a short prompt "
            "('Anyone want to weigh in on the caching side?'). When the discussion "
            "has covered the key angles, close it with: 'Good discussion -- let's "
            "wrap up there.' Keep everything you say brief and natural, like a real "
            "meeting chair, not a formal moderator script."
        ),
        "description": "Opens the meeting, keeps discussion on track, and closes it when the key angles are covered.",
    },
    "Frontend_Expert": {
        "provider": "groq", "model": GROQ_MODEL,
        "system_message": (
            "You are the Frontend Expert: HTML/CSS/JS, React/Vue/etc., accessibility, "
            "responsive design, browser quirks. If the question touches backend, database, "
            "or research-level concerns, say so explicitly and name which expert should "
            "weigh in next (e.g. 'I'd like the Backend Expert to confirm the API contract "
            "here'). Keep answers concrete and give code where useful."
        ) + MEETING_STYLE,
        "description": "Answers questions about UI, client-side code, browser behavior, and frontend frameworks.",
    },
    "Backend_Expert": {
        "provider": "groq", "model": GROQ_MODEL,
        "system_message": (
            "You are the Backend Expert: APIs, server architecture, auth, performance, "
            "language-specific idioms. If the question touches database design or "
            "query performance, say so explicitly and invite the DBMS Expert to weigh in. "
            "Keep answers concrete and give code where useful."
        ) + MEETING_STYLE,
        "description": "Answers questions about server-side architecture, APIs, auth, and backend performance.",
    },
    "DBMS_Expert": {
        "provider": "google", "model": GOOGLE_MODEL,
        "system_message": (
            "You are the DBMS Expert: schema design, indexing, query optimization, "
            "normalization, transactions, scaling strategies. Weigh in whenever data "
            "modeling or query performance is relevant, even if not directly addressed."
        ) + MEETING_STYLE,
        "description": "Answers questions about database schema, indexing, query optimization, and data modeling.",
    },
    "Research_Expert": {
        "provider": "google", "model": GOOGLE_MODEL,
        "system_message": (
            "You are the R&D Expert: emerging techniques, trade-offs between approaches, "
            "recent developments in software engineering. Flag clearly when something is "
            "uncertain or actively evolving. Weigh in when a question is genuinely open-ended "
            "or involves choosing between competing approaches."
        ) + MEETING_STYLE,
        "description": "Answers questions about architectural trade-offs, emerging techniques, and open-ended technical decisions.",
    },
    "General_Expert": {
        "provider": "groq", "model": GROQ_MODEL,
        "system_message": (
            "You are a Generalist Software Engineer. Answer directly when a question doesn't "
            "clearly belong to frontend, backend, DBMS, or research -- and don't be shy about "
            "saying when nobody else's input has been needed."
        ) + MEETING_STYLE,
        "description": "Answers general software engineering questions that don't clearly fit another expert's specialty.",
    },
}

MANAGER_MODEL = {"provider": "groq", "model": GROQ_SMALL_MODEL}
SYNTHESIZER_MODEL = {"provider": "google", "model": GOOGLE_MODEL}

MAX_DEBATE_ROUNDS = 6  # hard cap so a hand-off loop can't run forever

class MemoryStore:
    def __init__(self, path: str = "memory_store.json"):
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text("[]")

    def save_exchange(self, question: str, final_answer: str):
        history = json.loads(self.path.read_text())
        history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "final_answer": final_answer,
        })
        self.path.write_text(json.dumps(history, indent=2))

    def load_recent_context(self, n: int = 3) -> str:
        history = json.loads(self.path.read_text())
        if not history:
            return ""
        recent = history[-n:]
        lines = ["Context from earlier conversations (for reference only):"]
        for item in recent:
            lines.append(f"- Q: {item['question']}\n  A: {item['final_answer'][:300]}")
        return "\n".join(lines)

def build_expert_agents() -> dict:
    return {
        name: autogen.AssistantAgent(
            name=name,
            system_message=cfg["system_message"],
            description=cfg["description"],
            llm_config=make_llm_config(cfg["provider"], cfg["model"]),
        )
        for name, cfg in EXPERT_CONFIG.items()
    }


def build_user_proxy() -> autogen.UserProxyAgent:
    return autogen.UserProxyAgent(
        name="User",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=0,
        code_execution_config=False,
    )


def build_synthesizer() -> autogen.AssistantAgent:
    return autogen.AssistantAgent(
        name="Synthesizer",
        system_message=(
            "You read a multi-expert discussion about a developer's question and produce "
            "ONE concrete, actionable final answer. Note briefly where experts agreed or "
            "disagreed if it matters, but end with a clear recommendation -- don't just "
            "summarize, actually decide."
        ),
        llm_config=make_llm_config(SYNTHESIZER_MODEL["provider"], SYNTHESIZER_MODEL["model"]),
    )

def meeting_speaker_selection(last_speaker, groupchat):
    """Moderator always opens and closes; the manager LLM picks freely in between."""
    if len(groupchat.messages) <= 1:
        moderator = groupchat.agent_by_name("Moderator")
        return moderator if moderator else "auto"
    if len(groupchat.messages) >= MAX_DEBATE_ROUNDS - 1:
        moderator = groupchat.agent_by_name("Moderator")
        return moderator if moderator else "auto"
    return "auto"

def ask(question: str, memory: MemoryStore, verbose: bool = True) -> str:
    check_env()

    expert_agents = build_expert_agents()
    user_proxy = build_user_proxy()
    synthesizer = build_synthesizer()

    context = memory.load_recent_context()
    opening_message = f"{context}\n\nNew question: {question}" if context else question

    groupchat = autogen.GroupChat(
        agents=list(expert_agents.values()) + [user_proxy],
        messages=[],
        max_round=MAX_DEBATE_ROUNDS,
        speaker_selection_method=meeting_speaker_selection,  # manager LLM decides who speaks next each turn
    )
    manager = autogen.GroupChatManager(
        groupchat=groupchat,
        llm_config=make_llm_config(MANAGER_MODEL["provider"], MANAGER_MODEL["model"]),
    )

    if verbose:
        log.info("Starting expert discussion (visible below)...")

    # silent=False (default): the user watches the whole discussion happen
    # live, message by message, as it's printed to the console/notebook.
    user_proxy.initiate_chat(manager, message=opening_message)

    transcript = "\n\n".join(
        f"{m['name']}: {m['content']}" for m in groupchat.messages if m.get("content")
    )

    if verbose:
        log.info("Discussion finished -- synthesizing final answer...")

    user_proxy.initiate_chat(
        synthesizer,
        message=f"Original question: {question}\n\nFull discussion:\n{transcript}",
        max_turns=1,
        silent=True,  # only the final answer needs to print, not this one call
    )
    final_answer = synthesizer.last_message()["content"]

    memory.save_exchange(question, final_answer)
    return final_answer

if __name__ == "__main__":
    demo_question = (
        "How should we design a scalable e-commerce app for 100,000 concurrent users, "
        "with search, cart, checkout, and order history? What frontend, backend, and "
        "database architecture would you use, and what trade-offs matter most?"
    )
    memory = MemoryStore()
    print(f"Running demo question:\n{demo_question}\n")
    result = ask(demo_question, memory)
    print("\n" + "=" * 60)
    print("FINAL ANSWER")
    print("=" * 60)
    print(result)