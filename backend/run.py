"""Arranca el prototipo:  python run.py   →   http://127.0.0.1:8000

Sirve la API (/api/...) y el frontend (/) desde el mismo proceso.
"""

import uvicorn

from cerebro import config

if __name__ == "__main__":
    print(f"\n  Cerebro Cuántico Optogenético → http://{config.HOST}:{config.PORT}\n")
    uvicorn.run("cerebro.api.app:app", host=config.HOST, port=config.PORT, reload=False)
