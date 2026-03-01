"""
Auth0 JWT verification and Instagram token retrieval.
Uses Auth0 Management API to get the user's stored Instagram access token.
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Load from env (same .env as server; do not overwrite teammates' env)
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "").rstrip("/").replace("https://", "")
AUTH0_API_AUDIENCE = os.getenv("AUTH0_API_AUDIENCE", "")  # e.g. https://api.neurosinc.local
AUTH0_MGMT_CLIENT_ID = os.getenv("AUTH0_MGMT_CLIENT_ID", "")
AUTH0_MGMT_CLIENT_SECRET = os.getenv("AUTH0_MGMT_CLIENT_SECRET", "")
ALGORITHMS = ["RS256"]

security = HTTPBearer(auto_error=False)


def get_jwks():
    url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    with httpx.Client() as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()


def verify_token(token: str) -> dict:
    if not AUTH0_DOMAIN or not AUTH0_API_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth0 not configured (AUTH0_DOMAIN, AUTH0_API_AUDIENCE)",
        )
    try:
        jwks = get_jwks()
        unverified = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks.get("keys", []):
            if key["kid"] == unverified.get("kid"):
                rsa_key = key
                break
        if not rsa_key:
            raise HTTPException(status_code=401, detail="Invalid token key")
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=ALGORITHMS,
            audience=AUTH0_API_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_mgmt_token() -> str:
    url = f"https://{AUTH0_DOMAIN}/oauth/token"
    payload = {
        "client_id": AUTH0_MGMT_CLIENT_ID,
        "client_secret": AUTH0_MGMT_CLIENT_SECRET,
        "audience": f"https://{AUTH0_DOMAIN}/api/v2/",
        "grant_type": "client_credentials",
    }
    with httpx.Client() as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json()["access_token"]


def get_instagram_token(auth0_user_id: str) -> str | None:
    """Fetch the user's Instagram access token from Auth0 (Token Vault / identities)."""
    if not AUTH0_MGMT_CLIENT_ID or not AUTH0_MGMT_CLIENT_SECRET:
        return None
    mgmt_token = get_mgmt_token()
    url = f"https://{AUTH0_DOMAIN}/api/v2/users/{auth0_user_id}"
    with httpx.Client() as client:
        r = client.get(
            url,
            headers={"Authorization": f"Bearer {mgmt_token}"},
            params={"fields": "user_id,identities"},
        )
        if r.status_code != 200:
            return None
        data = r.json()
    # Token Vault: access_token may be in identities or in a separate token vault response
    identities = data.get("identities") or []
    for ident in identities:
        if ident.get("provider") == "instagram" or "instagram" in ident.get("provider", "").lower():
            return ident.get("access_token")
    return None


def get_current_user_and_ig_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> tuple[dict, str]:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    payload = verify_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token")
    ig_token = get_instagram_token(sub)
    if not ig_token:
        raise HTTPException(
            status_code=403,
            detail="No Instagram token found. Log in with Instagram (Auth0 connection) to use analytics.",
        )
    return payload, ig_token
