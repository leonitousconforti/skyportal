import sqlalchemy as sa
from skyportal_py_models.ai_connection import AIConnectionPutBody, AIConnectionResponse
from tornado.ioloop import IOLoop

from baselayer.app.access import auth_or_token

from ....models import AIConnection
from ....models.ai_connection import PROVIDERS
from ....utils.user_url import check_user_base_url
from ...base import BaseHandler


class AIConnectionHandler(BaseHandler):
    """The calling user's own AI connection. The key is set by the user and
    never handed back, so nobody, admins included, reads it through the API."""

    async def own_connection(self, session):
        return await session.scalar(
            sa.select(AIConnection).where(
                AIConnection.user_id == self.associated_user_object.id
            )
        )

    @auth_or_token
    async def get(self) -> AIConnectionResponse:
        """
        ---
        summary: Get your AI connection
        description: Null when none is set. The key itself is never returned,
          only whether one is set and its last four characters.
        """
        async with self.AsyncSession() as session:
            row = await self.own_connection(session)
            if row is None:
                return self.success(data=None)
            api_key = row.api_key or ""
            return self.success(
                data={
                    "provider": row.provider,
                    "base_url": row.base_url,
                    "model": row.model,
                    "api_key_set": bool(api_key),
                    # A short key would be mostly given away by its last four.
                    "api_key_last4": api_key[-4:] if len(api_key) >= 12 else None,
                }
            )

    @auth_or_token
    async def put(self, *, body: AIConnectionPutBody = None):
        """
        ---
        summary: Set your AI connection
        description: Creates or replaces the calling user's own connection. A
          blank key keeps the stored one, unless the provider or base URL
          changes, since a key is only ever sent to the address it was saved for.
        responses:
          200:
            content:
              application/json:
                schema: Success
          400:
            content:
              application/json:
                schema: Error
        """
        body = self.parse_body(AIConnectionPutBody)
        if body.provider not in PROVIDERS:
            return self.error(
                f"Unknown provider '{body.provider}'; expected one of: "
                f"{', '.join(PROVIDERS)}"
            )
        base_url = (body.base_url or "").strip() or None
        if base_url is not None:
            # Checked before the session, so a slow DNS lookup holds no DB
            # connection.
            try:
                base_url = await IOLoop.current().run_in_executor(
                    None, check_user_base_url, base_url
                )
            except ValueError as e:
                return self.error(str(e))
        api_key = (body.api_key or "").strip()
        # The key goes into a request header, where a line break could split it.
        if api_key and not (api_key.isascii() and api_key.isprintable()):
            return self.error("The API key must be printable ASCII")

        async with self.AsyncSession() as session:
            row = await self.own_connection(session)
            if not api_key:
                if row is None:
                    return self.error("An API key is required")
                if (row.provider, row.base_url) != (body.provider, base_url):
                    return self.error(
                        "Enter the API key again: a saved key is only sent to "
                        "the provider and base URL it was saved for"
                    )
            if row is None:
                row = AIConnection(user_id=self.associated_user_object.id)
                session.add(row)
            row.provider = body.provider
            row.base_url = base_url
            row.model = (body.model or "").strip() or None
            if api_key:
                row.api_key = api_key
            await session.commit()
            return self.success()

    @auth_or_token
    async def delete(self):
        """
        ---
        summary: Delete your AI connection
        responses:
          200:
            content:
              application/json:
                schema: Success
        """
        async with self.AsyncSession() as session:
            row = await self.own_connection(session)
            if row is not None:
                await session.delete(row)
                await session.commit()
            return self.success()
