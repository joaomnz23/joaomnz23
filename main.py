import glob
import os
import re
import shutil
import sys
from datetime import datetime

# Nome que aparece no prompt (padrão da lib é "x0rzavi").
# Precisa ser definido ANTES do "import gifos".
USER = "joaomnz23"
os.environ["GIFOS_GENERAL_USER_NAME"] = USER


def carregar_env():
    """Lê o GITHUB_TOKEN do arquivo .env (ou .env.txt) que está ao lado do main.py."""
    pasta = os.path.dirname(os.path.abspath(__file__))
    for nome in (".env", ".env.txt"):
        caminho = os.path.join(pasta, nome)
        if not os.path.isfile(caminho):
            continue
        with open(caminho, encoding="utf-8-sig") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, valor = linha.split("=", 1)
                os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))
        print(f"INFO: variáveis lidas de {nome}")
        return
    print("AVISO: arquivo .env não encontrado ao lado do main.py")


carregar_env()

import gifos
from PIL import Image, ImageChops, ImageDraw, ImageSequence

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DO MASCOTE
# O gifos só desenha o texto e deixa um bloco reservado à esquerda. Depois, o
# script cola o GIF do mascote (em tamanho real, nítido) por cima desse bloco.
# ---------------------------------------------------------------------------
SPRITE_ARQUIVO = "axew.gif"  # GIF do mascote (na mesma pasta do main.py)
SPRITE_COLS = 38             # largura da área do mascote (cada coluna = 8 px)
SPRITE_ROWS = 20             # altura da área do mascote (cada linha = 18 px)
PRETO_E_BRANCO = True        # True = mascote em quadradinhos cinza (estilo do x0rzavi)
QUADRADO = 10                # tamanho de cada quadradinho em pixels (o dele é 10)
# Cores dos quadradinhos (as mesmas do gatinho do x0rzavi) e cortes de brilho (0 a 1):
# abaixo do 1º corte = sem quadradinho (olho/contorno), depois escuro, médio e claro.
TONS = [(45, 52, 55), (112, 118, 119), (179, 185, 184)]
CORTES = [0.0, 0.30, 0.55]
SPRITE_HOLD = 1              # quantos quadros do GIF final cada pose do mascote dura
FPS = 15                     # mesmo fps da lib (padrão 15)
SEGUNDOS_ANIM = 8            # quanto tempo o final fica parado com o mascote animado

MARCADOR = "\x1b[105m"       # cor do bloco reservado (some depois, é substituído)

# Cores ANSI
C = "\x1b[96m"      # ciano (rótulos)
Y = "\x1b[93m"      # amarelo (valores)
H = "\x1b[30;101m"  # destaque vermelho (títulos)
X = "\x1b[0m"


def montar_stats():
    """Busca stats reais no GitHub (precisa de GITHUB_TOKEN). Se falhar, usa reserva."""
    try:
        s = gifos.utils.fetch_github_stats(USER)
        langs = ", ".join(l[0] for l in s.languages_sorted[:4])
        ano = datetime.now().year - 1
        return [
            f"{C}User Rating: {Y}{s.user_rank.level}{X}",
            f"{C}Total Stars Earned: {Y}{s.total_stargazers}{X}",
            f"{C}Total Commits ({ano}): {Y}{s.total_commits_last_year}{X}",
            f"{C}Total PRs: {Y}{s.total_pull_requests_made}{X}",
            f"{C}Total Contributions: {Y}{s.total_repo_contributions}{X}",
            f"{C}Top Languages: {Y}{langs}{X}",
        ]
    except (Exception, SystemExit) as erro:  # sem token, sem internet, etc.
        print(f"AVISO: não consegui buscar os stats do GitHub ({erro}).")
        print("       Usando valores fixos. Veja a explicação do GITHUB_TOKEN.")
        return [
            f"{C}Public Repos: {Y}5{X}",
            f"{C}Followers: {Y}11{X}",
            f"{C}Top Languages: {Y}PHP, HTML, Java{X}",
        ]


def montar_resumo():
    return [
        f"{H}{USER}@GitHub{X}",
        "--------------",
        f"{C}Host:     {Y}SENAI{X}",
        f"{C}Kernel:   {Y}Systems Development (Technical Course){X}",
        f"{C}Focus:    {Y}Logic & Robotics{X}",
        f"{C}Location: {Y}São Paulo, Brazil{X}",
        f"{C}Langs:    {Y}C++, Java, Python, PHP, JS{X}",
        "",
        f"{H}Contact:{X}",
        "--------------",
        f"{C}Email:     {Y}jmunizsilvestre@gmail.com{X}",
        f"{C}LinkedIn:  {Y}joaopedromunizsilvestre{X}",
        f"{C}Instagram: {Y}joao.mnz_{X}",
        "",
        f"{H}GitHub Stats:{X}",
        "--------------",
    ] + montar_stats()


# ---------------------------------------------------------------------------
# PÓS-PROCESSAMENTO: cola o mascote por cima do bloco reservado
# ---------------------------------------------------------------------------
NEAREST = getattr(Image, "Resampling", Image).NEAREST
BOX = getattr(Image, "Resampling", Image).BOX
ADAPTIVE = getattr(Image, "Palette", Image).ADAPTIVE
SEM_TRAMADO = getattr(Image, "Dither", Image).NONE


def carregar_sprite(caminho):
    img = Image.open(caminho)
    quadros = [f.convert("RGBA") for f in ImageSequence.Iterator(img)]
    caixa = None  # recorta todos os quadros pela mesma caixa (tira a borda vazia)
    for q in quadros:
        b = q.getchannel("A").point(lambda a: 255 if a > 127 else 0).getbbox()
        if b is not None:
            caixa = b if caixa is None else (
                min(caixa[0], b[0]), min(caixa[1], b[1]),
                max(caixa[2], b[2]), max(caixa[3], b[3]),
            )
    if caixa:
        quadros = [q.crop(caixa) for q in quadros]
    if PRETO_E_BRANCO:
        quadros = para_blocos_pb(quadros)
    return quadros


def para_blocos_pb(quadros):
    """Converte o sprite em uma grade de quadradinhos chapados (QUADRADO x QUADRADO px),
    no mesmo estilo do gatinho do x0rzavi. Fora da silhueta fica transparente."""
    w, h = quadros[0].size
    gmax_w = SPRITE_COLS * 8 // QUADRADO
    gmax_h = SPRITE_ROWS * 18 // QUADRADO
    esc = min(gmax_w / w, gmax_h / h)
    gw, gh = max(1, round(w * esc)), max(1, round(h * esc))

    cinzas = [
        Image.alpha_composite(Image.new("RGBA", q.size, (0, 0, 0, 255)), q)
        .convert("L").resize((gw, gh), BOX)
        for q in quadros
    ]
    alfas = [q.getchannel("A").resize((gw, gh), BOX) for q in quadros]

    # faixa de brilho global (igual para todos os quadros, senão ele piscaria)
    valores = []
    for g, a in zip(cinzas, alfas):
        valores += [v for v, m in zip(g.tobytes(), a.tobytes()) if m > 110]
    valores.sort()
    lo = valores[int(len(valores) * 0.02)]
    hi = valores[int(len(valores) * 0.98)]
    faixa = max(1, hi - lo)

    saida = []
    for g, a in zip(cinzas, alfas):
        img = Image.new("RGBA", (gw * QUADRADO, gh * QUADRADO), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        gb, ab = g.tobytes(), a.tobytes()
        for y in range(gh):
            for x in range(gw):
                i = y * gw + x
                if ab[i] <= 110:
                    continue
                n = (gb[i] - lo) / faixa
                cor = None
                for corte, tom in zip(CORTES, TONS):
                    if n >= corte:
                        cor = tom
                if cor:
                    d.rectangle(
                        [x * QUADRADO, y * QUADRADO,
                         (x + 1) * QUADRADO - 1, (y + 1) * QUADRADO - 1],
                        fill=cor + (255,),
                    )
        saida.append(img)
    return saida


def ajustar_tamanho(quadros, larg, alt):
    """Amplia por múltiplos inteiros (mantém o pixel art nítido) até caber na área."""
    w, h = quadros[0].size
    esc = min(larg // w, alt // h)
    if esc >= 1:
        novo = (w * esc, h * esc)
    else:  # sprite maior que a área: reduz
        f = min(larg / w, alt / h)
        novo = (max(1, int(w * f)), max(1, int(h * f)))
    return [q.resize(novo, NEAREST) for q in quadros]


def caixa_da_cor(img, cor, tol=6):
    mask = None
    for canal, v in zip(img.split(), cor):
        m = canal.point(lambda p, v=v: 255 if abs(p - v) <= tol else 0)
        mask = m if mask is None else ImageChops.multiply(mask, m)
    return mask.getbbox()


def cor_parecida(a, b, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def gerar_gif_bruto(saida="output.gif", fps=FPS):
    """Monta o GIF a partir dos PNGs da pasta ./frames com o Pillow.
    Substitui o t.gen_gif(), que falha no Windows por causa das aspas do FFmpeg."""

    def numero(p):
        achado = re.findall(r"\d+", os.path.basename(p))
        return int(achado[-1]) if achado else 0

    arquivos = sorted(glob.glob(os.path.join("frames", "*.png")), key=numero)
    if not arquivos:
        sys.exit("Não achei nenhum PNG na pasta ./frames")
    print(f"INFO: montando GIF com {len(arquivos)} quadros...")

    def gerar():
        for a in arquivos:
            with Image.open(a) as im:
                yield im.convert("RGB").convert(
                    "P", palette=ADAPTIVE, colors=256, dither=SEM_TRAMADO
                )

    gen = gerar()
    primeiro = next(gen)
    primeiro.save(
        saida, save_all=True, append_images=gen,
        duration=1000 // fps, loop=0, optimize=False,
    )


def compor_sprite(bruto, final):
    sprite = carregar_sprite(SPRITE_ARQUIVO)
    origem = Image.open(bruto)
    total = origem.n_frames

    # Na última imagem o bloco reservado está inteiro: as 2 cores mais comuns
    # são o fundo do terminal e o bloco.
    origem.seek(total - 1)
    ultima = origem.convert("RGB")
    cores = sorted(ultima.getcolors(1 << 24), reverse=True)
    fundo, marcador = cores[0][1], cores[1][1]
    caixa = caixa_da_cor(ultima, marcador)
    if caixa is None or (caixa[2] - caixa[0]) < 20 or (caixa[3] - caixa[1]) < 20:
        raise RuntimeError("não achei o bloco reservado do mascote no GIF")
    larg, alt = caixa[2] - caixa[0], caixa[3] - caixa[1]
    sprite = ajustar_tamanho(sprite, larg, alt)
    centro = ((caixa[0] + caixa[2]) // 2, (caixa[1] + caixa[3]) // 2)

    # Plano: para cada quadro do GIF bruto, quantas cópias gerar. Quadros que têm
    # o mascote e duram muito (tela parada) são "abertos" em quadros curtos, senão
    # o mascote ficaria congelado durante a parte parada.
    plano = []  # (indice, tem_mascote, copias, duracao_de_cada)
    for i in range(total):
        origem.seek(i)
        dur = origem.info.get("duration", 1000 // FPS)
        rgb = origem.convert("RGB")
        # o bloco tem frestas pretas entre as linhas, então testa vários pontos
        # (um pixel só no centro podia cair numa fresta e perder o bloco)
        tem = any(
            cor_parecida(rgb.getpixel((centro[0], y)), marcador)
            for y in range(caixa[1], caixa[3], 3)
        )
        copias = max(1, round(dur * FPS / 1000)) if tem else 1
        plano.append((i, tem, copias, max(10, dur // copias)))
    duracoes = [d for (_, _, c, d) in plano for _ in range(c)]

    def quadros():
        k = 0
        for i, tem, copias, _ in plano:
            origem.seek(i)
            base = origem.convert("RGB")
            for _ in range(copias):
                fr = base.copy()
                if tem:
                    fr.paste(fundo, caixa)  # apaga o bloco reservado
                    sp = sprite[(k // SPRITE_HOLD) % len(sprite)]
                    k += 1
                    x = caixa[0] + (larg - sp.width) // 2
                    y = caixa[1] + (alt - sp.height) // 2
                    fr.paste(sp, (x, y), sp)
                yield fr.convert("P", palette=ADAPTIVE, colors=256, dither=SEM_TRAMADO)

    gen = quadros()
    primeiro = next(gen)
    primeiro.save(
        final, save_all=True, append_images=gen, duration=duracoes, loop=0
    )


def main():
    if not os.path.isfile(SPRITE_ARQUIVO):
        sys.exit(
            f"Não achei {SPRITE_ARQUIVO} nesta pasta. Baixe o GIF do mascote para "
            "cá (ou mude SPRITE_ARQUIVO no topo do main.py)."
        )
    resumo = montar_resumo()

    # Tamanho do terminal: margem + área do mascote + resumo
    colunas = 2 + SPRITE_COLS + 3 + 52
    linhas_necessarias = 2 + max(len(resumo), SPRITE_ROWS) + 4
    shutil.rmtree("frames", ignore_errors=True)  # limpa quadros de execuções antigas
    os.makedirs("frames", exist_ok=True)         # o gifos não recria essa pasta sozinho
    t = gifos.Terminal(
        max(800, colunas * 8 + 40), max(540, linhas_necessarias * 18 + 50), 15, 15
    )

    # ----------------------- BIOS ---------------------------------------
    t.gen_text("", 1, count=10)
    t.toggle_show_cursor(False)
    ano = datetime.now().year
    t.gen_text("GIF_OS Modular BIOS v1.0.11", 1)
    t.gen_text(f"Copyright (C) {ano}, \x1b[31m{USER} Softwares Inc.\x1b[0m", 2)
    t.gen_text("\x1b[94mGitHub Profile ReadMe Terminal, Rev 1011\x1b[0m", 4)
    t.gen_text("Krypton(tm) GIFCPU - 250Hz", 6)
    t.gen_text(
        "Press \x1b[94mDEL\x1b[0m to enter SETUP, \x1b[94mESC\x1b[0m to cancel Memory Test",
        t.num_rows,
    )
    for i in range(0, 65653, 7168):  # 64K de "memória"
        t.delete_row(7)
        if i < 30000:
            t.gen_text(f"Memory Test: {i}", 7, count=2, contin=True)
        else:
            t.gen_text(f"Memory Test: {i}", 7, contin=True)
    t.delete_row(7)
    t.gen_text("Memory Test: 64KB OK", 7, count=10, contin=True)
    t.gen_text("", 11, count=10, contin=True)

    # ----------------------- INICIANDO ----------------------------------
    t.clear_frame()
    t.gen_text("Initiating Boot Sequence ", 1, contin=True)
    t.gen_typing_text(".....", 1, contin=True)
    total = 24
    for i in range(total + 1):
        barra = "#" * i + "-" * (total - i)
        t.delete_row(3)
        t.gen_text(f"[{barra}] {int(i * 100 / total)}%", 3, count=2, contin=True)
    t.delete_row(3)
    t.gen_text("\x1b[92mDone!\x1b[0m", 3, count=10, contin=True)

    # logo com efeito "embaralhar"
    t.clear_frame()
    t.gen_text("\x1b[96m", 1, count=0, contin=True)
    logo = "JOAO OS"
    meio_linha = (t.num_rows + 1) // 2
    meio_col = (t.num_cols - len(logo) + 1) // 2
    efeito = gifos.effects.text_scramble_effect_lines(logo, 3, include_special=False)
    for linha in efeito:
        t.delete_row(meio_linha + 1)
        t.gen_text(linha, meio_linha + 1, meio_col + 1)

    # ----------------------- LOGIN --------------------------------------
    t.clear_frame()
    t.clone_frame(5)
    t.toggle_show_cursor(False)
    t.gen_text("\x1b[93mGIF OS v1.0.11 (tty1)\x1b[0m", 1, count=5)
    t.gen_text("login: ", 3, count=5)
    t.toggle_show_cursor(True)
    t.gen_typing_text(USER, 3, contin=True)
    t.gen_text("", 4, count=5)
    t.toggle_show_cursor(False)
    t.gen_text("password: ", 4, count=5)
    t.toggle_show_cursor(True)
    t.gen_typing_text("*********", 4, contin=True)
    t.toggle_show_cursor(False)
    agora = datetime.now().strftime("%a %b %d %I:%M:%S %p %Y")
    t.gen_text(f"Last login: {agora} on tty1", 6)

    # ----------------------- CLEAR --------------------------------------
    t.gen_prompt(7, count=5)
    prompt_col = t.curr_col
    t.toggle_show_cursor(True)
    t.gen_typing_text("\x1b[91mclea", 7, contin=True)
    t.delete_row(7, prompt_col)  # simula "syntax highlighting"
    t.gen_text("\x1b[92mclear\x1b[0m", 7, count=3, contin=True)

    # ----------------------- COMANDO QUE "RESUME" O README ---------------
    t.clear_frame()
    t.gen_prompt(1)
    prompt_col = t.curr_col
    t.clone_frame(10)
    t.toggle_show_cursor(True)
    t.gen_typing_text("\x1b[91mcat READM", 1, contin=True)
    t.delete_row(1, prompt_col)
    t.gen_text(
        "\x1b[92mcat\x1b[0m README.md | \x1b[92mresumo.sh\x1b[0m", 1, contin=True
    )
    t.gen_typing_text(f" -u {USER}", 1, contin=True)
    t.toggle_show_cursor(False)

    # ----------------------- RESUMO APARECENDO ---------------------------
    primeira = 2
    # 1) bloco reservado do mascote (sem gerar quadros ainda)
    for i in range(SPRITE_ROWS):
        t.gen_text(f"{MARCADOR}{' ' * SPRITE_COLS}{X}", primeira + i, 2, count=0, contin=True)
    # 2) resumo aparecendo linha por linha, ao lado do bloco
    col_texto = 2 + SPRITE_COLS + 3
    for i, linha in enumerate(resumo):
        t.gen_text(linha, primeira + i, col_texto, count=2, contin=True)

    # mensagem final no prompt
    fim = primeira + max(len(resumo), SPRITE_ROWS) + 1
    t.toggle_show_cursor(True)
    t.gen_prompt(fim)
    t.gen_typing_text(
        "\x1b[92m# Thanks for stopping by! :D", fim, contin=True
    )
    t.toggle_show_cursor(False)

    # tela parada no final: o mascote continua animado por cima
    t.clone_frame(SEGUNDOS_ANIM * FPS)

    gerar_gif_bruto()  # gera output.gif (ainda com o bloco reservado no lugar do mascote)

    # ----------------------- COLA O MASCOTE ------------------------------
    if not os.path.isfile("output.gif"):
        sys.exit(
            "\nO gifos não criou o output.gif. Verifique se a pasta "
            "./frames foi gerada com os PNGs."
        )
    os.replace("output.gif", "output_bruto.gif")
    try:
        compor_sprite("output_bruto.gif", "output.gif")
        print("INFO: output.gif gerado com o mascote")
    except Exception as erro:
        os.replace("output_bruto.gif", "output.gif")
        print(f"ERRO ao colar o mascote: {erro}")
        print("      O output.gif foi gerado, mas com o bloco reservado no lugar dele.")


if __name__ == "__main__":
    main()