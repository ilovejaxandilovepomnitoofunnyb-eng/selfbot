#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SELFBOT v1.0 — Raid Edition
Rodando como CONTA DE USUÁRIO (selfbot) via discord.py-self.

== DIFERENÇAS VS BOT NORMAL ==
- Funciona em DM, GRUPOS e servidores (prefixo, sem slash — slash não existe
  pra selfbot; mensagens de usuário funcionam em qualquer lugar).
- @everyone / @here marcam onde o usuário tem permissão de mencionar.
- Voice: entra na call (Voice State Update via gateway) e toca áudio opus
  (libopus + libsodium + ffmpeg).

== SEGURANÇA ANTI-BAN (configurável) ==
- DELAY_MEDIO: intervalo humano entre mensagens (jitter aleatório).
- MAX_MSGS_POR_MINUTO: cap global de mensagens por minuto.
- USAR_TYPING: aciona indicador "digitando" antes de enviar (parece humano).
- VARIAR_PAYLOAD: varia levemente o conteúdo entre mensagens.
- SEM_MENÇÃO_EM_DM: não marca @everyone/@here em DMs (fator de flag forte).
- RATE_LIMIT_BACKOFF: pausa longa automática se o Discord reclamar.

== RPC (Rich Presence) ==
- RPC_VIA_GATEWAY = True: define presença personalizada (jogo/filme/status)
  direto no gateway, sem conectar um app RPC externo. Funciona offline
  do client Discord (o status aparece pra qualquer um que veja o perfil).
- Comandos: rpc set <tipo> <texto>, rpc clear, rpc loop.

== ACESSO ==
- Somente OWNER_ID (dono da conta) pode usar comandos.
- OWNER_ID é detectado automaticamente no login (self bot = própria conta).
- WHITELIST: arquivo whitelist.json com IDs extras permitidos.
  Comandos: wl add <id>, wl remove <id>, wl list.
"""

import asyncio
import datetime
import json
import math
import os
import random
import re
import struct
import sys
import time
import urllib.request
import urllib.error

import discord
from discord.ext import commands

# ============================ CONFIG ============================
PREFIX = "."
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "self_token.txt")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "selfbot_config.json")

# --- Segurança anti-ban (edite à vontade) ---
DELAY_MEDIO = 1.2            # segundos base entre mensagens (jitter +-50%)
MAX_MSGS_POR_MINUTO = 30     # cap global (0 = sem cap)
USAR_TYPING = True           # mostra "digitando..." antes de enviar
VARIAR_PAYLOAD = True        # varia payload entre mensagens
SEM_MENÇÃO_EM_DM = True      # remove @everyone/@here em DMs
RATE_LIMIT_BACKOFF = 30      # pausa (s) se o Discord acusar rate limit/403

# --- RPC ---
RPC_VIA_GATEWAY = True       # presença via gateway (recomendado p/ selfbot)

# ============================ ESTADO ============================
# discord.py-self (fork 1.7.x) não usa Intents — selfbot recebe tudo do gateway.

# --- Carrega libopus manualmente (Termux/Android não está no PATH padrão) ---
def _ensure_opus():
    try:
        if discord.opus.is_loaded():
            return
    except Exception:
        pass
    for cand in ["/data/data/com.termux/files/usr/lib/libopus.so",
                 "/usr/lib/libopus.so",
                 "/usr/lib/x86_64-linux-gnu/libopus.so",
                 "libopus.so.0", "libopus.so"]:
        try:
            discord.opus.load_opus(cand)
            break
        except Exception:
            continue
    try:
        print(f"[opus] carregado: {discord.opus.is_loaded()}")
    except Exception:
        pass

_ensure_opus()

bot = commands.Bot(command_prefix=PREFIX,
                   user_bot=True, help_command=None)

# ============================ DEVICE SPOOF (pc/celular/vr/web/console) ============================
# O Discord mostra a plataforma pelas properties do IDENTIFY:
#   $os / $browser / $device
#   Discord Client (Win/Mac/Linux)  -> desktop
#   Discord Android / Discord iOS   -> celular
#   Discord VR + device oculus      -> VR (Meta Quest)
#   Chrome / Firefox                -> navegador
#   Discord Embedded                -> console (Xbox/PlayStation)
DEVICE_PRESETS = {
    "pc":      {"$os": "Windows", "$browser": "Discord Client", "$device": "Windows"},
    "mac":     {"$os": "Mac OS X", "$browser": "Discord Client", "$device": "macOS"},
    "linux":   {"$os": "Linux", "$browser": "Discord Client", "$device": "Linux"},
    "android": {"$os": "Android", "$browser": "Discord Android", "$device": "SM-G991B"},
    "iphone":  {"$os": "iOS", "$browser": "Discord iOS", "$device": "iPhone15,2"},
    "ipad":    {"$os": "iOS", "$browser": "Discord iOS", "$device": "iPad13,4"},
    "web":     {"$os": "Windows", "$browser": "Chrome", "$device": ""},
    "webmac":  {"$os": "Mac OS X", "$browser": "Firefox", "$device": ""},
    "vr":      {"$os": "Android", "$browser": "Discord VR", "$device": "oculus"},
    "xbox":    {"$os": "Xbox", "$browser": "Discord Embedded", "$device": "Xbox Series X"},
    "play":    {"$os": "PlayStation", "$browser": "Discord Embedded", "$device": "PlayStation 5"},
}

_active_device = None  # nome do preset ativo; None = default

def _device_identify_wrapper(original):
    """Envolve DiscordWebSocket.identify injetando as properties do device."""
    import discord.gateway as _gw
    async def wrapped(self):
        if _active_device and _active_device in DEVICE_PRESETS:
            sp = getattr(getattr(self, "_headers", None), "super_properties", None)
            if sp is not None:
                for k, v in DEVICE_PRESETS[_active_device].items():
                    sp[k] = v
        return await original(self)
    return wrapped

def _apply_device_patch():
    """Monkeypatch do identify (aplica o preset no próximo IDENTIFY)."""
    import discord.gateway as _gw
    if not getattr(_gw.DiscordWebSocket, "_device_patched", False):
        _gw.DiscordWebSocket.identify = _device_identify_wrapper(_gw.DiscordWebSocket.identify)
        _gw.DiscordWebSocket._device_patched = True

_apply_device_patch()

async def _reconnect_for_device():
    """Fecha o ws com 4000 -> gateway reconecta e reenvia IDENTIFY com o device novo."""
    ws = bot.ws
    if ws is None:
        return
    try:
        await ws.close(code=4000)
    except Exception:
        pass

@bot.command(name="device", aliases=["plataforma", "dev"])
async def device(ctx, nome: str = None):
    """Forja a plataforma do client (pc/mac/linux/android/iphone/ipad/web/vr/xbox/play). Uso: .device <nome> | .device reset | .device list"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    global _active_device
    if nome is None or nome.lower() in ("list", "lista"):
        linhas = "\n".join(f"  {k}  ->  {v['$browser']} ({v['$os']}{'/' + v['$device'] if v['$device'] else ''})" for k, v in DEVICE_PRESETS.items())
        atual = _active_device or "default"
        await safe_send(ctx, f"**device atual**: {atual}\n**presets:**\n{linhas}")
        return
    nome = nome.lower()
    if nome == "reset":
        _active_device = None
        await safe_send(ctx, "device resetado (default)")
        await _reconnect_for_device()
        return
    if nome not in DEVICE_PRESETS:
        await safe_send(ctx, "device invalido. `.device list`")
        return
    _active_device = nome
    await safe_send(ctx, f"**device -> {nome}** ({DEVICE_PRESETS[nome]['$browser']}), reconectando...")
    await _reconnect_for_device()

OWNER_ID = None
whitelist = set()

# estado do blast de voz
voice_ctx = None          # (voice_client, task)
blast_task = None

# ============================ UTILITÁRIOS ============================

def load_token() -> str:
    # Prioridade: env DISCORD_TOKEN (GitHub Actions secret) depois arquivo
    env_token = os.getenv("DISCORD_TOKEN", "").strip()
    if env_token:
        return env_token
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def load_whitelist():
    global whitelist
    try:
        with open(os.path.join(os.path.dirname(__file__), "whitelist.json"),
                  "r", encoding="utf-8") as f:
            whitelist = set(json.load(f))
    except Exception:
        whitelist = set()

def save_whitelist():
    with open(os.path.join(os.path.dirname(__file__), "whitelist.json"),
              "w", encoding="utf-8") as f:
        json.dump(sorted(whitelist), f, indent=2)

def allowed(author_id: int) -> bool:
    return author_id == OWNER_ID or author_id in whitelist

def human_delay() -> float:
    med = DELAY_MEDIO
    return max(0.3, med * random.uniform(0.5, 1.5))

async def maybe_typing(channel, secs: float = 1.2):
    """Simula digitação humana antes de mandar mensagem."""
    if USAR_TYPING and isinstance(channel, (discord.TextChannel,
                                            discord.DMChannel)):
        try:
            async with channel.typing():
                await asyncio.sleep(min(secs, human_delay()))
        except Exception:
            await asyncio.sleep(human_delay())

async def safe_send(ctx_or_ch, content, *, mention_ok=True):
    """Envia com proteções de segurança. Retorna 0 se bloqueado por cap."""
    ch = ctx_or_ch.channel if hasattr(ctx_or_ch, "channel") else ctx_or_ch
    if SEM_MENÇÃO_EM_DM and isinstance(ch, discord.DMChannel):
        content = content.replace("@everyone", "everyone")
        content = content.replace("@here", "here")
    try:
        if mention_ok:
            await ch.send(content)
        else:
            await ch.send(content, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as e:
        if e.status in (429, 403):
            print(f"[!] Rate/403: pausando {RATE_LIMIT_BACKOFF}s")
            await asyncio.sleep(RATE_LIMIT_BACKOFF)
            return 0
        raise
    return 1

# ============================ PAYLOADS ============================

ZALGO_TOP = "".join(chr(c) for c in range(0x0300, 0x036F))
ZALGO_MID = "\u0335\u0336\u0337\u0338"
WEIRD = [
    "\u1242B", "\u202E", "\u200B", "\u200D", "\uFE0F", "\uFE0E",
    "\u180E", "\u3164", "\uFFA0", "\u061C", "\u2066\u2069",
    "\u0000\uFFF9\uFFFA\uFFFB", "\uE0000\uE007F", "\u10FFFF",
]

def zalgo(n=8):
    b = random.choice("AESTNHOXM")
    out = b
    for _ in range(n):
        out += random.choice(ZALGO_TOP) + random.choice(ZALGO_TOP)
        if random.random() < 0.4:
            out += random.choice(ZALGO_MID)
    return out

def build_payload(vezes: int = 10) -> list:
    """Lista de mensagens max-length (~1990 chars) ou normais."""
    out = []
    for _ in range(max(1, vezes)):
        parts = []
        cur = 0
        target = 1990
        while cur < target:
            r = random.random()
            if r < 0.18:
                seg = "@everyone"
            elif r < 0.28:
                seg = "@here"
            elif r < 0.5:
                seg = "\u1242B" * random.randint(8, 20)
            elif r < 0.7:
                seg = "\u202E" + zalgo(random.randint(5, 12)) + "\u202C"
            elif r < 0.9:
                seg = "".join(random.choice(WEIRD) * random.randint(1, 4)
                              for _ in range(random.randint(3, 10)))
            else:
                seg = "SELFBOT" + "𒐫" * random.randint(5, 15)
            if cur + len(seg) > target:
                seg = seg[: target - cur]
            parts.append(seg)
            cur += len(seg)
        out.append("".join(parts))
    return out

# ============================ EVENTOS ============================

@bot.event
async def on_ready():
    global OWNER_ID
    OWNER_ID = bot.user.id
    load_whitelist()
    cfg = load_config()
    if OWNER_ID not in whitelist:
        whitelist.add(OWNER_ID)
        save_whitelist()
    print(f"[+] SELFBOT online: {bot.user} (ID: {OWNER_ID})")
    print(f"[+] Prefixo: {PREFIX} | Whitelist: {sorted(whitelist)}")
    print(f"[+] Anti-ban: delay={DELAY_MEDIO}s cap={MAX_MSGS_POR_MINUTO}/min "
          f"typing={USAR_TYPING} variar={VARIAR_PAYLOAD}")

@bot.event
async def on_message(msg):
    # 1) o proprio self: processa comandos
    if msg.author.id == bot.user.id:
        await bot.process_commands(msg)
        return
    # 2) whitelisted: tambem podem usar comandos (stealth)
    if allowed(msg.author.id):
        await bot.process_commands(msg)
        return
    # 3) autoreporter: vigia mensagens de outros
    try:
        await auto_report(msg)
    except Exception:
        pass

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    try:
        await ctx.send(f"`{type(error).__name__}: {error}`", delete_after=5)
    except Exception:
        pass

# ============================ PERMISSÃO (only me / whitelist) ============================

async def check_perms(ctx) -> bool:
    if allowed(ctx.author.id):
        # auto-delete: apaga a msg do comando após executar (stealth)
        try:
            await ctx.message.delete()
        except Exception:
            pass
        return True
    try:
        await ctx.message.delete()
    except Exception:
        pass
    return False

# ============================ COMANDOS: RAID ============================

@bot.command(name="spam", aliases=["flood"])
async def spam(ctx, vezes: int = 10):
    """Spam payload máximo (zalgo + @everyone/@here) no canal atual. --r p/ rápido"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    rapido = "rapido" not in ctx.invoked_with and False
    payloads = build_payload(min(vezes, 500 if rapido else MAX_MSGS_POR_MINUTO or 30))
    for p in payloads:
        await maybe_typing(ctx.channel)
        await safe_send(ctx, p)
        if rapido:
            await asyncio.sleep(0.15)
        else:
            await asyncio.sleep(human_delay())

@bot.command(name="spamc", aliases=["custom"])
async def spamc(ctx, *, texto: str):
    """Spam de texto personalizado. Uso: .spamc 10 texto | .spamc texto (10x) | --r rápido"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    # detecta vezes se o texto COMEÇAR com número: ".spamc 50 texto"
    if texto and texto.split(maxsplit=1)[0].isdigit():
        vezes = int(texto.split(maxsplit=1)[0])
        texto = texto.split(maxsplit=1)[1] if " " in texto else ""
    else:
        vezes = 10
    rapido = False
    if texto.rstrip().endswith("--r"):
        rapido = True
        texto = texto.rstrip()[:-3].rstrip()
    for _ in range(min(vezes, 500 if rapido else MAX_MSGS_POR_MINUTO or 30)):
        content = texto
        if VARIAR_PAYLOAD:
            content = texto + random.choice(["", " ", "\u200B", "\u202E", "𒐫"])
        await safe_send(ctx, content)
        if rapido:
            await asyncio.sleep(0.015 + random.random() * 0.03)  # ~20-40 msg/s (máx p/ 429)
        else:
            await asyncio.sleep(human_delay())

# ============================ ALT (conta secundaria) ============================
ALT_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "alt_token.txt")
BOT_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "bot_token.txt")

def _load_alt_token():
    t = os.environ.get("ALT_TOKEN", "")
    if not t:
        try:
            with open(ALT_TOKEN_FILE, encoding="utf-8") as f:
                t = f.read().strip()
        except Exception:
            t = ""
    return t

def _load_bot_token():
    t = os.environ.get("BOT_TOKEN", "") or os.environ.get("NUKE_TOKEN", "")
    if not t:
        try:
            with open(BOT_TOKEN_FILE, encoding="utf-8") as f:
                t = f.read().strip()
        except Exception:
            t = ""
    return t

alt_token = _load_alt_token()
bot_token = _load_bot_token()

UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def api_rest(method: str, url: str, token: str, payload=None, bot: bool = False):
    """Chamada REST direta no Discord. Token de user (selfbot/alt) ou bot."""
    h = {
        'Authorization': ('Bot ' + token) if bot else token,
        'User-Agent': UA_BROWSER,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=h, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            try:
                return {"status": r.status, "json": json.loads(raw)}
            except Exception:
                return {"status": r.status, "json": None, "text": raw.decode('utf-8', 'replace')}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            j = json.loads(raw)
        except Exception:
            j = None
        return {"status": e.code, "json": j, "text": raw.decode('utf-8', 'replace')}

def alt_info_sync():
    d = api_rest("GET", "https://discord.com/api/v9/users/@me", alt_token)
    if d.get("status") == 200 and d.get("json"):
        j = d["json"]
        return (f"**ALT**: {j.get('username')} (`{j.get('id')}`) | flags: {j.get('flags')} | "
                f"verified: {j.get('verified')} | phone: {'sim' if j.get('phone') else 'nao'}")
    return f"alt token invalido (status {d.get('status')}) - use `.altset <token>`"

@bot.command(name="altset")
async def altset(ctx, token: str):
    """Registra o token da alt. Uso: .altset <token>"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    global alt_token
    teste = api_rest("GET", "https://discord.com/api/v9/users/@me", token)
    if teste.get("status") == 200 and teste.get("json"):
        alt_token = token
        try:
            with open(ALT_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(token)
        except Exception:
            pass
        await safe_send(ctx, f"**ALT registrada**: {teste['json'].get('username')} `{teste['json'].get('id')}`")
    else:
        await safe_send(ctx, f"token invalido (status {teste.get('status')})")

@bot.command(name="alt")
async def alt(ctx):
    """Info da alt cadastrada."""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if not alt_token:
        await safe_send(ctx, "nenhuma alt cadastrada - use `.altset <token>`")
        return
    await safe_send(ctx, alt_info_sync())

@bot.command(name="altservers", aliases=["altguilds"])
async def altservers(ctx):
    """Lista servidores da alt."""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if not alt_token:
        await safe_send(ctx, "nenhuma alt cadastrada - use `.altset <token>`")
        return
    d = api_rest("GET", "https://discord.com/api/v9/users/@me/guilds", alt_token)
    if d.get("status") == 200 and d.get("json"):
        linhas = ["**Servidores da alt**:", "```"]
        for g in d["json"]:
            linhas.append("%s (%s)" % (g.get("name"), g.get("id")))
        linhas.append("```")
        msg = "\n".join(linhas)
        await safe_send(ctx, msg[:1950])
    else:
        await safe_send(ctx, "erro: status %s %s" % (d.get("status"), d.get("text", ""))[:400])

@bot.command(name="altjoin")
async def altjoin(ctx, invite: str, cargo: str = None):
    """Alt entra num servidor via invite. OPCIONAL: cargo_id p/ o bot dar cargo.
    Uso: .altjoin discord.gg/codigo [cargo_id]"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if not alt_token:
        await safe_send(ctx, "nenhuma alt cadastrada - use `.altset <token>`")
        return
    code = invite.split("/")[-1].split("invite/")[-1].strip()
    d = api_rest("POST", "https://discord.com/api/v9/invites/%s" % code, alt_token)
    if d.get("status") not in (200, 201, 204):
        await safe_send(ctx, "falhou ao entrar: status %s %s" % (d.get("status"), d.get("text", ""))[:400])
        return
    j = d.get("json") or {}
    gid = str(j.get("guild", {}).get("id", ""))
    await safe_send(ctx, "**ALT entrou** em `%s` (guild %s)" % (j.get("guild", {}).get("name", "?"), gid))
    if cargo and gid:
        await _alt_dar_cargo(ctx, gid, cargo)

async def _alt_dar_cargo(ctx, gid: str, cargo: str):
    if not bot_token:
        await safe_send(ctx, "sem token de bot (env BOT_TOKEN / bot_token.txt) - nao deu cargo")
        return
    arid = None
    try:
        arid = str(int(cargo))
    except Exception:
        pass
    if arid is None:
        await safe_send(ctx, "cargo precisa ser o ID numerico (veja `.altroles`)")
        return
    alt_id = "1532322571704336468"
    if alt_id == "1532322571704336468":
        try:
            me = api_rest("GET", "https://discord.com/api/v9/users/@me", alt_token)
            if me.get("status") == 200 and me.get("json"):
                alt_id = str(me["json"]["id"])
        except Exception:
            pass
    d = api_rest("PUT", "https://discord.com/api/v9/guilds/%s/members/%s/roles/%s" % (gid, alt_id, arid),
                 bot_token, bot=True)
    if d.get("status") in (200, 201, 204):
        await safe_send(ctx, "**cargo dado**: <@&%s>" % arid)
    else:
        await safe_send(ctx, "falha no cargo: status %s %s" % (d.get("status"), d.get("text", ""))[:300])

@bot.command(name="altrole")
async def altrole(ctx, cargo: str, gid: str = None):
    """Bot Jax da cargo pra alt. Uso: .altrole <cargo_id> [guild_id] (padrao: guild atual)"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if not gid:
        gid = str(ctx.guild.id if ctx.guild else "")
    if not gid:
        await safe_send(ctx, "use em um servidor ou passe guild_id")
        return
    await _alt_dar_cargo(ctx, gid, cargo)

@bot.command(name="altroles")
async def altroles(ctx, gid: str = None):
    """Lista cargos do servidor (via bot). Uso: .altroles [guild_id]"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if not bot_token:
        await safe_send(ctx, "sem token de bot (env BOT_TOKEN / bot_token.txt)")
        return
    if not gid:
        gid = str(ctx.guild.id if ctx.guild else "")
    if not gid:
        await safe_send(ctx, "use em um servidor ou passe guild_id")
        return
    d = api_rest("GET", "https://discord.com/api/v9/guilds/%s/roles" % gid, bot_token, bot=True)
    if d.get("status") == 200 and d.get("json"):
        roles = sorted(d["json"], key=lambda r: (r.get("position", 0),), reverse=True)
        linhas = ["**Cargos de %s**" % gid, "```"]
        for r in roles:
            if r.get("name") == "@everyone":
                continue
            linhas.append("%s | %s | id=%s" % (r.get("name"), r.get("position"), r.get("id")))
        linhas.append("```")
        msg = "\n".join(linhas)
        await safe_send(ctx, msg[:1950])
    else:
        await safe_send(ctx, "erro: status %s %s" % (d.get("status"), d.get("text", ""))[:300])

@bot.command(name="altnick")
async def altnick(ctx, *, nick: str):
    """Muda o nick da alt no servidor atual (onde ela estiver)."""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if not alt_token:
        await safe_send(ctx, "nenhuma alt cadastrada - use `.altset <token>`")
        return
    gid = str(ctx.guild.id if ctx.guild else "")
    if not gid:
        await safe_send(ctx, "use em um servidor")
        return
    d = api_rest("PATCH", "https://discord.com/api/v9/guilds/%s/members/@me" % gid, alt_token,
                 payload={"nick": nick})
    if d.get("status") in (200, 201, 204):
        await safe_send(ctx, "**nick alterado** p/ `%s`" % nick)
    else:
        await safe_send(ctx, "falha: status %s %s" % (d.get("status"), d.get("text", ""))[:300])

# ============================ JVC (entrar em call) ============================

@bot.command(name="jvc", aliases=["entrarcall"])
async def jvc(ctx, canal_id: str = None):
    """Entra na call. Uso: .jvc (call onde tu ta) | .jvc <voice_channel_id>"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    vc = None
    if canal_id:
        try:
            ch = bot.get_channel(int(canal_id))
        except Exception:
            ch = None
        if ch and isinstance(ch, discord.VoiceChannel):
            vc = ch
    elif ctx.guild and getattr(ctx.author, "voice", None) and ctx.author.voice.channel:
        vc = ctx.author.voice.channel  # call onde o dono esta
    elif ctx.guild:
        vcs = [c for c in ctx.guild.voice_channels if c.permissions_for(ctx.guild.me).connect]
        if vcs:
            vc = vcs[0]
    if not vc:
        await safe_send(ctx, "canal de voz nao encontrado (use `.jvc <voice_channel_id>`)")
        return
    for c in list(bot.voice_clients):
        try:
            await c.disconnect(force=True)
        except Exception:
            pass
    try:
        await vc.connect()
        await safe_send(ctx, "**na call**: `%s`" % vc.name)
    except Exception as e:
        await safe_send(ctx, "erro: %s" % (str(e)[:200]))

@bot.command(name="sair", aliases=["leavecall", "dc"])
async def saircall(ctx):
    """Sai da call."""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    for c in list(bot.voice_clients):
        try:
            await c.disconnect(force=True)
        except Exception:
            pass
    await safe_send(ctx, "saiu da call")

# ============================ REPORT SYSTEM ============================

# Caminhos (breadcrumbs) das categorias - extraidos do /reporting/menu
REPORT_MSG_CATS = {
    "spam": [7, 98], "assedio": [7, 76, 101], "odio": [7, 76, 107],
    "gore": [7, 76, 86, 108], "nsfw": [7, 76, 86, 109], "nsfw_degradante": [7, 76, 86, 110],
    "vinganca": [7, 76, 86, 111], "lori": [7, 76, 88, 112], "menor_sexualizado": [7, 76, 88, 113],
    "menor_cwm": [7, 76, 88, 114], "menor_caam": [7, 76, 88, 115], "csam": [7, 76, 88, 116],
    "ameaca": [7, 76, 90, 117], "glorifica_violencia": [7, 76, 90, 118],
    "menor_idade": [7, 80, 91, 127], "impersonacao": [7, 80, 121, 163],
    "golpe": [7, 80, 121, 167], "contas": [7, 80, 123], "drogas": [7, 80, 124], "hack": [7, 80, 126],
}
REPORT_USER_CATS = {
    "spam": [62, 19, 25], "odio": [62, 19, 29, 36], "ameaca": [62, 19, 28, 33, 45],
    "nsfw": [62, 19, 28, 32, 38], "lori": [62, 19, 28, 34, 41], "menor_caam": [62, 19, 28, 34, 43],
    "csam": [62, 19, 28, 34, 44], "impersonacao": [62, 19, 30, 47], "golpe": [62, 19, 30, 51],
    "menor_idade": [62, 19, 31, 35, 56], "drogas": [62, 19, 31, 54], "hack": [62, 19, 31, 55],
    "autormutilacao": [62, 93, 57],
}
REPORT_GUILD_CATS = {
    "spam": [4, 2, 98], "odio": [4, 2, 76, 107], "nsfw": [4, 2, 86, 82], "gore": [4, 2, 86, 108],
    "lori": [4, 2, 86, 88, 112], "csam": [4, 2, 86, 88, 116], "contas": [4, 2, 80, 123],
    "drogas": [4, 2, 80, 124], "hack": [4, 2, 80, 126], "auto_mutilacao": [4, 85, 128],
    "suicidio": [4, 85, 129],
}
REPORT_CATS_BY_TYPE = {"msg": REPORT_MSG_CATS, "user": REPORT_USER_CATS, "server": REPORT_GUILD_CATS}

def do_report(name: str, breadcrumbs, **ids):
    """Envia report. ids: message_id+channel_id / user_id / guild_id. Retorna (ok, resp)."""
    payload = {
        "version": "1.0", "variant": "latest", "name": name,
        "language": "en", "breadcrumbs": breadcrumbs,
    }
    payload.update(ids)
    d = api_rest("POST", "https://discord.com/api/v9/reporting/%s" % name, alt_token or SELF_TOKEN(), payload=payload)
    if d.get("status") == 200 and d.get("json") and d["json"].get("report_id"):
        return True, d["json"]["report_id"]
    return False, "%s %s" % (d.get("status"), (d.get("text") or "")[:200])

def SELF_TOKEN():
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def _split_ids(texto: str) -> list:
    import re as _re
    ids = _re.findall(r"\d{15,22}", texto)
    return list(dict.fromkeys(ids))

@bot.command(name="report")
async def report(ctx, tipo: str, categoria: str = None, *, ids_str: str = None):
    """Reporta no Discord. Uso:
    .report cats [msg|user|server]
    .report msg <cat> <msg_id ou link da msg> [mais ids...]
    .report user <cat> <user_id> [mais ids...]
    .report server <cat> <server_id> [mais ids...]"""
    if not await check_perms(ctx):
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    tipo = tipo.lower()
    if tipo == "cats":
        alvo = (categoria or "msg").lower()
        cats = REPORT_CATS_BY_TYPE.get(alvo, REPORT_MSG_CATS)
        await safe_send(ctx, "**Categorias (%s)**: %s" % (alvo, ", ".join(sorted(cats))))
        return
    if tipo not in REPORT_CATS_BY_TYPE:
        await safe_send(ctx, "tipo invalido: msg | user | server")
        return
    if not categoria or not ids_str:
        await safe_send(ctx, "uso: .report %s <categoria> <id(s)>" % tipo)
        return
    cat = categoria.lower()
    cats = REPORT_CATS_BY_TYPE[tipo]
    if cat not in cats:
        await safe_send(ctx, "categoria invalida. `.report cats %s`" % tipo)
        return
    ids = _split_ids(ids_str)
    if not ids:
        await safe_send(ctx, "nenhum id valido (precisa ter 15+ digitos)")
        return
    ok = 0
    erros = []
    for rid in ids:
        if tipo == "msg":
            guild_id = str(ctx.guild.id) if ctx.guild else None
            payload_ids = {"message_id": rid, "channel_id": str(ctx.channel.id)}
            if guild_id:
                payload_ids["guild_id"] = guild_id
            func = lambda: do_report("message", cats[cat], **payload_ids)
        elif tipo == "user":
            func = lambda: do_report("user", cats[cat], user_id=rid)
        else:
            func = lambda: do_report("guild", cats[cat], guild_id=rid)
        try:
            r, resp = await bot.loop.run_in_executor(None, func)
        except Exception as exc:
            r, resp = False, str(exc)[:120]
        if r:
            ok += 1
        else:
            erros.append("%s:%s" % (rid, resp))
        await asyncio.sleep(1.2)
    msg = "**report enviado**: %d/%d (%s/%s)" % (ok, len(ids), tipo, cat)
    if erros:
        msg += "\n```%s```" % "\n".join(erros[:5])
    await safe_send(ctx, msg[:1800])

# ============================ AUTOREPORTER (deteccao de risco) ============================

# seeds de termos que podem levar a banimento/denuncia (pt + en)
_SLU = ["nigger", "nigga", "negroid", "coon", "kike", "faggot", "fag", "tranny", "retard",
        "mongoloid", "spic", "wetback", "chink", "gook", "raghead", "sandnigger", "beaner",
        "dyke", "cunt", "whore", "slut", "bitch", "bastard", "pedo", "pedophile", "pedofilo",
        "cp", "loli", "lolita", "rape", "estupro", "estupra", "violar", "viola",
        "kys", "se mata", "se mate", "mata-te", "morre", "suicida", "suicidio",
        "cocaina", "cocaína", "crack", "heroina", "heroína", "meta", "mdma", "ecstasy",
        "vendo", "vendo droga", "compro droga", "maconha", "skank", "cigarro eletronico",
        "golpe", "golpista", "falcatrua", "scam", "phishing", "fraude", "fraudador",
        "nitro gratis", "nitro free", "gift scam", "boost scam", "cartao roubado",
        "cartão roubado", "ccs", "dumps", "carding", "nude", "nudes", "pack", "onlyfans"]

# variacoes leet para evasao
_LEET = [("a", ["a", "4", "@", "á", "à", "ã"]), ("b", ["b", "8", "6"]),
         ("e", ["e", "3", "é", "ê"]), ("i", ["i", "1", "!", "í", "|"]),
         ("o", ["o", "0", "ó", "ô"]), ("s", ["s", "5", "$", "z"]),
         ("t", ["t", "7", "+"]), ("g", ["g", "9", "6"]), ("l", ["l", "1", "í"])]

def _normaliza_msg(texto: str) -> str:
    """Normaliza: lowercase, remove acentos, remove nao-alfanum (mantem espacos)."""
    import unicodedata as _u
    t = texto.lower()
    t = _u.normalize("NFKD", t)
    t = "".join(c for c in t if not _u.combining(c))  # remove acentos
    t = "".join(c for c in t if c.isalnum() or c in " .-_+")
    return t

def _leet_normalize(texto: str) -> str:
    """Mapa leet inverso: v3nd0 dr0g4 -> vendo droga. Usado na deteccao."""
    t = _normaliza_msg(texto)
    t = t.replace("4", "a").replace("@", "a").replace("3", "e").replace("1", "i") \
         .replace("0", "o").replace("5", "s").replace("$", "s").replace("7", "t") \
         .replace("8", "b").replace("9", "g").replace("!", "i").replace("+", "t")
    return t

_RISCO_CACHE = None

def _build_risco():
    """Monta as frases de risco (normalizadas + sem espacos)."""
    global _RISCO_CACHE
    if _RISCO_CACHE:
        return _RISCO_CACHE
    frases = set()
    for termo in _SLU:
        base = _leet_normalize(termo).replace(" ", "")
        if len(base) > 3:
            frases.add(base)
    # numeros extremos conhecidos
    for n in range(8, 18):
        frases.add("eutenho%d" % n)
        frases.add("tenho%d" % n)
        frases.add("tenho%danos" % n)
        frases.add("sou%d" % n)
        frases.add("im%d" % n)
        frases.add("iam%d" % n)
    _RISCO_CACHE = (frases, len(frases))
    return _RISCO_CACHE

_AGE_RE = None

def _detect_risco(texto: str):
    """Retorna (tipo, cat_key) se achar conteudo de risco; senao None."""
    global _AGE_RE
    if _AGE_RE is None:
        _AGE_RE = re.compile(r"(eu tenho|tenho|sou|im|i am|i'm|my age is|age is|amo|adoro)\s*[: ]?\s*(\d{1,2})", re.I)
    if not texto or len(texto) < 4:
        return None
    flat = _leet_normalize(texto).replace(" ", "")
    frases, _total = _build_risco()
    achou = False
    for f in frases:
        if f in flat:
            achou = True
            break
    # idade < 18 (categoria menor_idade)
    m = _AGE_RE.search(texto)
    idade = None
    if m:
        try:
            idade = int(m.group(2))
        except Exception:
            idade = None
    if idade is not None and 0 < idade < 18:
        if achou:
            return ("msg", "menor_sexualizado")
        return ("msg", "menor_idade")
    if achou:
        # escolhe categoria baseada nos termos encontrados
        if any(x in flat for x in ["nigger", "nigga", "negroid", "kike", "faggot", "tranny", "retard", "spic", "chink", "gook", "wetback", "beaner", "dyke"]):
            return ("msg", "odio")
        if any(x in flat for x in ["loli", "lolita", "pedo", "pedophile", "pedofilo", "cp"]):
            return ("msg", "lori")
        if any(x in flat for x in ["cocaina", "crack", "heroina", "meta", "mdma", "ecstasy", "maconha"]):
            return ("msg", "drogas")
        if any(x in flat for x in ["vendo", "vendodroga", "golpe", "golpista", "scam", "phishing", "fraude", "nitrogratis", "cartaoroubado", "ccs", "dumps", "carding"]):
            return ("msg", "golpe")
        if any(x in flat for x in ["kys", "semata", "semate", "matate", "morre", "suicida", "suicidio"]):
            return ("msg", "ameaca")
        return ("msg", "assedio")
    return None

_last_auto = {}

async def auto_report(msg):
    """Vigia mensagens de outros e reporta automaticamente conteudo de risco."""
    if not alt_token:
        return
    if msg.guild and msg.guild.id in (1533181118336073958, 1534727445226324130):
        return  # servidores proprios: nao reportar a si mesmos
    if msg.author.id == OWNER_ID:
        return
    det = _detect_risco(msg.content or "")
    if not det:
        return
    tipo, cat = det
    now = time.time()
    chave = "%s:%s" % (msg.author.id, cat)
    if now - _last_auto.get(chave, 0) < 600:
        return  # max 1 report por autor/categoria a cada 10 min
    try:
        # POST em thread separada: nao bloqueia o event loop do bot
        def _p():
            return do_report("message", REPORT_MSG_CATS[cat],
                             message_id=str(msg.id), channel_id=str(msg.channel.id),
                             guild_id=str(msg.guild.id) if msg.guild else None)
        ok, resp = await bot.loop.run_in_executor(None, _p)
        if ok:
            _last_auto[chave] = now
            print("[AUTOREPORT] %s -> %s (%s) msg %s" % (msg.author, cat, resp, msg.id), flush=True)
    except Exception:
        pass

@bot.command(name="pg", aliases=["ghostping"])
async def pg(ctx):
    """Ghost ping: menciona e apaga a própria mensagem."""
    if not await check_perms(ctx):
        return
    msg = await ctx.send("@everyone")
    await asyncio.sleep(0.4)
    try:
        await msg.delete()
    except Exception:
        pass

@bot.command(name="pguser", aliases=["ghostpinguser"])
async def pguser(ctx, alvo: discord.User):
    """Ghost ping num usuário específico."""
    if not await check_perms(ctx):
        return
    msg = await ctx.send(alvo.mention)
    await asyncio.sleep(0.4)
    try:
        await msg.delete()
    except Exception:
        pass

@bot.command(name="dm", aliases=["dmspam"])
async def dm(ctx, alvo: discord.User, vezes: int = 10):
    """Spam na DM de alguém. Uso: .dm <id|@> <vezes>"""
    if not await check_perms(ctx):
        return
    for _ in range(min(vezes, MAX_MSGS_POR_MINUTO or 30)):
        try:
            await alvo.send(build_payload(1)[0][:500])
        except Exception:
            break
        await asyncio.sleep(human_delay())

@bot.command(name="purge", aliases=["clear"])
async def purge(ctx, n: int = 50):
    """Apaga mensagens PRÓPRIAS no canal. Uso: .purge <n>"""
    if not await check_perms(ctx):
        return
    apagadas = 0
    try:
        async for m in ctx.channel.history(limit=200):
            if apagadas >= n:
                break
            if m.author.id == bot.user.id:
                try:
                    await m.delete()
                    apagadas += 1
                except Exception:
                    continue
                await asyncio.sleep(0.3)
    except Exception as e:
        await ctx.send(f"`{e}`", delete_after=4)
    try:
        await ctx.send(f"`+{apagadas} msgs próprias apagadas`", delete_after=3)
    except Exception:
        pass

@bot.command(name="call", aliases=["blaststart"])
async def call(ctx, segundos: int = 30):
    """Entra na call do seu canal de voz e toca o som estourado.
    Uso: .call <segundos> (0 = infinito até você sair/usar .leave)
    O bot só entra na call que VOCÊ está."""
    global blast_task
    if not await check_perms(ctx):
        return
    if not ctx.author.voice:
        await ctx.send("`você não está numa call`", delete_after=4)
        return
    vc = ctx.author.voice.channel
    try:
        # Se já tiver um voice client ativo, desconecta antes
        for client in bot.voice_clients:
            try:
                await client.disconnect()
            except Exception:
                pass
        vclient = await vc.connect()
    except Exception as e:
        import traceback
        traceback.print_exc()
        await ctx.send(f"`erro ao entrar: {type(e).__name__}: {e}`", delete_after=6)
        return

    som = BlastSource(loop=True, dur=None if segundos == 0 else segundos)

    def _after(err):
        # áudio acabou (dur atingido) ou erro -> desconecta sozinho
        asyncio.create_task(_disconnect_after())

    async def _disconnect_after():
        await asyncio.sleep(0.5)
        try:
            for client in bot.voice_clients:
                client.stop()
                await client.disconnect()
        except Exception:
            pass

    vclient.play(som, after=_after)

    if blast_task and not blast_task.done():
        blast_task.cancel()
    async def vigia():
        # monitora: sai quando o dono sair da call
        # (com dur finito, o after desconecta; vigia só cobre dur=infinito)
        while vclient.is_connected():
            if ctx.author.voice is None or \
               ctx.author.voice.channel.id != vc.id:
                break
            await asyncio.sleep(2)
        try:
            vclient.stop()
            await vclient.disconnect()
        except Exception:
            pass
    if segundos == 0:
        blast_task = asyncio.create_task(vigia())
    try:
        await ctx.send(f"`🔊 estourando na call {vc.name}`", delete_after=3)
    except Exception:
        pass

@bot.command(name="leave", aliases=["blaststop"])
async def leave(ctx):
    """Sai da call e para o som."""
    if not await check_perms(ctx):
        return
    for client in bot.voice_clients:
        try:
            client.stop()
            await client.disconnect()
        except Exception:
            pass
    await ctx.send("`🔇 saiu`", delete_after=3)

# ============================ VOICE / ÁUDIO ============================

class BlastSource(discord.AudioSource):
    """
    Gera o som estourado EM TEMPO REAL (48kHz stereo opus-ready).
    Receita aprovada v2 (mais HIGH PITCH):
    - SUB 55Hz quadrada + 6k/12k/14k/16k quadradas + serrote 7.4k + ruído
    - Fuzz tanh drive 16x + hard clip
    - Bitcrush 4-bit + tremolo 37Hz + estalo metálico 220Hz
    - dur=None => infinito; dur=N => N segundos e desconecta
    """

    def __init__(self, loop: bool = True, dur: float = None):
        self.loop = loop
        self.dur = dur
        self.sr = 48000
        self.pos = 0
        self.max_pos = int(self.sr * dur) if dur else None

    def dist(self, s):
        s = math.tanh(s * 16.0) * 1.15
        return max(-1.0, min(1.0, s))

    @staticmethod
    def bitcrush(s, bits=4):
        q = 2 ** (bits - 1)
        return round(s * q) / q

    def read(self):
        if self.max_pos is not None and self.pos >= self.max_pos:
            return b""  # fim
        frames = bytearray()
        for _ in range(960):  # 20ms @48k
            t = self.pos / self.sr
            if self.dur is None:
                env = 1.0
            else:
                env = 1.0 if t < self.dur - 0.5 else max(0.0, 1.0 - (t - (self.dur - 0.5)) / 0.5)
            sub = 1.0 if math.sin(2 * math.pi * 55 * t) >= 0 else -1.0
            sq6 = 1.0 if math.sin(2 * math.pi * 6000 * t) >= 0 else -1.0
            sq12 = 1.0 if math.sin(2 * math.pi * 12000 * t) >= 0 else -1.0
            sq14 = 1.0 if math.sin(2 * math.pi * 14000 * t) >= 0 else -1.0
            sq16 = 1.0 if math.sin(2 * math.pi * 16000 * t) >= 0 else -1.0
            saw = 2.0 * ((7400 * t) % 1.0) - 1.0
            tick = 1.0 if (t * 220) % 1.0 < 0.12 else 0.0
            trem = 0.7 + 0.3 * math.sin(2 * math.pi * 37 * t)
            mix = sub * 0.9 + sq6 * 0.55 + sq12 * 0.5 + sq14 * 0.42 + \
                  sq16 * 0.38 + saw * 0.65 + random.uniform(-1, 1) * 0.25 + tick * 0.35
            out = self.dist(mix) * trem * env
            out = self.bitcrush(out, 4)
            v = int(max(-1.0, min(1.0, out)) * 32767)
            frames += struct.pack("<hh", v, v)
            self.pos += 1
        return bytes(frames)

# ============================ RPC (Rich Presence) ============================

RPC_TIPOS = {
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "streaming": discord.ActivityType.streaming,
    "competing": discord.ActivityType.competing,
    "custom": discord.ActivityType.custom,
}

def _parse_flags(texto: str):
    """Separa flags --key valor do texto livre (à prova de aspas quebradas).
    Retorna (texto_limpo, dict_flags)."""
    import shlex
    tokens = None
    try:
        tokens = shlex.split(texto)
    except ValueError:
        # fallback manual: quebra por espaço simples, remove aspas soltas
        tokens = texto.replace('"', '').replace("'", "").split()
    limpo = []
    flags = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--") and "=" in t:
            k, v = t[2:].split("=", 1)
            flags[k] = v
        elif t.startswith("--") and i + 1 < len(tokens):
            k = t[2:]
            flags[k] = tokens[i + 1]
            i += 1
        else:
            limpo.append(t)
        i += 1
    return " ".join(limpo), flags

def _mount_activity(tipo: str, nome: str, flags: dict):
    """Monta a Activity com todos os recursos do Rich Presence."""
    # timestamps
    ts = None
    if "elapsed" in flags:
        try:
            secs = int(flags["elapsed"])
            ts = discord.ActivityTimestamps(
                start=datetime.datetime.now(
                    datetime.timezone.utc) - datetime.timedelta(seconds=secs))
        except Exception:
            ts = None
    elif "remaining" in flags:
        try:
            secs = int(flags["remaining"])
            ts = discord.ActivityTimestamps(
                end=datetime.datetime.now(
                    datetime.timezone.utc) + datetime.timedelta(seconds=secs))
        except Exception:
            ts = None
    elif "start" in flags:
        try:
            ts = discord.ActivityTimestamps(start=datetime.datetime.fromtimestamp(int(flags["start"]), datetime.timezone.utc))
        except Exception:
            ts = None
    elif "end" in flags:
        try:
            ts = discord.ActivityTimestamps(end=datetime.datetime.fromtimestamp(int(flags["end"]), datetime.timezone.utc))
        except Exception:
            ts = None

    # assets (foto grande/pequena — precisa de art assets no app)
    assets = None
    if "large" in flags or "small" in flags:
        assets = {}
        if "large" in flags:
            assets["large_image"] = flags["large"]
        if "large_text" in flags:
            assets["large_text"] = flags["large_text"]
        if "small" in flags:
            assets["small_image"] = flags["small"]
        if "small_text" in flags:
            assets["small_text"] = flags["small_text"]

    # party (ex: 2/5)
    party = None
    if "party" in flags and "/" in flags["party"]:
        try:
            cur, ma = flags["party"].split("/")
            party = {"size": [int(cur), int(ma)]}
        except Exception:
            party = None

    # botões (até 2, separar "label|url")
    buttons = []
    for b in ("button1", "button2"):
        if b in flags and "|" in flags[b]:
            lbl, url = flags[b].split("|", 1)
            buttons.append({"label": lbl, "url": url})

    kwargs = dict(
        type=RPC_TIPOS[tipo],
        name=nome,
        state=flags.get("state"),
        details=flags.get("details"),
        url=flags.get("url"),
        timestamps=ts,
        assets=assets,
        party=party,
        buttons=buttons or None,
    )
    if "app" in flags:
        try:
            kwargs["application_id"] = int(flags["app"])
        except Exception:
            pass
    return discord.Activity(**kwargs)

@bot.command(name="rpc")
async def rpc(ctx, tipo: str = None, *, texto: str = None):
    """Define presença completa (RPC via gateway).
    Uso: .rpc playing Nome --details Desc --state Estado --elapsed 3600
         .rpc playing Jogo --large img_key --small img_key2 --party 2/5
         .rpc playing Jogo --button1 "Site|https://x.com" --app 123
         .rpc watching Anime --remaining 600 --url https://...
         .rpc custom Status | .rpc clear | .rpc help (flags)"""
    if not await check_perms(ctx):
        return
    if not RPC_VIA_GATEWAY:
        await ctx.send("`RPC via gateway desligado no config`", delete_after=3)
        return
    if tipo is None or tipo.lower() == "help":
        await ctx.send("```"
                       ".rpc playing <nome> --details <desc> --state <estado>\n"
                       "    --elapsed <seg> | --remaining <seg> | --start <unix> | --end <unix>\n"
                       "    --large <img_key> --large_text <txt> --small <img_key> --small_text <txt>\n"
                       "    --party <atual>/<max> --button1 \"label|url\" --button2 \"label|url\"\n"
                       "    --url <link> --app <application_id> --emoji <emoji>\n"
                       "ex: .rpc playing GTA V --details Modo história --state 50% --elapsed 7200 --large gta --party 2/4```",
                       delete_after=15)
        return
    tipo = tipo.lower()
    if tipo == "clear":
        await bot.change_presence(activity=None, status=discord.Status.online)
        await ctx.send("`presença limpa`", delete_after=3)
        return
    if tipo not in RPC_TIPOS:
        await ctx.send("`tipo inválido`", delete_after=3)
        return
    if not texto:
        await ctx.send("`faltou o texto (use .rpc help pra ver flags)`", delete_after=3)
        return

    if tipo == "custom":
        nome_limpo, flags = _parse_flags(texto)
        act = discord.CustomActivity(
            name=nome_limpo,
            emoji=flags.get("emoji"),
        )
    elif tipo == "streaming":
        nome_limpo, flags = _parse_flags(texto)
        act = discord.Streaming(
            name=nome_limpo,
            url=flags.get("url") or "https://twitch.tv/selfbot",
            details=flags.get("details"),
            state=flags.get("state"),
        )
    else:
        nome_limpo, flags = _parse_flags(texto)
        act = _mount_activity(tipo, nome_limpo, flags)
    try:
        await bot.change_presence(activity=act, status=discord.Status.online)
        resumo = f"presença: {tipo} '{nome_limpo}'"
        if flags.get("details"):
            resumo += f" | details: {flags['details']}"
        if flags.get("state"):
            resumo += f" | state: {flags['state']}"
        if "elapsed" in flags:
            resumo += f" | elapsed: {flags['elapsed']}s"
        if "remaining" in flags:
            resumo += f" | remaining: {flags['remaining']}s"
        if "large" in flags:
            resumo += f" | img: {flags['large']}"
        if "party" in flags:
            resumo += f" | party: {flags['party']}"
        await ctx.send(f"`{resumo}`", delete_after=4)
        if tipo not in ("custom", "streaming") and "app" not in flags:
            await ctx.send(
                "`⚠ rich presence de conta de usuário só renderiza com --app <id> "
                "(cria app em discord.com/developers e usa o Application ID)`",
                delete_after=8)
    except Exception as e:
        await ctx.send(f"`erro rpc: {e}`", delete_after=4)

# ============================ STATUS / PERFIL ============================

STATUS_MAP = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "invisible": discord.Status.invisible,
    "offline": discord.Status.offline,
}

@bot.command(name="status", aliases=["st"])
async def setstatus(ctx, qual: str = None):
    """Muda teu status: .status online|idle|dnd|invisible"""
    if not await check_perms(ctx):
        return
    if qual not in STATUS_MAP:
        await ctx.send("`uso: .status online|idle|dnd|invisible`", delete_after=3)
        return
    await bot.change_presence(status=STATUS_MAP[qual])
    await ctx.send(f"`status: {qual}`", delete_after=3)

@bot.command(name="nick", aliases=["nickname"])
async def nick(ctx, *, nome: str = None):
    """Muda teu apelido no servidor atual: .nick <nome>"""
    if not await check_perms(ctx):
        return
    if ctx.guild is None:
        await ctx.send("`use num servidor`", delete_after=3)
        return
    try:
        await ctx.author.edit(nick=nome)
        await ctx.send(f"`nick: {nome or 'resetado'}`", delete_after=3)
    except Exception as e:
        await ctx.send(f"`erro: {e}`", delete_after=3)

@bot.command(name="pfp", aliases=["avatar"])
async def pfp(ctx, url: str = None):
    """Troca foto de perfil: .pfp <url_da_imagem>"""
    if not await check_perms(ctx):
        return
    if not url:
        await ctx.send("`uso: .pfp <url>`", delete_after=3)
        return
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            img = r.read()
        await bot.user.edit(avatar=img)
        await ctx.send("`avatar atualizado`", delete_after=3)
    except Exception as e:
        await ctx.send(f"`erro pfp: {e}`", delete_after=3)

@bot.command(name="bio", aliases=["about"])
async def bio(ctx, *, texto: str = None):
    """Muda tua bio (sobre mim): .bio <texto>"""
    if not await check_perms(ctx):
        return
    try:
        await bot.user.edit(bio=texto)
        await ctx.send(f"`bio: {texto or 'limpa'}`", delete_after=3)
    except Exception as e:
        await ctx.send(f"`erro bio: {e}`", delete_after=3)

@bot.command(name="typing", aliases=["digitando"])
async def typing(ctx, segundos: int = 5):
    """Fica 'digitando...' por N segundos: .typing 10"""
    if not await check_perms(ctx):
        return
    ch = ctx.channel
    try:
        async with ch.typing():
            await asyncio.sleep(min(segundos, 60))
    except Exception:
        await asyncio.sleep(min(segundos, 60))
    await ctx.send(f"`typing {segundos}s`", delete_after=3)

@bot.command(name="react", aliases=["reagir"])
async def react(ctx, msg_id: int, emoji: str):
    """Reage numa mensagem do canal atual: .react <id_msg> <emoji>"""
    if not await check_perms(ctx):
        return
    try:
        msg = await ctx.channel.fetch_message(msg_id)
        await msg.add_reaction(emoji)
        await ctx.send(f"`reagiu {emoji} em {msg_id}`", delete_after=3)
    except Exception as e:
        await ctx.send(f"`erro react: {e}`", delete_after=3)

# ============================ WHITELIST ============================

@bot.command(name="wl", aliases=["whitelist"])
async def wl(ctx, acao: str = None, alvo: int = None):
    """Gerencia quem pode usar o bot.
    Uso: .wl add <id> | .wl remove <id> | .wl list"""
    if not await check_perms(ctx):
        return
    if acao is None:
        await ctx.send("`uso: .wl add <id> | .wl remove <id> | .wl list`", delete_after=5)
        return
    acao = acao.lower()
    if acao == "list":
        await ctx.send(f"`whitelist: {sorted(whitelist)}`", delete_after=5)
    elif acao in ("add", "remove") and alvo:
        if acao == "add":
            whitelist.add(alvo)
        else:
            whitelist.discard(alvo)
        save_whitelist()
        await ctx.send(f"`{acao} {alvo} -> {sorted(whitelist)}`", delete_after=5)
    else:
        await ctx.send("`uso: .wl add <id> | .wl remove <id> | .wl list`", delete_after=5)

@bot.command(name="ping")
async def ping(ctx):
    if not await check_perms(ctx):
        return
    await ctx.send(f"`pong | {(bot.latency*1000):.0f}ms`", delete_after=3)

@bot.command(name="help", aliases=["cmds"])
async def helpcmd(ctx):
    if not await check_perms(ctx):
        return
    cmds = [
        ".help — mostra esta lista",
        ".spam <n> — flood payload max (zalgo+@everyone/@here)",
        ".spamc [n] <texto> [--r] — flood personalizado (--r = rapido)",
        ".pg / .pguser <user> — ghost ping",
        ".dm <user> <n> — flood na DM de alguém",
        ".purge <n> — apaga suas mensagens no canal",
        ".call <seg|0> — entra na call e toca som estourado",
        ".leave — sai da call e para o som",
        ".jvc [voice_id] — entra numa call (a tua ou por id)",
        ".sair — sai da call",
        ".report cats [msg|user|server] — lista categorias",
        ".report msg <cat> <msg_id> — reporta mensagem",
        ".report user <cat> <id> — reporta usuário",
        ".report server <cat> <id> — reporta servidor",
        ".altset <token> — define token da alt",
        ".alt <cmd...> — usa a alt (ver .help alt)",
        ".altjoin <invite> [cargo_id] — entra com a alt",
        ".altrole <cargo_id> [guild_id] — da cargo na alt",
        ".altroles [guild_id] — lista cargos",
        ".altnick <nick> — muda nick da alt",
        ".rpc <tipo> <texto> — presença completa (use .rpc help)",
        ".rpc custom <texto> / .rpc clear",
        ".status online|idle|dnd|invisible — muda teu status",
        ".device <pc|mac|linux|android|iphone|ipad|web|vr|xbox|play> — forja a plataforma",
        ".nick <nome> — muda apelido no servidor",
        ".pfp <url> — troca foto de perfil",
        ".bio <texto> — muda a bio",
        ".typing <seg> — fica 'digitando...' por N segundos",
        ".react <id_msg> <emoji> — reage numa mensagem",
        ".wl add|remove|list — whitelist de usuários",
        ".ping — latência",
    ]
    await ctx.send("```" + "\n".join(cmds) + "```")

# ============================ MAIN ============================

if __name__ == "__main__":
    if not os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write("")
    token = load_token()
    if not token:
        print(f"[!] Token ausente: defina env DISCORD_TOKEN ou crie {TOKEN_FILE}.")
        sys.exit(1)
    print("[*] iniciando selfbot...")
    bot.run(token)