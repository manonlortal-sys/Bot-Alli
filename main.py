import os
import threading
from flask import Flask
import discord
from discord.ext import commands

from storage import create_db, upsert_guild_config

# ========= Flask keep-alive =========
app = Flask(__name__)

@app.get("/")
def home():
    return "Bot actif"

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# ========= Discord setup =========
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise SystemExit("Missing DISCORD_TOKEN environment variable.")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook():
    print("🚀 setup_hook démarré")

    for ext in ["cogs.alerts", "cogs.reactions", "cogs.leaderboard", "cogs.stats", "cogs.snapshots"]:
        try:
            await bot.load_extension(ext)
            print(f"✅ {ext} chargé")
        except Exception as e:
            print(f"❌ Erreur chargement {ext} :", e)

    try:
        from cogs.alerts import PingButtonsView
        bot.add_view(PingButtonsView(bot))
        print("✅ View PingButtonsView persistante enregistrée")
    except Exception as e:
        print("❌ Erreur enregistrement View PingButtonsView :", e)

    try:
        await bot.tree.sync()
        print("✅ Slash commands sync (global)")
    except Exception as e:
        print("❌ Slash sync error :", e)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    try:
        for g in bot.guilds:
            await bot.tree.sync(guild=discord.Object(id=g.id))
        print("✅ Slash commands synced per guild")
    except Exception as e:
        print("❌ Per-guild slash sync error:", e)

if __name__ == "__main__":
    print("⚡ Démarrage du bot...")
    try:
        create_db()
        # ⚙️ Config du serveur (tes IDs)
        upsert_guild_config(
            guild_id=1139550147190214727,          # Serveur
            alert_channel_id=1139550892471889971,  # Canal alertes
            leaderboard_channel_id=1421866004270682113,  # Canal leaderboard
            snapshot_channel_id=1421866144679329984,     # Canal snapshots
            role_g1_id=1419320456263237663,        # Wanted
            role_g2_id=1421860260377006295,        # Wanted 2
            role_g3_id=1421859079755927682,        # Snowflake
            role_g4_id=1419320615999111359,        # Secteur K
            role_test_id=1421867268421320844,      # TEST
            admin_role_id=1139578015676895342      # Admin
        )
        print("✅ DB vérifiée/initialisée avec config serveur")
    except Exception as e:
        print("⚠️ Impossible d'initialiser la DB :", e)

    bot.run(DISCORD_TOKEN)
