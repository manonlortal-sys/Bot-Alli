import os
import threading
from flask import Flask
import discord
from discord.ext import commands

app = Flask(__name__)

@app.get("/")
def home():
    return "Bot actif"

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise SystemExit("Missing DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.reactions = True
# 🔴 Important pour lire le contenu des messages supprimés
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def setup_hook():
    print("🚀 setup_hook…")

    for ext in [
        "cogs.alerts",
        "cogs.alerts_runtime",# ✅ nouveau cog pour les logs de suppression
    ]:
        try:
            await bot.load_extension(ext)
            print(f"OK {ext}")
        except Exception as e:
            print(f"ERREUR {ext} →", e)

    for g in bot.guilds:
        try:
            await bot.tree.sync(guild=discord.Object(id=g.id))
            print("SYNC :", g.id)
        except Exception as e:
            print("SYNC ERROR :", e)


@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")


if __name__ == "__main__":
    print("⚡ Booting…")
    bot.run(DISCORD_TOKEN)
