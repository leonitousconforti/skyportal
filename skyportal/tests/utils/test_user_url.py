"""Which base URLs the server will send a user's key to."""

import pytest

from skyportal.utils.user_url import check_user_base_url


@pytest.mark.parametrize(
    "url",
    [
        "http://8.8.8.8/v1",
        "https:///v1",
        "https://127.0.0.1/v1",
        "https://10.1.2.3",
        "https://169.254.169.254",
        "https://[::1]/",
        "https://[::ffff:127.0.0.1]/",
        "https://[::ffff:0:7f00:1]/",
        "https://[64:ff9b::a00:1]/",
        "https://user:pw@8.8.8.8",
        "https://localhost",
        "https://straße.example/v1",
    ],
)
def test_a_url_off_the_public_https_internet_is_refused(url):
    with pytest.raises(ValueError):
        check_user_base_url(url)


def test_a_public_https_url_is_kept_stripped():
    assert check_user_base_url(" https://8.8.8.8/v1 ") == "https://8.8.8.8/v1"
