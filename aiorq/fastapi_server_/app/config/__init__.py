# -*- coding: utf-8 -*-

import os

env = os.getenv("PRODUCTION", "")
if env:
    pass
else:
    from .development_config import settings
