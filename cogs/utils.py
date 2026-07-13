import discord
from discord import app_commands
from discord.ext import commands

class ImpromptuMessages(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="say", description="Force the bot to send a message, emoji, or sticker to a channel.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Where to send it", 
        message="What to say (Can include raw emojis like <:name:id>)",
        sticker_name="Optional: Name of a sticker from the bot's servers"
    )
    async def say(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel, 
        message: str = None, 
        sticker_name: str = None
    ):
        # Ensure the user provided at least a text message or a sticker
        if not message and not sticker_name:
            await interaction.response.send_message("❌ You must provide either a message or a sticker name!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            stickers_to_send = []
            
            # If a sticker name was given, search all servers the bot is in
            if sticker_name:
                found_sticker = None
                # Loop through every guild (server) the bot belongs to
                for guild in self.bot.guilds:
                    # Look for a sticker matching the typed name (case-insensitive)
                    found_sticker = discord.utils.get(guild.stickers, name=sticker_name)
                    if found_sticker:
                        break # Stop looking once found
                
                if found_sticker:
                    stickers_to_send.append(found_sticker)
                else:
                    await interaction.followup.send(f"⚠️ Warning: Could not find a sticker named '{sticker_name}'. Sending message only.")

            # Send the message to the target channel
            # stickers parameter takes a list, so we pass our list of 1 sticker
            await channel.send(content=message, stickers=stickers_to_send)
            
            await interaction.followup.send(f"✅ Successfully sent to {channel.mention}!", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to send: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ImpromptuMessages(bot))