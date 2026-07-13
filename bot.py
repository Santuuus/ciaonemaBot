import datetime
import re
import requests
import discord
from discord import app_commands
from discord.ext import commands

# --- CONFIGURATION ---
TMDB_API_KEY = "92b9c9418069636f6417443209800aad"  # Replace with your TMDB v3 API Key
BOT_TOKEN = "MTUyNjIxODQ4Mjk0Nzk4NTQ0OA.GW8gh6.NDUXJEVTCX0wFlDRsuJF0yNalI9OZjOMUNOU90"
# ---------------------

intents = discord.Intents.default()
intents.guilds = True  # Required to manage server events [cite: 7]

class MovieEventBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        print(f'Logged in as {self.user}')
        await self.tree.sync()

bot = MovieEventBot()

def get_movie_data(tmdb_url: str):
    """Extracts the movie ID from the URL and fetches its data from TMDB."""
    # Extract the ID from a link like https://www.themoviedb.org/movie/12345-movie-name [cite: 19]
    match = re.search(r"/movie/(\d+)", tmdb_url)
    if not match:
        raise ValueError("Invalid TMDB movie URL format.")
    
    movie_id = match.group(1)
    
    # Query TMDB API for movie details [cite: 19]
    api_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
    response = requests.get(api_url)
    
    if response.status_code != 200:
        raise Exception("Could not find movie info on TMDB.")
        
    data = response.json()
    
    # Extract structural details [cite: 19]
    title = data.get("title", "Unknown Movie")
    release_date = data.get("release_date", "")
    year = release_date.split("-")[0] if release_date else "N/A"
    runtime = data.get("runtime", 0)
    
    # Get image banner (backdrop_path preferred for event banners) [cite: 19]
    image_path = data.get("backdrop_path") or data.get("poster_path")
    image_bytes = None
    if image_path:
        image_url = f"https://image.tmdb.org/t/p/w780{image_path}"
        img_res = requests.get(image_url)
        if img_res.status_code == 200:
            image_bytes = img_res.content

    return {
        "name": f"{title} ({year})",                     # Format: "Movie (year)" [cite: 19, 25]
        "description": f"Runtime de {runtime} minutos.",  # Format: "Runtime de [X] minutos." [cite: 19, 25]
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
    channel: discord.VoiceChannel  # Creates an interactive dropdown choice in Discord 
):
    # Defer response because fetching data and downloading images takes time [cite: 23]
    await interaction.response.defer(ephemeral=True)

    try:
        # 1. Parse combined date and time string into a timezone-aware UTC datetime object 
        try:
            naive_dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError("Incorrect date format. Please use 'YYYY-MM-DD HH:MM' (e.g., 2026-07-13 21:15).")
            
        start_time = naive_dt.replace(tzinfo=datetime.timezone.utc) # Discord requires aware datetimes [cite: 13, 26]
        end_time = start_time + datetime.timedelta(hours=2, minutes=30)  # Default buffer duration

        # 2. Fetch movie info and poster bytes from TMDB [cite: 19]
        movie = get_movie_data(tmdb_url)

        # 3. Create Scheduled Voice Event on the Server [cite: 9, 10, 68]
        guild = interaction.guild
        scheduled_event = await guild.create_scheduled_event(
            name=movie["name"],
            description=movie["description"],
            start_time=start_time,
            end_time=end_time,
            entity_type=discord.EntityType.voice, # Native Discord voice channel event 
            channel=channel,                      # Associated voice channel object 
            image=movie["image"],                 # Sets the movie poster/backdrop as the banner [cite: 19, 23]
            privacy_level=discord.PrivacyLevel.guild_only
        )

        await interaction.followup.send(
            f"🎬 **Event Created!**\n**Title:** {movie['name']}\n**Channel:** {channel.mention}\n**Link:** {scheduled_event.url}"
        )

    except ValueError as ve:
        await interaction.followup.send(f"❌ Input Error: {ve}")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to create event: {e}")

bot.run(BOT_TOKEN)