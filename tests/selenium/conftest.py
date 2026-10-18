"""Selenium Grid 4 fixtures. Browsers run on the grid nodes; the test runner talks to the API directly.

GRID_URL  Selenium hub seen from the runner        (default http://localhost:4444)
WEB_BASE  Guest Web Player seen from the browsers   (default http://host.docker.internal:8080)
API_BASE  Backend seen from the runner              (default http://localhost:8080)
"""
import os

import pytest
import requests
from selenium import webdriver

GRID_URL = os.environ.get("GRID_URL", "http://localhost:4444")
WEB_BASE = os.environ.get("WEB_BASE", "http://host.docker.internal:8080")
API_BASE = os.environ.get("API_BASE", "http://localhost:8080")
BROWSERS = [b.strip() for b in os.environ.get("GRID_BROWSERS", "chrome,firefox").split(",") if b.strip()]


def _options(name: str):
    if name == "firefox":
        opts = webdriver.FirefoxOptions()
        opts.add_argument("-headless")
    else:
        opts = webdriver.ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--autoplay-policy=no-user-gesture-required")
    opts.add_argument("--window-size=1280,900")
    return opts


@pytest.fixture(params=BROWSERS)
def browser(request):
    try:
        requests.get(GRID_URL + "/status", timeout=3)
    except requests.RequestException:
        pytest.skip("Selenium Grid not reachable at " + GRID_URL)
    driver = webdriver.Remote(command_executor=GRID_URL, options=_options(request.param))
    driver.set_window_size(1280, 900)
    yield driver
    driver.quit()


@pytest.fixture()
def api():
    s = requests.Session()
    s.base = API_BASE
    return s
