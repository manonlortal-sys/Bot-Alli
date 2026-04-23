import os
import discord
from discord.ext import commands

intents = discord.Intents.all()

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook():
    await bot.load_extension("cogs.alerts")
    await bot.load_extension("cogs.reactions")
    await bot.tree.sync()

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))