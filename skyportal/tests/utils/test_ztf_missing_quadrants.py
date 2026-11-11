"""Only a recent ZTF night updates the instrument's missing quadrants."""

from types import SimpleNamespace

import pytest
from astropy.time import Time

from skyportal.facility_apis import ztf
from skyportal.models import DBSession

# a night of 100 processed exposures with nothing on quadrants 0 and 1
RECENTPROC = [
    {"exposure_id": i, "field_id": 1, "filter_id": 1, "status": 0, "rcid": 2 + i % 62}
    for i in range(100)
]


class _Depot:
    def head(self, url):
        return SimpleNamespace(status_code=200)

    def get(self, url):
        return SimpleNamespace(json=lambda: RECENTPROC)


@pytest.fixture
def instrument(ztf_camera):
    ztf_camera.configuration_data = {"missing_quadrants": [1]}
    DBSession().commit()
    return ztf_camera


def _fetch(instrument, jd_start, jd_end):
    ztf.fetch_depot_observations(instrument.id, _Depot(), "depot", jd_start, jd_end)
    DBSession().refresh(instrument)
    return instrument.configuration_data["missing_quadrants"]


def test_old_night_leaves_missing_quadrants_unchanged(instrument):
    jd = Time("2024-01-01").jd
    assert _fetch(instrument, jd, jd + 1) == [1]


def test_recent_night_updates_missing_quadrants(instrument):
    jd = Time.now().jd
    assert _fetch(instrument, jd - 1, jd) == [0, 1]
