import os
import threading
from flask import Flask
import discord
from discord.ext import commands

from storage import create_db, upsert_guild_config, upsert_team

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

    for ext in ["cogs.alerts", "cogs.reactions", "cogs.leaderboard", "cogs.attaque", "cogs.stats", "cogs.attackers", "cogs.pvp", "cogs.snapshots"]:
        try:
            await bot.load_extension(ext)
            print(f"✅ {ext} chargé")
        except Exception as e:
            print(f"❌ Erreur chargement {ext} :", e)

    # On conserve l'enregistrement d'une vue persistante vide (compat),
    # le panneau utilisé est généré dynamiquement à l'appel de /pingpanel
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
        # ⚙️ Config serveur principal (tes IDs d'origine)
        upsert_guild_config(
            guild_id=1139550147190214727,          # Serveur principal
            alert_channel_id=1139550892471889971,
            leaderboard_channel_id=1421866004270682113,
            snapshot_channel_id=1421866144679329984,
            role_g1_id=1419320456263237663,        # Wanted
            role_g2_id=1421860260377006295,        # Wanted 2
            role_g3_id=1421859079755927682,        # Snowflake
            role_g4_id=1419320615999111359,        # Secteur K
            role_test_id=1421867268421320844,      # TEST
            admin_role_id=1139578015676895342
        )
        # Seed des équipes dynamiques (1→7) + Prisme (8)
        upsert_team(1139550147190214727, 1, "Wanted",        1419320456263237663, "WANTED 1",     1)
        upsert_team(1139550147190214727, 2, "Wanted 2",      1421860260377006295, "WANTED 2",     2)
        upsert_team(1139550147190214727, 3, "Snowflake",     1421859079755927682, "SNOWFLAKE",    3)
        upsert_team(1139550147190214727, 4, "Secteur K",     1419320615999111359, "SECTEUR K",    4)
        upsert_team(1139550147190214727, 6, "HAGRATIME",     1421927858967810110, "HAGRATIME",    6)
        upsert_team(1139550147190214727, 7, "HagraPaLtime",  1421927953188524144, "HAGRAPALTIME", 7)
        # ➕ Nouvelle équipe : PRISME (bouton bleu)
        upsert_team(1139550147190214727, 8, "Prisme",        1421953218719518961, "PRISME",       8)

        print("✅ DB vérifiée/initialisée avec config serveur & équipes")
    except Exception as e:
        print("⚠️ Impossible d'initialiser la DB :", e)

    bot.run(DISCORD_TOKEN)
