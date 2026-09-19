"""
Tests for the click helpers in modules/clickers_and_finders.py.

The behaviour under test is `click_when_stable`'s retry: LinkedIn re-renders the
filter panel and search results after every click, so WebDriverWait can hand back a
WebElement bound to a node that is invalidated before the click lands. The helper is
supposed to re-resolve the element and click the fresh node, bounded by an attempt
COUNT (`time` must NOT be used for wall-clock deadline here - it shadows the `time`
module inside the function body).
"""

import pytest
from selenium.common.exceptions import StaleElementReferenceException

from modules import clickers_and_finders as cf


class FakeElement:
    """
    A stand-in WebElement that raises `StaleElementReferenceException` for its first
    `stale_times` clicks, then records the click. `is_displayed` is what
    `pick_first_displayed` filters on.
    """

    def __init__(self, stale_times=0, displayed=True):
        self.stale_times = stale_times
        self.displayed = displayed
        self.clicks = 0

    def is_displayed(self):
        return self.displayed

    def click(self):
        if self.clicks < self.stale_times:
            self.clicks += 1
            raise StaleElementReferenceException("node replaced by a re-render")
        self.clicks += 1

    # scroll_to_view may resolve the owning driver off the element.
    parent = None


class FakeDriver:
    """Returns `elements` from every `find_elements` call, however many times it is asked."""

    def __init__(self, elements):
        self.elements = elements
        self.find_calls = 0

    def find_elements(self, by, locator):
        self.find_calls += 1
        return list(self.elements)

    def execute_script(self, script, element=None):
        return None


def test_click_when_stable_retries_once_after_a_stale_element():
    """The core contract: a stale node is re-resolved and the SAME control is clicked."""
    element = FakeElement(stale_times=1)
    driver = FakeDriver([element])

    result = cf.click_when_stable(driver, "//*", time=5.0)

    assert result is element, "should return the element it clicked"
    assert element.clicks == 2, "one failed (stale) click, then one successful retry"


def test_click_when_stable_gives_up_after_the_attempt_bound():
    """
    With time=0.3 the attempt count is max(int(0.3*4), 1) + 1 == 2, so a permanently
    stale node is tried exactly twice before the exception is re-raised.
    """
    element = FakeElement(stale_times=99)
    driver = FakeDriver([element])

    with pytest.raises(StaleElementReferenceException):
        cf.click_when_stable(driver, "//*", time=0.3)

    assert element.clicks == 2, "the retry loop must be bounded by the attempt count"


def test_click_when_stable_surfaces_other_errors_as_false():
    """A non-stale failure (e.g. not interactable) is reported by returning False, not raising."""

    class Boom(FakeElement):
        def click(self):
            raise RuntimeError("intercepted")

    driver = FakeDriver([Boom()])

    assert cf.click_when_stable(driver, "//*", time=1.0) is False


def test_click_when_stable_returns_false_when_nothing_is_displayed():
    """A hidden-only match must not be clicked - LinkedIn renders hidden duplicates first."""
    driver = FakeDriver([FakeElement(displayed=False)])

    assert cf.click_when_stable(driver, "//*", time=0.3) is False


def test_pick_first_displayed_skips_hidden_and_stale_candidates():
    """The first VISIBLE, still-valid element wins; hidden and stale ones are skipped."""
    hidden = FakeElement(displayed=False)
    visible = FakeElement(displayed=True)

    assert cf.pick_first_displayed([hidden, visible]) is visible


def test_wait_xp_click_delegates_to_click_when_stable(monkeypatch):
    """wait_xp_click is a named alias; it must keep routing through click_when_stable."""
    sentinel = object()
    seen = {}

    def fake_click_when_stable(driver, xpath, time=5.0, scrollTop=False):
        seen["args"] = (driver, xpath, time, scrollTop)
        return sentinel

    monkeypatch.setattr(cf, "click_when_stable", fake_click_when_stable)

    result = cf.wait_xp_click("DRIVER", "//button", time=2.0, scrollTop=True)

    assert result is sentinel
    assert seen["args"] == ("DRIVER", "//button", 2.0, True)
