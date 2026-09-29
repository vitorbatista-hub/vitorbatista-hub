#!/usr/bin/env python3
"""
Gera os cards de projetos (assets/projects/*.svg) e reescreve o trecho do
README entre os marcadores PROJETOS:START e PROJETOS:END.

Cada card mostra nome, descrição, quantidade de commits do usuário e as
tecnologias do repositório: linguagens detectadas pelo GitHub mais frameworks,
bancos e ferramentas encontrados nos arquivos do projeto (package.json,
requirements.txt, pom.xml, Dockerfile, .sql...).

Considera só os repositórios públicos do próprio usuário (sem forks).

Uso: GITHUB_TOKEN=... python3 scripts/update_projects.py
"""

import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("GITHUB_USER", "vitorbatista-hub")

# Repositórios que não viram card (o do próprio perfil).
IGNORAR = {"vitorbatista-hub"}

RAIZ = Path(__file__).resolve().parent.parent
PASTA_CARDS = RAIZ / "assets" / "projects"
README = RAIZ / "README.md"
INICIO, FIM = "<!-- PROJETOS:START -->", "<!-- PROJETOS:END -->"

# Dependência (ou trecho dela) -> (nome exibido, cor da tag).
TECNOLOGIAS = {
    "next": ("Next.js", "#8b949e"),
    "react-native": ("React Native", "#61dafb"),
    "expo": ("Expo", "#8b949e"),
    "react": ("React", "#61dafb"),
    "vue": ("Vue", "#42b883"),
    "@angular/core": ("Angular", "#dd0031"),
    "svelte": ("Svelte", "#ff3e00"),
    "express": ("Express", "#8b949e"),
    "@nestjs/core": ("NestJS", "#e0234e"),
    "tailwindcss": ("Tailwind CSS", "#38bdf8"),
    "shadcn": ("shadcn/ui", "#8b949e"),
    "@supabase/supabase-js": ("Supabase", "#3ecf8e"),
    "firebase": ("Firebase", "#ffca28"),
    "prisma": ("Prisma", "#5a67d8"),
    "mysql2": ("MySQL", "#4479a1"),
    "pg": ("PostgreSQL", "#336791"),
    "mongoose": ("MongoDB", "#47a248"),
    "django": ("Django", "#44b78b"),
    "flask": ("Flask", "#8b949e"),
    "fastapi": ("FastAPI", "#009688"),
    "spring-boot": ("Spring Boot", "#6db33f"),
}
ARQUIVOS_DEPENDENCIAS = ("package.json", "requirements.txt", "pyproject.toml", "pom.xml", "build.gradle")

QUERY = """
query($login: String!) {
  user(login: $login) {
    id
    repositories(first: 100, privacy: PUBLIC, isFork: false, ownerAffiliations: OWNER,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        nameWithOwner
        description
        url
        languages(first: 6, orderBy: {field: SIZE, direction: DESC}) { nodes { name color } }
      }
    }
  }
}
"""

QUERY_COMMITS = """
query($owner: String!, $name: String!, $autor: ID!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit { history(author: {id: $autor}) { totalCount } } } }
  }
}
"""


def token():
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not t:
        sys.exit("Defina GITHUB_TOKEN para acessar a API do GitHub.")
    return t


def graphql(query, **variaveis):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variaveis}).encode(),
        headers={"Authorization": f"bearer {token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        dados = json.load(resp)
    if dados.get("errors"):
        sys.exit(f"Erro da API do GitHub: {dados['errors']}")
    return dados["data"]


def rest(caminho):
    """GET na API REST; devolve None se o recurso não existir (ex.: repositório vazio)."""
    req = urllib.request.Request(
        f"https://api.github.com/{caminho}",
        headers={"Authorization": f"bearer {token()}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as erro:
        if erro.code in (404, 409):
            return None
        raise


def contar_commits(repo, autor_id):
    dono, nome = repo["nameWithOwner"].split("/")
    dados = graphql(QUERY_COMMITS, owner=dono, name=nome, autor=autor_id)
    ref = (dados.get("repository") or {}).get("defaultBranchRef")
    return ref["target"]["history"]["totalCount"] if ref else 0


def ler_arquivo(repo, caminho):
    dados = rest(f"repos/{repo['nameWithOwner']}/contents/{caminho}")
    if not dados or "content" not in dados:
        return ""
    return base64.b64decode(dados["content"]).decode("utf-8", "replace")


def tecnologias(repo):
    """Linguagens do GitHub + frameworks/bancos/ferramentas achados nos arquivos."""
    tags = [(l["name"], l["color"] or "#8b949e") for l in repo["languages"]["nodes"]]

    arvore = rest(f"repos/{repo['nameWithOwner']}/git/trees/HEAD?recursive=1") or {}
    caminhos = [
        i["path"] for i in arvore.get("tree", [])
        if i["type"] == "blob" and "node_modules/" not in i["path"]
    ]
    extras = []

    for caminho in caminhos:
        nome = caminho.rsplit("/", 1)[-1]
        if nome not in ARQUIVOS_DEPENDENCIAS:
            continue
        conteudo = ler_arquivo(repo, caminho)
        if nome == "package.json":
            try:
                pacote = json.loads(conteudo)
            except ValueError:
                continue
            deps = {**pacote.get("dependencies", {}), **pacote.get("devDependencies", {})}
            encontrados = [d for d in TECNOLOGIAS if d in deps]
        else:
            texto = conteudo.lower()
            encontrados = [d for d in TECNOLOGIAS if re.search(rf"(^|[^a-z0-9-]){re.escape(d)}([^a-z0-9-]|$)", texto)]
        extras += [TECNOLOGIAS[d] for d in encontrados]

    if any(re.search(r"(^|/)(Dockerfile|docker-compose\.ya?ml|compose\.ya?ml)$", c) for c in caminhos):
        extras.append(("Docker", "#2496ed"))

    # Scripts .sql: tenta descobrir o banco pelo próprio conteúdo.
    for caminho in [c for c in caminhos if c.endswith(".sql")][:3]:
        texto = ler_arquivo(repo, caminho).lower()
        if "mysql" in texto:
            extras.append(("MySQL", "#4479a1"))
        elif "postgres" in texto:
            extras.append(("PostgreSQL", "#336791"))
        else:
            extras.append(("SQL", "#e38c00"))

    vistos = set()
    unicos = []
    for nome, cor in tags + extras:
        if nome.lower() not in vistos:
            vistos.add(nome.lower())
            unicos.append((nome, cor))
    return unicos


# ---------- desenho do card ----------

def quebrar(texto, limite=96, max_linhas=2):
    linhas, atual = [], ""
    for palavra in texto.split():
        if len(atual) + len(palavra) + 1 > limite:
            linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    if atual:
        linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] = linhas[-1].rstrip(".,; ") + "…"
    return linhas


def clarear(cor, fator=0.55):
    """Mistura a cor com branco, para o texto das tags."""
    cor = cor.lstrip("#")
    r, g, b = (int(cor[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (round(c + (255 - c) * fator) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def card_svg(repo, commits, tags):
    """Card com nome, descrição, quantidade de commits e tecnologias."""
    titulo = repo["name"]
    linhas = quebrar(repo["description"] or "Projeto sem descrição no GitHub.")

    y_desc = 92
    y_info = y_desc + 24 * (len(linhas) - 1) + 34
    y_tags = y_info + 22
    altura = (y_tags + 24 + 22) if tags else (y_info + 30)

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="880" height="{altura}" viewBox="0 0 880 {altura}" '
        f'role="img" aria-label="{escape(titulo)}">',
        "  <!-- Gerado por scripts/update_projects.py — não edite à mão. -->",
        "  <defs>",
        '    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '      <stop offset="0" stop-color="#161b22"/>',
        '      <stop offset="1" stop-color="#1c0f2b"/>',
        "    </linearGradient>",
        '    <linearGradient id="acento" x1="0" y1="0" x2="1" y2="0">',
        '      <stop offset="0" stop-color="#7b3fa0"/>',
        '      <stop offset="1" stop-color="#3ddc97"/>',
        "    </linearGradient>",
        '    <linearGradient id="brilho" x1="0" y1="0" x2="1" y2="0">',
        '      <stop offset="0" stop-color="#ffffff" stop-opacity="0"/>',
        '      <stop offset="0.5" stop-color="#ffffff" stop-opacity="0.06"/>',
        '      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>',
        "    </linearGradient>",
        f'    <clipPath id="forma"><rect width="880" height="{altura}" rx="16"/></clipPath>',
        "  </defs>",
        "  <style>",
        "    .sans { font-family: 'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif; }",
        "    .mono { font-family: Consolas, 'DejaVu Sans Mono', 'SFMono-Regular', Menlo, monospace; }",
        "    .in { opacity: 0; animation: in .6s ease-out forwards; }",
        "    @keyframes in { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: none; } }",
        "    .borda { opacity: .15; animation: respira 6s ease-in-out 1s infinite; }",
        "    @keyframes respira { 0%,100% { opacity: .15; } 50% { opacity: .55; } }",
        "    .brilho { transform: translateX(-320px) skewX(-20deg); animation: varre 1.8s ease-in-out .8s forwards; }",
        "    @keyframes varre { to { transform: translateX(1200px) skewX(-20deg); } }",
        "    .traco { transform-origin: 40px 0; transform: scaleX(0); animation: cresce .8s cubic-bezier(.2,.8,.2,1) .3s forwards; }",
        "    @keyframes cresce { to { transform: scaleX(1); } }",
        "    @media (prefers-reduced-motion: reduce) { * { animation: none !important; opacity: 1 !important; transform: none !important; }"
        " .brilho { display: none; } .borda { opacity: .3 !important; } }",
        "  </style>",
        "",
        f'  <rect x="0.5" y="0.5" width="879" height="{altura - 1}" rx="16" fill="url(#bg)" stroke="#30363d"/>',
        f'  <rect class="borda" x="0.5" y="0.5" width="879" height="{altura - 1}" rx="16" fill="none" stroke="url(#acento)" stroke-width="1.5"/>',
        f'  <g clip-path="url(#forma)"><rect class="brilho" x="0" y="0" width="160" height="{altura}" fill="url(#brilho)"/></g>',
        "",
        f'  <text x="40" y="58" class="sans in" font-size="26" font-weight="700" fill="#f0e6ff" style="animation-delay: .1s">{escape(titulo)}</text>',
        '  <rect class="traco" x="40" y="69" width="36" height="3" rx="1.5" fill="url(#acento)"/>',
        '  <g class="sans in" font-size="16" fill="#b1bac4" style="animation-delay: .25s">',
    ]
    for i, linha in enumerate(linhas):
        partes.append(f'    <text x="40" y="{y_desc + 24 * i}">{escape(linha)}</text>')
    partes.append("  </g>")

    partes.append(
        f'  <text x="40" y="{y_info}" class="mono in" font-size="13" fill="#8b949e" style="animation-delay: .4s">'
        f'{commits} commit{"s" if commits != 1 else ""}</text>'
    )

    if tags:
        partes.append("")
        partes.append("  <!-- tecnologias -->")
        partes.append('  <g class="mono" font-size="12.5">')
        x = 40
        for i, (nome, cor) in enumerate(tags):
            w = round(len(nome) * 7.6 + 20)
            if x + w > 840:
                break
            partes.append(
                f'    <g class="in" style="animation-delay: {0.5 + 0.08 * i:.2f}s">'
                f'<rect x="{x}" y="{y_tags}" width="{w}" height="24" rx="6" fill="{cor}" fill-opacity="0.22"/>'
                f'<text x="{x + w / 2}" y="{y_tags + 16}" text-anchor="middle" fill="{clarear(cor)}">{escape(nome)}</text></g>'
            )
            x += w + 8
        partes.append("  </g>")

    partes.append("</svg>")
    return "\n".join(partes) + "\n"


# ---------- README ----------

def bloco_readme(cards):
    linhas = [INICIO, "<!-- Gerado por scripts/update_projects.py — não edite à mão. -->", ""]
    for url, arquivo, alt in cards:
        linhas += [
            '<p align="center">',
            f'  <a href="{url}"><img src="./assets/projects/{arquivo}" width="88%" alt="{escape(alt, {chr(34): "&quot;"})}" /></a>',
            "</p>",
            "",
        ]
    linhas.append(FIM)
    return "\n".join(linhas)


def main():
    dados = graphql(QUERY, login=USER)["user"]
    autor_id = dados["id"]
    repos = [r for r in dados["repositories"]["nodes"] if r["name"] not in IGNORAR]

    PASTA_CARDS.mkdir(parents=True, exist_ok=True)
    gerados, cards = set(), []

    for repo in repos:
        commits = contar_commits(repo, autor_id)
        tags = tecnologias(repo)
        svg = card_svg(repo, commits, tags)
        # O hash no nome faz o navegador baixar o card de novo quando ele muda.
        base = re.sub(r"[^a-z0-9]+", "-", repo["nameWithOwner"].lower()).strip("-")
        nome_arquivo = f"{base}-{hashlib.sha1(svg.encode()).hexdigest()[:8]}.svg"
        (PASTA_CARDS / nome_arquivo).write_text(svg, encoding="utf-8")
        gerados.add(nome_arquivo)
        alt = f"{repo['name']} — {repo['description'] or 'projeto no GitHub'}"
        cards.append((repo["url"], nome_arquivo, alt))
        print(f"card: {nome_arquivo} ({commits} commits; {', '.join(n for n, _ in tags) or 'sem tecnologias'})")

    # remove cards antigos ou de repositórios que sumiram/ficaram privados
    for antigo in PASTA_CARDS.glob("*.svg"):
        if antigo.name not in gerados:
            antigo.unlink()
            print(f"removido: {antigo.name}")

    texto = README.read_text(encoding="utf-8")
    padrao = re.compile(re.escape(INICIO) + r".*?" + re.escape(FIM), re.S)
    if not padrao.search(texto):
        sys.exit(f"Marcadores {INICIO} / {FIM} não encontrados no README.")
    README.write_text(padrao.sub(lambda _: bloco_readme(cards), texto), encoding="utf-8")


if __name__ == "__main__":
    main()
