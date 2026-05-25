from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from rgc_backend_kit.security import JWTManager
from rgc_backend_kit.security.fastapi_adapter import FastAPIJWTAuth


async def load_user(user_id: str) -> dict[str, str] | None:
    if user_id == "missing":
        return None
    return {"id": user_id}


async def get(app: FastAPI, path: str, *, token: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, headers={"Authorization": f"Bearer {token}"})


async def test_fastapi_adapter_returns_current_payload(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1")
    auth = FastAPIJWTAuth(jwt_manager)
    app = FastAPI()

    @app.get("/me")
    async def me(payload=Depends(auth.current_payload_dependency())):
        return {"sub": payload.subject}

    response = await get(app, "/me", token=pair.access_token)

    assert response.status_code == 200
    assert response.json() == {"sub": "user-1"}


async def test_fastapi_adapter_rejects_invalid_token(jwt_manager: JWTManager) -> None:
    auth = FastAPIJWTAuth(jwt_manager)
    app = FastAPI()

    @app.get("/me")
    async def me(payload=Depends(auth.current_payload_dependency())):
        return {"sub": payload.subject}

    response = await get(app, "/me", token="invalid")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_fastapi_adapter_loads_current_user(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1")
    auth = FastAPIJWTAuth(jwt_manager)
    app = FastAPI()

    @app.get("/me")
    async def me(user=Depends(auth.current_user_dependency(load_user))):
        return user

    response = await get(app, "/me", token=pair.access_token)

    assert response.status_code == 200
    assert response.json() == {"id": "user-1"}


async def test_fastapi_adapter_rejects_missing_user(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("missing")
    auth = FastAPIJWTAuth(jwt_manager)
    app = FastAPI()

    @app.get("/me")
    async def me(user=Depends(auth.current_user_dependency(load_user))):
        return user

    response = await get(app, "/me", token=pair.access_token)

    assert response.status_code == 401
    assert response.json() == {"detail": "User not found."}
