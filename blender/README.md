# Escena de Blender

Video cinematográfico del láser optogenético y la propagación cuántica, con los mismos datos y la misma física que la app.

| Archivo | Qué es |
| --- | --- |
| `animar_gusano.py` | Script de Blender (`bpy`): arma la escena y la anima |
| `datos_escena.json` | Datos exportados por el backend (neuronas, sinapsis, cuerpo, P_k(t)) |
| `renderizar.bat` | Atajo para Windows: exporta los datos y renderiza el video |
| `exportar_glb.py` | Lleva a la app el cuerpo retocado en Blender, sin modificar la escena |
| `render/` | Aquí queda el video (`cerebro_cuantico.mp4`) |
| `escena_gusano.blend` | La escena guardada, para abrirla y retocarla (se genera al correr el script) |

Requiere Blender 4.2 LTS o superior.

## Uso rápido (Windows)

```
blender\renderizar.bat eevee borrador AVM      # prueba rápida (960×540)
blender\renderizar.bat eevee media AVM         # 1920×1080, ~12 s de video
blender\renderizar.bat cycles alta AVM         # máxima calidad (lento)
```

## Uso manual

```
python backend/scripts/exportar_blender.py --fuente AVM      # 1. datos
blender --python blender/animar_gusano.py                     # 2a. abrir la escena en Blender
blender --background --python blender/animar_gusano.py -- --render --calidad media   # 2b. render directo
```

## Qué contiene la escena

- **Neuronas:** 302 esferas en posiciones reales. Su brillo y tamaño siguen P_k(t), mediante la propiedad `actividad` animada por cuadro, y el color en reposo depende del tipo de neurona.
- **Sinapsis:** las 800 más fuertes, como hilos emisivos.
- **Cuerpo y faringe:** la misma malla anatómica que usa la app, con material de cutícula translúcida.
- **Láser:** el haz, el destello y la onda expansiva sobre la neurona fuente durante los primeros 40 cuadros.
- **Cámara:** abre en primer plano del láser, se aleja mientras la excitación se propaga y gira lento al final.
- **Resplandor:** se agrega en el compositor (nodo Glare).
- **Rótulo:** muestra el tiempo t y la fórmula.

Para retocar la escena, abre `escena_gusano.blend` y cambia materiales, cámara o duración. Las constantes principales están al inicio del script: `CUADROS_LASER`, `CUADROS_WALK`, `ESCALA`, `PALETA` y `CALIDADES`.

## Editar el cuerpo para la app

1. En Blender, edita los objetos `Cuerpo` y `Faringe`, sin moverlos ni escalarlos como objeto.
2. Exporta sin reconstruir la escena: `blender --background blender/escena_gusano.blend --python blender/exportar_glb.py -- frontend/assets/gusano.glb`. También puedes usar *File → Export → glTF*, con *+Y Up*, sólo los objetos seleccionados y formato `.glb`.
3. Recarga la app y el nuevo cuerpo aparece solo. Los detalles de las coordenadas están en `docs/MODELO_3D.md`.

> El script se probó contra una versión simulada de la API de Blender, pero no en un Blender real. Si una versión específica de Blender cambia algún nombre de la API, el script avisa y sigue sin ese detalle; por ejemplo, el resplandor del compositor.
