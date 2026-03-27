# -*- coding: utf-8 -*-
"""Fixtures compartilhadas para testes."""

import sys
from pathlib import Path

# Garantir que o projeto esta no path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
