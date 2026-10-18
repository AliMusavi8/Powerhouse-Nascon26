"""Guest Web Player on Selenium Grid 4 (spec 6.2.3). Run: pytest -n 3 tests/selenium/ --junitxml=tests/reports/selenium-report.xml

No /reset here: tests run in parallel on shared state, so each one only depends on what it changes.
"""
import time
import uuid
from urllib.parse import urlparse

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from conftest import WEB_BASE

TESTIDS = ("guest-video-player", "live-score-banner", "pinned-merch-card", "add-to-guest-cart-btn",
           "guest-cart-count", "chat-message-list", "chat-input-field", "chat-send-btn", "progressive-auth-modal")


def tid(name):
    return By.CSS_SELECTOR, f'[data-testid="{name}"]'


def open_live(driver):
    driver.get(WEB_BASE + "/q/m1-live")
    WebDriverWait(driver, 3).until(EC.visibility_of_element_located(tid("live-score-banner")))
    WebDriverWait(driver, 3).until(lambda d: " - " in d.find_element(*tid("live-score-banner")).text)


def test_1_qr_resolution_zero_friction_load(browser):
    start = time.monotonic()
    browser.get(WEB_BASE + "/q/m1-live")
    assert urlparse(browser.current_url).path == "/web/matches/match-m1/live"
    WebDriverWait(browser, 3).until(EC.visibility_of_element_located(tid("guest-video-player")))
    WebDriverWait(browser, 3).until(EC.visibility_of_element_located(tid("live-score-banner")))
    assert time.monotonic() - start < 3.0
    assert not browser.find_element(*tid("progressive-auth-modal")).is_displayed()
    for name in TESTIDS:
        assert browser.find_elements(*tid(name)), name


def test_2_guest_write_block_opens_progressive_modal(browser):
    open_live(browser)
    text = "guest says hi " + uuid.uuid4().hex[:6]
    browser.find_element(*tid("chat-input-field")).send_keys(text)
    browser.find_element(*tid("chat-send-btn")).click()
    WebDriverWait(browser, 3).until(EC.visibility_of_element_located(tid("progressive-auth-modal")))
    assert text not in browser.find_element(*tid("chat-message-list")).text


def test_3_guest_cart_staging_and_realtime_score(browser, api):
    open_live(browser)
    browser.find_element(*tid("add-to-guest-cart-btn")).click()
    WebDriverWait(browser, 3).until(lambda d: d.find_element(*tid("guest-cart-count")).text == "1")

    before = browser.find_element(*tid("live-score-banner")).text
    time.sleep(0.5)  # let the realtime stream subscribe
    r = api.post(api.base + "/audit/v1/events", json={"event_id": "grid-" + uuid.uuid4().hex[:10],
                                                      "match_id": "match-m1", "type": "score",
                                                      "payload": {"team_id": "club-alpha-1", "event_type": "goal"}},
                 timeout=5)
    assert r.status_code == 201, r.text
    WebDriverWait(browser, 0.5, poll_frequency=0.05).until(
        lambda d: d.find_element(*tid("live-score-banner")).text != before)


def test_accessibility_targets_labels_and_keyboard(browser):
    open_live(browser)
    for name in ("add-to-guest-cart-btn", "chat-send-btn", "chat-input-field"):
        el = browser.find_element(*tid(name))
        assert el.size["width"] >= 48 and el.size["height"] >= 48, name
        assert el.get_attribute("aria-label"), name
    assert browser.find_element(*tid("guest-video-player")).get_attribute("aria-label")
    reached = set()
    keys = ActionChains(browser)
    for _ in range(40):
        keys.send_keys(Keys.TAB).perform()
        reached.add(browser.switch_to.active_element.get_attribute("data-testid"))
        if "chat-send-btn" in reached:
            break
    assert {"add-to-guest-cart-btn", "chat-input-field", "chat-send-btn"} <= reached
