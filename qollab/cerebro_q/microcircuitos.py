"""Microcircuitos del reflejo de toque suave (Chalfie et al., 1985).

Iluminar con luz azul los receptores de toque que expresan channelrhodopsina-2
provoca la respuesta de escape del gusano (Nagel et al., 2005).
"""

MICROCIRCUITOS = {
    "toque-6": {
        "nombre": "Gentle touch · 6 neurons",
        "neuronas": ["AVM", "ALML", "AVDL", "AVAL", "PVCL", "PLML"],
        "fuente": "AVM",
        "descripcion": "Touch receptors AVM, ALM and PLM with the command interneurons AVD, AVA and PVC (left side). "
                       "6 qubits and 8 connections: the recommended circuit for IonQ.",
        "hardware": True,
    },
    "toque-7": {
        "nombre": "Gentle touch · 7 neurons (with AVB)",
        "neuronas": ["AVM", "ALML", "AVDL", "AVAL", "PVCL", "AVBL", "PLML"],
        "fuente": "AVM",
        "descripcion": "Adds AVB, the forward-motion interneuron: backward and forward compete.",
        "hardware": True,
    },
    "toque-bilateral-10": {
        "nombre": "Bilateral touch · 10 neurons",
        "neuronas": ["ALML", "AVM", "AVDL", "AVDR", "AVAL", "AVAR", "PVCL", "PVCR", "PLML", "PLMR"],
        "fuente": "AVM",
        "descripcion": "Both sides of the body (25 connections). On hardware, Givens mode is the better choice.",
        "hardware": False,
    },
}
