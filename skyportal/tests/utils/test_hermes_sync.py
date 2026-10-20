"""The Hermes sync service's handling of a single message."""

import uuid

import sqlalchemy as sa

from skyportal.models import DBSession, Obj, Source, init_db
from skyportal.tests import cfg


def test_sources_are_saved_without_configured_instruments(public_group, user):
    from services.hermes_skyportal_sync import hermes_skyportal_sync

    init_db(**cfg["database"])  # undo the service's import-time init_db()

    obj_id = str(uuid.uuid4())
    message = {
        "title": "Test message",
        "data": {
            "targets": [{"name": obj_id, "ra": 10.0, "dec": 20.0}],
            "photometry": [
                {
                    "target_name": obj_id,
                    "date_obs": 2460000.5,
                    "brightness": 18.0,
                    "brightness_error": 0.1,
                    "bandpass": "ztfg",
                    "telescope": "P48",
                    "instrument": "ZTF",
                }
            ],
        },
    }
    processor = hermes_skyportal_sync.SourceProcessor(
        default_group_ids=[public_group.id], bot_user_id=user.id
    )
    processor.process_message(DBSession(), message)
    # The service closes its session after each message, dropping uncommitted rows.
    DBSession().rollback()

    assert DBSession().scalar(sa.select(Obj).where(Obj.id == obj_id)) is not None
    assert (
        DBSession().scalar(
            sa.select(Source).where(
                Source.obj_id == obj_id, Source.group_id == public_group.id
            )
        )
        is not None
    )
