"""Novidades do add-on, exibidas uma vez a cada atualização.

A versão mais recente fica no topo. O número de cada seção precisa bater com a
versão do manifest.ini; se não bater, a janela usa a seção mais recente.
"""

CHANGELOG = (
    (
        "1.0.0",
        (
            "Vento com velocidade e direção (rosa dos ventos de 8 pontos).",
            "Rajadas de vento, nebulosidade, visibilidade e pressão atmosférica.",
            "Índice UV atual e máximo do dia, com classificação falada.",
            "Qualidade do ar (AQI e PM2.5), vinda de um segundo serviço da Open-Meteo.",
            "Chuva contínua, pancadas e horas de chuva no dia.",
            "Nascer e pôr do sol, nascer e pôr da lua e fase da lua, em itens separados.",
            "Horas de sol, duração do dia e sensação máxima e mínima.",
            "F2 nas listas de campos lê o valor do campo para o local selecionado.",
        ),
    ),
    (
        "0.1.0",
        (
            "Primeira versão: clima atual, próximas 24 horas e próximos dias.",
            "Locais salvos, busca por nome, anúncios automáticos e beeps.",
        ),
    ),
)


def version_key(version) -> tuple:
    """Converte "1.0.0" em (1,), ignorando zeros à direita, para comparar versões."""
    parts = []
    for piece in str(version or "").split("."):
        digits = "".join(char for char in piece if char.isdigit())
        parts.append(int(digits) if digits else 0)
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts) or (0,)


def _entry_for(version, allow_fallback=True) -> list:
    key = version_key(version)
    for entry_version, bullets in CHANGELOG:
        if version_key(entry_version) == key:
            return [(entry_version, bullets)]
    if allow_fallback and CHANGELOG:
        return [CHANGELOG[0]]
    return []


def current_news(version) -> list:
    """Seção da versão atual (ou a mais recente, se ela não estiver listada)."""
    return _entry_for(version)


def news_since(seen_version) -> list:
    """Todas as versões mais novas do que a já vista, da mais nova à mais antiga."""
    seen = version_key(seen_version)
    return [
        (entry_version, bullets)
        for entry_version, bullets in CHANGELOG
        if version_key(entry_version) > seen
    ]


def news_for(seen_version, version, first_install=False) -> list:
    """Novidades a mostrar: bem-vindas na instalação, histórico nas atualizações."""
    if first_install or not str(seen_version or "").strip():
        return current_news(version)
    entries = news_since(seen_version)
    return entries or current_news(version)
