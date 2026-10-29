"""Sequências de beeps e silêncios (modelo puro, sem NVDA nem wx).

Cada passo é um dicionário:

- ``{"type": "beep", "frequency": 800, "duration": 50}``
- ``{"type": "silence", "duration": 100}``

As frequências são em Hz e as durações em milissegundos.
"""

BEEP = "beep"
SILENCE = "silence"

STEP_TYPES = {BEEP: "Beep", SILENCE: "Silêncio"}

FREQUENCY_MIN = 200
FREQUENCY_MAX = 12000
FREQUENCY_DEFAULT = 800

BEEP_DURATION_MIN = 10
BEEP_DURATION_MAX = 5000
BEEP_DURATION_DEFAULT = 50

SILENCE_DURATION_MIN = 10
SILENCE_DURATION_MAX = 10000
SILENCE_DURATION_DEFAULT = 100

DEFAULT_BEEP_SEQUENCE = (
    {"type": BEEP, "frequency": FREQUENCY_DEFAULT, "duration": BEEP_DURATION_DEFAULT},
    {"type": SILENCE, "duration": 60},
    {"type": BEEP, "frequency": FREQUENCY_DEFAULT, "duration": BEEP_DURATION_DEFAULT},
)


def _clamp(value, minimum, maximum, default):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def normalize_step(step):
    """Valida e limita um passo; devolve ``None`` para entrada inválida."""
    if not isinstance(step, dict):
        return None
    kind = str(step.get("type", BEEP)).strip().lower()
    if kind == SILENCE:
        return {
            "type": SILENCE,
            "duration": _clamp(
                step.get("duration"),
                SILENCE_DURATION_MIN,
                SILENCE_DURATION_MAX,
                SILENCE_DURATION_DEFAULT,
            ),
        }
    return {
        "type": BEEP,
        "frequency": _clamp(
            step.get("frequency"),
            FREQUENCY_MIN,
            FREQUENCY_MAX,
            FREQUENCY_DEFAULT,
        ),
        "duration": _clamp(
            step.get("duration"),
            BEEP_DURATION_MIN,
            BEEP_DURATION_MAX,
            BEEP_DURATION_DEFAULT,
        ),
    }


def normalize_sequence(sequence):
    if not isinstance(sequence, (list, tuple)):
        return ()
    steps = []
    for step in sequence:
        normalized = normalize_step(step)
        if normalized is not None:
            steps.append(normalized)
    return tuple(steps)


def step_duration(step):
    if not isinstance(step, dict):
        return 0
    try:
        return max(0, int(step.get("duration", 0) or 0))
    except (TypeError, ValueError):
        return 0


def sequence_duration(sequence):
    return sum(step_duration(step) for step in normalize_sequence(sequence))


def step_label(step, index=None):
    normalized = normalize_step(step)
    prefix = f"{index + 1}. " if index is not None else ""
    if normalized is None:
        return prefix + "Passo inválido"
    if normalized["type"] == SILENCE:
        return f"{prefix}Silêncio de {normalized['duration']} ms"
    return (
        f"{prefix}Beep de {normalized['frequency']} Hz "
        f"por {normalized['duration']} ms"
    )


def sequence_summary(sequence):
    steps = normalize_sequence(sequence)
    if not steps:
        return "Nenhum beep configurado"
    beeps = sum(1 for step in steps if step["type"] == BEEP)
    silences = len(steps) - beeps
    parts = []
    if beeps:
        parts.append(f"{beeps} beep" + ("s" if beeps != 1 else ""))
    if silences:
        parts.append(f"{silences} silêncio" + ("s" if silences != 1 else ""))
    return f"{' e '.join(parts)} ({sequence_duration(steps)} ms)"
