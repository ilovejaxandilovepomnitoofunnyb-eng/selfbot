import re

src = open("nuke_bot.py").read()
lines = src.split("\n")

# ---- 1) remove comando /raid inteiro ----
start = end = None
for i, l in enumerate(lines):
    if 'hybrid_command(name="raid"' in l:
        s = i - 1
        while s >= 0 and lines[s].strip().startswith("@"):
            s -= 1
        start = s + 1
    elif start is not None and i > start:
        st = l.strip()
        if (st.startswith("@bot.") or st.startswith("async def m_")) \
           and not st.startswith("@install") and not st.startswith("@ctx"):
            end = i
            break
if end is None:
    end = len(lines)
while end > start and lines[end - 1].strip() == "":
    end -= 1
print(f"/raid: removendo linhas {start+1}..{end}")
del lines[start:end]
src = "\n".join(lines)

# ---- 2) efemero em todo feedback de comando ----
PUBLIC_KEYS = ("poll=", "Raided succesfully", "send(texto)", "send(embed=e)",
               "embeds=[emb", "embeds=[e,", "embeds=[e]", "files=[")
out = src.split("\n")
n = len(out)
res = []
idx = 0
changed = 0
while idx < n:
    line = out[idx]
    res.append(line)
    m = re.search(r"await ctx\.(followup\.)?send\(", line)
    if not m:
        idx += 1
        continue
    # segmento ate fechar o parenteses da chamada send(
    seg = line
    j = idx
    depth = seg.count("(") - seg.count(")")
    while depth > 0 and j + 1 < n:
        j += 1
        seg += "\n" + out[j]
        depth += out[j].count("(") - out[j].count(")")
    if "ephemeral=" in seg or any(k in seg for k in PUBLIC_KEYS):
        idx = j + 1
        continue
    pos = seg.rfind(")")
    novo = seg[:pos] + ", ephemeral=True" + seg[pos:]
    nl = novo.split("\n")
    res = res[:-1] + nl
    changed += 1
    idx = j + 1

open("nuke_bot.py", "w").write("\n".join(res))
print(f"envios tornados efemeros: {changed}")
