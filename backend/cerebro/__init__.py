"""Cerebro Cuántico Optogenético — núcleo del backend.

Paquetes:
    connectome      datos reales de C. elegans y construcción del grafo
    hamiltonian     modelo XY / quantum walk de tiempo continuo (solución exacta)
    circuits        IR de circuitos, simulador, constructores y compilación a IonQ
    ionq            cliente REST de IonQ (API v0.4) y flujo de experimentos
    analysis        post-selección por simetría y métricas
    microcircuits   microcircuitos predefinidos (reflejo de toque)
    api             servidor HTTP (Starlette) que usa el frontend

La teoría detrás de cada módulo está en docs/TEORIA.md.
"""

__version__ = "0.1.0"
