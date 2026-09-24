import db
from devqa import ask, MemoryStore, check_env

CLI_USERNAME = "cli_user"
CLI_PASSWORD = "cli-local-only"  # not meant to be secure -- this account is local-only


def get_cli_user_id() -> int:
    db.init_db()
    user = db.authenticate_user(CLI_USERNAME, CLI_PASSWORD)
    if user is None:
        db.create_user(CLI_USERNAME, CLI_PASSWORD)
        user = db.authenticate_user(CLI_USERNAME, CLI_PASSWORD)
    return user["id"]


if __name__ == "__main__":
    check_env()
    user_id = get_cli_user_id()
    memory = MemoryStore(user_id)
    print("Multi-agent dev Q&A (AutoGen) -- type a question (or 'quit'):\n")
    while True:
        q = input("> ").strip()
        if q.lower() in ("quit", "exit"):
            break
        if not q:
            continue
        try:
            answer = ask(q, memory)
            print("\n" + "=" * 60)
            print("FINAL ANSWER")
            print("=" * 60)
            print(answer + "\n")
        except Exception as e:
            print(f"\n[error] {e}\n")