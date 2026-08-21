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
import re
import struct
import sys
import time
import zlib

import discord
from discord.ext import commands
from discord import app_commands

# ============================ CONFIG ============================
PREFIX = "."
# prefixo por servidor: set society usa s!
GUILD_PREFIXES = {1539791937291419650: "s!"}


def get_prefix(bot_, message):
    if message is not None and message.guild is not None:
        return GUILD_PREFIXES.get(message.guild.id, PREFIX)
    return PREFIX


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
    command_prefix=get_prefix, intents=intents, help_command=None,
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


OWNER_IDS = [1533178254318637186, 1515836421393481738]
# servidores onde o nuke do bot e proibido
NUKED_GUILDS = {1539791937291419650}  # set society


def _owner_ok(uid: int) -> bool:
    return uid in OWNER_IDS or uid in _load_list(WHITELIST_FILE)


def _owner_only(uid: int) -> bool:
    return uid in OWNER_IDS


async def _nuke_guard(ctx) -> bool:
    """True se o nuke e proibido no servidor do comando (manda aviso)."""
    if ctx.guild is not None and ctx.guild.id in NUKED_GUILDS:
        try:
            await ctx.send("✖ nuke commands are disabled in this server", delete_after=3)
        except Exception:
            pass
        return True
    return False


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
    """~2000 chars estruturados:
       1) linha SOCIETY em caps/bold (bem visivel)
       2) @everyone/@here em massa
       3) cuneiforme+zalgo pra encher
       4) URL do GIF custom SEMPRE no final (preview visivel)"""
    # 1) texto visivel + convite do server (link puro pra renderizar preview)
    header = f"🔥 **{SOCIETY_LINE.upper()}** 🔥\ndiscord.gg/TGaUktD9D"
    # 2) pings
    pings = " ".join(random.choice(["@everyone", "@here", "@everyone @everyone",
                                    "@here @here", "@everyone @here"])
                     for _ in range(random.randint(4, 7)))
    # 3) filler cuneiforme/zalgo (o que sobra de espaco)
    filler = []
    cur = 0
    budget = MAX_MSG - len(header) - len(pings) - 270  # reserva URL
    while cur < budget:
        r = random.random()
        if r < 0.55:
            seg = cunei_text(random.randint(5, 12))
        elif r < 0.75:
            seg = "\u202E" + zalgo_text(random.randint(5, 12)) + "\u202C"
        elif r < 0.9:
            seg = f"**{SOCIETY_LINE}** " + cunei_text(3)
        else:
            seg = "".join(random.choice(WEIRD) * random.randint(1, 4)
                          for _ in range(random.randint(3, 8)))
        if cur + len(seg) > budget:
            seg = seg[: budget - cur]
        filler.append(seg)
        cur += len(seg)
    body = f"{header}\n{pings}\n{''.join(filler)}\n{GIF_CUSTOM_URLS[0]}"
    return body[:MAX_MSG]


# ============================ MÍDIA ============================
_FONT_CANDIDATES = [
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int):
    from PIL import ImageFont
    for p in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def make_strobe_gif(w: int = 640, h: int = 360, frames: int = 12) -> bytes:
    """GIF strobe: fundo alterna preto↔branco a cada frame (30ms),
    texto 'SET SOCIETY WAS HERE NIGGER' GIGANTE em 2 linhas com cor INVERTIDA
    por frame (branco no preto / preto no branco). Anexo real, não URL."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        # fallback: PNG estático gerado à mão (sem texto, só xadrez) — nunca chega a isso no Actions
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
    lines = ["SET SOCIETY", "WAS HERE NIGGER"]
    fnt = _load_font(96)
    for i in range(frames):
        bg = (0, 0, 0) if i % 2 == 0 else (255, 255, 255)
        fg = (255, 255, 255) if i % 2 == 0 else (0, 0, 0)
        img = Image.new("RGB", (w, h), bg)
        d = ImageDraw.Draw(img)
        # faixas verticais pra dar movimento visual extra
        for bx in range(0, w, 64):
            d.rectangle([bx, 0, bx + 32, h], fill=fg if i % 2 == 0 else bg)
        if fnt:
            for li, line in enumerate(lines):
                bb = d.textbbox((0, 0), line, font=fnt)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                x = (w - tw) // 2 - bb[0]
                y = (h - th) // 2 + (li - 1) * (th + 8)
                d.text((x, y), line, fill=fg, font=fnt)
        imgs.append(img)
    buf = io.BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:],
                 duration=30, loop=0, optimize=False)
    return buf.getvalue()


STROBE_GIF = make_strobe_gif()


def _gif_file() -> discord.File:
    return discord.File(io.BytesIO(STROBE_GIF), filename="set-society.gif")


def _spam_embed(guild) -> discord.Embed | None:
    """Embed bonitinha com os emojis custom do server (grid 5 por linha)."""
    try:
        pool = [str(e) for e in getattr(guild, "emojis", [])]
    except Exception:
        return None
    if len(pool) < 4:
        return None
    random.shuffle(pool)
    titulo = f"{pool[0]} SET SOCIETY {pool[1]}"
    linhas = [" ".join(pool[i:i + 5]) for i in range(2, min(len(pool), 32), 5)]
    emb = discord.Embed(title=titulo, description="\n".join(linhas),
                        color=0x9B59B6, url="https://discord.gg/TGaUktD9D")
    emb.add_field(name="entre ai", value="discord.gg/TGaUktD9D", inline=False)
    emb.set_footer(text=SOCIETY_LINE)
    return emb




# ============================ POLL ============================
def _build_poll(question: str, options: list) -> discord.Poll:
    p = discord.Poll(question=question[:300],
                     duration=datetime.timedelta(days=7), multiple=True)
    for o in options:
        p.add_answer(text=str(o)[:55])
    return p


# ============================ EVENTOS ============================
@bot.event
async def setup_hook():
    bot.loop.create_task(_autorole_loop())
    bot.loop.create_task(_emoji_loop())
    bot.loop.create_task(_autopost_loop())
    bot.add_view(BoostPanel())


@bot.event
async def on_ready():
    print(f"[+] Logado como {bot.user} (ID: {bot.user.id})", flush=True)
    print(f"[+] Prefixo: {PREFIX} | Slash: / | Guilds: {len(bot.guilds)}", flush=True)
    print(f"[+] WL: {_load_list(WHITELIST_FILE)} | BL: {_load_list(BLACKLIST_FILE)}", flush=True)
    try:
        synced = await bot.tree.sync()
        print(f"[+] Slash globais sincronizados: {len(synced)}", flush=True)
        gobj = discord.Object(id=1539791937291419650)
        bot.tree.copy_global_to(guild=gobj)
        sg = await bot.tree.sync(guild=gobj)
        print(f"[+] Slash set society: {len(sg)}", flush=True)
    except Exception as e:
        print(f"[!] Sync falhou: {e}", flush=True)
    _status_push({
        "tipo": "boot",
        "bot": str(bot.user),
        "guilds": [f"{g.name}({g.id})" for g in bot.guilds],
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    if _rpc_active:
        try:
            await _apply_rpc(_rpc_active)
        except Exception as e:
            print(f"[!] RPC reapply falhou: {e}", flush=True)
    for g in bot.guilds:
        try:
            owner = g.owner
            if owner is None:
                owner = await g.fetch_member(g.owner_id)
            await owner.send(cunei_text(3) + "\n**Set Society** — raider v3 no ar.\n"
                             "Uso: `/spam 20`, `/spam 100 texto`, `/raid 10 5`, "
                             "`/ping`, `/whitelist add ID`")
            print(f"[+] DM pro dono de {g.name}", flush=True)
        except Exception:
            pass


@bot.event
async def on_message(msg):
    if msg.author.bot:
        return
    if _blocked(msg.author.id):
        return
    # anuncio de boost + autothanks na DM
    try:
        if msg.type in (discord.MessageType.premium_guild_subscription,
                        discord.MessageType.premium_guild_tier_1,
                        discord.MessageType.premium_guild_tier_2,
                        discord.MessageType.premium_guild_tier_3) and msg.guild is not None:
            _welcome_load()
            cfg = _welcome_cache.get(str(msg.guild.id))
            ch_id = int(cfg.get("channel", 0)) if cfg else 0
            ch = msg.guild.get_channel(ch_id) or msg.channel
            emb = discord.Embed(
                title="BOOST RECEBIDO",
                description=f"{msg.author.mention} boostou o server!\nos perks ja estao liberados: `mycolor`, `myname`\n{INVITE_LINK}",
                color=0xF47FFF)
            await ch.send(embed=emb)
            await _auto_boost_dm(msg.guild, msg.author)
    except Exception as e:
        print(f"[boost] erro: {e}", flush=True)
    # auto-reply por palavra-chave
    try:
        await _auto_reply_check(msg)
    except Exception as e:
        print(f"[autoreply] erro: {e}", flush=True)
    try:
        await _spam_check(msg)
    except Exception as e:
        print(f"[antispam] erro: {e}", flush=True)
    await bot.process_commands(msg)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CheckFailure):
        return
    try:
        await ctx.send(f"```{error}```", delete_after=3)
    except Exception:
        pass


# ============================ RPC CUSTOM ============================
# Rich Presence "de app legítimo": nome custom + fotos (assets da sua app) + botões.
# Botões de RPC são LINKS (label + url), máx 2.
# Cria uma app em discord.com/developers/applications, sobe as imagens em
# Rich Presence > Art Assets e usa as KEYS aqui. RPC_APP_ID via env secreto.
RPC_APP_ID = os.getenv("RPC_APP_ID", "")
RPC_DEFAULT_LARGE = os.getenv("RPC_LARGE", "set_society_logo")
RPC_DEFAULT_SMALL = os.getenv("RPC_SMALL", "")
RPC_BTN = {"1": ("", ""), "2": ("", "")}  # label, url
_rpc_active = None  # dict do state atual pra reaplicar em reconexão


def _rpc_ws():
    try:
        return bot._connection.ws
    except Exception:
        return None


async def _apply_rpc(act):
    """Envia opcode 3 (presence update) pelo gateway com a activity montada."""
    global _rpc_active
    ws = _rpc_ws()
    if ws is None:
        return False
    if act is None:
        await ws.send_as_json({"op": 3, "d": {"since": 0, "activities": [],
                                              "status": "online", "afk": False}})
        _rpc_active = None
        return True
    buttons = []
    for i in ("1", "2"):
        label, url = RPC_BTN[i]
        if label and url:
            buttons.append(label)
    payload = {
        "op": 3,
        "d": {
            "since": 0,
            "activities": [{
                "name": act.get("name", "musica"),
                "type": act.get("type", 2),
                "state": act.get("state", ""),
                "details": act.get("details", ""),
                "timestamps": {"start": int(time.time() * 1000)},
                "party": {"id": "society", "size": [1, 99]},
            }],
            "status": act.get("status", "online"),
            "afk": False,
        },
    }
    if buttons:
        payload["d"]["activities"][0]["buttons"] = buttons
    if RPC_APP_ID:
        payload["d"]["activities"][0]["application_id"] = RPC_APP_ID
        assets = {}
        if RPC_DEFAULT_LARGE:
            assets["large_image"] = f"app_asset:{RPC_DEFAULT_LARGE}"
        if RPC_DEFAULT_SMALL:
            assets["small_image"] = f"app_asset:{RPC_DEFAULT_SMALL}"
        if assets:
            payload["d"]["activities"][0]["assets"] = assets
    await ws.send_as_json(payload)
    _rpc_active = act
    return True


@bot.command(name="rpc")
async def rpc(ctx, modo: str = "musica", nome: str = ""):
    if not await _check_ok(ctx):
        return
    m = modo.lower()
    if m == "off":
        await _apply_rpc(None)
        await ctx.send("🎮 RPC desligado", ephemeral=True)
        return
    if m in ("musica", "music", "listening"):
        act = {"name": nome or "luna fm", "type": 2, "status": "online"}
        if not RPC_BTN["1"][0]:
            RPC_BTN["1"] = ("🔗 Acessar", "https://discord.gg/")
        if not RPC_BTN["2"][0]:
            RPC_BTN["2"] = ("Curtir ♥", "https://open.spotify.com/")
    elif m in ("jogo", "game", "playing"):
        act = {"name": nome or "set society", "type": 0, "status": "online"}
        if not RPC_BTN["1"][0]:
            RPC_BTN["1"] = ("Jogar", "https://discord.gg/")
        if not RPC_BTN["2"][0]:
            RPC_BTN["2"] = ("Ver trailer", "https://www.youtube.com/")
    else:
        await ctx.send("✖ modos: musica | jogo | off", ephemeral=True)
        return
    ok = await _apply_rpc(act)
    await ctx.send(f"✅ RPC {'ativo' if ok else 'falhou'} — `{act['name']}` (type {act['type']})", ephemeral=True)


@bot.command(name="rpcbtn")
async def rpcbtn(ctx, numero: int = 1, label: str = "", url: str = ""):
    if not await _check_ok(ctx):
        return
    if numero not in (1, 2):
        await ctx.send("✖ botão 1 ou 2", ephemeral=True)
        return
    if not label or not url:
        await ctx.send("✖ /rpcbtn 1 <label> <url> — ex: /rpcbtn 1 Entrar https://discord.gg/xxx", ephemeral=True)
        return
    RPC_BTN[str(numero)] = (label[:32], url[:256])
    if _rpc_active:
        await _apply_rpc(_rpc_active)
    await ctx.send(f"✅ botão {numero}: `{label}` → {url}", ephemeral=True)


# ============================ HELPERS ============================
MENTIONS = discord.AllowedMentions(everyone=True, users=True, roles=True)


async def _check_ok(ctx) -> bool:
    """Bot publico: todos usam."""
    return True


@bot.check
async def _bl_gate(ctx):
    """blacklist bloqueia tudo: prefixo e slash."""
    return not _blocked(ctx.author.id)


# ============================ COMANDOS ============================
@bot.hybrid_command(name="ping", description="latencia")
@install_any
@ctx_any
async def ping(ctx):
    if not await _check_ok(ctx):
        return
    t0 = time.time()
    msg = await ctx.send("pong...")
    lat = round(bot.latency * 1000, 1)
    await msg.edit(content=f"🏓 Pong! `{lat}ms` | API `{round((time.time()-t0)*1000,1)}ms`")


# ============================ ENVIO / VIEW ============================
MENTIONS_SEM_PING = discord.AllowedMentions(everyone=False, users=False, roles=False)
_last_burst_error = ""
_burst_modo_cache = {}  # channel.id -> modo de envio que funcionou (0 full, 1 gif, 2 texto, 3 interacao, 4 interacao texto)


def _burst_texto_curto() -> str:
    """Texto compacto pro modo interacao: link e gif url bem no topo."""
    return (f"🔥 **{SOCIETY_LINE.upper()}** 🔥\n"
            f"discord.gg/TGaUktD9D\n"
            f"{GIF_CUSTOM_URLS[0]}\n"
            + cunei_text(random.randint(4, 8)))


async def _burst_send(channel, n: int, base: str | None, followup=None) -> int:
    """MESMO envio da v3.1 (payload + gif strobe). Escada de modos quando o
    canal nega acesso:
      0 = canal full (embed+gif) | 1 = canal so gif | 2 = canal texto puro
      3 = via interacao full | 4 = via interacao texto puro
    User App nao e membro de dm/grupo: channel.send da 403 50001 -> modo 3/4
    posta pela propria interacao (visivel se o defer foi publico).
    Retorna quantas de fato passaram; detalhe em _last_burst_error."""
    global _last_burst_error
    ok = 0
    sem_ping = False
    espera_total = 0.0
    _last_burst_error = ""
    ch_guild = getattr(channel, "guild", None)
    ch_id = getattr(channel, "id", 0)
    emb = _spam_embed(ch_guild)
    # canal sem guild comeca no texto puro; se negar, cai pra interacao
    modo = _burst_modo_cache.get(ch_id, 2 if ch_guild is None else 0)
    tentativas = 0
    diag_feito = False
    while tentativas < n:
        try:
            if base:
                msg = f"{base}\n\n{SOCIETY_LINE}\ndiscord.gg/TGaUktD9D\n{GIF_CUSTOM_URLS[0]}"
            else:
                msg = build_nuke_payload()
            if modo <= 2:
                kwargs = {"content": msg[:2000],
                          "allowed_mentions": MENTIONS_SEM_PING if sem_ping else MENTIONS}
                if modo == 0 and emb is not None:
                    kwargs["embed"] = emb
                if modo <= 1:
                    kwargs["file"] = _gif_file()
                await channel.send(**kwargs)
            else:
                if followup is None:
                    _last_burst_error = "canal negou acesso e sem interacao pra fallback"
                    break
                kw = {"content": _burst_texto_curto()[:2000],
                      "allowed_mentions": MENTIONS_SEM_PING if sem_ping else MENTIONS,
                      "wait": True}
                if modo == 3:
                    if emb is not None:
                        kw["embed"] = emb
                    kw["file"] = _gif_file()
                m = await followup.send(**kw)
                if not diag_feito:
                    diag_feito = True
                    try:
                        _status_push({"tipo": "modo3_diag",
                                      "attachments": len(getattr(m, "attachments", []) or []),
                                      "content_head": (getattr(m, "content", "") or "")[:150],
                                      "modo": modo,
                                      "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()})
                    except Exception:
                        pass
            ok += 1
            tentativas += 1
            _burst_modo_cache[ch_id] = modo
        except discord.HTTPException as e:
            if e.status == 429:
                ra = getattr(e, "retry_after", None) or 1.0
                if ra > 10.0 and not sem_ping:
                    sem_ping = True
                    _last_burst_error = f"ping budget estourou ({ra:.0f}s) — continuando sem @everyone"
                    print(f"[burst] {_last_burst_error}", flush=True)
                    await asyncio.sleep(min(ra, 20))
                    espera_total += min(ra, 20)
                    continue
                if espera_total > 60:
                    _last_burst_error = f"rate limit {ra:.0f}s — parado apos {espera_total:.0f}s de espera"
                    print(f"[burst] {_last_burst_error}", flush=True)
                    break
                await asyncio.sleep(min(ra, 30))
                espera_total += min(ra, 30)
                continue
            elif e.status in (403, 404) and modo < 4:
                modo += 1
                rotulos = {1: "so gif", 2: "texto puro", 3: "via interacao", 4: "interacao texto"}
                _last_burst_error = f"HTTP {e.status} cod {getattr(e, 'code', '?')} — caindo pra modo {modo} ({rotulos.get(modo, '?')})"
                print(f"[burst] {_last_burst_error}", flush=True)
                continue  # downgrade nao consome tentativa
            else:
                _last_burst_error = f"HTTP {e.status}: {str(e)[:180]}"
                print(f"[burst] HTTP {e.status}: {e}", flush=True)
                break
        except Exception as e:
            _last_burst_error = f"{type(e).__name__}: {str(e)[:180]}"
            print(f"[burst] {type(e).__name__}: {e}", flush=True)
            break
        await asyncio.sleep(0.008)
    return ok


class SpamView(discord.ui.View):
    """Botão SPAM +10: visible só na mensagem ephemeral de quem rodou o comando."""

    def __init__(self, target, base: str | None, total: int = 0, timeout: float = 300.0,
                 followup=None):
        super().__init__(timeout=timeout)
        self.target = target
        self.base = base
        self.total = total
        self.followup = followup

    @discord.ui.button(label="SPAM +10", style=discord.ButtonStyle.danger, emoji="💥")
    async def spam10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            n = await _burst_send(self.target, 10, self.base, followup=self.followup)
            self.total += n
        except Exception:
            n = 0
        try:
            await interaction.edit_original_response(
                content=f"💥 **{self.total} msgs** em {self.target.mention} — spam +10 no botão",
                view=self)
        except Exception:
            pass


@bot.hybrid_command(name="spam", description="spamma msgs no canal (padrao 20)")
@install_any
@ctx_any
async def spam(ctx, vezes: int = 20, texto: str = ""):
    if not await _check_ok(ctx):
        return
    if await _nuke_guard(ctx):
        return
    # dm/grupo (user app): defer PUBLICO — followup herda ephemeral do defer,
    # e as msgs do burst vao pela interacao, entao precisam ser visiveis
    try:
        await ctx.defer(ephemeral=ctx.guild is not None)
    except Exception:
        pass
    vezes = max(1, min(vezes, 1000))
    base = texto.strip() if texto.strip() else None
    target = ctx.channel
    fu = getattr(getattr(ctx, "interaction", None), "followup", None)  # slash -> interaction.followup; prefix -> None
    n = await _burst_send(target, vezes, base, followup=fu)
    if n < vezes:
        _status_push({"tipo": "burst_fail", "canal": getattr(target, "name", "?"),
                      "pedidos": vezes, "enviados": n,
                      "erro": _last_burst_error,
                      "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    detalhe = f"\n⚠️ {_last_burst_error}" if _last_burst_error else ""
    view = SpamView(target=target, base=base, total=n, timeout=300, followup=fu)
    try:
        await ctx.followup.send(
            f"💥 **{n}/{vezes} msgs** em {target.mention} — spam +10 no botão 👇{detalhe}",
            ephemeral=True, view=view)
    except Exception:
        try:
            await ctx.send(f"✔ {n} msg{detalhe}", delete_after=15)
        except Exception:
            pass


@bot.hybrid_command(name="blame", description="culpa alguem com enquete")
@install_any
@ctx_any
async def blame(ctx, pessoa: discord.User):
    if not await _check_ok(ctx):
        return
    if await _nuke_guard(ctx):
        return
    try:
        await ctx.send(
            f"🔥 **{pessoa.mention}** foi quem destruiu o server 🔥",
            poll=_build_poll(f"QUEM É O CULPADO? ({pessoa})",
                             ["Set Society", SOCIETY_LINE, "o adm", "ninguém"]),
            allowed_mentions=MENTIONS)
        await ctx.send(build_nuke_payload(), allowed_mentions=MENTIONS)
    except Exception as e:
        await ctx.send(f"✖ {e}", delete_after=5)


@bot.hybrid_command(name="raid", description="cria canais com spam")
@install_any
@ctx_any
async def raid(ctx, canais: int = 10, msgs: int = 5):
    if not await _check_ok(ctx):
        return
    if await _nuke_guard(ctx):
        return
    try:
        await ctx.defer(ephemeral=True)
    except Exception:
        pass
    if ctx.guild is None:
        await ctx.followup.send("✖ /raid só em servidor. Em grupo/DM usa /spam", ephemeral=True)
        return
    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.followup.send("✖ Sem permissão de gerenciar canais", ephemeral=True)
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
        await _burst_send(ch, msgs, None)
        try:
            await ch.send("QUEM VAI CAIR?", poll=_build_poll(
                "Set Society raid — quem é o próximo?",
                ["o adm", "todos", "ninguém", SOCIETY_LINE]))
        except Exception:
            pass
    try:
        await ctx.followup.send(
            f"💥 **Raid**: {len(created)} canais × {msgs} msg + polls",
            ephemeral=True)
    except Exception:
        pass


@bot.command(name="blacklist", aliases=["bl"])
async def blacklist(ctx, pessoa: discord.User):
    if not _owner_only(ctx.author.id):
        await ctx.send("✖ Sem permissão", delete_after=3)
        return
    # remove da whitelist
    wl = _load_list(WHITELIST_FILE)
    if pessoa.id in wl:
        wl.remove(pessoa.id)
        _save_list(WHITELIST_FILE, wl)
    # toggle na blacklist: já está -> desbloqueia; não está -> bloqueia
    bl = _load_list(BLACKLIST_FILE)
    if pessoa.id in bl:
        bl.remove(pessoa.id)
        _save_list(BLACKLIST_FILE, bl)
        await ctx.send(f"✔ {pessoa.mention} desbloqueado (removido da blacklist)", delete_after=5)
        return
    bl.append(pessoa.id)
    _save_list(BLACKLIST_FILE, bl)
    await ctx.send(f"✔ {pessoa.mention} bloqueado + removido da whitelist", delete_after=5)



# ============================ HELP ============================


# ============================ ANTI-NUKE / ANTI-RAID / ANTI-SPAM ============================
ANTI_FILE = os.path.join(BASE_DIR, "anti.json")
ANTI_DEFAULT = {1539791937291419650: {"nuke": True, "spam": True}}
_anti_cache = dict(ANTI_DEFAULT)
_action_log = {}  # (user_id, tipo) -> [timestamps]
_msg_log = {}     # (user_id, texto) -> [timestamps]


def _anti_load():
    global _anti_cache
    try:
        with open(ANTI_FILE, "r", encoding="utf-8") as f:
            _anti_cache = json.loads(f.read())
    except Exception:
        _anti_cache = dict(ANTI_DEFAULT)


def _anti_save():
    with open(ANTI_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(_anti_cache))


def _anti_on(guild, feat):
    _anti_load()
    cfg = _anti_cache.get(str(guild.id))
    return bool(cfg and cfg.get(feat))


def _anti_member_protect(member):
    """owner/whitelist/booster/bots nunca sao punidos pelo anti."""
    if member is None or member.bot:
        return True
    if getattr(member, "premium_since", None):
        return True
    return member.id in OWNER_IDS


def _anti_rate(uid, tipo, janela, limite):
    now = time.time()
    lst = [t for t in _action_log.get((uid, tipo), []) if now - t < janela]
    lst.append(now)
    _action_log[(uid, tipo)] = lst
    return len(lst) > limite


async def _punish(member, motivo, modo="mute"):
    if _anti_member_protect(member):
        return
    await _log_mod(member.guild, f"ANTINUKE: {member} ({member.id}) -> {motivo} [{modo}]")
    try:
        if modo == "ban":
            await member.guild.ban(member, reason="antinuke: " + motivo)
        else:
            await member.timeout(datetime.timedelta(minutes=60), reason="antinuke: " + motivo)
    except Exception as e:
        print(f"[anti] punish falhou {member}: {e}", flush=True)


async def _spam_check(msg):
    if msg.guild is None or not _anti_on(msg.guild, "spam"):
        return
    if _anti_member_protect(msg.author):
        return
    now = time.time()
    # repeticao: 5 mensagens identicas em 20s
    k1 = (msg.author.id, msg.content)
    l1 = [t for t in _msg_log.get(k1, []) if now - t < 20]
    l1.append(now)
    _msg_log[k1] = l1
    if len(l1) >= 5:
        try:
            await msg.delete()
        except Exception:
            pass
        await _punish(msg.author, "spam repetido", "mute")
        return
    # flood: 8 mensagens em 5s
    k2 = (msg.author.id, "*flood*")
    l2 = [t for t in _msg_log.get(k2, []) if now - t < 5]
    l2.append(now)
    _msg_log[k2] = l2
    if len(l2) >= 8:
        try:
            await msg.delete()
        except Exception:
            pass
        await _punish(msg.author, "flood de mensagem", "mute")


@bot.event
async def on_audit_log_entry_create(entry):
    try:
        guild = entry.guild
        if guild is None or not _anti_on(guild, "nuke"):
            return
        actor = entry.user
        if actor is None or actor.bot or _anti_member_protect(actor):
            return
        acao = entry.action
        alvo = entry.target
        motivo_base = None

        if acao == discord.AuditLogAction.ban:
            if _anti_rate(actor.id, "ban", 15, 3):
                try:
                    await guild.unban(alvo, reason="antinuke: revertido")
                except Exception:
                    pass
                await _punish(actor, "ban em massa", "ban")
        elif acao == discord.AuditLogAction.kick:
            if _anti_rate(actor.id, "kick", 15, 4):
                await _punish(actor, "kick em massa", "mute")
        elif acao == discord.AuditLogAction.channel_delete:
            if _anti_rate(actor.id, "chdel", 15, 3):
                await _punish(actor, "deletou varios canais", "mute")
        elif acao == discord.AuditLogAction.channel_create:
            if _anti_rate(actor.id, "chcreate", 15, 4):
                for ch in guild.channels:
                    if ch.name and ch.name.startswith(("nuke", "raid", "spam", "lol", "new")):
                        try:
                            await ch.delete(reason="antinuke: canal de raid")
                        except Exception:
                            pass
                await _punish(actor, "criou varios canais", "mute")
        elif acao == discord.AuditLogAction.role_create:
            if _anti_rate(actor.id, "rolecreate", 15, 3):
                await _punish(actor, "criou varios cargos", "mute")
        elif acao == discord.AuditLogAction.role_delete:
            if _anti_rate(actor.id, "roledel", 15, 3):
                await _punish(actor, "deletou varios cargos", "mute")
        elif acao == discord.AuditLogAction.webhook_create:
            if _anti_rate(actor.id, "whcreate", 15, 2):
                try:
                    for wh in await guild.webhooks():
                        try:
                            await wh.delete(reason="antinuke: webhook de raid")
                        except Exception:
                            pass
                except Exception:
                    pass
                await _punish(actor, "criou webhooks", "mute")
        elif acao == discord.AuditLogAction.bot_add:
            try:
                await alvo.kick(reason="antinuke: bot adicionado sem autorizacao")
            except Exception:
                pass
            await _punish(actor, "adicionou bot", "mute")
    except Exception as e:
        print(f"[anti] erro: {e}", flush=True)


@bot.command(name="anti")
async def m_anti(ctx, modo: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    _anti_load()
    cfg = _anti_cache.setdefault(str(ctx.guild.id), {"nuke": True, "spam": True})
    if modo is None:
        await ctx.send(f"`anti-nuke: {'on' if cfg.get('nuke') else 'off'} | anti-spam: {'on' if cfg.get('spam') else 'off'}`", delete_after=10)
        return
    m = modo.lower()
    if m in ("on", "off", "1", "0", "true", "false", "all"):
        val = m in ("on", "1", "true", "all")
        cfg["nuke"] = val
        cfg["spam"] = val
    elif m in ("nuke", "raid"):
        cfg["nuke"] = not cfg.get("nuke")
    elif m == "spam":
        cfg["spam"] = not cfg.get("spam")
    else:
        await ctx.send("`uso: s!anti [on|off|nuke|spam]`", delete_after=5)
        return
    _anti_save()
    _git_push_config(("anti.json",))
    await _log_mod(ctx.guild, f"anti: {ctx.author} mudou config p/ nuke={'on' if cfg.get('nuke') else 'off'} spam={'on' if cfg.get('spam') else 'off'}")
    await ctx.send(f"`anti-nuke: {'on' if cfg.get('nuke') else 'off'} | anti-spam: {'on' if cfg.get('spam') else 'off'}`", delete_after=10)


# ============================ MODERACAO ============================
MOD_WARN_FILE = os.path.join(BASE_DIR, "moderation.json")
MODLOG_CHANNEL = {1539791937291419650: 1539797833304248330}  # set society -> #log


def _load_warns():
    try:
        with open(MOD_WARN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_warns(d):
    try:
        with open(MOD_WARN_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


async def _log_mod(guild, txt: str):
    ch_id = MODLOG_CHANNEL.get(guild.id) if guild else None
    if not ch_id:
        return
    try:
        ch = guild.get_channel(ch_id) or await guild.fetch_channel(ch_id)
        await ch.send(f"`{txt}`")
    except Exception:
        pass


@bot.command(name="kick")
async def m_kick(ctx, alvo: discord.Member, *, motivo: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.kick(reason=motivo)
        await _log_mod(ctx.guild, f"kick: {alvo} ({alvo.id}) por {ctx.author} [{motivo or 'sem motivo'}]")
        await ctx.send(f"`kick {alvo} - {motivo or 'sem motivo'}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`kick falhou: {e}`", delete_after=5)


@bot.command(name="ban")
async def m_ban(ctx, alvo: discord.Member, *, motivo: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.ban(reason=motivo, delete_message_days=0)
        await _log_mod(ctx.guild, f"ban: {alvo} ({alvo.id}) por {ctx.author} [{motivo or 'sem motivo'}]")
        await ctx.send(f"`ban {alvo} - {motivo or 'sem motivo'}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`ban falhou: {e}`", delete_after=5)


@bot.command(name="unban")
async def m_unban(ctx, user_id: int, *, motivo: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
        await ctx.guild.unban(entry.user, reason=motivo)
        await _log_mod(ctx.guild, f"unban: {user_id} por {ctx.author} [{motivo or 'sem motivo'}]")
        await ctx.send(f"`unban {user_id}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`unban falhou: {e}`", delete_after=5)


@bot.command(name="softban")
async def m_softban(ctx, alvo: discord.Member, *, motivo: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.ban(reason="softban " + (motivo or ""), delete_message_days=1)
        await ctx.guild.unban(alvo, reason="softban completo")
        await _log_mod(ctx.guild, f"softban: {alvo} ({alvo.id}) por {ctx.author}")
        await ctx.send(f"`softban {alvo}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`softban falhou: {e}`", delete_after=5)


@bot.command(name="mute")
async def m_mute(ctx, alvo: discord.Member, *, resto: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    minutos = 10
    motivo = None
    if resto:
        partes = resto.strip().split(maxsplit=1)
        try:
            minutos = float(partes[0].replace(",", "."))
            if len(partes) > 1:
                motivo = partes[1]
        except ValueError:
            motivo = resto.strip()
    elif len(alvo.roles) > 0:
        pass
    try:
        await alvo.timeout(datetime.timedelta(minutes=minutos), reason="mute " + (motivo or ""))
        await _log_mod(ctx.guild, f"mute: {alvo} ({alvo.id}) {minutos}min por {ctx.author} [{motivo or 'sem motivo'}]")
        await ctx.send(f"`mute {alvo} {minutos}min - {motivo or 'sem motivo'}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`mute falhou: {e}`", delete_after=5)


@bot.command(name="unmute")
async def m_unmute(ctx, alvo: discord.Member):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.timeout(None, reason="unmute")
        await _log_mod(ctx.guild, f"unmute: {alvo} ({alvo.id}) por {ctx.author}")
        await ctx.send(f"`unmute {alvo}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`unmute falhou: {e}`", delete_after=5)


@bot.command(name="vmute")
async def m_vmute(ctx, alvo: discord.Member):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.edit(mute=True)
        await _log_mod(ctx.guild, f"vmute: {alvo} ({alvo.id}) por {ctx.author}")
        await ctx.send(f"`vmute {alvo}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`vmute falhou: {e}`", delete_after=5)


@bot.command(name="unvmute")
async def m_unvmute(ctx, alvo: discord.Member):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.edit(mute=False)
        await ctx.send(f"`unvmute {alvo}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`unvmute falhou: {e}`", delete_after=5)


@bot.command(name="deafen")
async def m_deafen(ctx, alvo: discord.Member):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.edit(deafen=True)
        await _log_mod(ctx.guild, f"deafen: {alvo} ({alvo.id}) por {ctx.author}")
        await ctx.send(f"`deafen {alvo}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`deafen falhou: {e}`", delete_after=5)


@bot.command(name="undeafen")
async def m_undeafen(ctx, alvo: discord.Member):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.edit(deafen=False)
        await ctx.send(f"`undeafen {alvo}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`undeafen falhou: {e}`", delete_after=5)


@bot.command(name="vkick")
async def m_vkick(ctx, alvo: discord.Member):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.edit(voice_channel=None)
        await _log_mod(ctx.guild, f"vkick: {alvo} ({alvo.id}) por {ctx.author}")
        await ctx.send(f"`vkick {alvo}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`vkick falhou: {e}`", delete_after=5)


@bot.command(name="move")
async def m_move(ctx, alvo: discord.Member, canal: discord.VoiceChannel):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await alvo.edit(voice_channel=canal)
        await _log_mod(ctx.guild, f"move: {alvo} ({alvo.id}) -> {canal.name} por {ctx.author}")
        await ctx.send(f"`move {alvo} -> {canal.name}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`move falhou: {e}`", delete_after=5)


@bot.command(name="clear")
async def m_clear(ctx, n: int = 20):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    n = max(1, min(n, 500))
    try:
        deleted = await ctx.channel.purge(limit=n)
        await ctx.send(f"`clear {len(deleted)} msg`", delete_after=5)
        await _log_mod(ctx.guild, f"clear: {len(deleted)} msg em #{ctx.channel.name} por {ctx.author}")
    except Exception as e:
        await ctx.send(f"`clear falhou: {e}`", delete_after=5)


@bot.command(name="purgeuser")
async def m_purgeuser(ctx, alvo: discord.Member, n: int = 20):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    n = max(1, min(n, 200))
    try:
        deleted = await ctx.channel.purge(limit=n * 3, check=lambda m: m.author.id == alvo.id)
        await ctx.send(f"`purgeuser {alvo} - {len(deleted)} msg`", delete_after=5)
        await _log_mod(ctx.guild, f"purgeuser: {len(deleted)} msg de {alvo} por {ctx.author}")
    except Exception as e:
        await ctx.send(f"`purgeuser falhou: {e}`", delete_after=5)


@bot.command(name="warn")
async def m_warn(ctx, alvo: discord.Member, *, motivo: str = "sem motivo"):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    warns = _load_warns()
    uid = str(alvo.id)
    if uid not in warns:
        warns[uid] = []
    warns[uid].append(motivo)
    _save_warns(warns)
    await _log_mod(ctx.guild, f"warn {len(warns[uid])}: {alvo} ({alvo.id}) [{motivo}] por {ctx.author}")
    await ctx.send(f"`warn {alvo} [{motivo}] - total {len(warns[uid])}`", delete_after=5)


@bot.command(name="warns")
async def m_warns(ctx, alvo: discord.Member = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    alvo = alvo or ctx.author
    warns = _load_warns().get(str(alvo.id), [])
    if not warns:
        await ctx.send(f"`{alvo} sem warns`", delete_after=5)
        return
    linhas = "\n".join(f"{i + 1}. {w}" for i, w in enumerate(warns))
    await ctx.send(f"```warns de {alvo} ({len(warns)}):\n{linhas}```", delete_after=15)


@bot.command(name="delwarn")
async def m_delwarn(ctx, alvo: discord.Member, idx: int):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    warns = _load_warns()
    uid = str(alvo.id)
    lst = warns.get(uid, [])
    if idx < 1 or idx > len(lst):
        await ctx.send(f"`idx invalido (1-{len(lst)})`", delete_after=5)
        return
    removido = lst.pop(idx - 1)
    if not lst:
        warns.pop(uid, None)
    else:
        warns[uid] = lst
    _save_warns(warns)
    await _log_mod(ctx.guild, f"delwarn: {alvo} ({alvo.id}) removeu [{removido}] por {ctx.author}")
    await ctx.send(f"`delwarn {alvo} - removido [{removido}]`", delete_after=5)


@bot.command(name="clearwarns")
async def m_clearwarns(ctx, alvo: discord.Member):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    warns = _load_warns()
    warns.pop(str(alvo.id), None)
    _save_warns(warns)
    await _log_mod(ctx.guild, f"clearwarns: {alvo} ({alvo.id}) por {ctx.author}")
    await ctx.send(f"`clearwarns {alvo} - zerado`", delete_after=5)


@bot.command(name="slowmode")
async def m_slowmode(ctx, segundos: int = 5):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        segundos = max(0, min(segundos, 21600))
        await ctx.channel.edit(slowmode_delay=segundos)
        await ctx.send(f"`slowmode {segundos}s em #{ctx.channel.name}`", delete_after=5)
        await _log_mod(ctx.guild, f"slowmode: {segundos}s em #{ctx.channel.name} por {ctx.author}")
    except Exception as e:
        await ctx.send(f"`slowmode falhou: {e}`", delete_after=5)


@bot.command(name="lock")
async def m_lock(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send(f"`#{ctx.channel.name} trancado`", delete_after=5)
        await _log_mod(ctx.guild, f"lock: #{ctx.channel.name} por {ctx.author}")
    except Exception as e:
        await ctx.send(f"`lock falhou: {e}`", delete_after=5)


@bot.command(name="unlock")
async def m_unlock(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.send(f"`#{ctx.channel.name} destrancado`", delete_after=5)
        await _log_mod(ctx.guild, f"unlock: #{ctx.channel.name} por {ctx.author}")
    except Exception as e:
        await ctx.send(f"`unlock falhou: {e}`", delete_after=5)


@bot.command(name="hide")
async def m_hide(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.send(f"`#{ctx.channel.name} escondido`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`hide falhou: {e}`", delete_after=5)


@bot.command(name="unhide")
async def m_unhide(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=None)
        await ctx.send(f"`#{ctx.channel.name} visivel`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`unhide falhou: {e}`", delete_after=5)


@bot.command(name="setnick")
async def m_setnick(ctx, alvo: discord.Member, *, nick: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        if nick is not None and len(nick) > 32:
            nick = nick[:32]
        await alvo.edit(nick=nick)
        await _log_mod(ctx.guild, f"setnick: {alvo} ({alvo.id}) -> '{nick}' por {ctx.author}")
        await ctx.send(f"`setnick {alvo} -> {nick}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`setnick falhou: {e}`", delete_after=5)


@bot.command(name="role")
async def m_role(ctx, alvo: discord.Member, cargo: discord.Role):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        if cargo in alvo.roles:
            await alvo.remove_roles(cargo)
            await ctx.send(f"`role - {cargo.name} de {alvo}`", delete_after=5)
        else:
            await alvo.add_roles(cargo)
            await ctx.send(f"`role + {cargo.name} em {alvo}`", delete_after=5)
        await _log_mod(ctx.guild, f"role: {alvo} ({alvo.id}) {cargo.name} por {ctx.author}")
    except Exception as e:
        await ctx.send(f"`role falhou: {e}`", delete_after=5)


@bot.command(name="announce")
async def m_announce(ctx, *, texto: str):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        embed = discord.Embed(description=texto, color=0x202225)
        embed.set_footer(text="set society")
        await ctx.send(embed=embed)
        await _log_mod(ctx.guild, f"announce em #{ctx.channel.name} por {ctx.author}")
    except Exception as e:
        await ctx.send(f"`announce falhou: {e}`", delete_after=5)


# ============================ EMBED / WEBHOOK ============================
@bot.command(name="embed", aliases=["mkembed"])
async def m_embed(ctx, *, args: str):
    """Cria embed. uso: embed <titulo> | <desc> --color #hex --footer <txt> --image <url> --thumb <url>"""
    if not await _check_ok(ctx):
        return
    flags = {"--color": None, "--footer": None, "--image": None, "--thumb": None}
    partes = []
    tokens = args.split()
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in flags:
            vals = []
            i += 1
            while i < len(tokens) and tokens[i] not in flags:
                vals.append(tokens[i])
                i += 1
            flags[t] = " ".join(vals)
        else:
            partes.append(t)
            i += 1
    texto = " ".join(partes)
    if " | " in texto:
        titulo, _, desc = texto.partition(" | ")
    else:
        titulo, desc = texto, ""
    color = 0x202225
    if flags["--color"]:
        try:
            color = int(flags["--color"].lstrip("#"), 16)
        except Exception:
            pass
    try:
        e = discord.Embed(title=titulo or None, description=desc or None, color=color)
        if flags["--footer"]:
            e.set_footer(text=flags["--footer"])
        if flags["--image"]:
            e.set_image(url=flags["--image"])
        if flags["--thumb"]:
            e.set_thumbnail(url=flags["--thumb"])
        await ctx.send(embed=e)
        if ctx.guild:
            await _log_mod(ctx.guild, f"embed por {ctx.author}")
    except Exception as ex:
        await ctx.send(f"`embed erro: {ex}`", delete_after=5)


@bot.command(name="webhook", aliases=["wh"])
async def m_webhook(ctx, acao: str = None, alvo: str = None, *, extra: str = None):
    """Webhooks. uso: webhook create|list|send|embed|delete"""
    if not await _check_ok(ctx):
        return
    acao = (acao or "").lower()
    ch = ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None
    try:
        if acao == "create":
            nome = alvo or "hook"
            canal = None
            if extra and extra.isdigit():
                canal = ctx.guild.get_channel(int(extra))
            c = canal or ch
            if c is None:
                await ctx.send("`sem canal de texto`", delete_after=5)
                return
            wh = await c.create_webhook(name=nome)
            if ctx.guild:
                await _log_mod(ctx.guild, f"webhook create: {nome} em #{c.name} por {ctx.author}")
            await ctx.send(f"`webhook criado: {wh.url}`", delete_after=15)
        elif acao == "list":
            c = ch
            if alvo and alvo.isdigit():
                c = ctx.guild.get_channel(int(alvo)) or c
            hooks = await (c or ch).webhooks()
            if not hooks:
                await ctx.send("`sem webhooks`", delete_after=5)
                return
            txt = "\n".join(f"{h.id} | {h.name} | {h.url}" for h in hooks)
            await ctx.send(f"```{txt}```", delete_after=15)
        elif acao == "send":
            url = alvo or ""
            texto = extra or ""
            if not url or not texto:
                await ctx.send("`uso: webhook send <url> <texto>`", delete_after=5)
                return
            wh = discord.SyncWebhook.from_url(url)
            wh.send(texto)
            await ctx.send("`enviado`", delete_after=3)
        elif acao == "embed":
            url = alvo or ""
            texto = extra or ""
            if not url or not texto:
                await ctx.send("`uso: webhook embed <url> <titulo> | <desc>`", delete_after=5)
                return
            titulo, _, desc = texto.partition(" | ")
            e = discord.Embed(title=titulo or None, description=desc or None, color=0x202225)
            wh = discord.SyncWebhook.from_url(url)
            wh.send(embed=e)
            await ctx.send("`enviado`", delete_after=3)
        elif acao == "delete":
            alvo = alvo or ""
            hooks = await ch.webhooks()
            for h in hooks:
                if str(h.id) == alvo:
                    await h.delete()
                    if ctx.guild:
                        await _log_mod(ctx.guild, f"webhook delete: {alvo} por {ctx.author}")
                    await ctx.send(f"`webhook {alvo} deletado`", delete_after=5)
                    return
            await ctx.send("`webhook nao achado (use webhook list)`", delete_after=5)
        else:
            await ctx.send("`uso: webhook create|list|send|embed|delete`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`webhook erro: {e}`", delete_after=5)




# ============================ HELP EXPANDIDO ============================
INVITE_LINK = "https://discord.gg/TGaUktD9D"

HELP_CATS = {
    "mod": [
        ("kick @user [motivo]", "expulsa"),
        ("ban @user [motivo]", "bane"),
        ("unban <id>", "desbane"),
        ("softban @user", "ban rapido q limpa msgs"),
        ("mute @user [min] [motivo]", "timeout"),
        ("unmute @user", "tira timeout"),
        ("vmute @user", "muta na call"),
        ("unvmute @user", "desmuta na call"),
        ("deafen @user", "corta audio na call"),
        ("undeafen @user", "volta audio"),
        ("vkick @user", "tira da call"),
        ("move @user <canal>", "move na call"),
        ("moveall <canal>", "move todo mundo"),
        ("clear [n]", "apaga msgs do canal"),
        ("purgeuser @user [n]", "apaga msgs do user"),
        ("warn @user <motivo>", "adverte"),
        ("warns @user", "mostra warns"),
        ("delwarn @user <n>", "remove warn"),
        ("clearwarns @user", "zera warns"),
        ("slowmode [seg]", "slowmode do canal"),
        ("lock / unlock", "trava/destrava canal"),
        ("hide / unhide", "esconde/mostra canal"),
        ("setnick @user <nick>", "troca nick"),
        ("role @user <cargo>", "da cargo"),
        ("roleall <cargo>", "cargo pra todos"),
        ("delroleall <cargo>", "tira cargo de todos"),
        ("announce <texto>", "anuncio embed"),
        ("fixroles", "autorole pra quem falta"),
    ],
    "canal": [
        ("create texto|voz <nome>", "cria canal"),
        ("delete <canal>", "deleta canal"),
        ("clone <canal>", "clona canal"),
        ("rename <canal> <nome>", "renomeia"),
        ("topic <texto>", "topico do canal"),
        ("thread <nome>", "cria thread"),
        ("invite", "link de convite"),
    ],
    "info": [
        ("avatar [@user]", "foto de perfil"),
        ("banner [@user]", "banner"),
        ("userinfo [@user]", "info do user"),
        ("serverinfo", "info do server"),
        ("roleinfo <cargo>", "info do cargo"),
        ("emojis", "emojis do server"),
        ("ping", "latencia"),
    ],
    "embed/webhook": [
        ("embed titulo | desc", "embed custom"),
        ("webhook create/list/send/embed/delete", "gerencia webhooks"),
    ],
    "diversao": [
        ("poll pergunta | op1 | op2", "enquete"),
        ("say <texto>", "bot fala"),
        ("calc <conta>", "calculadora"),
        ("roll [n]", "dado aleatorio"),
    ],
    "boost": [
        ("perks", "lista perks de booster"),
        ("setupperks", "owner: seta perms + painel privado"),
        ("painel: cor/nome/nick/call", "botoes no #booster-lounge"),
        ("perms automaticas", "slowmode, prioridade, threads"),
    ],
    "auto": [
        ("auto", "status das auto-coisas"),
        ("autothanks on/off/text <txt>", "dm de obrigado p/ booster"),
        ("autodm on/off/text <txt>", "dm de boas vindas"),
        ("autoreply add/del/list", "resposta por palavra"),
        ("autopost #canal <min> <txt>", "post automatico"),
        ("autopost off", "desliga post automatico"),
    ],
    "raid": [
        ("/spam [n] [texto]", "spamma"),
        ("/raid [canais] [msgs]", "raida canais"),
        ("/blame @user", "culpa alguem"),
        ("nuke <canal>", "renasce canal"),
        (".blacklist @user", "owner: bloqueia alguem"),
        ("anti on/off/nuke/spam", "protecao anti-nuke"),
    ],
}


async def _send_chunks(ctx, linhas):
    """envia em msgs de ate 1900 chars (limite do discord e 2000)."""
    buf = []
    total = 0
    for l in linhas:
        if total + len(l) + 1 > 1900 and buf:
            await ctx.send("\n".join(buf), delete_after=None)
            buf = []
            total = 0
        buf.append(l)
        total += len(l) + 1
    if buf:
        await ctx.send("\n".join(buf), delete_after=None)


@bot.command(name="help", aliases=["cmds", "ajuda"])
async def jax_help(ctx, cat: str = None):
    if not await _check_ok(ctx):
        return
    if cat:
        cat = cat.lower()
        if cat not in HELP_CATS:
            await ctx.send("`categorias: " + " | ".join(HELP_CATS) + "`", delete_after=10)
            return
        linhas = [f"**{cat}**"]
        linhas += [f"  `{c}` - {d}" for c, d in HELP_CATS[cat]]
        await _send_chunks(ctx, linhas)
        return
    linhas = ["**comandos** (`s!` no set society, `.` nos outros)"]
    for nome, cmds in HELP_CATS.items():
        linhas.append(f"\n**{nome}:**")
        linhas += [f"  `{c}`" + (f" - {d}" if d else "") for c, d in cmds]
    linhas.append(f"\nentrou no queridinho: {INVITE_LINK}")
    await _send_chunks(ctx, linhas)



# ============================ MANIPULACAO DE CANAL ============================
@bot.command(name="create")
async def m_create(ctx, tipo: str = "texto", nome: str = "novo-canal", *, categoria: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        ctype = discord.ChannelType.voice if tipo.lower() in ("voz", "voice", "vc") else discord.ChannelType.text
        parent = None
        if categoria:
            parent = discord.utils.get(ctx.guild.categories, name=categoria)
        ch = await ctx.guild.create_channel(nome, type=ctype, category=parent)
        await _log_mod(ctx.guild, f"create: #{ch.name} por {ctx.author}")
        await ctx.send(f"`criado #{ch.name} (id {ch.id})`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`create falhou: {e}`", delete_after=5)


@bot.command(name="delete")
async def m_delete(ctx, canal: discord.abc.GuildChannel = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    canal = canal or ctx.channel
    if canal.id == ctx.guild.rules_channel_id or canal.id == ctx.guild.public_updates_channel_id:
        await ctx.send("`nao apago canal de regras/updates`", delete_after=5)
        return
    try:
        nome = canal.name
        await canal.delete()
        await _log_mod(ctx.guild, f"delete: #{nome} por {ctx.author}")
        await ctx.send(f"`#{nome} deletado`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`delete falhou: {e}`", delete_after=5)


@bot.command(name="clone")
async def m_clone(ctx, canal: discord.abc.GuildChannel = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    canal = canal or ctx.channel
    try:
        novo = await canal.clone()
        await _log_mod(ctx.guild, f"clone: #{canal.name} -> #{novo.name} por {ctx.author}")
        await ctx.send(f"`#{canal.name} clonado -> #{novo.name}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`clone falhou: {e}`", delete_after=5)


@bot.command(name="rename")
async def m_rename(ctx, canal: discord.abc.GuildChannel, *, nome: str):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        antigo = canal.name
        await canal.edit(name=nome)
        await _log_mod(ctx.guild, f"rename: #{antigo} -> #{nome} por {ctx.author}")
        await ctx.send(f"`#{antigo} -> #{nome}`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`rename falhou: {e}`", delete_after=5)


@bot.command(name="topic")
async def m_topic(ctx, *, texto: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await ctx.channel.edit(topic=texto or "")
        await ctx.send(f"`topic atualizado`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`topic falhou: {e}`", delete_after=5)


@bot.command(name="thread")
async def m_thread(ctx, *, nome: str):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        t = await ctx.channel.create_thread(name=nome, auto_archive_duration=1440)
        await ctx.send(f"`thread {t.name} criada`", delete_after=5)
    except Exception as e:
        await ctx.send(f"`thread falhou: {e}`", delete_after=5)


@bot.command(name="invite")
async def m_invite(ctx, canal: discord.TextChannel = None):
    if not await _check_ok(ctx):
        return
    canal = canal or ctx.channel
    try:
        inv = await canal.create_invite(max_age=0, max_uses=0)
        await ctx.send(f"`{inv.url}`", delete_after=None)
    except Exception as e:
        await ctx.send(f"`invite falhou: {e}`", delete_after=5)


# ============================ MASS ACTIONS ============================
@bot.command(name="moveall")
async def m_moveall(ctx, canal: discord.VoiceChannel):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    moved = 0
    for m in ctx.guild.members:
        if m.voice and m.voice.channel and m.voice.channel != canal:
            try:
                await m.edit(voice_channel=canal)
                moved += 1
            except Exception:
                pass
    await _log_mod(ctx.guild, f"moveall: {moved} -> {canal.name} por {ctx.author}")
    await ctx.send(f"`moveall: {moved} movidos -> {canal.name}`", delete_after=5)


@bot.command(name="roleall")
async def m_roleall(ctx, cargo: discord.Role):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    ok = 0
    for m in ctx.guild.members:
        if cargo not in m.roles and not m.bot:
            try:
                await m.add_roles(cargo)
                ok += 1
            except Exception:
                pass
    await _log_mod(ctx.guild, f"roleall: {ok} + {cargo.name} por {ctx.author}")
    await ctx.send(f"`roleall: {ok} membros + {cargo.name}`", delete_after=5)


@bot.command(name="delroleall")
async def m_delroleall(ctx, cargo: discord.Role):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    ok = 0
    for m in ctx.guild.members:
        if cargo in m.roles and not m.bot:
            try:
                await m.remove_roles(cargo)
                ok += 1
            except Exception:
                pass
    await _log_mod(ctx.guild, f"delroleall: {ok} - {cargo.name} por {ctx.author}")
    await ctx.send(f"`delroleall: {ok} membros - {cargo.name}`", delete_after=5)


# ============================ INFO ============================
@bot.command(name="avatar")
async def m_avatar(ctx, alvo: discord.Member = None):
    if not await _check_ok(ctx):
        return
    alvo = alvo or ctx.author
    try:
        await ctx.send(alvo.avatar.url if alvo.avatar else "sem avatar")
    except Exception as e:
        await ctx.send(f"`avatar falhou: {e}`", delete_after=5)


@bot.command(name="banner")
async def m_banner(ctx, alvo: discord.Member = None):
    if not await _check_ok(ctx):
        return
    alvo = alvo or ctx.author
    try:
        user = await ctx.bot.fetch_user(alvo.id)
        await ctx.send(user.banner.url if user.banner else "sem banner")
    except Exception as e:
        await ctx.send(f"`banner falhou: {e}`", delete_after=5)


@bot.command(name="userinfo")
async def m_userinfo(ctx, alvo: discord.Member = None):
    if not await _check_ok(ctx):
        return
    alvo = alvo or ctx.author
    try:
        roles = ", ".join(r.mention for r in alvo.roles[1:][:8]) or "nenhum"
        await ctx.send(
            f"**{alvo}** ({alvo.id})\n"
            f"criou: {alvo.created_at:%d/%m/%Y}\n"
            f"entrou: {alvo.joined_at:%d/%m/%Y}\n"
            f"top role: {alvo.top_role.mention}\n"
            f"cargos: {roles}\n"
            f"bot: {'sim' if alvo.bot else 'nao'}",
            delete_after=None)
    except Exception as e:
        await ctx.send(f"`userinfo falhou: {e}`", delete_after=5)


@bot.command(name="serverinfo")
async def m_serverinfo(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    g = ctx.guild
    try:
        await ctx.send(
            f"**{g.name}** ({g.id})\n"
            f"dono: {g.owner.mention}\n"
            f"membros: {g.member_count}\n"
            f"canais: {len(g.channels)} | cargos: {len(g.roles)}\n"
            f"criado: {g.created_at:%d/%m/%Y}",
            delete_after=None)
    except Exception as e:
        await ctx.send(f"`serverinfo falhou: {e}`", delete_after=5)


@bot.command(name="roleinfo")
async def m_roleinfo(ctx, cargo: discord.Role):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        await ctx.send(
            f"**{cargo.name}** ({cargo.id})\n"
            f"cor: #{cargo.color.value:06x}\n"
            f"posicao: {cargo.position}\n"
            f"membros: {len(cargo.members)}\n"
            f"menção: {cargo.mention}",
            delete_after=None)
    except Exception as e:
        await ctx.send(f"`roleinfo falhou: {e}`", delete_after=5)


@bot.command(name="emojis")
async def m_emojis(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        if not ctx.guild.emojis:
            await ctx.send("`sem emojis`", delete_after=5)
            return
        linhas = []
        for e in sorted(ctx.guild.emojis, key=lambda x: x.name):
            pre = "a" if e.animated else ""
            linhas.append(f":{e.name}: -> `<{pre}:{e.name}:{e.id}>` id `{e.id}`")
        await _send_chunks(ctx, ["**emojis do server:**"] + linhas)
    except Exception as e:
        await ctx.send(f"`emojis falhou: {e}`", delete_after=5)


# ============================ DIVERSÃO ============================
@bot.command(name="poll")
async def m_poll(ctx, *, args: str):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    try:
        parts = [p.strip() for p in args.split("|")]
        pergunta = parts[0]
        respostas = parts[1:] or ["sim", "nao"]
        poll = discord.Poll(question=pergunta[:300], multiple=False)
        for r in respostas[:10]:
            poll.add_answer(text=r[:55])
        await ctx.send(poll=poll)
    except Exception as e:
        await ctx.send(f"`poll falhou: {e}`", delete_after=5)


@bot.command(name="say")
async def m_say(ctx, *, texto: str):
    if not await _check_ok(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(texto)


@bot.command(name="calc")
async def m_calc(ctx, *, expr: str):
    if not await _check_ok(ctx):
        return
    try:
        expr2 = expr.replace("x", "*").replace(",", ".")
        if not re.fullmatch(r"[0-9+\-*/().% ]+", expr2):
            await ctx.send("`expressao invalida`", delete_after=5)
            return
        resultado = eval(expr2, {"__builtins__": {}}, {})
        await ctx.send(f"`{expr} = {resultado}`", delete_after=10)
    except Exception as e:
        await ctx.send(f"`calc erro: {e}`", delete_after=5)


@bot.command(name="roll")
async def m_roll(ctx, n: int = 100):
    if not await _check_ok(ctx):
        return
    n = max(2, min(n, 1_000_000))
    await ctx.send(f"`🎲 {random.randint(1, n)}`", delete_after=10)


# ============================ NUKE (off no set society) ============================
@bot.command(name="nuke")
async def m_nuke(ctx, canal: discord.TextChannel = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    if await _nuke_guard(ctx):
        return
    canal = canal or ctx.channel
    try:
        nome, parent = canal.name, canal.category
        pos = canal.position
        novo = await canal.clone(name=nome, category=parent)
        await canal.delete()
        try:
            await novo.edit(position=pos)
        except Exception:
            pass
        await ctx.send(f"💥 #{nome} renascido", delete_after=5)
    except Exception as e:
        await ctx.send(f"`nuke falhou: {e}`", delete_after=5)



def _git_push_config(caminhos=("autorole.json",)):
    """Tenta commitar configs de volta no repo p/ persistencia entre runs."""
    try:
        gt = os.environ.get("GIT_TOKEN")
        repo = os.environ.get("REPO")
        if not gt or not repo:
            return False
        import subprocess
        base = "/home/runner/work"
        # encontra o dir do repo clonado
        for root in (f"/home/runner/work/{repo.split('/')[-1]}", "/home/runner/work"):
            if os.path.isdir(root):
                parts = root.split("/")
                work = "/home/runner/work/" + (parts[-1] if parts[-1] else "")
                for d in os.listdir(work) if os.path.isdir(work) else []:
                    cand = os.path.join(work, d)
                    if os.path.isdir(os.path.join(cand, ".git")):
                        base = cand
                        break
                break
        if not os.path.isdir(os.path.join(base, ".git")):
            return False
        url = f"https://x-access-token:{gt}@github.com/{repo}.git"
        subprocess.run(["git", "config", "user.email", "jax@bot.local"], cwd=base, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Jax Bot"], cwd=base, capture_output=True)
        subprocess.run(["git", "add", "-A", "--", *caminhos], cwd=base, capture_output=True)
        subprocess.run(["git", "commit", "-m", "config: autorole/wl/bl atualizados pelo bot"], cwd=base, capture_output=True)
        subprocess.run(["git", "remote", "set-url", "origin", url], cwd=base, capture_output=True)
        r = subprocess.run(["git", "push", "origin", "HEAD"], cwd=base, capture_output=True, timeout=30)
        return r.returncode == 0
    except Exception as e:
        print(f"[gitcfg] {e}", flush=True)
        return False


def _find_repo_dir():
    """Acha o dir clonado no runner (checkout aninhado: work/repo/repo)."""
    work = "/home/runner/work"
    if not os.path.isdir(work):
        return None
    for root, dirs, _files in os.walk(work):
        if root[len(work):].count(os.sep) >= 4:
            dirs[:] = []
            continue
        if ".git" in dirs:
            return root
    return None


def _status_push(dados: dict, arquivo="status.json"):
    """Escreve diagnostico num json e commita no repo p/ leitura externa."""
    try:
        gt = os.environ.get("GIT_TOKEN")
        repo = os.environ.get("REPO")
        if not gt or not repo:
            print("[status] sem GIT_TOKEN/REPO", flush=True)
            return False
        import subprocess
        base = _find_repo_dir()
        if not base:
            print("[status] repo dir nao encontrado", flush=True)
            return False
        path = os.path.join(base, arquivo)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
        url = f"https://x-access-token:{gt}@github.com/{repo}.git"
        subprocess.run(["git", "config", "user.email", "jax@bot.local"], cwd=base, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Jax Bot"], cwd=base, capture_output=True)
        subprocess.run(["git", "add", "-A", "--", arquivo], cwd=base, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"status: {dados.get('tipo', 'info')}"], cwd=base, capture_output=True)
        subprocess.run(["git", "remote", "set-url", "origin", url], cwd=base, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=base, capture_output=True, timeout=30)
        r = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=base, capture_output=True, timeout=30)
        if r.returncode != 0:
            print(f"[status] push falhou: {r.stderr.decode(errors='replace')[:300]}", flush=True)
        return r.returncode == 0
    except Exception as e:
        print(f"[status] {e}", flush=True)
        return False


# ============================ AUTO-ROLE ============================
AUTOROLE_FILE = "autorole.json"
# fallback se nao tiver config: {guild_id: role_id}
AUTOROLE_DEFAULT = {1539791937291419650: 1539797800932610068}  # set society -> member
_autorole_cache = dict(AUTOROLE_DEFAULT)


def _autorole_load():
    global _autorole_cache
    try:
        with open(AUTOROLE_FILE, "r", encoding="utf-8") as f:
            _autorole_cache = json.loads(f.read())
    except Exception:
        _autorole_cache = dict(AUTOROLE_DEFAULT)


def _autorole_save():
    with open(AUTOROLE_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(_autorole_cache))


@bot.command(name="setautorole")
async def m_setautorole(ctx, cargo: discord.Role = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    _autorole_load()
    if cargo is None:
        atual = _autorole_cache.get(str(ctx.guild.id))
        r = ctx.guild.get_role(atual) if atual else None
        await ctx.send(f"`autorole -> {r.name if r else 'nenhum'}`", delete_after=10)
        return
    _autorole_cache[str(ctx.guild.id)] = cargo.id
    _autorole_save()
    _git_push_config()
    await _log_mod(ctx.guild, f"autorole: novo membro ganha {cargo.name} (set por {ctx.author})")
    await ctx.send(f"`autorole -> {cargo.name}`", delete_after=10)


@bot.command(name="delautorole")
async def m_delautorole(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    _autorole_load()
    if str(ctx.guild.id) in _autorole_cache:
        del _autorole_cache[str(ctx.guild.id)]
        _autorole_save()
        _git_push_config()
    await ctx.send("`autorole removido`", delete_after=10)


@bot.event
async def on_member_join(member):
    try:
        _autorole_load()
        role_id = _autorole_cache.get(str(member.guild.id))
        if role_id:
            role = member.guild.get_role(int(role_id))
            if role is not None:
                await member.add_roles(role)
                await _log_mod(member.guild, f"autore: {member} entrou e levou {role.name}")
    except Exception as e:
        print(f"[autore] falha: {e}", flush=True)
    try:
        await _send_welcome(member)
    except Exception as e:
        print(f"[welcome] falha: {e}", flush=True)
    try:
        await _auto_welcome_dm(member)
    except Exception as e:
        print(f"[autodm] falha: {e}", flush=True)

def _get_autorole(guild):
    _autorole_load()
    rid = _autorole_cache.get(str(guild.id))
    if not rid:
        return None
    return guild.get_role(int(rid))


async def _fix_member_roles(guild):
    """Garante que todo membro (exceto owner e bots) tenha o cargo de autorole."""
    role = _get_autorole(guild)
    if role is None:
        return 0
    try:
        await guild.chunk(cache=True)
    except Exception:
        pass
    ok = 0
    for m in guild.members:
        if m.bot or m.id == guild.owner_id:
            continue
        if role not in m.roles:
            try:
                await m.add_roles(role)
                ok += 1
            except Exception:
                pass
    return ok


@bot.command(name="fixroles")
async def m_fixroles(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    n = await _fix_member_roles(ctx.guild)
    role = _get_autorole(ctx.guild)
    rname = role.name if role else "?"
    await _log_mod(ctx.guild, f"fixroles: {n} membros receberam {rname} (por {ctx.author})")
    await ctx.send(f"`fixroles: {n} membros + {rname}`", delete_after=10)


async def _autorole_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(15)
    while not bot.is_closed():
        try:
            for g in bot.guilds:
                try:
                    n = await _fix_member_roles(g)
                    if n:
                        print(f"[autore] varredura em {g.name}: {n} membros atualizados", flush=True)
                except Exception as e:
                    print(f"[autore] varredura {g.name} erro: {e}", flush=True)
        except Exception as e:
            print(f"[autore] loop erro: {e}", flush=True)
        await asyncio.sleep(300)




# ============================ WELCOME ============================
WELCOME_FILE = "welcome.json"
# fallback: {guild_id: canal_id} -> set society usa o geral
WELCOME_DEFAULT = {1539791937291419650: 1539797820180140183}
_welcome_cache = dict(WELCOME_DEFAULT)


def _welcome_load():
    global _welcome_cache
    try:
        with open(WELCOME_FILE, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        _welcome_cache = {
            str(k): (v if isinstance(v, dict) else {"channel": int(v), "text": None})
            for k, v in data.items()
        }
    except Exception:
        _welcome_cache = {str(g): {"channel": c, "text": None} for g, c in WELCOME_DEFAULT.items()}


def _welcome_save():
    with open(WELCOME_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(_welcome_cache))


def _welcome_embed(member, text=None):
    if not text:
        text = f"salve {member.mention}!"
        if member.guild.rules_channel is not None:
            text += f"\nle as regras em {member.guild.rules_channel.mention}"
    else:
        text = text.replace("{user}", member.mention)
    emb = discord.Embed(title="bem-vindo", description=text[:2000], color=0x2C2F33)
    emb.set_footer(text="discord.gg/TGaUktD9D")
    return emb


async def _send_welcome(member):
    _welcome_load()
    cfg = _welcome_cache.get(str(member.guild.id))
    if not cfg:
        return False
    ch = member.guild.get_channel(int(cfg.get("channel", 0)))
    if ch is None:
        return False
    await ch.send(embed=_welcome_embed(member, cfg.get("text")))
    return True


@bot.command(name="setwelcome")
async def m_setwelcome(ctx, canal: discord.TextChannel = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    _welcome_load()
    if canal is None:
        atual = _welcome_cache.get(str(ctx.guild.id))
        c = None
        tx = None
        if isinstance(atual, dict):
            c = ctx.guild.get_channel(int(atual.get("channel", 0))) if atual.get("channel") else None
            tx = atual.get("text")
        elif atual:
            c = ctx.guild.get_channel(int(atual))
        msg = f"`welcome -> #{c.name if c else 'nenhum'}`"
        if tx:
            msg += f"\n`texto: {tx[:100]}`"
        await ctx.send(msg, delete_after=10)
        return
    atual = _welcome_cache.get(str(ctx.guild.id), {})
    _welcome_cache[str(ctx.guild.id)] = {"channel": canal.id, "text": atual.get("text") if isinstance(atual, dict) else None}
    _welcome_save()
    _git_push_config(("welcome.json",))
    await _log_mod(ctx.guild, f"welcome: novas entradas vao p/ #{canal.name} (set por {ctx.author})")
    await ctx.send(f"`welcome -> #{canal.name}`", delete_after=10)


@bot.command(name="welcometext")
async def m_welcometext(ctx, *, texto: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    _welcome_load()
    atual = _welcome_cache.get(str(ctx.guild.id), {})
    if not isinstance(atual, dict):
        atual = {"channel": int(atual) if atual else 0, "text": None}
    if texto is None or texto.strip().lower() == "reset":
        nv = None if (texto and texto.strip().lower() == "reset") else atual.get("text")
        _welcome_cache[str(ctx.guild.id)] = {"channel": atual.get("channel", 0), "text": nv}
        _welcome_save()
        _git_push_config(("welcome.json",))
        if texto and texto.strip().lower() == "reset":
            await ctx.send("`texto do welcome voltou ao padrao`", delete_after=10)
        else:
            cur = atual.get("text") or "padrao"
            await ctx.send(f"`texto atual: {cur[:200]}`", delete_after=None)
        return
    _welcome_cache[str(ctx.guild.id)] = {"channel": atual.get("channel", 0), "text": texto}
    _welcome_save()
    _git_push_config(("welcome.json",))
    await _log_mod(ctx.guild, f"welcome: texto alterado por {ctx.author}")
    await ctx.send("`texto do welcome atualizado`", delete_after=10)


@bot.command(name="delwelcome")
async def m_delwelcome(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    _welcome_load()
    if str(ctx.guild.id) in _welcome_cache:
        del _welcome_cache[str(ctx.guild.id)]
        _welcome_save()
        _git_push_config(("welcome.json",))
    await ctx.send("`welcome removido`", delete_after=10)


@bot.command(name="testwelcome")
async def m_testwelcome(ctx, alvo: discord.Member = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    alvo = alvo or ctx.author
    ok = await _send_welcome(alvo)
    await ctx.send("`welcome enviado`" if ok else "`welcome nao configurado`", delete_after=5)

# ============================ BOOSTER PERKS ============================
def _is_booster(member):
    return bool(getattr(member, "premium_since", None))


async def _booster_gate(ctx):
    if not _is_booster(ctx.author):
        await ctx.send("`perk exclusiva de booster. boosta o server: " + INVITE_LINK + "`", delete_after=8)
        return False
    return True


def _boost_role_of(member):
    for r in member.guild.roles:
        if r.name.startswith("\u2726") and member in r.members:
            return r
    return None


@bot.command(name="mycolor")
async def m_mycolor(ctx, *, cor: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    if not await _booster_gate(ctx):
        return
    if not cor:
        await ctx.send("`uso: mycolor #ff0055`", delete_after=8)
        return
    hexv = cor.strip().lstrip("#")
    try:
        color = discord.Color(int(hexv, 16))
    except Exception:
        await ctx.send("`cor invalida. ex: mycolor #ff0055`", delete_after=8)
        return
    role = _boost_role_of(ctx.author)
    try:
        if role is None:
            nome = "\u2726 " + ctx.author.display_name[:20]
            role = await ctx.guild.create_role(name=nome, color=color, hoist=False, permissions=discord.Permissions.none(), reason="perk booster")
            base = ctx.guild.get_role(1539797800932610068)
            pos = base.position + 1 if base else role.position
            try:
                await role.edit(position=pos)
            except Exception:
                pass
            await ctx.author.add_roles(role)
        else:
            await role.edit(color=color, reason="perk booster")
        await ctx.send(f"`teu cargo {role.name} agora e #{hexv}`", delete_after=8)
    except Exception as e:
        await ctx.send(f"`mycolor falhou: {e}`", delete_after=8)


@bot.command(name="myname")
async def m_myname(ctx, *, nome: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    if not await _booster_gate(ctx):
        return
    if not nome:
        await ctx.send("`uso: myname rei do set`", delete_after=8)
        return
    role = _boost_role_of(ctx.author)
    try:
        if role is None:
            role = await ctx.guild.create_role(name="\u2726 " + nome[:20], hoist=False, permissions=discord.Permissions.none(), reason="perk booster")
            base = ctx.guild.get_role(1539797800932610068)
            pos = base.position + 1 if base else role.position
            try:
                await role.edit(position=pos)
            except Exception:
                pass
            await ctx.author.add_roles(role)
        else:
            await role.edit(name="\u2726 " + nome[:20], reason="perk booster")
        await ctx.send(f"`cargo renomeado pra {role.name}`", delete_after=8)
    except Exception as e:
        await ctx.send(f"`myname falhou: {e}`", delete_after=8)


@bot.command(name="perks")
async def m_perks(ctx):
    if not await _check_ok(ctx):
        return
    b = _is_booster(ctx.author)
    linhas = [
        "**PERKS DE BOOSTER** (automaticas, sem comando)",
        "- bypass de slowmode em todos os canais",
        "- prioridade de fala na call (priority speaker)",
        "- criar threads publicas e privadas",
        "- usar emojis de outros servers nas msgs",
        "- bypass total do anti-spam/anti-raid",
        "- dm automatica de obrigado quando boosta",
        "",
        "**no painel privado #booster-lounge (botoes):**",
        "- cor do teu cargo personalizado (sem perm nenhuma, invisivel na listinha)",
        "- nome do teu cargo",
        "- trocar teu nick quando quiser",
        "- criar tua call privada (some quando vazia)",
        "",
        f"tu {'JA ES booster' if b else 'nao es booster. boosta ai: ' + INVITE_LINK}",
    ]
    await ctx.send("\n".join(linhas), delete_after=None)


# ============================ SYNC EMOJIS ============================
EMOJI_DIR = os.path.join(BASE_DIR, "emojis")
_last_emoji_errors = []


def _shrink_gif(data: bytes, max_bytes=250_000) -> bytes:
    """Reduz um gif animado ate caber no limite de upload de emoji."""
    try:
        from PIL import Image, ImageSequence
        for lado in (100, 80, 64, 48):
            img = Image.open(io.BytesIO(data))
            frames = []
            for fr in ImageSequence.Iterator(img):
                f = fr.convert("RGBA").resize((lado, int(lado * fr.height / max(fr.width, 1))) if fr.width > fr.height else (int(lado * fr.width / max(fr.height, 1)), lado))
                frames.append(f)
            buf = io.BytesIO()
            frames[0].save(buf, format="GIF", save_all=True,
                           append_images=frames[1:],
                           duration=img.info.get("duration", 100),
                           loop=img.info.get("loop", 0), optimize=True)
            out = buf.getvalue()
            if len(out) <= max_bytes:
                return out
        return out
    except Exception:
        return data


async def _sync_emojis(guild):
    global _last_emoji_errors
    if not os.path.isdir(EMOJI_DIR):
        await _log_mod(guild, "emoji: pasta emojis/ nao encontrada")
        _last_emoji_errors = ["pasta emojis/ nao encontrada"]
        return 0, 0
    # dedupe: remove emojis repetidos com o mesmo nome (mantem o mais antigo)
    vistos = {}
    for e in list(guild.emojis):
        n = e.name.lower()
        if n in vistos:
            try:
                await e.delete(reason="dedupe")
                print(f"[emoji] dedupe removido {n} ({e.id})", flush=True)
            except Exception as ex:
                print(f"[emoji] dedupe falhou {n}: {ex}", flush=True)
        else:
            vistos[n] = e
    existentes = set(vistos)
    ok = fail = 0
    erros = []
    for fn in sorted(os.listdir(EMOJI_DIR)):
        base, ext = os.path.splitext(fn)
        nome = re.sub(r"[^a-zA-Z0-9_]", "_", base.lower()).strip("_")
        if not nome or len(nome) < 2 or nome in existentes:
            continue
        path = os.path.join(EMOJI_DIR, fn)
        try:
            data = open(path, "rb").read()
            if len(data) > 256_000:
                if ext.lower() == ".gif":
                    data = _shrink_gif(data)
                else:
                    try:
                        from PIL import Image
                        img = Image.open(io.BytesIO(data))
                        img.thumbnail((128, 128))
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        data = buf.getvalue()
                    except Exception:
                        pass
            await guild.create_custom_emoji(name=nome, image=data, reason="sync pack")
            ok += 1
            print(f"[emoji] criado {nome}", flush=True)
        except Exception as e:
            fail += 1
            erros.append(f"{nome}: {type(e).__name__} {str(e)[:200]}")
            print(f"[emoji] falhou {nome}: {e}", flush=True)
    _last_emoji_errors = list(erros)
    await _log_mod(guild, f"emoji sync: {ok} criados, {fail} falhas" + (f" | {erros[:3]}" if erros else ""))
    return ok, fail


@bot.command(name="emojifix")
async def m_emojifix(ctx):
    if not _owner_ok(ctx.author.id) or ctx.guild is None:
        return
    await ctx.send("`re-sincronizando emojis...`", delete_after=5)
    ok, fail = await _sync_emojis(ctx.guild)
    await ctx.send(f"`emoji sync: {ok} criados, {fail} falhas | total agora: {len(ctx.guild.emojis)}`", delete_after=None)


async def _post_emoji_ids(guild):
    ch_id = MODLOG_CHANNEL.get(guild.id)
    if not ch_id or not guild.emojis:
        return
    ch = guild.get_channel(ch_id) or await guild.fetch_channel(ch_id)
    linhas = []
    for e in sorted(guild.emojis, key=lambda x: x.name):
        pre = "a" if e.animated else ""
        linhas.append(f":{e.name}: -> `<{pre}:{e.name}:{e.id}>` id `{e.id}`")
    txt = "\n".join(linhas)
    for i in range(0, len(txt), 1900):
        await ch.send(("**emojis do server:**\n" if i == 0 else "") + txt[i:i + 1900])


async def _emoji_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(20)
    import traceback
    for g in bot.guilds:
        resultado = ""
        try:
            ok, fail = await _sync_emojis(g)
            resultado = f"{ok} criados, {fail} falhas, total agora {len(g.emojis)}"
        except Exception:
            resultado = traceback.format_exc()[-900:]
        _status_push({
            "tipo": "emoji_sync",
            "guild": g.name,
            "guild_id": g.id,
            "resultado": resultado,
            "erros": _last_emoji_errors[:10],
            "pasta_existe": os.path.isdir(EMOJI_DIR),
            "arquivos": sorted(os.listdir(EMOJI_DIR))[:40] if os.path.isdir(EMOJI_DIR) else [],
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        try:
            await _post_emoji_ids(g)
        except Exception as e:
            print(f"[emoji] ids {g.name}: {e}", flush=True)


# ============================ AUTO-COISAS (configuravel) ============================
AUTO_FILE = os.path.join(BASE_DIR, "auto.json")
_auto_cache = {}


def _auto_load():
    global _auto_cache
    try:
        with open(AUTO_FILE, "r", encoding="utf-8") as f:
            _auto_cache = json.loads(f.read())
    except Exception:
        _auto_cache = {}


def _auto_save():
    with open(AUTO_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(_auto_cache))


def _auto_cfg(gid):
    _auto_load()
    return _auto_cache.setdefault(str(gid), {
        "autothanks": {"on": True, "text": "valeu pelo boost {user}! tu e brabo. aproveita teus perks: mycolor e myname"},
        "autodm": {"on": True, "text": "bem-vindo {user}! le as regras e manda um salve no lobby"},
        "autoreply": {},
        "autopost": {"on": False, "channel_id": 0, "min": 60, "text": ""},
    })


async def _dm_send(user, texto):
    try:
        await user.send(texto[:2000])
        return True
    except Exception:
        return False


async def _auto_boost_dm(guild, member):
    cfg = _auto_cfg(guild.id).get("autothanks", {})
    if not cfg.get("on"):
        return
    texto = cfg.get("text", "").replace("{user}", member.mention)
    if texto:
        await _dm_send(member, texto)


async def _auto_welcome_dm(member):
    cfg = _auto_cfg(member.guild.id).get("autodm", {})
    if not cfg.get("on"):
        return
    texto = cfg.get("text", "").replace("{user}", member.mention)
    if texto:
        await _dm_send(member, texto)


async def _auto_reply_check(msg):
    if msg.guild is None:
        return
    replies = _auto_cfg(msg.guild.id).get("autoreply", {})
    baixo = msg.content.lower().strip()
    for palavra, resposta in replies.items():
        if palavra.lower() in baixo:
            await msg.channel.send(resposta[:2000])
            break


@bot.command(name="auto")
async def m_auto(ctx):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    c = _auto_cfg(ctx.guild.id)
    ar = ", ".join(list(c.get("autoreply", {}).keys())[:5]) or "nenhum"
    ap = c.get("autopost", {})
    await ctx.send(
        "**auto-coisas**\n"
        f"`autothanks`: {'on' if c['autothanks'].get('on') else 'off'} - dm de obrigado pra quem boosta\n"
        f"`autodm`: {'on' if c['autodm'].get('on') else 'off'} - dm de boas vindas\n"
        f"`autoreply`: {ar}\n"
        f"`autopost`: {'on' if ap.get('on') else 'off'} - post automatico a cada {ap.get('min', 60)}min",
        delete_after=None)


@bot.command(name="autothanks")
async def m_autothanks(ctx, modo: str = None, *, texto: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    c = _auto_cfg(ctx.guild.id)
    if modo is None:
        t = c["autothanks"].get("text", "")
        await ctx.send(f"`autothanks {'on' if c['autothanks'].get('on') else 'off'} | texto: {t[:150]}`", delete_after=None)
        return
    m = modo.lower()
    if m == "off":
        c["autothanks"]["on"] = False
    elif m == "on":
        c["autothanks"]["on"] = True
    elif m == "text" and texto:
        c["autothanks"]["text"] = texto
    else:
        await ctx.send("`uso: autothanks on/off/text <texto com {user}>`", delete_after=8)
        return
    _auto_save()
    _git_push_config(("auto.json",))
    await ctx.send("`autothanks atualizado`", delete_after=8)


@bot.command(name="autodm")
async def m_autodm(ctx, modo: str = None, *, texto: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    c = _auto_cfg(ctx.guild.id)
    if modo is None:
        t = c["autodm"].get("text", "")
        await ctx.send(f"`autodm {'on' if c['autodm'].get('on') else 'off'} | texto: {t[:150]}`", delete_after=None)
        return
    m = modo.lower()
    if m == "off":
        c["autodm"]["on"] = False
    elif m == "on":
        c["autodm"]["on"] = True
    elif m == "text" and texto:
        c["autodm"]["text"] = texto
    else:
        await ctx.send("`uso: autodm on/off/text <texto com {user}>`", delete_after=8)
        return
    _auto_save()
    _git_push_config(("auto.json",))
    await ctx.send("`autodm atualizado`", delete_after=8)


@bot.command(name="autoreply")
async def m_autoreply(ctx, acao: str = None, palavra: str = None, *, resposta: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    c = _auto_cfg(ctx.guild.id)
    reps = c.setdefault("autoreply", {})
    if acao is None or acao.lower() == "list":
        if not reps:
            await ctx.send("`nenhum autoreply. usa: autoreply add <palavra> <resposta>`", delete_after=10)
            return
        linhas = [f"`{k}` -> {v[:80]}" for k, v in list(reps.items())[:15]]
        await ctx.send("**autoreply:**\n" + "\n".join(linhas), delete_after=None)
        return
    a = acao.lower()
    if a == "add" and palavra and resposta:
        reps[palavra.lower()] = resposta
    elif a == "del" and palavra:
        reps.pop(palavra.lower(), None)
    else:
        await ctx.send("`uso: autoreply add <palavra> <resposta> | del <palavra> | list`", delete_after=8)
        return
    _auto_save()
    _git_push_config(("auto.json",))
    await ctx.send("`autoreply atualizado`", delete_after=8)


@bot.command(name="autopost")
async def m_autopost(ctx, *, resto: str = None):
    if not await _check_ok(ctx) or ctx.guild is None:
        return
    c = _auto_cfg(ctx.guild.id)
    ap = c.setdefault("autopost", {"on": False, "channel_id": 0, "min": 60, "text": ""})
    if resto is None:
        st = "on" if ap.get("on") else "off"
        ch = ctx.guild.get_channel(int(ap.get("channel_id", 0)))
        await ctx.send(f"`autopost {st} | canal #{ch.name if ch else '?'} | a cada {ap.get('min', 60)}min`", delete_after=None)
        return
    if resto.strip().lower() == "off":
        ap["on"] = False
        _auto_save()
        _git_push_config(("auto.json",))
        await ctx.send("`autopost desligado`", delete_after=8)
        return
    partes = resto.strip().split(maxsplit=2)
    if len(partes) < 3:
        await ctx.send("`uso: autopost #canal <minutos> <texto>`", delete_after=8)
        return
    conv = commands.ChannelConverter()
    try:
        canal = await conv.convert(ctx, partes[0])
    except Exception:
        await ctx.send("`canal invalido`", delete_after=8)
        return
    try:
        minutos = max(5, int(partes[1]))
    except ValueError:
        await ctx.send("`minutos invalido`", delete_after=8)
        return
    ap.update({"on": True, "channel_id": canal.id, "min": minutos, "text": partes[2]})
    _autopost_last[ctx.guild.id] = 0  # posta ja na proxima passada
    _auto_save()
    _git_push_config(("auto.json",))
    await ctx.send(f"`autopost on: #{canal.name} a cada {minutos}min`", delete_after=8)


_autopost_last = {}  # guild_id -> timestamp do ultimo post


async def _autopost_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(30)
    while not bot.is_closed():
        try:
            _auto_load()
            now = time.time()
            for gid, c in _auto_cache.items():
                ap = c.get("autopost", {})
                if not ap.get("on"):
                    continue
                intervalo = max(5, int(ap.get("min", 60))) * 60
                if now - _autopost_last.get(int(gid), 0) < intervalo:
                    continue
                guild = bot.get_guild(int(gid))
                if guild is None:
                    continue
                ch = guild.get_channel(int(ap.get("channel_id", 0)))
                txt = ap.get("text", "")
                if ch is not None and txt:
                    try:
                        await ch.send(txt[:2000])
                        _autopost_last[int(gid)] = now
                    except Exception as e:
                        print(f"[autopost] falhou em {guild.name}: {e}", flush=True)
        except Exception as e:
            print(f"[autopost] loop erro: {e}", flush=True)
        await asyncio.sleep(30)


# ============================ PAINEL BOOSTER (botoes) ============================
BOOSTER_PERMS = dict(
    priority_speaker=True,      # prioridade na call
    bypass_slowmode=True,       # ignora slowmode
    use_external_emojis=True,   # usa emoji de outros servers (nao cria)
    use_external_stickers=True,
    create_public_threads=True,
    create_private_threads=True,
    send_messages=True, read_messages=True, add_reactions=True,
    embed_links=True, attach_files=True, connect=True, speak=True,
)


class CorModal(discord.ui.Modal, title="cor do teu cargo"):
    hexv = discord.ui.TextInput(label="hex da cor", placeholder="#ff0055", max_length=7)

    async def on_submit(self, inter):
        try:
            color = discord.Color(int(str(self.hexv.value).strip().lstrip("#"), 16))
        except Exception:
            await inter.response.send_message("cor invalida. ex: #ff0055", ephemeral=True)
            return
        role = await _panel_role(inter.user, color=color)
        await inter.response.send_message(f"teu cargo {role.name} agora e #{str(self.hexv.value).lstrip('#')}", ephemeral=True)


class NomeModal(discord.ui.Modal, title="nome do teu cargo"):
    nome = discord.ui.TextInput(label="nome do cargo", placeholder="rei do set", max_length=20)

    async def on_submit(self, inter):
        role = await _panel_role(inter.user, name="\u2726 " + str(self.nome.value)[:20])
        await inter.response.send_message(f"cargo renomeado pra {role.name}", ephemeral=True)


class NickModal(discord.ui.Modal, title="teu nick no server"):
    nick = discord.ui.TextInput(label="nick", placeholder="como quiser aparecer", max_length=32)

    async def on_submit(self, inter):
        try:
            await inter.user.edit(nick=str(self.nick.value)[:32], reason="perk booster")
            await inter.response.send_message(f"nick trocado pra {self.nick.value}", ephemeral=True)
        except Exception as e:
            await inter.response.send_message(f"falhou: {e}", ephemeral=True)


async def _panel_role(member, color=None, name=None):
    role = _boost_role_of(member)
    if role is None:
        nome = name or ("\u2726 " + member.display_name[:20])
        role = await member.guild.create_role(name=nome, color=color or discord.Color.default(), hoist=False, permissions=discord.Permissions.none(), reason="perk booster")
        base = member.guild.get_role(1539797800932610068)
        pos = base.position + 1 if base else role.position
        try:
            await role.edit(position=pos)
        except Exception:
            pass
        await member.add_roles(role)
    else:
        kw = {}
        if color is not None:
            kw["color"] = color
        if name is not None:
            kw["name"] = name
        if kw:
            await role.edit(hoist=False, permissions=discord.Permissions.none(), **kw)
    return role


class BoostPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _gate(self, inter):
        m = inter.user
        if isinstance(m, discord.Member) and getattr(m, "premium_since", None):
            return True
        await inter.response.send_message("so pra booster.", ephemeral=True)
        return False

    @discord.ui.button(label="cor do cargo", style=discord.ButtonStyle.primary, custom_id="boost_cor")
    async def b_cor(self, inter, button):
        if not await self._gate(inter):
            return
        await inter.response.send_modal(CorModal())

    @discord.ui.button(label="nome do cargo", style=discord.ButtonStyle.primary, custom_id="boost_nome")
    async def b_nome(self, inter, button):
        if not await self._gate(inter):
            return
        await inter.response.send_modal(NomeModal())

    @discord.ui.button(label="meu nick", style=discord.ButtonStyle.secondary, custom_id="boost_nick")
    async def b_nick(self, inter, button):
        if not await self._gate(inter):
            return
        await inter.response.send_modal(NickModal())

    @discord.ui.button(label="minha call", style=discord.ButtonStyle.success, custom_id="boost_call")
    async def b_call(self, inter, button):
        if not await self._gate(inter):
            return
        guild = inter.guild
        brole = guild.premium_subscriber_role
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),
            inter.user: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True),
            guild.me: discord.PermissionOverwrite(connect=True),
        }
        if brole is not None:
            overwrites[brole] = discord.PermissionOverwrite(connect=True)
        ch = await guild.create_voice_channel(
            name=f"call de {inter.user.display_name}"[:100],
            user_limit=10, overwrites=overwrites, reason="perk booster")
        await inter.response.send_message(f"call privada criada: {ch.name}", ephemeral=True)


@bot.event
async def on_voice_state_update(member, before, after):
    # auto-delete de call de booster vazia
    try:
        ch = before.channel
        if ch is not None and ch.name.startswith("call de ") and len(ch.members) == 0:
            await asyncio.sleep(15)
            if len(ch.members) == 0:
                await ch.delete(reason="mycall vazia")
    except Exception:
        pass


@bot.event
async def on_member_update(before, after):
    # perdeu boost -> remove cargo custom
    try:
        bp = getattr(before, "premium_since", None)
        ap_ = getattr(after, "premium_since", None)
        if bp and not ap_:
            role = _boost_role_of(after)
            if role is not None:
                await role.delete(reason="perdeu boost")
            await _log_mod(after.guild, f"boost: {after} perdeu boost, cargo custom removido")
    except Exception as e:
        print(f"[boost] update erro: {e}", flush=True)


@bot.command(name="setupperks")
async def m_setupperks(ctx):
    if not _owner_ok(ctx.author.id) or ctx.guild is None:
        return
    guild = ctx.guild
    brole = guild.premium_subscriber_role
    if brole is None:
        await ctx.send("`ninguem boostou ainda, sem cargo booster pra configurar`", delete_after=8)
        return
    # perms direto no cargo Booster padrao (sem comando nenhum)
    await brole.edit(permissions=discord.Permissions(**BOOSTER_PERMS), reason="perks de booster")
    # canal privado dos boosters
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        brole: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    ch = discord.utils.get(guild.text_channels, name="booster-lounge")
    if ch is None:
        ch = await guild.create_text_channel("booster-lounge", overwrites=overwrites, reason="painel booster")
    else:
        await ch.edit(overwrites=overwrites)
    emb = discord.Embed(
        title="PAINEL BOOSTER",
        description="usa os botoes ai embaixo:\n"
                    "- cor do cargo: teu cargo personalizado com a cor que quiser\n"
                    "- nome do cargo: renomeia teu cargo\n"
                    "- meu nick: troca teu nick quando quiser\n"
                    "- minha call: cria call privada so tua (some quando vazia)",
        color=0xF47FFF)
    emb.set_footer(text="perks automaticas: bypass slowmode, prioridade na call, threads")
    await ch.purge(limit=20)
    await ch.send(embed=emb, view=BoostPanel())
    await ctx.send(f"`perks setadas no cargo {brole.name} + painel em #{ch.name}`", delete_after=8)


# ============================ MAIN ============================
if __name__ == "__main__":
    bot.run(TOKEN)