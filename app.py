import streamlit as st
import db
from devqa import ask, MemoryStore, check_env, EXPERT_CONFIG

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

PROVIDER_LABELS = {
    "groq": "Groq",
    "google": "Google Gemini",
    "cerebras": "Cerebras",
    "custom": "Custom model",
}

db.init_db()

if "user" not in st.session_state:
    st.session_state.user = None
if st.session_state.user is None:
    token = st.query_params.get("session")
    if token:
        recovered_user = db.get_user_by_session(token)
        if recovered_user:
            st.session_state.user = recovered_user
if "history" not in st.session_state:
    st.session_state.history = []
if "history_loaded_for" not in st.session_state:
    st.session_state.history_loaded_for = None


def provider_caption(expert_name: str) -> str:
    """e.g. 'Groq · openai/gpt-oss-120b' -- shown under each expert's name so the multi-model nature of the system is visible, not hidden."""
    cfg = EXPERT_CONFIG.get(expert_name)
    if not cfg:
        return ""
    label = PROVIDER_LABELS.get(cfg["provider"], cfg["provider"])
    return f"{label} · `{cfg['model']}`"

# Auth screen
def show_auth_screen():
    st.title("🧑‍💻 Multi-Agent Developer Q&A")
    st.caption(
        "A panel of specialist AI agents discusses your development questions "
        "together, then gives you one clear final answer."
    )
    st.divider()

    login_tab, register_tab = st.tabs(["Log In", "Register"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log In", use_container_width=True, type="primary")
            if submitted:
                user = db.authenticate_user(username, password)
                if user:
                    token = db.create_session(user["id"])
                    st.session_state.user = user
                    st.query_params["session"] = token
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")

    with register_tab:
        with st.form("register_form"):
            new_username = st.text_input("Choose a username", key="reg_username")
            new_password = st.text_input("Choose a password", type="password", key="reg_password")
            confirm_password = st.text_input("Confirm password", type="password", key="reg_confirm")
            submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")
            if submitted:
                if new_password != confirm_password:
                    st.error("Passwords don't match.")
                else:
                    success, message = db.create_user(new_username, new_password)
                    if success:
                        st.success(message + " Switch to the Log In tab.")
                    else:
                        st.error(message)


if st.session_state.user is None:
    show_auth_screen()
    st.stop()

user_id = st.session_state.user["id"]
username = st.session_state.user["username"]

try:
    check_env()
except EnvironmentError as e:
    st.error(str(e))
    st.stop()

if "memory" not in st.session_state or st.session_state.get("memory_user_id") != user_id:
    st.session_state.memory = MemoryStore(user_id)
    st.session_state.memory_user_id = user_id

if st.session_state.history_loaded_for != user_id:
    past = db.get_conversations(user_id)
    st.session_state.history = [
        {"question": p["question"], "turns": p["turns"], "final_answer": p["final_answer"]}
        for p in past
    ]
    st.session_state.history_loaded_for = user_id

# Sidebar: account info, logout, and a quick-glance list of past questions
with st.sidebar:
    st.markdown(f"### 👤 {username}")
    if st.button("Log Out", use_container_width=True):
        token = st.query_params.get("session")
        if token:
            db.delete_session(token)
        st.query_params.clear()
        st.session_state.user = None
        st.session_state.history = []
        st.session_state.history_loaded_for = None
        st.rerun()

    st.divider()
    st.markdown("**Your recent questions**")
    if not st.session_state.history:
        st.caption("Nothing yet -- ask your first question to get started.")
    else:
        for exchange in reversed(st.session_state.history[-10:]):
            q = exchange["question"]
            short = q if len(q) <= 60 else q[:57] + "..."
            st.caption(f"• {short}")

# Main chat area
st.title("🧑‍💻 Expert Panel")
st.caption("Ask a development question below.")
st.divider()


def render_expert_turn(turn):
    avatar = AVATARS.get(turn["name"], "🗣️")
    display_name = turn["name"].replace("_", " ")
    caption = provider_caption(turn["name"])
    with st.chat_message(display_name, avatar=avatar):
        st.markdown(f"**{display_name}**" + (f"  \n:gray[{caption}]" if caption else ""))
        st.write(turn["content"])


def render_final_answer(final_answer):
    with st.chat_message("Final Answer", avatar=FINAL_AVATAR):
        st.markdown("**Final Answer**")
        st.write(final_answer)


if not st.session_state.history:
    st.markdown("**Try an example, or type your own question below:**")
    cols = st.columns(3)
    examples = [
        "Should we use REST or GraphQL for this app, and why?",
        "Should authentication use server-side sessions or JWT tokens?",
        "How should we design a scalable e-commerce checkout flow?",
    ]
    example_clicked = None
    for col, ex in zip(cols, examples):
        if col.button(ex, use_container_width=True):
            example_clicked = ex
else:
    example_clicked = None

for i, exchange in enumerate(st.session_state.history):
    st.chat_message("You", avatar=USER_AVATAR).write(exchange["question"])
    for turn in exchange["turns"]:
        render_expert_turn(turn)
    render_final_answer(exchange["final_answer"])
    if i < len(st.session_state.history) - 1:
        st.divider()

typed = st.chat_input("Ask a development question...")
question = typed or example_clicked

if question:
    st.divider()
    st.chat_message("You", avatar=USER_AVATAR).write(question)

    with st.spinner("The expert panel is discussing your question..."):
        final_answer, turns = ask(question, st.session_state.memory, verbose=False, return_turns=True)

    for turn in turns:
        render_expert_turn(turn)
    render_final_answer(final_answer)

    st.session_state.history.append({
        "question": question,
        "turns": turns,
        "final_answer": final_answer,
    })
    st.rerun()