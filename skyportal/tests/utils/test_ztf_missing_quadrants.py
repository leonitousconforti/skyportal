"""Only a recent ZTF night updates the instrument's missing quadrants."""

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.time import Time

from skyportal import models
from skyportal.facility_apis import ztf


@pytest.fixture
def instrument(monkeypatch):
    instrument = SimpleNamespace(configuration_data={"missing_quadrants": [1]})

    @contextmanager
    def new_session():
        yield SimpleNamespace(get=lambda *args: instrument, commit=lambda: None)

    monkeypatch.setattr(models, "new_session", new_session)
    return instrument


def _night(jd):
    # quadrants 0 and 1 did not process
    return (jd, 500, set(range(2, 64)))


def test_old_night_leaves_missing_quadrants_unchanged(instrument):
    ztf.update_missing_quadrants(1, [_night(Time("2024-01-01").jd)])
    assert instrument.configuration_data == {"missing_quadrants": [1]}


def test_recent_night_updates_missing_quadrants(instrument):
    ztf.update_missing_quadrants(1, [_night(np.floor(Time.now().jd))])
    assert instrument.configuration_data == {"missing_quadrants": [0, 1]}
