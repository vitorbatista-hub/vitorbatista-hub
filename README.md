# Salve este arquivo em: .github/workflows/snake.yml
# (no repositório vitorbatista-hub/vitorbatista-hub)
name: Generate Snake

on:
  schedule:
    - cron: "0 */12 * * *"   # atualiza a cada 12h
  workflow_dispatch:          # permite rodar manualmente
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: Platane/snk@v3
        with:
          github_user_name: ${{ github.repository_owner }}
          outputs: |
            dist/github-snake.svg
            dist/github-snake-dark.svg?palette=github-dark

      - uses: crazy-max/ghaction-github-pages@v4
        with:
          target_branch: output
          build_dir: dist
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
