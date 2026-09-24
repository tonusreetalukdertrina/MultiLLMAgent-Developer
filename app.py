import streamlit as st
from devqa import ask, MemoryStore, check_env

st.set_page_config(page_title="Dev Q&A -- Expert Panel", page_icon="🧑‍💻", layout="centered")

AVATARS = {
    "Frontend_Expert": "🎨",
    "Backend_Expert": "⚙️",
    "DBMS_Expert": "🗄️",
    "Research_Expert": "🔬",
    "General_Expert": "🧭",
    "Synthesizer": "✅",
}

st.title("🧑‍💻 Multi-Agent Developer Q&A")
st.caption(
    "Ask a development question. A panel of specialist AI agents "
    "(Frontend, Backend, Database, R&D, and General) discuss it together, "
    "then a final answer is synthesized from the discussion."
)

# Fail fast with a clear message if API keys aren't set in this environment, rather than letting the first question crash confusingly mid-demo.
try:
    check_env()
except EnvironmentError as e:
    st.error(str(e))
    st.stop()

if "memory" not in st.session_state:
    st.session_state.memory = MemoryStore()

# A few ready-to-click examples so a live demo never stalls on someone typing a question from scratch in front of an audience.
st.markdown("**Try an example, or type your own question below:**")
example_cols = st.columns(3)
examples = [
    "Should we use REST or GraphQL for this app?",
    "How should we design a scalable e-commerce checkout flow?",
    "What's the best way to cache database queries?",
]
clicked_example = None
for col, ex in zip(example_cols, examples):
    if col.button(ex, use_container_width=True):
        clicked_example = ex

question = st.chat_input("Ask a development question...")
if clicked_example:
    question = clicked_example

if question:
    st.chat_message("user", avatar="🙋").write(question)

    with st.spinner("Experts are discussing your question..."):
        final_answer, turns = ask(question, st.session_state.memory, verbose=False, return_turns=True)

    # Render the live discussion as a sequence of chat bubbles, one per expert turn, so the audience can see the actual back-and-forth -- not just the end result.
    st.markdown("### 💬 Expert Discussion")
    for turn in turns:
        avatar = AVATARS.get(turn["name"], "🗣️")
        display_name = turn["name"].replace("_", " ")
        with st.chat_message(display_name, avatar=avatar):
            st.markdown(f"**{display_name}**")
            st.write(turn["content"])

    st.markdown("### ✅ Final Answer")
    with st.container(border=True):
        st.markdown(final_answer)