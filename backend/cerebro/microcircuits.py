"""Microcircuitos predefinidos para correr en hardware IonQ.

Todos derivan del circuito de respuesta al toque suave (Chalfie et al., 1985):
    receptores de toque  ALM, AVM (anteriores) · PLM (posterior)
    interneuronas        AVD, AVA (retroceso) · PVC, AVB (avance)
En C. elegans, iluminar con luz azul los receptores de toque que expresan
channelrhodopsina-2 provoca la respuesta de escape (Nagel et al., 2005): es el
experimento optogenético clásico que este proyecto reinterpreta.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Microcircuit:
    id: str
    name: str
    neurons: tuple[str, ...]
    default_source: str
    description: str
    hardware_ready: bool  # cabe con margen en IonQ Forte (≤ ~60 ZZ con Trotter de 2º orden)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["neurons"] = list(self.neurons)
        return d


MICROCIRCUITS: dict[str, Microcircuit] = {
    m.id: m
    for m in [
        Microcircuit(
            id="toque-6",
            name="Toque suave · 6 neuronas",
            neurons=("AVM", "ALML", "AVDL", "AVAL", "PVCL", "PLML"),
            default_source="AVM",
            description="Receptores AVM/ALM/PLM y las interneuronas de mando AVD, AVA y PVC del lado izquierdo. "
            "Es el circuito por defecto para hardware: 6 qubits y 8 conexiones.",
            hardware_ready=True,
        ),
        Microcircuit(
            id="toque-7",
            name="Toque suave · 7 neuronas (con AVB)",
            neurons=("AVM", "ALML", "AVDL", "AVAL", "PVCL", "AVBL", "PLML"),
            default_source="AVM",
            description="Agrega AVB, la interneurona de avance: permite ver la competencia retroceso/avance.",
            hardware_ready=True,
        ),
        Microcircuit(
            id="toque-bilateral-10",
            name="Toque suave bilateral · 10 neuronas",
            neurons=("ALML", "AVM", "AVDL", "AVDR", "AVAL", "AVAR", "PVCL", "PVCR", "PLML", "PLMR"),
            default_source="AVM",
            description="Ambos lados del cuerpo (25 conexiones). Cabe en Forte, pero el modo Trotter es profundo: "
            "se recomienda el modo compilado (Givens) en hardware.",
            hardware_ready=False,
        ),
        Microcircuit(
            id="toque-14",
            name="Circuito de toque completo · 14 neuronas",
            neurons=("ALML", "ALMR", "AVM", "PLML", "PLMR", "PVM", "AVDL", "AVDR", "AVAL", "AVAR",
                     "PVCL", "PVCR", "AVBL", "AVBR"),
            default_source="AVM",
            description="Las 6 neuronas receptoras y las 8 interneuronas de mando (44 conexiones). Para simulación.",
            hardware_ready=False,
        ),
    ]
}
