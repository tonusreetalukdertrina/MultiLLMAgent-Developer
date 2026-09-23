import autogen

config = {"config_list": [{
    "model": "Ornith-1.5-35B-A3B-APEX-MTP-Quality",
    "api_key": "sk-llm-TsDyP9RPgjuaFxFrY3V1J-UFMy1p5gZINlS3YcPk6pw",
    "base_url": "https://models.betopiacloud.com/ornith/v1",
    "api_type": "openai",
}]}

agent = autogen.AssistantAgent(name="test", llm_config=config)
reply = agent.generate_reply(messages=[{"role": "user", "content": "What is a monolith?"}])
print(repr(reply))