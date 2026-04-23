import os
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# =======================
# TOKEN
# =======================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise SystemExit("Missing DISCORD_TOKEN")

# =======================
# INTENTS
# =======================
intents = discord.Intents.all()

bot = commands.Bot(command_prefix="!", intents=intents)

# =======================
# FLASK KEEP ALIVE
# =======================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Discord en ligne !"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# =======================
# COG LOADING (SAFE)
# =======================
@bot.event
async def setup_hook():
    print("🚀 Chargement des cogs...")

    extensions = [
        "cogs.alerts",
        "cogs.reactions",
        "cogs.pari",
    ]

    for ext in extensions:
        try:
            await bot.load_extension(ext)
            print(f"✔ {ext}")
        except Exception as e:
            print(f"❌ {ext} -> {e}")

    # =======================
    # SLASH SYNC (SAFE GLOBAL)
    # =======================
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Slash commands sync: {len(synced)}")
    except Exception as e:
        print(f"❌ Sync error: {e}")

# =======================
# READY
# =======================
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# =======================
# START
# =======================
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)