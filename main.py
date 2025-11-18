import os
import threading
from flask import Flask
import discord
from discord.ext import commands

from storage import create_db, upsert_guild_config, upsert_team

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

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def setup_hook():
    print("🚀 setup_hook…")

    for ext in [
        "cogs.alerts",
        "cogs.reactions",
        "cogs.leaderboard",
        "cogs.attackers",
        "cogs.attaque",
        "cogs.pvp",
        "cogs.rota",
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

    create_db()

    upsert_guild_config(
        guild_id=1139550147190214727,
        alert_channel_id=1139550892471889971,
        leaderboard_channel_id=1421866004270682113,
        snapshot_channel_id=1421866144679329984,
        role_g1_id=1419320456263237663,
        role_g2_id=1421860260377006295,
        role_g3_id=1421859079755927682,
        role_g4_id=1419320615999111359,
        role_test_id=1421867268421320844,
        admin_role_id=1139578015676895342
    )

    upsert_team(1139550147190214727, 1, "Wanted", 1419320456263237663, "WANTED 1", 1)
    upsert_team(1139550147190214727, 2, "Wanted 2", 1421860260377006295, "WANTED 2", 2)
    upsert_team(1139550147190214727, 3, "Snowflake", 1421859079755927682, "SNOWFLAKE", 3)
    upsert_team(1139550147190214727, 4, "Secteur K", 1419320615999111359, "SECTEUR K", 4)
    upsert_team(1139550147190214727, 5, "Rixe", 1421927584802934915, "RIXE", 5)
    upsert_team(1139550147190214727, 6, "HAGRATIME", 1421927858967810110, "HAGRATIME", 6)
    upsert_team(1139550147190214727, 7, "HagraPaLtime", 1421927953188524144, "HAGRAPALTIME", 7)
    upsert_team(1139550147190214727, 9, "Ruthless", 1437841408856948776, "RUTHLESS", 9)

    bot.run(DISCORD_TOKEN)
