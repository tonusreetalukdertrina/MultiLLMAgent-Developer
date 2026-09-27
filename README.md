# Multi-Agent Developer Q&A

A web app where a panel of AI experts (Frontend, Backend, Database, Research, General) discusses a development question together, then gives one clear final answer. Users can log in, keep private chats, and organize them into folders.

## What you need before starting

- Python 3.10 or newer
- Git
- API keys for:
  - **Groq** — free at [console.groq.com/keys](https://console.groq.com/keys)
  - **Google Gemini** — free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
  - **Google Gemini** — free at [betopia.ai](https://betopia.ai/)

## How to run it

### 1. Get the code

```bash
git clone https://github.com/tonusreetalukdertrina/MultiLLMAgent-Developer
cd MultiLLMAgent-Developer
```

### 2. Set up Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Add your API keys

Create a file named `.env` in the project folder with this content:

```
GROQ_API_KEY=your_groq_key_here
GOOGLE_API_KEY=your_google_key_here
CUSTOM_API_KEY=your_custom_key_here
```

### 4. Start the app

```bash
streamlit run app.py
```

A browser link will appear in the terminal (usually `http://localhost:8501`) — open it.

## Common issues

| Problem | Fix |
| --- | --- |
| `command not found: python` | Run `source venv/bin/activate` first |
| "Missing environment variable" error | Check your `.env` file has both API keys |
| App won't open in browser | Copy the exact URL printed in the terminal and paste it into your browser |
