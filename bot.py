import os
import threading
import asyncio
import discord
from discord.ext import commands
from http.server import SimpleHTTPRequestHandler, HTTPServer

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.guilds = True

class CiAonemaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # os.walk travels down through every subfolder recursively
        for root, dirs, files in os.walk("./cogs"):
            for filename in files:
                if filename.endswith(".py"):
                    # 1. Convert the system path syntax into python module dots
                    clean_root = root.replace("\\", ".").replace("/", ".")
                    
                    # 2. STRIP LEADING DOTS (Fixes the ExtensionNotFound error)
                    while clean_root.startswith("."):
                        clean_root = clean_root[1:]
                        
                    # 3. Combine folder path with the filename (removing the .py extension)
                    module_path = f"{clean_root}.{filename[:-3]}"
                    
                    await self.load_extension(module_path)
                    print(f"Loaded extension: {module_path}")

    async def on_ready(self):
        print(f'Logged in as {self.user}')
        
        # --- DYNAMIC CUSTOM STATUS ---
        # It reads from Render's Environment variables. 
        # If the variable isn't found, it defaults to "Watching CiAonema"
        status_text = os.environ.get("BOT_STATUS")
        
        custom_status = discord.CustomActivity(name=status_text)
        await self.change_presence(activity=custom_status)
        print(f"Custom Status dynamically set to: {status_text}")
        # -----------------------------

        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s) globally.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

bot = CiAonemaBot()

# --- RENDER WEB SERVICE WORKAROUND ---
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Dummy web server listening on port {port} to keep Render happy...")
    server.serve_forever()

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN environment variable is missing!")
    else:
        threading.Thread(target=run_dummy_server, daemon=True).start()
        bot.run(BOT_TOKEN)