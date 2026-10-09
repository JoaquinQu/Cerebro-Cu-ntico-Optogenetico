"""Malla anatómica (estilizada) del cuerpo de C. elegans construida a partir de los datos.

Coordenadas de los datos (µm): x = izquierda–derecha, y = anteroposterior (cabeza < 0),
z = dorsoventral. La postura del gusano viene de las posiciones reales de las neuronas
(OpenWorm), que no está recto: la línea media se ajusta a la nube de somas.

Piezas:
    cuerpo   tubo cerrado con nariz redondeada, cola afinada y anillos de cutícula sutiles
    faringe  tubo interno con procorpus, metacorpus (bulbo medio), istmo y bulbo terminal

La faringe es una aproximación de proporciones (~16 % del largo, bulbos al 45 % y 88 %):
sirve para orientar visualmente la cabeza, no es un dato del conectoma.
"""

from __future__ import annotations

import numpy as np


def _smooth(a: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return a
    k = int(3 * sigma) + 1
    x = np.arange(-k, k + 1)
    w = np.exp(-0.5 * (x / sigma) ** 2)
    w /= w.sum()
    pad = np.pad(a, [(k, k)] + [(0, 0)] * (a.ndim - 1), mode="edge")
    if a.ndim == 1:
        return np.convolve(pad, w, mode="valid")
    return np.stack([np.convolve(pad[:, j], w, mode="valid") for j in range(a.shape[1])], axis=1)


def centerline(pos: np.ndarray, n_rings: int = 220, nose_extra: float = 14.0, tail_extra: float = 40.0):
    """Línea media suavizada a lo largo del eje y, con radios estimados de los datos."""
    y0, y1 = pos[:, 1].min() - nose_extra, pos[:, 1].max() + tail_extra
    ys = np.linspace(y0, y1, n_rings)
    cx, cz, rd = np.zeros(n_rings), np.zeros(n_rings), np.zeros(n_rings)
    for i, y in enumerate(ys):
        w = 30.0
        near = pos[np.abs(pos[:, 1] - y) < w]
        while len(near) < 6 and w < 200:
            w *= 1.5
            near = pos[np.abs(pos[:, 1] - y) < w]
        cx[i], cz[i] = np.median(near[:, 0]), np.median(near[:, 2])
        d = np.hypot(near[:, 0] - cx[i], near[:, 2] - cz[i])
        rd[i] = np.percentile(d, 95) if len(d) else 0.0
    cx, cz = _smooth(cx, 6), _smooth(cz, 6)
    rd = _smooth(rd, 5)
    return ys, np.stack([cx, ys, cz], axis=1), rd


def _profile(s: np.ndarray) -> np.ndarray:
    """Perfil de radio relativo: nariz redondeada (s≈0) y cola en punta (s≈1)."""
    nose = np.sqrt(np.clip(s / 0.06, 0, 1)) * (0.55 + 0.45 * np.clip(s / 0.12, 0, 1))
    tail = np.clip((1 - s) / 0.22, 0, 1) ** 0.9
    return np.minimum(nose, 0.12 + 0.88 * tail) * np.where(s > 0.985, (1 - s) / 0.015, 1.0)


def _frames(C: np.ndarray):
    T = np.gradient(C, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    up = np.array([0.0, 0.0, 1.0])
    N = up - (T @ up)[:, None] * T
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    B = np.cross(T, N)
    return T, N, B


def _tube(C: np.ndarray, R: np.ndarray, seg: int = 48, cap: bool = True):
    T, N, B = _frames(C)
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    ring = C[:, None, :] + R[:, None, None] * (ca[None, :, None] * N[:, None, :] + sa[None, :, None] * B[:, None, :])
    V = ring.reshape(-1, 3)
    m = len(C)
    faces = []
    for i in range(m - 1):
        a = i * seg + np.arange(seg)
        b = i * seg + (np.arange(seg) + 1) % seg
        c = a + seg
        d = b + seg
        faces.append(np.stack([a, c, b], 1))
        faces.append(np.stack([b, c, d], 1))
    F = np.concatenate(faces)
    if cap:
        i0 = len(V)
        V = np.vstack([V, C[0] - T[0] * 0.5, C[-1] + T[-1] * 0.5])
        k = np.arange(seg)
        F = np.vstack([F, np.stack([np.full(seg, i0), k, (k + 1) % seg], 1),
                       np.stack([np.full(seg, i0 + 1), (m - 1) * seg + (k + 1) % seg, (m - 1) * seg + k], 1)])
    return V.astype(np.float32), F.astype(np.uint32)


def vertex_normals(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    n = np.zeros_like(V, dtype=np.float64)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(n, F[:, k], fn)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return n.astype(np.float32)


def build_worm(pos: np.ndarray, seg: int = 48, n_rings: int = 220) -> dict:
    """Devuelve {'cuerpo': (V, F, N), 'faringe': (V, F, N)} en µm (coordenadas de datos)."""
    ys, C, rd = centerline(pos, n_rings)
    L = ys[-1] - ys[0]
    s = (ys - ys[0]) / L
    mid = (s > 0.25) & (s < 0.75)
    Rmax = max(float(np.median(rd[mid])) * 1.15 + 6.0, 18.0)
    R = Rmax * _profile(s)
    R = np.maximum(R, np.minimum(rd * 1.08 + 4.0, Rmax * 1.25) * (_profile(s) > 0.3))  # contener todos los somas
    R = _smooth(R, 2) * (1 + 0.012 * np.cos(2 * np.pi * ys / 8.0))  # anillos de cutícula (estilizados)
    R[0] = R[-1] = 0.0
    Vb, Fb = _tube(C, np.maximum(R, 0.05), seg, cap=False)

    # Faringe: desde la nariz hasta ~16 % del largo
    sp = np.linspace(0.01, 0.165, 90)
    yp = ys[0] + sp * L
    Cp = np.stack([np.interp(yp, ys, C[:, 0]), yp, np.interp(yp, ys, C[:, 2])], axis=1)
    Rloc = np.interp(yp, ys, R)
    u = (sp - sp[0]) / (sp[-1] - sp[0])
    bulb = lambda c, w: np.exp(-0.5 * ((u - c) / w) ** 2)
    rel = 0.17 + 0.20 * bulb(0.45, 0.07) + 0.27 * bulb(0.88, 0.07) - 0.05 * bulb(0.68, 0.08)
    rel *= np.clip(u / 0.04, 0.3, 1) * np.clip((1 - u) / 0.04, 0.2, 1)
    Vp, Fp = _tube(Cp, Rloc * rel + 0.5, 32, cap=True)
    return {
        "cuerpo": (Vb, Fb, vertex_normals(Vb, Fb)),
        "faringe": (Vp, Fp, vertex_normals(Vp, Fp)),
        "info": {"largo_um": float(L), "radio_max_um": float(Rmax)},
    }
