import json
import time
import uuid
from datetime import timedelta

from skyportal.tests import api

from ....utils.naive_datetime import utcnow_naive


def test_post_and_verify_recurring_api(
    view_only_token, public_group, super_admin_token
):
    next_call = utcnow_naive() + timedelta(seconds=1)
    obj_id = str(uuid.uuid4())

    request_data = {
        "next_call": next_call.strftime("%Y-%m-%dT%H:%M:%S"),
        "call_delay": 0.001,
        "method": "POST",
        "endpoint": "sources",
        "payload": "{Test incorrect payload}",
    }

    status, data = api(
        "POST",
        "recurring_api",
        data=request_data,
        token=super_admin_token,
    )
    assert status == 400
    assert "payload must be a valid JSON string" in data["message"]

    request_data["payload"] = json.dumps(
        {
            "id": obj_id,
            "ra": 234.22,
            "dec": -22.33,
            "redshift": 3,
            "group_ids": [public_group.id],
        }
    )

    endpoint = "recurring_api"
    status, data = api(
        "POST",
        endpoint,
        data=request_data,
        token=super_admin_token,
    )
    assert status == 200
    assert data["status"] == "success"
    recurring_api_id = data["data"]["id"]

    endpoint = f"recurring_api/{recurring_api_id}"
    status, data = api(
        "GET",
        endpoint,
        token=super_admin_token,
    )
    assert status == 200
    assert data["status"] == "success"

    endpoint = f"sources/{obj_id}"
    n_retries = 0
    while n_retries < 10:
        status, data = api(
            "GET",
            endpoint,
            token=view_only_token,
        )
        if data["status"] == "success":
            break
        time.sleep(15)
        n_retries += 1
    assert n_retries < 10
    assert status == 200


def test_recurring_api_call_that_raises_counts_as_failed(super_admin_token):
    # A JSON list cannot be encoded as GET params, so the call itself raises.
    request_data = {
        "next_call": utcnow_naive().strftime("%Y-%m-%dT%H:%M:%S"),
        "call_delay": 1,
        "method": "GET",
        "endpoint": "sources",
        "payload": "[1, 2]",
    }
    status, data = api(
        "POST",
        "recurring_api",
        data=request_data,
        token=super_admin_token,
    )
    assert status == 200
    recurring_api_id = data["data"]["id"]

    try:
        for _ in range(30):
            status, data = api(
                "GET",
                f"recurring_api/{recurring_api_id}",
                token=super_admin_token,
            )
            assert status == 200
            if data["data"]["number_of_retries"] < 10:
                break
            time.sleep(2)
        assert data["data"]["number_of_retries"] < 10
    finally:
        api("DELETE", f"recurring_api/{recurring_api_id}", token=super_admin_token)
