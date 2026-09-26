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
PROVIDER_LABELS = {"groq": "Groq", "google": "Google Gemini", "cerebras": "Cerebras", "custom": "Custom model"}
 
db.init_db()
 
for key, default in [
    ("user", None),
    ("current_chat_id", None),
    ("chat_history", []),
    ("history_loaded_for_chat", None),
    ("show_new_folder_input", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default
 
# Recover login after a page refresh via the session token in the URL.
if st.session_state.user is None:
    token = st.query_params.get("session")
    if token:
        recovered = db.get_user_by_session(token)
        if recovered:
            st.session_state.user = recovered
 
 
def provider_caption(expert_name: str) -> str:
    cfg = EXPERT_CONFIG.get(expert_name)
    if not cfg:
        return ""
    label = PROVIDER_LABELS.get(cfg["provider"], cfg["provider"])
    return f"{label} · `{cfg['model']}`"

# Auth screen
def show_auth_screen():
    st.title("🧑‍💻 Multi-Agent Developer Q&A")
    st.caption("Log in or create an account to start asking questions.")
    st.divider()
    login_tab, register_tab = st.tabs(["Log In", "Register"])
 
    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            if st.form_submit_button("Log In", use_container_width=True, type="primary"):
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
            confirm = st.text_input("Confirm password", type="password", key="reg_confirm")
            if st.form_submit_button("Create Account", use_container_width=True, type="primary"):
                if new_password != confirm:
                    st.error("Passwords don't match.")
                else:
                    success, message = db.create_user(new_username, new_password)
                    (st.success if success else st.error)(
                        message + (" Switch to the Log In tab." if success else "")
                    )
 
 
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

# Sidebar
 with st.sidebar:
    st.markdown(f"### 👤 {username}")
    if st.button("Log Out", use_container_width=True):
        token = st.query_params.get("session")
        if token:
            db.delete_session(token)
        st.query_params.clear()
        for key in ["user", "current_chat_id", "chat_history", "history_loaded_for_chat"]:
            st.session_state[key] = None if key != "chat_history" else []
        st.rerun()
 
    st.divider()
 
    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        new_chat_id = db.create_chat(user_id, folder_id=None, title="New Chat")
        st.session_state.current_chat_id = new_chat_id
        st.session_state.chat_history = []
        st.session_state.history_loaded_for_chat = new_chat_id
        st.rerun()
 
    if st.button("📁 New Folder", use_container_width=True):
        st.session_state.show_new_folder_input = True
 
    if st.session_state.show_new_folder_input:
        with st.form("new_folder_form", clear_on_submit=True):
            folder_name = st.text_input("Folder name", label_visibility="collapsed", placeholder="Folder name")
            if st.form_submit_button("Create Folder", use_container_width=True):
                if folder_name.strip():
                    db.create_folder(user_id, folder_name.strip())
                    st.session_state.show_new_folder_input = False
                    st.rerun()
 
    st.divider()
 
    folders = db.get_folders(user_id)
    all_chats = db.get_chats(user_id)
    unfiled_chats = [c for c in all_chats if c["folder_id"] is None]
 
    def chat_button(chat):
        label = chat["title"] if len(chat["title"]) <= 32 else chat["title"][:29] + "..."
        is_current = chat["id"] == st.session_state.current_chat_id
        if st.button(("💬 " if not is_current else "▶️ ") + label, key=f"chat_{chat['id']}", use_container_width=True):
            st.session_state.current_chat_id = chat["id"]
            st.session_state.history_loaded_for_chat = None  # force reload below
            st.rerun()
 
    for folder in folders:
        folder_chats = [c for c in all_chats if c["folder_id"] == folder["id"]]
        with st.expander(f"📁 {folder['name']} ({len(folder_chats)})", expanded=False):
            if not folder_chats:
                st.caption("No chats here yet.")
            for chat in folder_chats:
                chat_button(chat)
 
    if unfiled_chats:
        st.markdown("**Chats**")
        for chat in unfiled_chats:
            chat_button(chat)
 
    if not all_chats:
        st.caption("No chats yet -- click **New Chat** to start.")
 
    # Controls for the currently open chat: move to folder, rename, delete.
    if st.session_state.current_chat_id:
        current = db.get_chat(st.session_state.current_chat_id, user_id)
        if current:
            st.divider()
            st.caption("Current chat settings")
            folder_options = {"(none)": None, **{f["name"]: f["id"] for f in folders}}
            current_folder_name = next(
                (name for name, fid in folder_options.items() if fid == current["folder_id"]), "(none)"
            )
            chosen = st.selectbox(
                "Move to folder", options=list(folder_options.keys()),
                index=list(folder_options.keys()).index(current_folder_name),
                key=f"move_{current['id']}",
            )
            if folder_options[chosen] != current["folder_id"]:
                db.move_chat(current["id"], user_id, folder_options[chosen])
                st.rerun()
 
            if st.button("🗑️ Delete this chat", use_container_width=True):
                db.delete_chat(current["id"], user_id)
                st.session_state.current_chat_id = None
                st.session_state.chat_history = []
                st.rerun()

# Main area
st.title("🧑‍💻 Expert Panel")
 
if st.session_state.current_chat_id is None:
    st.info("Start a **New Chat** from the sidebar to ask your first question.")
    st.stop()
 
current_chat = db.get_chat(st.session_state.current_chat_id, user_id)
if current_chat is None:
    st.session_state.current_chat_id = None
    st.rerun()
 
st.caption(f"Chat: **{current_chat['title']}**")
st.divider()
 
if "memory" not in st.session_state or st.session_state.get("memory_chat_id") != current_chat["id"]:
    st.session_state.memory = MemoryStore(current_chat["id"])
    st.session_state.memory_chat_id = current_chat["id"]
 
if st.session_state.history_loaded_for_chat != current_chat["id"]:
    past = db.get_conversations(current_chat["id"])
    st.session_state.chat_history = past
    st.session_state.history_loaded_for_chat = current_chat["id"]
 
 
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
 
 
if not st.session_state.chat_history:
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
 
for i, exchange in enumerate(st.session_state.chat_history):
    st.chat_message("You", avatar=USER_AVATAR).write(exchange["question"])
    for turn in exchange["turns"]:
        render_expert_turn(turn)
    render_final_answer(exchange["final_answer"])
    if i < len(st.session_state.chat_history) - 1:
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
 
    st.session_state.chat_history.append({"question": question, "turns": turns, "final_answer": final_answer})
 
    # Auto-title a fresh "New Chat" from its first question
    if current_chat["title"] == "New Chat" and len(st.session_state.chat_history) == 1:
        auto_title = question if len(question) <= 40 else question[:37] + "..."
        db.rename_chat(current_chat["id"], user_id, auto_title)
 
    st.rerun()
 
