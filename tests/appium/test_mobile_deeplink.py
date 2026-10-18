"""Native deep links (spec 6.3). Run: pytest tests/appium --junitxml=tests/reports/appium-report.xml"""
import time
import uuid

import requests
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from conftest import API_BASE, GRID_URL, PACKAGE, WEB_BASE


def tag(name):
    # Compose test tags are exposed as bare resource ids (testTagsAsResourceId), without the package prefix.
    return AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().resourceId("{name}")'


def deep_link(driver, url):
    # Same intent the desk runner fires: adb shell am start -W -a android.intent.action.VIEW -d <url>
    driver.execute_script("mobile: deepLink", {"url": url, "package": PACKAGE})


def test_match_deep_link_opens_live_screen(driver):
    start = time.monotonic()
    deep_link(driver, "nascon://entity/match-m1")
    WebDriverWait(driver, 2).until(EC.presence_of_element_located(tag("match-live-screen")))
    assert time.monotonic() - start < 2.5
    assert driver.current_package == PACKAGE


def test_costream_deep_link_opens_costream_screen(driver):
    requests.post(API_BASE + "/audit/v1/costream/session", json={
        "session_id": "cs-session-101", "host_player_id": "player-alpha-1",
        "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"]}, timeout=5)
    deep_link(driver, "nascon://stream/cs-session-101")
    WebDriverWait(driver, 2).until(EC.presence_of_element_located(tag("costream-screen")))


def test_cross_surface_chat_sync(driver):
    """App (Appium) and Guest Web Player (Selenium Grid) both show a member's chat message within 3 s."""
    from selenium import webdriver
    from selenium.webdriver.common.by import By

    deep_link(driver, "nascon://stream/cs-session-101")
    WebDriverWait(driver, 2).until(EC.presence_of_element_located(tag("costream-screen")))
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    web = webdriver.Remote(command_executor=GRID_URL, options=opts)
    try:
        web.get(WEB_BASE + "/web/costream/cs-session-101")
        WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-message-list"]')))
        time.sleep(1)
        token = requests.post(API_BASE + "/api/v1/auth/login", json={"email": "player@nascon.test",
                                                                     "password": "Nascon@26"}, timeout=5).json()["token"]
        text = "cross surface " + uuid.uuid4().hex[:6]
        sent = time.monotonic()
        r = requests.post(API_BASE + "/api/v1/chat", json={"chat_room_id": "chat-cs-session-101", "text": text},
                          headers={"Authorization": "Bearer " + token}, timeout=5)
        assert r.status_code == 200, r.text
        WebDriverWait(web, 3).until(lambda d: text in d.find_element(By.CSS_SELECTOR,
                                                                     '[data-testid="chat-message-list"]').text)
        WebDriverWait(driver, 3).until(lambda d: d.find_elements(AppiumBy.XPATH, f'//*[contains(@text, "{text}")]'))
        assert time.monotonic() - sent < 3.0
    finally:
        web.quit()
