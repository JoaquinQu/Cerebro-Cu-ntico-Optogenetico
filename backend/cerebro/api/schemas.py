"""Modelos de entrada de la API (validación con pydantic)."""

from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, Field


class WalkRequest(BaseModel):
    source: str = Field("AVM", description="Neurona iluminada por el láser")
    theta: float = Field(math.pi, ge=0, le=2 * math.pi, description="Ángulo de Rabi θ = Ω·τ")
    gamma: float = Field(1.0, gt=0, le=20, description="Escala de acoplamiento γ")
    t_max: float = Field(60.0, gt=0, le=1000)
    frames: int = Field(120, ge=2, le=600)
    weighting: Literal["log", "count", "binary"] = "log"


class MicrocircuitRequest(BaseModel):
    preset: Optional[str] = "toque-6"
    neurons: Optional[list[str]] = None
    sources: Optional[list[str]] = None
    theta: float = Field(math.pi, ge=0, le=2 * math.pi)
    t: float = Field(30.0, ge=0, le=500)
    gamma: float = Field(1.0, gt=0, le=20)
    mode: Literal["trotter", "givens"] = "trotter"
    steps: Optional[int] = Field(None, ge=1, le=20, description="None = elegir automáticamente")
    order: Literal[1, 2] = 2
    shots: int = Field(1000, ge=10, le=100_000)
    noisy: bool = True


class IonQSubmitRequest(MicrocircuitRequest):
    backend: str = Field("simulator", description="simulator | qpu.forte-1 | qpu.forte-enterprise-1")
    noise_model: Optional[str] = Field("forte-1", description="Sólo para backend=simulator")
    gateset: Literal["native", "qis"] = "native"
    steps: int = Field(2, ge=1, le=20)
