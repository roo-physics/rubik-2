# A minimal FastAPI application.
# The root endpoint (GET /) returns a JSON "Hello World" response.
# See https://fastapi.tiangolo.com/ for the framework reference.

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World2"}