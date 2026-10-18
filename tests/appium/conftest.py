"""Appium 2 (uiautomator2) fixtures for the Android app. Requires `appium` on :4723 and a device on adb."""
import os

import pytest
import requests

APPIUM_URL = os.environ.get("APPIUM_URL", "http://localhost:4723")
API_BASE = os.environ.get("API_BASE", "http://localhost:8080")
GRID_URL = os.environ.get("GRID_URL", "http://localhost:4444")
WEB_BASE = os.environ.get("WEB_BASE", "http://host.docker.internal:8080")
PACKAGE = "com.nascon.app"


@pytest.fixture(scope="session")
def driver():
    from appium import webdriver
    from appium.options.android import UiAutomator2Options
    try:
        ready = requests.get(APPIUM_URL + "/status", timeout=3).json()["value"]["ready"]
    except Exception:
        ready = False
    if not ready:
        pytest.skip("Appium server not ready at " + APPIUM_URL)
    opts = UiAutomator2Options()
    opts.platform_name = "Android"
    opts.automation_name = "UiAutomator2"
    opts.app_package = PACKAGE
    opts.app_activity = ".MainActivity"
    opts.no_reset = True
    opts.new_command_timeout = 120
    opts.set_capability("appium:skipDeviceInitialization", True)  # no Appium Settings helper needed for deep links
    opts.set_capability("appium:ignoreHiddenApiPolicyError", True)
    d = webdriver.Remote(APPIUM_URL, options=opts)
    yield d
    d.quit()
