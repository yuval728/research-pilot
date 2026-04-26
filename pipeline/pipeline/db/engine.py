"""
pipeline.db.engine
~~~~~~~~~~~~~~~~~~
Shared Supabase client singleton.

All graph nodes must import from here instead of calling
``create_engine()`` or ``create_client()`` inline — this ensures
connection pooling is reused across nodes rather than torn down after
every DB call.

    from pipeline.db.engine import get_supabase_client
"""

from __future__ import annotations

import functools

from supabase import Client, create_client  # type: ignore[import-untyped]


@functools.lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return a cached Supabase client singleton.

    The client is stateless HTTP but caching avoids repeated auth token
    negotiation overhead on every storage operation.
    """
    from pipeline.core.config import get_settings

    settings = get_settings()
    return create_client(
        settings.supabase.url,
        settings.supabase.service_role_key.get_secret_value(),
    )
