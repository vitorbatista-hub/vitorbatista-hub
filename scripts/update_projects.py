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
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("GITHUB_USER", "vitorbatista-hub")

# Repositórios que não viram card automático (o AçaíConecta tem card próprio).
IGNORAR = {"vitorbatista-hub", "AcaiConecta"}

RAIZ = Path(__file__).resolve().parent.parent
PASTA_CARDS = RAIZ / "assets" / "projects"
README = RAIZ / "README.md"
INICIO, FIM = "<!-- PROJETOS:START -->", "<!-- PROJETOS:END -->"

QUERY = """
query($login: String!) {
  user(login: $login) {
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


def card_svg(repo, contribuicao=False):
    """Card só com nome e descrição do projeto."""
    titulo = repo["name"]
    descricao = repo["description"] or (
        f"Repositório de {repo['owner']['login']} em que colaborei."
        if contribuicao else "Projeto sem descrição no GitHub."
    )
    linhas = quebrar(descricao)

    y_desc = 92
    altura = y_desc + 24 * (len(linhas) - 1) + 38

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="880" height="{altura}" viewBox="0 0 880 {altura}" '
        f'role="img" aria-label="{escape(titulo)}">',
        "  <!-- Gerado por scripts/update_projects.py — não edite à mão. -->",
        "  <defs>",
        '    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '      <stop offset="0" stop-color="#161b22"/>',
        '      <stop offset="1" stop-color="#1c0f2b"/>',
        "    </linearGradient>",
        "  </defs>",
        "  <style>",
        "    .sans { font-family: 'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif; }",
        "  </style>",
        "",
        f'  <rect x="0.5" y="0.5" width="879" height="{altura - 1}" rx="16" fill="url(#bg)" stroke="#30363d"/>',
        "",
        f'  <text x="40" y="58" class="sans" font-size="26" font-weight="700" fill="#f0e6ff">{escape(titulo)}</text>',
        '  <g class="sans" font-size="16" fill="#b1bac4">',
    ]
    for i, linha in enumerate(linhas):
        partes.append(f'    <text x="40" y="{y_desc + 24 * i}">{escape(linha)}</text>')
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

    proprios = [r for r in dados["repositories"]["nodes"] if r["name"] not in IGNORAR]
    contribuicoes = [r for r in dados["repositoriesContributedTo"]["nodes"] if not r["isPrivate"]]

    PASTA_CARDS.mkdir(parents=True, exist_ok=True)
    gerados, cards = set(), []

    for repo, contribuicao in [(r, False) for r in proprios] + [(r, True) for r in contribuicoes]:
        nome_arquivo = re.sub(r"[^a-z0-9]+", "-", repo["nameWithOwner"].lower()).strip("-") + ".svg"
        (PASTA_CARDS / nome_arquivo).write_text(card_svg(repo, contribuicao), encoding="utf-8")
        gerados.add(nome_arquivo)
        alt = f"{repo['name']} — {repo['description'] or 'projeto no GitHub'}"
        cards.append((repo["url"], nome_arquivo, alt))
        print(f"card: {nome_arquivo}")

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
