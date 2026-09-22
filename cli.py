from devqa import ask, MemoryStore, check_env

if __name__ == "__main__":
    check_env()  # fail fast with a clear message if keys aren't set
    memory = MemoryStore()
    print("Multi-agent dev Q&A (AutoGen) -- type a question (or 'quit'):\n")
    while True:
        q = input("> ").strip()
        if q.lower() in ("quit", "exit"):
            break
        if not q:
            continue
        try:
            print("─" * 60)
            print("MEETING STARTING")
            print("─" * 60 + "\n")
            answer = ask(q, memory)
            print("\n" + "=" * 60)
            print("FINAL ANSWER")
            print("=" * 60)
            print(answer + "\n")
        except Exception as e:
            print(f"\n[error] {e}\n")