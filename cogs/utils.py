import discord
from discord import app_commands
from discord.ext import commands

class ImpromptuMessages(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="say", description="Force the bot to send an impromptu message to a channel.")
    @app_commands.default_permissions(administrator=True) # Locks it to Admins only
    @app_commands.describe(channel="Where to send it", message="What to say")
    async def say(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        try:
            # Send the impromptu message to the targeted channel
            await channel.send(message)
            # Confirm back to you privately so nobody else sees the command usage
            await interaction.response.send_message(f"✅ Message sent to {channel.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to send: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ImpromptuMessages(bot))