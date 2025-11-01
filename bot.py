import discord
from discord.ext import commands
import wavelink
import json
from music_view import send_now_playing, get_lyrics, loop_status
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

with open("config.json") as f:
    config = json.load(f)

spotify = Spotify(auth_manager=SpotifyClientCredentials(
    client_id=config["spotify"]["client_id"],
    client_secret=config["spotify"]["client_secret"]
))

# ========== ON READY ==========
@bot.event
async def on_ready():
    print(f"✅ {bot.user} siap dipakai!")
    await wavelink.NodePool.create_node(
        bot=bot,
        host=config["lavalink"]["host"],
        port=config["lavalink"]["port"],
        password=config["lavalink"]["password"],
        https=config["lavalink"]["https"]
    )

# ========== PLAY ==========
@bot.command()
async def play(ctx, *, query: str):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect(cls=wavelink.Player)
        else:
            return await ctx.send("❌ Kamu harus di voice channel.")

    player: wavelink.Player = ctx.voice_client

    if "spotify.com" in query:
        if "track" in query:
            tid = query.split("/")[-1].split("?")[0]
            info = spotify.track(tid)
            query = f"{info['artists'][0]['name']} {info['name']}"
        elif "playlist" in query:
            pid = query.split("/")[-1].split("?")[0]
            items = spotify.playlist_items(pid)
            for item in items["items"]:
                s = item["track"]
                q = f"{s['artists'][0]['name']} {s['name']}"
                yt = await wavelink.YouTubeTrack.search(q, return_first=True)
                await player.queue.put_wait(yt)
            return await ctx.send(f"✅ {len(items['items'])} lagu dari playlist dimasukkan ke antrian.")

    track = await wavelink.YouTubeTrack.search(query, return_first=True)
    await player.play(track)
    await send_now_playing(ctx, bot, player, track, config["genius_token"])

# ========== LYRICS COMMAND ==========
@bot.command()
async def lyrics(ctx, *, query: str = None):
    query = query or "now playing"
    if query == "now playing" and ctx.voice_client and ctx.voice_client.is_playing():
        track = ctx.voice_client.track
        query = track.title
    await ctx.send("🔍 Mencari lirik...")
    lyrics = await get_lyrics(config["genius_token"], query)
    if not lyrics:
        return await ctx.send("❌ Lirik tidak ditemukan.")
    embed = discord.Embed(title=f"📜 Lirik — {query}", description=lyrics, color=discord.Color.purple())
    await ctx.send(embed=embed)

# ========== LEAVE ==========
@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Keluar dari voice channel.")
    else:
        await ctx.send("❌ Bot tidak sedang di voice channel.")

bot.run(config["token"])
