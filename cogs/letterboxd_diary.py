import discord
from discord import app_commands
from discord.ext import commands, tasks
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser
from datetime import datetime, timezone
import os
from supabase import create_client, Client
from curl_cffi import requests

# --- Supabase Setup ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class LetterboxdCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.check_letterboxd_feeds.start()

    async def cog_unload(self):
        self.check_letterboxd_feeds.cancel()

    def truncate_text(self, text: str, limit: int = 400) -> str:
        if not text:
            return ""
        text = text.strip()
        if len(text) > limit:
            return text[: limit - 3] + "..."
        return text

    def format_entry_date(self, entry) -> str:
        watched_date = entry.get("letterboxd_watcheddate") or entry.get("letterboxd_watchedDate")
        if watched_date:
            try:
                dt = datetime.strptime(watched_date, "%Y-%m-%d")
                return dt.strftime("%b %d")  # e.g., "Aug 06"
            except ValueError:
                pass

    def get_user_avatar(self, username: str) -> str:
        url = f"https://letterboxd.com/{username}/"
        
        try:
            # Impersonate a modern browser TLS signature
            response = requests.get(url, impersonate="chrome120", timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Strategy 1: OpenGraph image meta tag (contains avatar or default user image)
                og_image = soup.find("meta", property="og:image")
                if og_image and og_image.get("content"):
                    return og_image["content"]
                
                # Strategy 2: Profile avatar container img tag
                avatar_img = soup.select_one("div.profile-avatar img, section.profile-header img")
                if avatar_img:
                    src = avatar_img.get("src") or avatar_img.get("data-src")
                    if src:
                        return src

        except Exception as e:
            print(f"Error fetching avatar for {username}: {e}")

    # --- Embed Helper ---
    def create_entry_embed(self, username: str, entry):
        # --- 1. Parse Metadata ---
        film_title = entry.get("letterboxd_filmtitle", "A Film")
        film_year = entry.get("letterboxd_filmyear", "")
        rating_raw = entry.get("letterboxd_memberrating", None)
        is_rewatch = entry.get("letterboxd_rewatch", "No").lower() == "yes"
        link = entry.get("link", f"https://letterboxd.com/{username}/")
        is_liked = entry.get("letterboxd_memberlike", "No").lower()=="yes"
        author = entry.get("author")
        date = self.format_entry_date(entry)

        # --- 2. Format Rating, Like, and Rewatch Emojis ---
        rating_display = ""
        if rating_raw:
            try:
                score = float(rating_raw)
                full_stars = int(score)
                has_half = (score - full_stars) >= 0.5
                rating_display = "<:star:1535975804335423518>" * full_stars + ("<:hstar:1535975780620836895>" if has_half else "")
            except ValueError:
                rating_display = rating_raw

        metadata_line = []
        metadata_line.append(f"{date}")
        if rating_display:
            metadata_line.append(f"{rating_display}")
        if is_liked:
            metadata_line.append("<:like:1535975756620894238>")
        if is_rewatch:
            metadata_line.append("<:rewatch:1535975724425543790>")

        status_str = " ".join(metadata_line)

        # --- 3. Parse Review Text & Poster Image ---
        description_html = entry.get("description", "")
        soup = BeautifulSoup(description_html, "html.parser")

        img_tag = soup.find("img")
        poster_url = img_tag["src"] if img_tag else None

        # Fetch User Avatar
        avatar_url = self.get_user_avatar(username)

        # Extract clean text paragraphs (excluding image descriptions)
        paragraphs = [p.get_text().strip() for p in soup.find_all("p") if not p.find("img")]
        review_text = "\n\n".join(paragraphs).strip()
        truncated_review = self.truncate_text(review_text, limit=400)

        # --- 4. Construct Embed ---
        embed_title = f"{film_title} ({film_year})" if film_year else film_title

        embed = discord.Embed(
            title=embed_title,
            url=link,
            color=discord.Color.from_rgb(128, 0, 32)
        )

        # Author header
        embed.set_author(
            name=f"{author} viu...",
            url=f"https://letterboxd.com/{username}/",
            icon_url=avatar_url
        )

        # Description combining metadata emojis + review text
        description_parts = []
        if status_str:
            description_parts.append(f"**{status_str}**")
        if review_text:
            description_parts.append(truncated_review)

        if description_parts:
            embed.description = "\n┈┈┈┈┈┈┈┈┈┈┈┈\n".join(description_parts)

        # Set Poster Thumbnail
        if poster_url:
            embed.set_thumbnail(url=poster_url)
        return embed

    # --- Feed Checker Task ---
    @tasks.loop(minutes=1)
    async def check_letterboxd_feeds(self):
        # Fetch all active subscriptions from Supabase
        response = supabase.table("letterboxd_subscriptions").select("*").execute()
        subscriptions = response.data

        for sub in subscriptions:
            channel_id = int(sub["channel_id"])
            username = sub["username"]
            last_posted_iso = sub["last_posted_at"]

            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    continue

            rss_url = f"https://letterboxd.com/{username}/rss/"
            feed = feedparser.parse(rss_url)

            if feed.bozo or not feed.entries:
                continue

            last_posted_dt = parser.parse(last_posted_iso)
            latest_processed_dt = last_posted_dt

            # Process entries from oldest to newest
            for entry in reversed(feed.entries):
                if "published" not in entry:
                    continue

                entry_dt = parser.parse(entry.published)

                if entry_dt > last_posted_dt:
                    embed = self.create_entry_embed(username, entry)
                    try:
                        await channel.send(embed=embed)
                        if entry_dt > latest_processed_dt:
                            latest_processed_dt = entry_dt
                    except Exception as e:
                        print(f"Error sending message to {channel_id}: {e}")

            # Update database record if newer entries were posted
            if latest_processed_dt > last_posted_dt:
                supabase.table("letterboxd_subscriptions").update({
                    "last_posted_at": latest_processed_dt.isoformat()
                }).eq("channel_id", str(channel_id)).eq("username", username).execute()

    @check_letterboxd_feeds.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # --- Commands ---
    @app_commands.command(name="follow", description="Segue um utilizador do letterboxd neste canal.")
    @app_commands.describe(username="Utilizador a seguir")
    @app_commands.default_permissions(administrator=True)
    async def follow(self, interaction: discord.Interaction, username: str):
        clean_user = username.strip().lower()
        avatar = self.get_user_avatar(username)
        channel_id = str(interaction.channel_id)

        # Check if already followed in Supabase
        res = supabase.table("letterboxd_subscriptions")\
            .select("*")\
            .eq("channel_id", channel_id)\
            .eq("username", clean_user)\
            .execute()

        if res.data:
            await interaction.response.send_message(
                f"**{clean_user}** já está a ser seguido neste canal!",
                ephemeral=True
            )
            return

        # Validate feed existence
        feed = feedparser.parse(f"https://letterboxd.com/{clean_user}/rss/")
        if feed.bozo or not hasattr(feed, "status") or feed.status != 200:
            await interaction.response.send_message(
                f"Não encontrei o utilizador (**{clean_user}**).",
                ephemeral=True
            )
            return

        # Initialize latest timestamp
        if feed.entries and "published" in feed.entries[0]:
            initial_iso = parser.parse(feed.entries[0].published).isoformat()
        else:
            initial_iso = datetime.now(timezone.utc).isoformat()

        # Insert into Supabase
        supabase.table("letterboxd_subscriptions").insert({
            "channel_id": channel_id,
            "username": clean_user,
            "last_posted_at": initial_iso
        }).execute()

        embed = discord.Embed(
            description=f"A seguir **{clean_user}**.",
            colour=0x800020
        )
        embed.set_thumbnail(url=avatar)
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="unfollow", description="Parar de seguir um utilizador neste canal.")
    @app_commands.describe(username="Utilizador a deixar de seguir")
    @app_commands.default_permissions(administrator=True)
    async def unfollow(self, interaction: discord.Interaction, username: str):
        clean_user = username.strip().lower()
        channel_id = str(interaction.channel_id)
        avatar = self.get_user_avatar(username)

        res = supabase.table("letterboxd_subscriptions")\
            .delete()\
            .eq("channel_id", channel_id)\
            .eq("username", clean_user)\
            .execute()

        embed = discord.Embed(
                description=f"Deixei de seguir **{clean_user}**.",
                colour=0x800020
                )
        embed.set_thumbnail(url=avatar)

        if res.data:
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                f"**{clean_user}** não está a ser seguido neste canal.",
                ephemeral=True
            )

    @app_commands.command(name="following", description="Lista de todos os utilizadores a serem seguidos neste canal.")
    async def following(self, interaction: discord.Interaction):
        channel_id = str(interaction.channel_id)

        res = supabase.table("letterboxd_subscriptions")\
            .select("username")\
            .eq("channel_id", channel_id)\
            .execute()

        followed = [row["username"] for row in res.data]

        if not followed:
            await interaction.response.send_message("Não há utilizadores a serem seguidos neste canal.")
            return

        user_list = "\n".join([f"• [{u}](https://letterboxd.com/{u}/)" for u in followed])
        embed = discord.Embed(
            title="Utilizadores Seguidos:",
            description=user_list,
            color=0x800020
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="test", description="Testar se o bot consegue publicar a entrada mais recente de um utilizador.")
    @app_commands.describe(username="The Letterboxd username to test")
    @app_commands.default_permissions(administrator=True)
    async def test(self, interaction: discord.Interaction, username: str):
        clean_user = username.strip().lower()

        # Defer interaction response in case feed parsing takes a second
        await interaction.response.defer()

        # Fetch and parse user's RSS feed
        rss_url = f"https://letterboxd.com/{clean_user}/rss/"
        feed = feedparser.parse(rss_url)

        # Check if user exists or if feed is valid
        if feed.bozo or not hasattr(feed, "status") or feed.status != 200:
            await interaction.followup.send(
                f"Could not retrieve Letterboxd feed for user **{clean_user}**."
            )
            return

        # Check if user has any entries on their profile
        if not feed.entries:
            await interaction.followup.send(
                f"User **{clean_user}** exists, but has no public diary entries or reviews yet."
            )
            return

        # Get the latest entry (first item in the RSS entries list)
        latest_entry = feed.entries[0]

        # Generate embed using your existing helper method
        embed = self.create_entry_embed(clean_user, latest_entry)

        # Send response with a test message confirmation
        await interaction.followup.send(
            embed=embed
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(LetterboxdCog(bot))