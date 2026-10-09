"""Microcircuitos del reflejo de toque suave (Chalfie et al., 1985).

Iluminar con luz azul los receptores de toque que expresan channelrhodopsina-2
provoca la respuesta de escape del gusano (Nagel et al., 2005).
"""

MICROCIRCUITOS = {
    "toque-6": {
        "nombre": "Toque suave · 6 neuronas",
        "neuronas": ["AVM", "ALML", "AVDL", "AVAL", "PVCL", "PLML"],
        "fuente": "AVM",
        "descripcion": "Receptores AVM, ALM y PLM con las interneuronas de mando AVD, AVA y PVC (lado izquierdo). "
                       "6 qubits y 8 conexiones: el circuito recomendado para IonQ.",
        "hardware": True,
    },
    "toque-7": {
        "nombre": "Toque suave · 7 neuronas (con AVB)",
        "neuronas": ["AVM", "ALML", "AVDL", "AVAL", "PVCL", "AVBL", "PLML"],
        "fuente": "AVM",
        "descripcion": "Agrega AVB, la interneurona de avance: compiten retroceso y avance.",
        "hardware": True,
    },
    "toque-bilateral-10": {
        "nombre": "Toque bilateral · 10 neuronas",
        "neuronas": ["ALML", "AVM", "AVDL", "AVDR", "AVAL", "AVAR", "PVCL", "PVCR", "PLML", "PLMR"],
        "fuente": "AVM",
        "descripcion": "Ambos lados del cuerpo (25 conexiones). En hardware conviene el modo Givens.",
        "hardware": False,
    },
}
