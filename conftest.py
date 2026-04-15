import os

# Set dummy environment variables so config.py can be imported during test collection
# without requiring real credentials.
os.environ.setdefault("AZURE_SPEECH_KEY", "test-key")
os.environ.setdefault("AZURE_SPEECH_REGION", "japaneast")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
