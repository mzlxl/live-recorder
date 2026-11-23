# -*- coding: utf-8 -*-
"""启动入口：python run.py"""
import uvicorn
import config

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)
