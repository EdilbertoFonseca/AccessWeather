from __future__ import annotations

import requests

from .version import CHANGELOG_URL


FALLBACK_CHANGELOG = """# AccessWeather - Changelog

## 0.1.0
- Primeira versão do AccessWeather, um aplicativo portátil de clima acessível.
- Estrutura inicial: configurações portáteis, anúncios para leitor de tela,
  changelog e o mesmo sistema de atualizações do AccessPlayer.
- Cliente Open-Meteo: busca de locais, previsão atual, horária e diária,
  unidades configuráveis e condições do tempo em português.
- Locais salvos em `data/locations.json`: ordem, local padrão, apelido,
  favoritos e regras de alerta por local.
- Notificação de clima personalizada por local, em intervalo ajustável (1 a 360
  minutos), com escolha e ordenação dos campos exibidos (Alt+setas) e botão para
  testar a notificação.
"""


def fetch_changelog():
    response = requests.get(CHANGELOG_URL, timeout=10)
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    text = response.text.strip()
    if not text:
        raise ValueError("O changelog remoto está vazio.")
    return text