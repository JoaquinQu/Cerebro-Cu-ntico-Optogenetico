# Modelo 3D: convenciones compartidas

Datos, app y Blender usan el mismo marco de referencia, así que un modelo editado en Blender se puede usar en la app sin cambiar código.

| Marco | Ejes | Unidad |
| --- | --- | --- |
| **Datos** (`neurons.json`, `anatomy.py`) | x = izquierda–derecha, y = anteroposterior (cabeza < 0), z = dorsoventral | µm |
| **Blender** | X = x, Y = y, Z = z (Z arriba) | 1 unidad = 100 µm |
| **glTF / `gusano.glb`** | (X, Y, Z) = (x, z, −y) · 0,01 (Y arriba; lo mismo que exporta Blender con *+Y Up*) | 1 unidad = 100 µm |
| **App (three.js)** | X = (y − y_centro)·0,02, Y = (z − z_medio)·0,028, Z = (x − x_medio)·0,028 | escena; ejes transversales ×1,4 |

## Generar o reemplazar `frontend/assets/gusano.glb`

- **Automático:** `python backend/scripts/generar_modelo_3d.py` produce el cuerpo y la faringe a partir de la línea media de las neuronas, unos 630 KB.
- **Desde Blender:** ver `blender/README.md`. Los objetos cuyo nombre contiene `faringe`, `pharynx` o `intestin` se dibujan como órganos internos; el resto se dibuja como cuerpo.
- **Sin archivo:** si `gusano.glb` no existe o no se puede leer, la app arma un cuerpo aproximado por su cuenta.

## Anatomía

- **Cuerpo:** sigue la línea media de las neuronas, de modo que la postura (curvatura) es la del modelo de OpenWorm. Tiene la nariz redondeada, la cola en punta y anillos de cutícula sutiles. El radio es la mayor de dos cantidades: un perfil anatómico típico (máximo de unos 40 µm) o el radio necesario para contener los somas. Con esto, 301 de 302 somas quedan dentro del cuerpo.
- **Faringe:** es una aproximación de proporciones. Ocupa el primer 16 % del largo, con el metacorpus al 45 % y el bulbo terminal al 88 %. Sirve para orientar visualmente la cabeza; no es un dato del conectoma.
