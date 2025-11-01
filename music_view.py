import discord
import wavelink
import asyncio
import aiohttp
from itertools import cycle

color_cycle = cycle([
    discord.Color.red(),
    discord.Color.orange(),
    discord.Color.gold(),
    discord.Color.green(),
    discord.Color.blue(),
    discord.Color.purple(),
])

loop_status = {}
bass_status = {}

# ===============================================
# FETCH LYRICS DARI GENIUS API
# ===============================================

async def get_lyrics(genius_token, query):
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {genius_token}"}
        async with session.get(
            "https://api.genius.com/search",
            params={"q": query},
            headers=headers
        ) as r:
            data = await r.json()
            if not data["response"]["hits"]:
                return None

            url = data["response"]["hits"][0]["result"]["url"]

        async with session.get(url) as page:
            html = await page.text()

        # ambil teks dari <div> lirik
        import re
        lyrics = re.findall(r'<div class="Lyrics__Container[^>]+>(.*?)</div>', html)
        if not lyrics:
            return None

        clean = re.sub(r"<.*?>", "", "\n".join(lyrics))
        return clean.strip()[:4000]  # limit aman Discord

# ===============================================
# VIEW BUTTON UNTUK KONTROL MUSIK
# ===============================================

class MusicControlView(discord.ui.View):
    def __init__(self, bot, ctx, player, track, genius_token):
        super().__init__(timeout=None)
        self.bot = bot
        self.ctx = ctx
        self.player = player
        self.track = track
        self.genius_token = genius_token

    # ======= BARIS 1 =======

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.blurple, emoji="⏭", row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.stop()
        await interaction.response.send_message("⏭ Lagu dilewati.", ephemeral=True)

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.gray, emoji="⏸", row=0)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.is_paused():
            await self.player.resume()
            button.label = "Pause"
            button.emoji = "⏸"
            await interaction.response.send_message("▶️ Musik dilanjutkan.", ephemeral=True)
        else:
            await self.player.pause()
            button.label = "Resume"
            button.emoji = "▶"
            await interaction.response.send_message("⏸ Musik dijeda.", ephemeral=True)
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, emoji="⏹", row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.stop()
        await interaction.response.send_message("⏹ Musik dihentikan.", ephemeral=True)

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.green, emoji="🔁", row=0)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        current = loop_status.get(guild_id, False)
        loop_status[guild_id] = not current
        state = "Aktif ✅" if not current else "Nonaktif ❌"
        await interaction.response.send_message(f"🔁 Mode loop sekarang **{state}**", ephemeral=True)

    # ======= BARIS 2 =======

    @discord.ui.button(label="Bass Boost", style=discord.ButtonStyle.primary, emoji="🎚", row=1)
    async def bass(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        enabled = bass_status.get(guild_id, False)
        if enabled:
            await self.player.set_eq(wavelink.Equalizer.flat())
            bass_status[guild_id] = False
            await interaction.response.send_message("🎧 Bass Boost **dimatikan.**", ephemeral=True)
        else:
            eq = wavelink.Equalizer.bass_boost()
            await self.player.set_eq(eq)
            bass_status[guild_id] = True
            await interaction.response.send_message("🎚 Bass Boost **diaktifkan!**", ephemeral=True)

    @discord.ui.button(label="Lyrics", style=discord.ButtonStyle.blurple, emoji="📜", row=1)
    async def lyrics(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        lyrics = await get_lyrics(self.genius_token, self.track.title)
        if not lyrics:
            await interaction.followup.send("❌ Lirik tidak ditemukan.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"📜 Lirik — {self.track.title}",
            description=lyrics,
            color=discord.Color.purple()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Help", style=discord.ButtonStyle.gray, emoji="❓", row=1)
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"🎵 {self.bot.user.name} — Help Menu",
            description=(
                "**Tombol kontrol musik:**\n"
                "⏭ Skip\n⏸ / ▶ Pause / Resume\n⏹ Stop\n🔁 Loop\n🎚 Bass Boost\n📜 Lyrics\n❓ Help\n\n"
                "Atau gunakan command: `!play`, `!queue`, `!skip`, `!lyrics`"
            ),
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ===============================================
# EMBED NOW PLAYING
# ===============================================

async def send_now_playing(ctx, bot, player, track, genius_token):
    embed = discord.Embed(
        title=f"🎶 Sekarang Memutar: {track.title}",
        description=f"[Klik untuk membuka lagu]({track.uri})",
        color=next(color_cycle)
    )
    embed.set_thumbnail(url=getattr(track, "thumbnail", None))
    embed.add_field(name="👤 Diminta oleh", value=ctx.author.mention)
    embed.set_footer(text=f"{bot.user.name} Music Bot", icon_url=bot.user.avatar.url if bot.user.avatar else None)

    view = MusicControlView(bot, ctx, player, track, genius_token)
    message = await ctx.send(embed=embed, view=view)

    async def update_embed():
        total = track.length / 1000
        current = 0
        while player.is_playing():
            await asyncio.sleep(5)
            current += 5
            if current > total:
                break
            bar_len = 20
            progress = int((current / total) * bar_len)
            bar = "▰" * progress + "▱" * (bar_len - progress)
            embed.description = f"[Klik untuk membuka lagu]({track.uri})\n\n`{bar}` `{int(current//60):02d}:{int(current%60):02d} / {int(total//60):02d}:{int(total%60):02d}`"
            embed.color = next(color_cycle)
            await message.edit(embed=embed, view=view)

    bot.loop.create_task(update_embed())
