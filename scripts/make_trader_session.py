import os
from telethon import TelegramClient

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]

session_path = "/opt/tg-channel-lab/sessions/tg_lab_session_trader"
print("Creating trader session:", session_path + ".session")

client = TelegramClient(session_path, api_id, api_hash)
client.start()  # prompts phone + code (+ password if 2FA)
print("Session authorized =", client.is_user_authorized())
print("Saved:", session_path + ".session")
