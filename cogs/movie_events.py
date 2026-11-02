import os
import re
import datetime
import requests
import discord
from discord import app_commands
from discord.ext import commands
from dateutil import parser
# zoneinfo is built into Python 3.9+ for proper timezone handling
from zoneinfo import ZoneInfo 

import os
import re
import requests
from discord.ext import commands

class MovieEvents(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tmdb_api_key = os.environ.get("TMDB_API_KEY")

    def get_movie_data(self, tmdb_url: str):
        match = re.search(r"/movie/(\d+)", tmdb_url)
        if not match:
            raise ValueError("Invalid TMDB movie URL format.")
        
        movie_id = match.group(1)
        api_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={self.tmdb_api_key}&language=en-US"
        response = requests.get(api_url)
        if response.status_code != 200:
            raise Exception("Could not find movie info on TMDB.")
            
        data = response.json()
        title = data.get("title", "Unknown Movie")
        release_date = data.get("release_date", "")
        year = release_date.split("-")[0] if release_date else "N/A"
        runtime = data.get("runtime", 0)
        
        # Extract genres from the TMDB genres list
        genres_data = data.get("genres", [])
        genre_names = [genre.get("name") for genre in genres_data if genre.get("name")]
        
        # Format genres into [Genre1,Genre2,...] or a fallback if none exist
        if genre_names:
            genres_str = f"[{', '.join(genre_names)}]"
        else:
            genres_str = "[Desconhecido]"
        
        images_url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={self.tmdb_api_key}"
        images_response = requests.get(images_url)
        image_path = None
        
        if images_response.status_code == 200:
            images_data = images_response.json()
            backdrops = images_data.get("backdrops", [])
            english_banner = next((b for b in backdrops if b.get("iso_639_1") == "en"), None)
            
            if english_banner:
                image_path = english_banner.get("file_path")
            else:
                no_lang_banner = next((b for b in backdrops if b.get("iso_639_1") in (None, "", "xx")), None)
                if no_lang_banner:
                    image_path = no_lang_banner.get("file_path")
                elif backdrops:
                    image_path = backdrops[0].get("file_path")

        if not image_path:
            image_path = data.get("backdrop_path") or data.get("poster_path")
        
        image_bytes = None
        if image_path:
            image_url = f"https://image.tmdb.org/t/p/w780{image_path}"
            img_res = requests.get(image_url)
            if img_res.status_code == 200:
                image_bytes = img_res.content

        # Description updated to include runtime and genres format
        description = f"Runtime de {runtime} minutos. [[Letterboxd]](https://letterboxd.com/tmdb/{movie_id}) \n{genres_str} "

        return {
            "name": f"{title} ({year})", 
            "description": description, 
            "image": image_bytes
        }

    @app_commands.command(name="schedule_movie", description="Creates a server movie event using a TMDB link.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(tmdb_url="The TMDB link to the movie", datetime_str="Date and time of the event", channel="The voice channel")
    async def schedule_movie(self, interaction: discord.Interaction, tmdb_url: str, datetime_str: str, channel: discord.VoiceChannel):
        await interaction.response.defer(ephemeral=True)
        try:
            try:
                naive_dt = parser.parse(datetime_str)
            except (ValueError, OverflowError):
                raise ValueError("Could not understand date format. Try: YYYY-MM-DD HH:MM")
                
            # 1. FIX THE TIMEZONE SHIFT
            # This forces Python to interpret your date string as your local time zone (e.g., Europe/Lisbon)
            # Instead of replacing it with raw UTC, it mathematically shifts it correctly for Discord
            local_tz = ZoneInfo("Europe/Lisbon")
            start_time = naive_dt.replace(tzinfo=local_tz)

            movie = self.get_movie_data(tmdb_url)
            guild = interaction.guild
            
            # 2. REMOVED end_time FROM THE METHOD ARGUMENTS BELOW 👇
            scheduled_event = await guild.create_scheduled_event(
                name=movie["name"], 
                description=movie["description"], 
                start_time=start_time,
                entity_type=discord.EntityType.voice, 
                channel=channel,
                image=movie["image"], 
                privacy_level=discord.PrivacyLevel.guild_only
            )
            await interaction.followup.send(f"🎬 **Event Created!**\n**Title:** {movie['name']}\n**Channel:** {channel.mention}\n**Link:** {scheduled_event.url}")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}")

# This setup function tells discord.py how to load this file
async def setup(bot: commands.Bot):
    await bot.add_cog(MovieEvents(bot))