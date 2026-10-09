# Datos

| Archivo | Contenido | Fuente |
| --- | --- | --- |
| `connectome_cook2019.csv` | Sinapsis entre las 302 neuronas del hermafrodita: `source, target, weight` (n.º de sinapsis), `type` (`chemical` / `electrical`) | Cook et al., *Nature* 571, 63 (2019), vía [OpenWorm c302](https://github.com/openworm/c302) (`herm_full_edgelist.csv`). Se filtró a neuronas y se normalizaron nombres (`DA01` → `DA1`). |
| `neurons.json` | Nombre, posición del soma (µm) y tipo/neurotransmisor de cada neurona | Posiciones: [OpenWorm CElegansNeuroML](https://github.com/openworm/CElegansNeuroML) (`generatedNeuroML2/*.cell.nml`, segmento 0). Tipos: `owmeta_cache.json` de c302. |
| `results/jobs/` | Registros de trabajos enviados a IonQ (se generan al usar la API o el script) | — |

Los datos de OpenWorm se distribuyen bajo licencia MIT.
