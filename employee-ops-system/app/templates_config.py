"""
templates_config.py — Single shared Jinja2Templates instance for all routers.
Avoids circular imports between main.py and routers.
"""
import os
from fastapi.templating import Jinja2Templates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
