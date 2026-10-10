# Optogenetic Quantum Brain

**A quantum laser on the real *C. elegans* connectome: a 302-neuron quantum walk, and a spike cascade in which every jump is a 10-qubit Qiskit circuit.**

This effort is supported by Qollab & IonQ.

- **Demo video (2–3 min):** [add the public link]
- **Repository (MIT):** https://github.com/JoaquinQu/Cerebro-Cu-ntico-Optogenetico

---

## What it does

In optogenetics, a pulse of light makes a chosen neuron fire, and researchers watch the activity travel through the brain. This project translates that experiment into qubits:

| Optogenetics | This project |
| --- | --- |
| Neuron at rest / active | Qubit in \|0⟩ / \|1⟩ |
| Light pulse with dose θ | RX(θ) rotation on the illuminated neuron |
| Activity travels along synapses | Quantum walk under the XY Hamiltonian on the real connectome |
| Calcium imaging | Z-basis measurement: 1 = *spike* |

The page is organised in three chapters, one idea at a time, with a live "What you're seeing" narration over the 3D worm, "?" help next to every technical term, and the advanced settings tucked into a **Lab settings** drawer:

1. **Light (laser and exact theory).** Pick any of the 302 neurons and the 3D worm shows how the excitation spreads. With a single laser, the 302-qubit XY model reduces *exactly* to a quantum walk with 302 amplitudes, so this part is computed exactly with NumPy and serves as the reference.
2. **Measure (quantum spike cascade with Qiskit).** Each step is a 10-qubit circuit: the neuron that fired and its 9 neighbours with the most synapses. The XY evolution is built with `PauliEvolutionGate` + `SuzukiTrotter` and runs on the selected backend (**one job per step**). The neuron that comes out as 1 in a random shot triggers the next step; the spike jumps across the worm and leaves a trail. Each measurement is animated in 3D: the window neurons pulse together in superposition, then collapse onto the neuron that came out as 1, while a small circuit diagram shows that step's gates and measured bits.
3. **Inside the circuit (touch-reflex microcircuit with Qiskit).** A 6- to 10-qubit circuit (RX + RXX·RYY, via Trotter or Givens), compared with the exact theory, with an IonQ Forte-like noise model and with what the backend measures, using symmetry post-selection.

Every circuit can be shown drawn with `QuantumCircuit.draw("mpl")`, together with its count histogram.

## What problem it explores

Hamiltonian simulation is one of the most natural applications of a quantum computer, but it is hard to *see*. Here you can see it:

- the laser is a rotation, every synapse is an XY coupling, and propagation is interference;
- parts of the worm stay dark because paths cancel each other out;
- the **"What changes when you measure?"** section compares the coherent walk, the walk measured every τ, the 10-qubit cascade, and a classical random walk. It shows that measuring destroys interference and that measuring too often freezes propagation (the **quantum Zeno effect**).

It also shows the real steps needed to take the physics to hardware: Trotterization and its error, transpilation to the backend, and error mitigation through conservation of the excitation number.

## How to run it

1. Press **Run** and pick a backend. With the **Built-in simulator** everything is immediate and free.
2. **Chapter 1 · Light:** pick a neuron (or click one on the worm) and press **Fire laser**. Move θ to see how the light dose scales the response.
3. **Chapter 2 · Measure:** press **Start cascade** and watch each measurement collapse the wave. Try τ = 8 (the excitation moves) and τ = 2 (it barely moves: Zeno effect; τ is in the chapter, steps and shots in Lab settings). Then open **"What changes when you measure?"** and press **Compute comparison**. **Show the cascade circuits** draws each step with Qiskit.
4. **Chapter 3 · Inside the circuit:** pick the microcircuit, the mode and the time t, and press **Run circuit**: one job with 4 times, compared with theory (raw and post-selected TVD).
5. **IonQ:** on *IonQ Forte 1 (Remote simulator)*, which is free, each Run allows one job. The page respects this: the cascade runs one step and then locks the button. For another job, press Stop and Run.

The page is keyboard accessible (chapter tabs with the arrow keys; with focus on the worm: Space, ←/→, R; Esc closes help and settings), announces results to screen readers, has a data table behind every chart, and respects *prefers-reduced-motion*.

## How it works (theory summary)

- **Connectome → matrix J.** The chemical and electrical synapses from Cook et al. (2019) are symmetrized with binary weights (connected or not) and normalized by the largest eigenvalue, so that ‖J‖ = 1.
- **XY Hamiltonian.** H = γ Σ J_ij (X_i X_j + Y_i Y_j)/2 conserves the number of excitations. In the single-excitation sector it is exactly γJ: the continuous-time quantum walk of Farhi and Gutmann.
- **Central result.** For a laser θ on neuron j: P_k(t) = sin²(θ/2) · |[e^(−iγJt)]_kj|².
- **Circuit.** Each hop e^(−iα(XX+YY)/2) = RXX(α)·RYY(α). The walk is approximated with second-order Trotter–Suzuki (error O(t³/r²)).
- **Mitigation.** With one laser, no ideal measurement has more than one neuron at 1: those shots are discarded (symmetry post-selection).

With a single laser the problem is classically simulable: the hardware does not speed it up; it demonstrates the physics and measures how much noise and approximation degrade it. The classically hard regime appears with several simultaneous lasers (hard-core bosons), and the Trotter circuit already supports it.

## How to replicate and extend it

All the code is in this project and in the repository. `qollab/tests` contains 24 automated tests that check, among other things:

- single-excitation XY = walk;
- Trotter convergence and Givens exactness;
- `PauliEvolutionGate` against the theory;
- post-selection, one job per run, and the Qiskit figures.

The harness `qollab/dev/servidor.py` reproduces the Qollab environment on a local computer. The full theory is in `docs/TEORIA.md` and `docs/teoria_tex/` (in Spanish).

Ideas to extend it: several simultaneous lasers, directed synapses (chiral or stochastic quantum walks), inhibitory synapses with negative sign, other connectomes (*Drosophila*), or measuring in the X basis to reveal coherence.

## Prior work and credits

[To complete with the team: what existed before the hackathon build window and what was added during it. The rules require this on the project page.]

- **Data:** connectome from Cook et al., *Nature* 571, 63 (2019), via OpenWorm c302. Neuron positions: OpenWorm CElegansNeuroML. Touch reflex: Chalfie et al. (1985). Optogenetics in *C. elegans*: Nagel et al. (2005).
- **Libraries:** Qiskit, NumPy, SciPy, matplotlib and three.js.

**Themes:** Quantum Unlocked · Quantum Playground. **License:** MIT.

This effort is supported by Qollab & IonQ.
