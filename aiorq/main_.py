# -*- coding: utf-8 -*-
from aiorq.app_server import create_app

app = create_app()
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app='main_:app', host="127.0.0.1", port=8080, reload=True)