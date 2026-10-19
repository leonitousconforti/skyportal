"""Autonomous triage from shared AssistantQuery rows (skybot).

When an analysis completes, any active AssistantQuery whose
``analysis_service_match`` is in the service name and whose group the source is
saved to runs a skybot assistant job of its ``prompt``. The answer is delivered
to the query's subscribers who are members of its group, plus any always-on
``notify_groups`` (a dry-run query runs but notifies no one).

Read-only: it reuses the assistant loop (MCP read tools) and delivers its answer
as a notification and a skybot thread message; nothing is written to the source,
and the classifier's own result stays authoritative. Personal one-off schedules
stay in RecurringAPI; this is the shared, subscribable kind.

Needs a bot user named ``skybot`` (a member of the notify/query groups) with no
email, OAuth identity or API token (see SKYBOT). Absent it, triage is skipped.
"""

import sqlalchemy as sa

from baselayer.app.env import load_env
from baselayer.log import make_log

from ..models import (
    AssistantMessage,
    AssistantQuery,
    AssistantQuerySubscription,
    Group,
    GroupUser,
    Source,
    Token,
    User,
)
from .assistant import is_enabled

_, cfg = load_env()
log = make_log("assistant_triage")

SKYBOT_USERNAME = "skybot"
# The assistant service answers skybot's messages in these channels with the
# query owner's access, so the API refuses them for anyone else's messages.
QUERY_CHANNEL_PREFIX = "query:"

_social_auth = sa.table("social_auth_usersocialauth", sa.column("user_id"))
# An account nobody can sign in to or act as: no OAuth identity, no email that
# a sign-in could be matched to, and no API token.
NO_SIGN_IN = sa.and_(
    User.oauth_uid.is_(None),
    User.contact_email.is_(None),
    ~sa.exists().where(_social_auth.c.user_id == User.id),
    ~sa.exists().where(Token.created_by_id == User.id),
)
# skybot's runs read with their query owner's access and its account can read
# the answers back, so the name alone is not enough: anyone could take it
# before skybot is provisioned.
SKYBOT = sa.and_(User.username == SKYBOT_USERNAME, User.is_bot.is_(True), NO_SIGN_IN)

# Appended to every query run so the answer ends with a machine-readable urgency
# marker; the assistant service posts the comment either way but only notifies
# subscribers when this is "yes".
NOTIFY_SUFFIX = (
    "\n\nFinally, on the very last line output exactly `NOTIFY: yes` if a human "
    "should be alerted promptly (a genuine anomaly, a candidate needing "
    "spectroscopy, or something clearly unusual), otherwise `NOTIFY: no`. Use "
    "`yes` sparingly: most routine classifications are `NOTIFY: no`."
)


def triage_enabled(cfg) -> bool:
    """The master switch: autonomous triage on, and an assistant to run it."""
    settings = (cfg.get("app.assistant") or {}).get("analysis_triage") or {}
    return bool(settings.get("enabled")) and is_enabled(cfg)


def combine_recipients(subscriber_ids, group_member_ids, notify_group_member_ids):
    """Recipients = subscribers who are still in the query's group, plus the
    members of any always-on notify groups."""
    return sorted(
        (set(subscriber_ids) & set(group_member_ids)) | set(notify_group_member_ids)
    )


async def matching_queries(session, analysis):
    """Active AssistantQuery rows this completed analysis triggers: the service
    name contains their match string and the source is saved to their group."""
    name = (getattr(analysis.analysis_service, "name", "") or "").lower()
    if not name:
        return []
    group_ids = set(
        await session.scalars(
            sa.select(Source.group_id).where(
                Source.obj_id == analysis.obj_id, Source.active.is_(True)
            )
        )
    )
    if not group_ids:
        return []
    queries = (
        (
            await session.scalars(
                sa.select(AssistantQuery).where(
                    AssistantQuery.active.is_(True),
                    AssistantQuery.analysis_service_match.isnot(None),
                    AssistantQuery.group_id.in_(group_ids),
                )
            )
        )
        .unique()
        .all()
    )
    return [q for q in queries if q.analysis_service_match.lower() in name]


async def _recipients(session, query):
    subscriber_ids = set(
        await session.scalars(
            sa.select(AssistantQuerySubscription.user_id).where(
                AssistantQuerySubscription.query_id == query.id
            )
        )
    )
    group_member_ids = set(
        await session.scalars(
            sa.select(GroupUser.user_id).where(GroupUser.group_id == query.group_id)
        )
    )
    notify_member_ids = set()
    for gid in query.notify_groups or []:
        # skipped for the sitewide group, which every user is in
        notify_member_ids |= set(
            await session.scalars(
                sa.select(GroupUser.user_id)
                .join(Group, Group.id == GroupUser.group_id)
                .where(
                    GroupUser.group_id == int(gid),
                    Group.name != cfg["misc.public_group_name"],
                )
            )
        )
    return combine_recipients(subscriber_ids, group_member_ids, notify_member_ids)


async def enqueue_query_run(session, analysis, query) -> int | None:
    """Create a skybot run for one triggered query; returns the message id (the
    caller posts it to the assistant service), or None if the run is skipped.

    Skipped when skybot is absent, and when it or the query's owner, whose
    access the run reads with, is not a member of the query's group. A
    classification is readable only by the groups the source is saved to, so a
    run outside them reads an empty list and says the analysis does not exist
    -- on the page where everyone else can see it. Saying nothing is the better
    failure.
    """
    skybot = await session.scalar(sa.select(User).where(SKYBOT))
    if skybot is None:
        log(
            f"no {SKYBOT_USERNAME!r} bot that nobody can sign in to; skipping "
            f"query {query.id} for {analysis.obj_id}"
        )
        return None
    reads_the_group = await session.scalar(
        sa.select(GroupUser.id).where(
            GroupUser.group_id == query.group_id,
            GroupUser.user_id == skybot.id,
        )
    )
    if reads_the_group is None:
        log(
            f"{SKYBOT_USERNAME!r} is not a member of group {query.group_id}, so it "
            f"cannot read what it would be asked about; skipping query {query.id} "
            f"for {analysis.obj_id}"
        )
        return None
    owner_in_group = await session.scalar(
        sa.select(GroupUser.id).where(
            GroupUser.group_id == query.group_id,
            GroupUser.user_id == query.owner_id,
        )
    )
    if owner_in_group is None:
        log(
            f"the owner of query {query.id} is not a member of group "
            f"{query.group_id}; skipping it for {analysis.obj_id}"
        )
        return None
    notify = None
    if not query.dry_run:
        users = await _recipients(session, query)
        # comment_groups carries where skybot posts the full triage as a bot
        # comment; it runs even with no subscribers, so the group still sees it.
        notify = {"users": users, "comment_groups": [query.group_id]}
    message = AssistantMessage(
        user_id=skybot.id,
        text=query.prompt + NOTIFY_SUFFIX,
        channel=f"{QUERY_CHANNEL_PREFIX}{query.id}:{analysis.obj_id}",
        context_type=query.context_type or "source",
        context_id=analysis.obj_id,
        notify=notify,
    )
    session.add(message)
    await session.commit()
    return message.id
