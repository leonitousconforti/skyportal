import os
import uuid

import pytest
from playwright.sync_api import expect

from skyportal.tests import api, retry_until


@pytest.mark.flaky(reruns=2)
def test_upload_galaxies(page, super_admin_user, super_admin_token):
    page.goto(f"/become_user/{super_admin_user.id}")
    page.goto("/galaxies/")

    filename = "CLU_mini.csv"
    catalog_name = str(uuid.uuid4())

    page.get_by_label("Add a New Galaxy Catalog").click()

    page.locator('//*[@id="root_catalogName"]').first.fill(catalog_name)
    page.locator('//input[@type="file"]').first.set_input_files(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            filename,
        )
    )

    expect(page.locator(f'//*[contains(., "{filename}")]').first).to_be_visible()
    page.locator('//button[contains(.,"Submit")]').first.click()

    # The data grid quick filter searches galaxy names server-side.
    search_bar = page.locator('//*[@data-testid="galaxy-search-input"]//input').first
    search_bar.fill("6dFgs gJ0001313-055904")
    expect(page.locator('//*[text()="6dFgs gJ0001313-055904"]').first).to_be_visible()
    search_bar.fill("")

    def galaxies_loaded():
        status, data = api(
            "GET",
            "galaxy_catalog",
            token=super_admin_token,
            params={"catalog_name": catalog_name},
        )
        assert status == 200
        assert len(data["data"]["galaxies"]) == 10

    retry_until(galaxies_loaded, timeout=60)

    # Reload so the catalog list includes the new catalog, then show only it
    page.goto("/galaxies/")
    page.locator(f'//*[text()="{catalog_name}"]').first.click()

    # Sorting is done by the server: two clicks sort by distance, descending
    first_name = page.locator('//div[@data-rowindex="0"]//*[@data-field="name"]').first
    distance_header = page.locator(
        '//*[@role="columnheader" and @data-field="distmpc"]'
    ).first
    distance_header.click()
    distance_header.click()
    expect(first_name).to_have_text("MRSS 349-058718")

    page.locator("//button[@data-testid='Filter Table-iconButton']").first.click()
    dialog = page.locator('//div[@role="dialog"]')
    dialog.locator('//input[@name="maxDistance"]').first.fill("1")
    dialog.locator('//button[contains(., "Submit")]').first.click()
    expect(first_name).to_have_text("6dFgs gJ0001313-055904")

    # Resetting the form and submitting clears the distance filter
    dialog.locator('//button[contains(., "Reset")]').first.click()
    dialog.locator('//button[contains(., "Submit")]').first.click()
    expect(first_name).to_have_text("MRSS 349-058718")

    # An empty name field in the form keeps the toolbar search
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    search_bar.fill("MRSS")
    second_name = page.locator('//div[@data-rowindex="1"]//*[@data-field="name"]').first
    expect(second_name).to_have_text("MRSS 349-063591")
    page.locator("//button[@data-testid='Filter Table-iconButton']").first.click()
    dialog.locator('//input[@name="maxDistance"]').first.fill("199")
    dialog.locator('//button[contains(., "Submit")]').first.click()
    expect(first_name).to_have_text("MRSS 349-063591")
