"""Carga centralizada de variables de entorno.

Importar este módulo garantiza que el archivo ``.env`` de la raíz del proyecto
se haya leído antes de que cualquier otro módulo consulte ``os.getenv``.
"""

from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")
