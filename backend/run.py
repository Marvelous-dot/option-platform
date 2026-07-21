#!/usr/bin/env python3.11
import uvicorn
from main import app
uvicorn.run(app, host='0.0.0.0', port=8000)
