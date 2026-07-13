import os
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
import datetime
import re
import requests
import discord
from discord import app_commands
from discord.ext import commands

# --- CONFIGURATION (Render Environment Variables) ---
# os.environ.get() reads the secure keys you will type into the Render dashboard
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")  
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
# -----------------------------------------------------

intents = discord.Intents.default()
intents.guilds = True  # Required to manage server events

class MovieEventBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        print(f'Logged in as {self.user}')
        try:
            # Sync commands globally for production deployment
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s) globally.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

bot = MovieEventBot()

def get_movie_data(tmdb_url: str):
    """Extracts the movie ID from the URL and fetches its data and English banner from TMDB."""
    match = re.search(r"/movie/(\d+)", tmdb_url)
    if not match:
        raise ValueError("Invalid TMDB movie URL format.")
    
    movie_id = match.group(1)
    
    # Query main details (English title)
    api_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
    response = requests.get(api_url)
    if response.status_code != 200:
        raise Exception("Could not find movie info on TMDB.")
        
    data = response.json()
    title = data.get("title", "Unknown Movie")
    release_date = data.get("release_date", "")
    year = release_date.split("-")[0] if release_date else "N/A"
    runtime = data.get("runtime", 0)
    
    # Query the /images endpoint to prioritize English banners
    images_url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={TMDB_API_KEY}"
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

    return {
        "name": f"{title} ({year})",
        "description": f"Runtime de {runtime} minutos.",
        "image": image_bytes
    }

@bot.tree.command(name="schedule_movie", description="Creates a server movie event using a TMDB link.")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    tmdb_url="The TMDB link to the movie",
    datetime_str="Date and time of the event (YYYY-MM-DD HH:MM)",
    channel="The voice channel where the movie will be streamed"
)
async def schedule_movie(
    interaction: discord.Interaction, 
    tmdb_url: str, 
    datetime_str: str, 
    channel: discord.VoiceChannel
):
    await interaction.response.defer(ephemeral=True)
    try:
        try:
            naive_dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError("Incorrect date format. Please use 'YYYY-MM-DD HH:MM' (e.g., 2026-07-13 21:15).")
            
        start_time = naive_dt.replace(tzinfo=datetime.timezone.utc)
        end_time = start_time + datetime.timedelta(hours=2, minutes=30)

        movie = get_movie_data(tmdb_url)
        guild = interaction.guild
        
        scheduled_event = await guild.create_scheduled_event(
            name=movie["name"],
            description=movie["description"],
            start_time=start_time,
            end_time=end_time,
            entity_type=discord.EntityType.voice,
            channel=channel,
            image=movie["image"],
            privacy_level=discord.PrivacyLevel.guild_only
        )

        await interaction.followup.send(
            f"🎬 **Event Created!**\n**Title:** {movie['name']}\n**Channel:** {channel.mention}\n**Link:** {scheduled_event.url}"
        )
    except ValueError as ve:
        await interaction.followup.send(f"❌ Input Error: {ve}")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to create event: {e}")

# --- RENDER WEB SERVICE WORKAROUND ---
def run_dummy_server():
    # Render automatically injects a "PORT" environment variable into Web Services
    port = int(os.environ.get("PORT", 8080))
    
    # Create a basic server that listens on all interfaces (0.0.0.0)
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Dummy web server listening on port {port} to keep Render happy...")
    server.serve_forever()

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN environment variable is missing!")
    else:
        # 1. Start the web server in a background thread so Render marks it as "Healthy"
        threading.Thread(target=run_dummy_server, daemon=True).start()
        
        # 2. Run your actual Discord bot on the main thread
        bot.run(BOT_TOKEN)