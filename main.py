import os
import threading
from flask import Flask
import discord
from discord.ext import commands

# =============================
# FLASK (ANTI-SLEEP)
# =============================
app = Flask(__name__)

@app.get("/")
def home():
    return "Bot actif"

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# =============================
# DISCORD
# =============================
intents = discord.Intents.all()

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook():
    await bot.load_extension("cogs.alerts")
    await bot.load_extension("cogs.reactions")

    # sync global (important multi-serveur)
    await bot.tree.sync()

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))