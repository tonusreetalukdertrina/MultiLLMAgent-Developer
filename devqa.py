import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import re

import time
import random

import autogen

import warnings
warnings.filterwarnings("ignore", message="Cost calculation")
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("devqa")

REQUIRED_ENV_VARS = ["GROQ_API_KEY", "GOOGLE_API_KEY", "CEREBRAS_API_KEY", "CUSTOM_API_KEY", "CUSTOM_BASE_URL"]


def check_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Set them before calling ask() -- see the module docstring for how."
        )

def with_retry(fn, max_attempts=4, base_delay=2):
    """Retry a callable on transient provider errors (503/overload), with
    exponential backoff + jitter. Re-raises immediately on anything else."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            transient = "503" in str(e) or "UNAVAILABLE" in str(e) or "overloaded" in str(e).lower()
            if not transient or attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            log.warning(f"Transient error (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {delay:.1f}s...")
            if attempt == 1:
                print("  (one of the providers is briefly overloaded — retrying automatically, just a moment...)")
            time.sleep(delay)    

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
    if provider == "cerebras":
        return {"config_list": [{
            "model": model,
            "api_key": os.environ["CEREBRAS_API_KEY"],
            "base_url": "https://api.cerebras.ai/v1",
            "api_type": "openai",
            "max_tokens": max_tokens,
        }]}
    if provider == "custom":
        return {"config_list": [{
            "model": model,
            "api_key": os.environ["CUSTOM_API_KEY"],
            "base_url": os.environ["CUSTOM_BASE_URL"],
            "api_type": "openai",
            "max_tokens": max_tokens,
        }]}
    raise ValueError(f"Unknown provider: {provider}")

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_SMALL_MODEL = "openai/gpt-oss-20b"
GOOGLE_MODEL = "gemini-3.6-flash"
CEREBRAS_MODEL = "gpt-oss-120b" 
CUSTOM_MODEL = "Ornith-1.5-35B-A3B-APEX-MTP-Quality"        # from Step 2's output
# CUSTOM_MODEL_ALT = "your-other-available-model"  # uncomment if you want a second option

MEETING_STYLE = (
    "\n\n=== CONVERSATION FORMAT RULES (follow these exactly) ===\n"
    "You're a trusted expert someone is genuinely asking for help, not writing "
    "a report. Answer warmly and directly, like a knowledgeable colleague. If "
    "someone already spoke, react to what they said by name.\n\n"
    "STRICT FORMATTING RULES:\n"
    "- Do NOT use markdown headers (##, ###).\n"
    "- Do NOT use markdown tables.\n"
    "- Write in plain conversational paragraphs, like you're talking, not "
    "documenting. A short code snippet is fine if truly needed.\n\n"
    "STOPPING RULE:\n"
    "Most questions only need ONE or TWO experts. If the question is already "
    "fully and correctly answered by what's been said so far, you MUST end "
    "your entire message with the single word ALL_SET on its own final line. "
    "This is not optional -- check before you finish: 'has this been "
    "answered? If yes, my last line must be ALL_SET.'"
)

EXPERT_CONFIG = {
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
        "provider": "groq", "model": GROQ_MODEL,
        "system_message": (
            "You are the DBMS Expert: schema design, indexing, query optimization, "
            "normalization, transactions, scaling strategies. Weigh in whenever data "
            "modeling or query performance is relevant, even if not directly addressed."
        ) + MEETING_STYLE,
        "description": "Answers questions about database schema, indexing, query optimization, and data modeling.",
    },
    "Research_Expert": {
        "provider": "groq", "model": GROQ_MODEL,
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
SYNTHESIZER_FALLBACK = {"provider": "groq", "model": GROQ_MODEL}

MAX_DEBATE_ROUNDS = 4  # hard cap so a hand-off loop can't run forever

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

def ask(question: str, memory: MemoryStore, verbose: bool = True) -> str:
    check_env()

    expert_agents = build_expert_agents()
    user_proxy = build_user_proxy()
    synthesizer = build_synthesizer()

    groupchat = autogen.GroupChat(
        agents=list(expert_agents.values()) + [user_proxy],
        messages=[],
        max_round=MAX_DEBATE_ROUNDS,
        speaker_selection_method="auto",
        allow_repeat_speaker=False,
    )
    manager = autogen.GroupChatManager(
        groupchat=groupchat,
        llm_config=make_llm_config(MANAGER_MODEL["provider"], MANAGER_MODEL["model"]),
        is_termination_msg=lambda msg: "all_set" in msg.get("content", "").lower(),
    )

    context = memory.load_recent_context()
    if context:
        # Injected directly into history so the model sees it, without it ever being printed to the console -- printing only happens on actual send/receive between agents, not on raw list entries.
        groupchat.messages.append({"role": "user", "name": "User", "content": context})

    if verbose:
        log.info("Starting expert discussion (visible below)...")

    # silent=False (default): the user watches the whole discussion happen
    # live, message by message, as it's printed to the console/notebook.
    with_retry(lambda: user_proxy.initiate_chat(manager, message=question))

    transcript = "\n\n".join(
        f"{m['name']}: {re.sub(r'(?i)all_set', '', m['content']).strip()}"
        for m in groupchat.messages if m.get("content")
    )

    if verbose:
        log.info("Discussion finished -- synthesizing final answer...")

    try:
        with_retry(lambda: user_proxy.initiate_chat(
            synthesizer,
            message=f"Original question: {question}\n\nFull discussion:\n{transcript}",
            max_turns=1,
            silent=True,
        ))
        final_answer = synthesizer.last_message()["content"]
    except Exception as e:
        if verbose:
            log.warning(f"Primary synthesizer failed after retries ({e}); falling back to Groq.")
        fallback_synthesizer = autogen.AssistantAgent(
            name="Synthesizer_Fallback",
            system_message=synthesizer.system_message,
            llm_config=make_llm_config(SYNTHESIZER_FALLBACK["provider"], SYNTHESIZER_FALLBACK["model"]),
        )
        user_proxy.initiate_chat(
            fallback_synthesizer,
            message=f"Original question: {question}\n\nFull discussion:\n{transcript}",
            max_turns=1,
            silent=True,
        )
        final_answer = fallback_synthesizer.last_message()["content"]

    memory.save_exchange(question, final_answer)
    return final_answer

# if __name__ == "__main__":
#     demo_question = (
#         "How should we design a scalable e-commerce app for 100,000 concurrent users, "
#         "with search, cart, checkout, and order history? What frontend, backend, and "
#         "database architecture would you use, and what trade-offs matter most?"
#     )
#     memory = MemoryStore()
#     print(f"Running demo question:\n{demo_question}\n")
#     result = ask(demo_question, memory)
#     print("\n" + "=" * 60)
#     print("FINAL ANSWER")
#     print("=" * 60)
#     print(result)