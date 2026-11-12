import os

from dotenv import load_dotenv
from postgrest import SyncPostgrestClient
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("Set SUPABASE_URL and SUPABASE_ANON_KEY in the environment")

# Shared client for Supabase Auth operations only.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def create_user_database_client(access_token: str) -> SyncPostgrestClient:
    """Create a request-scoped PostgREST client authenticated as one user."""
    if not access_token:
        raise ValueError("A user access token is required")

    return SyncPostgrestClient(
        f"{SUPABASE_URL.rstrip('/')}/rest/v1",
        schema="public",
        headers={
            "apiKey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {access_token}",
        },
    )
