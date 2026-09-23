#!/usr/bin/env python3
"""
Gera os cards de projetos (assets/projects/*.svg) e reescreve o trecho do
README entre os marcadores PROJETOS:START e PROJETOS:END.

Busca na API do GitHub:
  - repositórios públicos do usuário (sem forks);
  - repositórios de outras pessoas em que o usuário fez commits ou PRs.

Uso: GITHUB_TOKEN=... python3 scripts/update_projects.py
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("GITHUB_USER", "vitorbatista-hub")

# Repositórios que não viram card automático (o AçaíConecta tem card próprio).
IGNORAR = {"vitorbatista-hub", "AcaiConecta"}

# Dias sem push até o repositório deixar de ser marcado como "ativo".
DIAS_ATIVO = 45

RAIZ = Path(__file__).resolve().parent.parent
PASTA_CARDS = RAIZ / "assets" / "projects"
README = RAIZ / "README.md"
INICIO, FIM = "<!-- PROJETOS:START -->", "<!-- PROJETOS:END -->"

MESES = "jan fev mar abr mai jun jul ago set out nov dez".split()

QUERY = """
query($login: String!) {
  user(login: $login) {
    id
    repositories(first: 100, privacy: PUBLIC, isFork: false, ownerAffiliations: OWNER,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes { ...repo }
    }
    repositoriesContributedTo(first: 50, includeUserRepositories: false,
                              contributionTypes: [COMMIT, PULL_REQUEST],
                              orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes { ...repo }
    }
  }
}
fragment repo on Repository {
  name
  nameWithOwner
  owner { login }
  description
  url
  isPrivate
  isArchived
  pushedAt
  stargazerCount
  repositoryTopics(first: 6) { nodes { topic { name } } }
  languages(first: 4, orderBy: {field: SIZE, direction: DESC}) { nodes { name color } }
}
"""

QUERY_COMMITS = """
query($owner: String!, $name: String!, $autor: ID!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit { history(author: {id: $autor}) { totalCount } } } }
  }
}
"""


def graphql(query, **variaveis):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("Defina GITHUB_TOKEN para acessar a API do GitHub.")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variaveis}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        dados = json.load(resp)
    if dados.get("errors"):
        sys.exit(f"Erro da API do GitHub: {dados['errors']}")
    return dados["data"]


def contar_commits(repo, autor_id):
    dados = graphql(QUERY_COMMITS, owner=repo["owner"]["login"], name=repo["name"], autor=autor_id)
    ref = (dados.get("repository") or {}).get("defaultBranchRef")
    return ref["target"]["history"]["totalCount"] if ref else 0


# ---------- desenho do card ----------

def clarear(cor, fator=0.55):
    """Mistura a cor com branco, para o texto das tags."""
    cor = cor.lstrip("#")
    r, g, b = (int(cor[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (round(c + (255 - c) * fator) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


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


def data_br(iso):
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


def selo(repo, contribuicao):
    """Retorna (texto, cor da borda, cor do texto, pulsa?)."""
    if contribuicao:
        return "contribuição", "#c9a8f5", "#e2d4fa", False
    if repo["isArchived"]:
        return "arquivado", "#8b949e", "#c9d1d9", False
    dias = (datetime.now(timezone.utc) - datetime.fromisoformat(repo["pushedAt"].replace("Z", "+00:00"))).days
    if dias <= DIAS_ATIVO:
        return "ativo", "#3ddc97", "#bff5dc", True
    return "sem commits recentes", "#8b949e", "#c9d1d9", False


def card_svg(repo, contribuicao=False, commits=0):
    titulo = repo["name"]
    descricao = repo["description"] or (
        f"Repositório de {repo['owner']['login']} em que colaborei."
        if contribuicao else "Projeto sem descrição no GitHub."
    )
    linhas = quebrar(descricao)

    texto_selo, cor_selo, cor_texto_selo, pulsa = selo(repo, contribuicao)
    largura_selo = round(len(texto_selo) * 7.4 + (44 if pulsa else 28))
    x_selo = 840 - largura_selo

    # informações em linha, em fonte mono
    info = []
    if contribuicao:
        info.append(f"em {repo['owner']['login']}")
    if commits:
        info.append(f"{commits} commit{'s' if commits != 1 else ''}")
    if repo["stargazerCount"]:
        info.append(f"★ {repo['stargazerCount']}")
    info.append(f"atualizado em {data_br(repo['pushedAt'])}")

    y_desc = 92
    y_info = y_desc + 24 * (len(linhas) - 1) + 34
    y_tags = y_info + 22
    altura = y_tags + 24 + 22

    tags = [(l["name"], l["color"] or "#8b949e") for l in repo["languages"]["nodes"]]
    tags += [(t["topic"]["name"], "#7b3fa0") for t in repo["repositoryTopics"]["nodes"]]
    tags = tags[:7]

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="880" height="{altura}" viewBox="0 0 880 {altura}" '
        f'role="img" aria-label="{escape(titulo)} — {escape(texto_selo)}">',
        "  <!-- Gerado por scripts/update_projects.py — não edite à mão. -->",
        "  <defs>",
        '    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '      <stop offset="0" stop-color="#161b22"/>',
        '      <stop offset="1" stop-color="#1c0f2b"/>',
        "    </linearGradient>",
        "  </defs>",
        "  <style>",
        "    .sans { font-family: 'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif; }",
        "    .mono { font-family: Consolas, 'DejaVu Sans Mono', 'SFMono-Regular', Menlo, monospace; }",
        "    .pulse { animation: pulse 1.8s ease-in-out infinite; transform-box: fill-box; transform-origin: center; }",
        "    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }",
        "    .in { opacity: 0; animation: in .5s ease-out .3s forwards; }",
        "    @keyframes in { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: none; } }",
        "    @media (prefers-reduced-motion: reduce) { * { animation: none !important; opacity: 1 !important; transform: none !important; } }",
        "  </style>",
        "",
        f'  <rect x="0.5" y="0.5" width="879" height="{altura - 1}" rx="16" fill="url(#bg)" stroke="#30363d"/>',
        "",
        "  <!-- cabeçalho -->",
        f'  <text x="40" y="58" class="sans" font-size="26" font-weight="700" fill="#f0e6ff">{escape(titulo)}</text>',
        "  <g>",
        f'    <rect x="{x_selo}" y="36" width="{largura_selo}" height="26" rx="13" fill="{cor_selo}" '
        f'fill-opacity="0.12" stroke="{cor_selo}" stroke-opacity="0.5"/>',
    ]
    if pulsa:
        partes.append(f'    <circle class="pulse" cx="{x_selo + 16}" cy="49" r="4.5" fill="{cor_selo}"/>')
        partes.append(f'    <text x="{x_selo + 28}" y="54" class="sans" font-size="13" font-weight="600" fill="{cor_texto_selo}">{escape(texto_selo)}</text>')
    else:
        partes.append(f'    <text x="{x_selo + largura_selo / 2}" y="54" text-anchor="middle" class="sans" font-size="13" font-weight="600" fill="{cor_texto_selo}">{escape(texto_selo)}</text>')
    partes.append("  </g>")

    partes.append('  <g class="sans" font-size="16" fill="#b1bac4">')
    for i, linha in enumerate(linhas):
        partes.append(f'    <text x="40" y="{y_desc + 24 * i}">{escape(linha)}</text>')
    partes.append("  </g>")

    partes.append(f'  <text x="40" y="{y_info}" class="mono in" font-size="13" fill="#8b949e">{escape("  ·  ".join(info))}</text>')

    if tags:
        partes.append("")
        partes.append("  <!-- tags -->")
        partes.append('  <g class="mono" font-size="12.5">')
        x = 40
        for nome, cor in tags:
            w = round(len(nome) * 7.6 + 20)
            partes.append(
                f'    <rect x="{x}" y="{y_tags}" width="{w}" height="24" rx="6" fill="{cor}" fill-opacity="0.22"/>'
                f'<text x="{x + w / 2}" y="{y_tags + 16}" text-anchor="middle" fill="{clarear(cor)}">{escape(nome)}</text>'
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

    proprios = [r for r in dados["repositories"]["nodes"] if r["name"] not in IGNORAR]
    contribuicoes = [r for r in dados["repositoriesContributedTo"]["nodes"] if not r["isPrivate"]]

    PASTA_CARDS.mkdir(parents=True, exist_ok=True)
    gerados, cards = set(), []

    for repo, contribuicao in [(r, False) for r in proprios] + [(r, True) for r in contribuicoes]:
        commits = contar_commits(repo, autor_id)
        nome_arquivo = re.sub(r"[^a-z0-9]+", "-", repo["nameWithOwner"].lower()).strip("-") + ".svg"
        (PASTA_CARDS / nome_arquivo).write_text(card_svg(repo, contribuicao, commits), encoding="utf-8")
        gerados.add(nome_arquivo)
        alt = f"{repo['name']} — {repo['description'] or 'projeto no GitHub'}"
        cards.append((repo["url"], nome_arquivo, alt))
        print(f"card: {nome_arquivo} ({commits} commits)")

    # remove cards de repositórios que sumiram ou ficaram privados
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
