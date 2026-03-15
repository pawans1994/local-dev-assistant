def load_system_prompt():
    with open("prompts/system.md") as f:
        return f.read()