import time
import streamlit as st
from devqa import ask, MemoryStore, check_env

st.set_page_config(page_title="Dev Q&A -- Expert Panel", page_icon="🧑‍💻", layout="centered")

AVATARS = {
    "Frontend_Expert": "🎨",
    "Backend_Expert": "⚙️",
    "DBMS_Expert": "🗄️",
    "Research_Expert": "🔬",
    "General_Expert": "🧭",
}
FINAL_AVATAR = "✅"
USER_AVATAR = "🙋"

st.title("🧑‍💻 Multi-Agent Developer Q&A")
st.caption(
    "Ask a development question. A panel of specialist AI agents "
    "(Frontend, Backend, Database, R&D, and General) discuss it together, "
    "then a final answer is synthesized from the discussion."
)

try:
    check_env()
except EnvironmentError as e:
    st.error(str(e))
    st.stop()

if "memory" not in st.session_state:
    st.session_state.memory = MemoryStore()
if "history" not in st.session_state:
    st.session_state.history = []  # list of {"question": str, "turns": [...], "final_answer": str}


def render_expert_turn(turn, animate=False):
    avatar = AVATARS.get(turn["name"], "🗣️")
    display_name = turn["name"].replace("_", " ")
    with st.chat_message(display_name, avatar=avatar):
        box = st.empty()
        if animate:
            box.markdown(f"**{display_name}** *is typing...*")
            time.sleep(0.5)
        box.markdown(f"**{display_name}**\n\n{turn['content']}")
    if animate:
        time.sleep(0.3)


def render_final_answer(final_answer, animate=False):
    with st.chat_message("Final Answer", avatar=FINAL_AVATAR):
        box = st.empty()
        if animate:
            box.markdown("**Final Answer** *is typing...*")
            time.sleep(0.5)
        box.markdown(f"**Final Answer**\n\n{final_answer}")


# ---- Render every past exchange as part of one continuous chat ----
for exchange in st.session_state.history:
    st.chat_message("You", avatar=USER_AVATAR).write(exchange["question"])
    for turn in exchange["turns"]:
        render_expert_turn(turn, animate=False)
    render_final_answer(exchange["final_answer"], animate=False)

# Only show example buttons before the conversation has started -- once
# there's history, they'd just clutter a real chat thread.
question = None
if not st.session_state.history:
    st.markdown("**Try an example, or type your own question below:**")
    cols = st.columns(3)
    examples = [
        "Should we use REST or GraphQL for this app, and why?",
        "Should authentication use server-side sessions or JWT tokens?",
        "How should we design a scalable e-commerce checkout flow?",
    ]
    for col, ex in zip(cols, examples):
        if col.button(ex, use_container_width=True):
            question = ex

typed = st.chat_input("Ask a development question...")
if typed:
    question = typed

# ---- Handle a new question: show it immediately, then animate the reply ----
if question:
    st.chat_message("You", avatar=USER_AVATAR).write(question)

    with st.spinner("Experts are discussing your question..."):
        final_answer, turns = ask(question, st.session_state.memory, verbose=False, return_turns=True)

    for turn in turns:
        render_expert_turn(turn, animate=True)
    render_final_answer(final_answer, animate=True)

    st.session_state.history.append({
        "question": question,
        "turns": turns,
        "final_answer": final_answer,
    })