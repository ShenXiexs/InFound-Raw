from typing import Callable

from fastapi import FastAPI

# Startup/shutdown hook signatures
StartupHook = Callable[[FastAPI], None]
ShutdownHook = Callable[[FastAPI], None]


# Default no-op hooks (when a service has no custom logic)
def default_startup_hook(app: FastAPI):
    pass


def default_shutdown_hook(app: FastAPI):
    pass
