import numpy as np
from scipy.io import wavfile

def generar_drone(duracion, sample_rate=44100):
    """Crea un colchón sonoro muy suave y continuo."""
    t = np.linspace(0, duracion, int(sample_rate * duracion), endpoint=False)
    # Acorde ambiental profundo
    onda1 = np.sin(2 * np.pi * 110.0 * t) # Nota A2
    onda2 = np.sin(2 * np.pi * 164.8 * t) # Nota E3
    # LFO (Low Frequency Oscillator) para hacer que el sonido "respire" lentamente
    lfo = 0.5 * (1 + np.sin(2 * np.pi * 0.2 * t)) 
    # Volumen fijado al 5% para que sea puramente ambiental
    return (onda1 + onda2) * lfo * 0.05 

def generar_laser(duracion=0.25, sample_rate=44100):
    """Simula el pulso optogenético (barrido de frecuencia descendente)."""
    t = np.linspace(0, duracion, int(sample_rate * duracion), endpoint=False)
    # Cae rápidamente de 2500 Hz a 100 Hz
    frecuencias = np.geomspace(2500, 100, len(t))
    fase = 2 * np.pi * np.cumsum(frecuencias) / sample_rate
    laser = np.sin(fase)
    
    envolvente = np.exp(-12 * t)
    return laser * envolvente * 0.6 

def generar_difusion_cuantica(duracion=4.0, sample_rate=44100):
    """Crea un sonido complejo de ecos desafinados que se desvanecen."""
    t = np.linspace(0, duracion, int(sample_rate * duracion), endpoint=False)
    frec_base = 220.0
    onda = np.zeros_like(t)
    
    # Sumamos 10 osciladores aleatorios para crear el "caos" de interferencia
    for _ in range(10):
        desafine = frec_base + np.random.uniform(-15, 15)
        fase_aleatoria = np.random.uniform(0, 2 * np.pi)
        tremolo = np.sin(2 * np.pi * np.random.uniform(2, 6) * t)
        onda += np.sin(2 * np.pi * desafine * t + fase_aleatoria) * (1 + 0.3 * tremolo)
        
    # Envolvente: Entra lentamente (ataque) y se difumina de a poco (decaimiento)
    ataque = np.clip(t / 0.5, 0, 1)
    decaimiento = np.exp(-0.8 * t)
    onda = onda * ataque * decaimiento
    
    return onda * 0.3 / np.max(np.abs(onda))

def orquestar_secuencia():
    print("Sintetizando paisaje sonoro: drone + láser + interferencia...")
    sample_rate = 44100
    duracion_total = 7.0 # 7 segundos de escena
    
    # 1. Pista de fondo ininterrumpida
    pista_fondo = generar_drone(duracion_total)
    
    # 2. Generar eventos
    laser = generar_laser(0.25)
    difusion = generar_difusion_cuantica(5.0)
    
    # 3. Lienzo para los eventos
    pista_eventos = np.zeros(int(sample_rate * duracion_total))
    
    # Posicionar el láser en el segundo 1.0
    idx_laser = int(sample_rate * 1.0)
    pista_eventos[idx_laser:idx_laser+len(laser)] += laser
    
    # Posicionar la difusión cuántica a partir del segundo 1.2 (cuando el láser golpea)
    idx_difusion = int(sample_rate * 1.2)
    fin_difusion = min(idx_difusion + len(difusion), len(pista_eventos))
    largo_real = fin_difusion - idx_difusion
    pista_eventos[idx_difusion:fin_difusion] += difusion[:largo_real]
    
    # 4. Mezclar el fondo con la acción
    audio_final = pista_fondo + pista_eventos
    
    # Normalizar a 16-bit PCM sin distorsionar
    audio_final = np.int16(audio_final / np.max(np.abs(audio_final)) * 32767)
    
    wavfile.write("spikes_demo.wav", sample_rate, audio_final)
    print("¡Audio generado exitosamente!")

if __name__ == "__main__":
    orquestar_secuencia()