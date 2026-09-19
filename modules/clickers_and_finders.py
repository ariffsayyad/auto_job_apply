'''
Author:     Sai Vignesh Golla
LinkedIn:   https://www.linkedin.com/in/saivigneshgolla/

Copyright (c) 2024-2026 Sai Vignesh Golla

License:    MIT License
            https://opensource.org/license/mit
            
GitHub:     https://github.com/GodsScion/Auto_job_applier_linkedIn

Support me: https://github.com/sponsors/GodsScion

version:    26.01.20.5.08
'''

from config.settings import click_gap, smooth_scroll
from modules.helpers import buffer, human_type, print_lg, sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException


# Matching helpers
def text_xpath(tag: str, text: str) -> str:
    '''
    XPath matching a `tag` whose text contains `text`, ignoring case and surrounding
    whitespace. LinkedIn re-words and re-cases its labels, exact matches keep breaking.
    '''
    # ponytail: translate() lowercases ASCII only, English labels are all this project targets.
    return (f'.//{tag}[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
            f'"abcdefghijklmnopqrstuvwxyz"), "{text.strip().lower()}")]')

def pick_first_displayed(elements: list[WebElement]) -> WebElement | None:
    '''
    Returns the first visible element of `elements`, or `None` if none are visible.
    LinkedIn renders hidden 0x0 duplicates that `find_element` happily returns first,
    and clicking those is what silently fails.
    '''
    for element in elements:
        try:
            if element.is_displayed(): return element
        except StaleElementReferenceException:
            continue
    return None

def wait_for_displayed(driver: WebDriver, xpath: str, time: float) -> WebElement:
    '''Waits up to `time` seconds for a *visible* element matching `xpath`, else raises `TimeoutException`.'''
    return WebDriverWait(driver, time).until(lambda d: pick_first_displayed(d.find_elements(By.XPATH, xpath)))

# Click Functions
def click_when_stable(driver: WebDriver, xpath: str, time: float=5.0, scrollTop: bool=False) -> WebElement | bool:
    '''
    Resolve the first *visible* element matching `xpath`, scroll it into view and click it,
    retrying while the node is stale.

    Why the retry: LinkedIn is a React app that re-renders the filter panel and search
    results after every click, and each render replaces the live nodes. WebDriverWait hands
    back a WebElement bound to the old node, so the `click()` that follows a successful wait
    throws `StaleElementReferenceException` - the click was found, then invalidated before it
    landed. Re-resolving the element loses nothing (the new node represents the same control)
    and turns a dropped click into a click that happens a moment later.

    Returns the clicked `WebElement`, or `False` if nothing visible matched within `time`.

    NOTE: bound the retries with an attempt COUNT, not a wall-clock deadline. The public
    parameter is named `time` (matching the rest of this module), which shadows the `time`
    module inside the function body - so any `time.monotonic()` call here would blow up with
    "'int' object has no attribute 'monotonic'".
    '''
    attempts = max(int(time * 4), 1) + 1     # ~250ms of delay per second requested
    for attempt in range(attempts):
        try:
            button = wait_for_displayed(driver, xpath, time)
            if scrollTop:   scroll_to_view(driver, button, True)
            button.click()
            buffer(click_gap)
            return button
        except StaleElementReferenceException:
            # The page re-rendered under us. Re-resolve and click the fresh node.
            if attempt == attempts - 1: raise
            sleep(0.25)
        except Exception as e:
            print_lg(f'Click Failed! Nothing visible matching "{xpath}"', f"({type(e).__name__})")
            return False

def wait_span_click(driver: WebDriver, text: str, time: float=5.0, click: bool=True, scroll: bool=True, scrollTop: bool=False) -> WebElement | bool:
    '''
    Finds the span element with the given `text`.
    - Returns `WebElement` if found, else `False` if not found.
    - Clicks on it if `click = True`.
    - Will spend a max of `time` seconds in searching for each element.
    - Will scroll to the element if `scroll = True`.
    - Will scroll to the top if `scrollTop = True`.
    '''
    if text:
        try:
            if not click:
                return wait_for_displayed(driver, text_xpath("span", text), time)
            return click_when_stable(driver, text_xpath("span", text), time, scrollTop)
        except Exception as e:
            print_lg("Click Failed! Didn't find '"+text+"'", f"({type(e).__name__})")
            return False

def wait_xp_click(driver: WebDriver | WebElement, xpath: str, time: float=5.0, scrollTop: bool=False) -> WebElement | bool:
    '''
    Same contract as `wait_span_click`, but takes an `xpath` instead of a span's text, so
    callers can anchor on an `id` or `aria-label` and scope the search to a modal.
    - Returns the clicked `WebElement`, or `False` if nothing visible matched.

    Kept as a distinct name even though it delegates straight to `click_when_stable`: the
    login, discard, Next/Review and Submit call sites all read as "click this xpath", and
    `tests/test_question_matching.py` monkeypatches `bot.wait_xp_click` by name to record
    which locators are clicked. Inlining it into `click_when_stable` would silently unpatch
    that test seam, so the alias stays.
    '''
    return click_when_stable(driver, xpath, time, scrollTop)

def multi_sel(driver: WebDriver, texts: list, time: float=5.0) -> None:
    '''
    - For each text in the `texts`, tries to find and click `span` element with that text.
    - Will spend a max of `time` seconds in searching for each element.
    '''
    for text in texts:
        # `click_when_stable` re-resolves the node on a stale-element retry, so the panel's
        # re-render after each click can't drop the next one.
        click_when_stable(driver, text_xpath("span", text), time)

def multi_sel_noWait(driver: WebDriver, texts: list, actions: ActionChains = None) -> None:
    '''
    - For each text in the `texts`, tries to find and click `span` element with that class.
    - If `actions` is provided, bot tries to search and Add the `text` to this filters list section.
    - Won't wait to search for each element, assumes that element is rendered.
    '''
    for text in texts:
        try:
            button = pick_first_displayed(driver.find_elements(By.XPATH, text_xpath("span", text)))
            if not button: raise NoSuchElementException(f'No visible span matching "{text}"')
            scroll_to_view(driver, button)
            button.click()
            buffer(click_gap)
        except Exception as e:
            if actions: company_search_click(driver,actions,text)
            else:   print_lg("Click Failed! Didn't find '"+text+"'", f"({type(e).__name__})")

def boolean_button_click(driver: WebDriver, actions: ActionChains, text: str) -> None:
    '''
    Tries to click on the boolean button with the given `text` text.
    '''
    try:
        list_container = driver.find_element(By.XPATH, text_xpath("h3", text) + '/ancestor::fieldset')
        # The switch input itself is often visually hidden by design, so don't filter it on displayed.
        button = list_container.find_element(By.XPATH, './/input[@role="switch"]')
        scroll_to_view(driver, button)
        actions.move_to_element(button).click().perform()
        buffer(click_gap)
    except Exception as e:
        print_lg("Click Failed! Didn't find '"+text+"'", f"({type(e).__name__})")

# Find functions
def find_by_class(driver: WebDriver, class_name: str, time: float=5.0) -> WebElement:
    '''
    Waits for a max of `time` seconds for element to be found and returns the `WebElement`.
    Raises `TimeoutException` if nothing matched - it does not return an exception object.
    '''
    return WebDriverWait(driver, time).until(EC.presence_of_element_located((By.CLASS_NAME, class_name)))

# Scroll functions
def scroll_to_view(driver: WebDriver, element: WebElement, top: bool = False, smooth_scroll: bool = smooth_scroll) -> None:
    '''
    Scrolls the `element` to view.
    - `smooth_scroll` will scroll with smooth behavior.
    - `top` will scroll to the `element` to top of the view.
    '''
    # Callers scope searches to a modal and pass that WebElement in here as `driver`.
    # Only the WebDriver can run scripts; every element knows its own driver as `.parent`.
    if not hasattr(driver, "execute_script"): driver = element.parent
    if top:
        return driver.execute_script('arguments[0].scrollIntoView();', element)
    behavior = "smooth" if smooth_scroll else "instant"
    return driver.execute_script('arguments[0].scrollIntoView({block: "center", behavior: "'+behavior+'" });', element)

# Enter input text functions
def text_input_by_ID(driver: WebDriver, id: str, value: str, time: float=5.0) -> None | Exception:
    '''
    Enters `value` into the input field with the given `id` if found, else throws NotFoundException.
    - `time` is the max time to wait for the element to be found.
    '''
    username_field = WebDriverWait(driver, time).until(EC.presence_of_element_located((By.ID, id)))
    username_field.send_keys(Keys.CONTROL + "a")
    human_type(username_field, value)

def try_xp(driver: WebDriver, xpath: str, click: bool=True) -> WebElement | bool:
    try:
        if click:
            driver.find_element(By.XPATH, xpath).click()
            buffer(click_gap)
            return True
        else:
            return driver.find_element(By.XPATH, xpath)
    except NoSuchElementException: return False     # simply not on the page, nothing to report
    except Exception as e:
        print_lg(f'Failed to {"click" if click else "find"} element with xpath "{xpath}"!', e)
        return False

def try_linkText(driver: WebDriver, linkText: str) -> WebElement | bool:
    try:    return driver.find_element(By.LINK_TEXT, linkText)
    except NoSuchElementException:  return False
    except Exception as e:
        print_lg(f'Failed to find link "{linkText}"!', e)
        return False

def try_find_by_classes(driver: WebDriver, classes: list[str]) -> WebElement:
    '''Return the first element matching any class in `classes`, else raise `ValueError`.

    The `ValueError` is RAISED, not returned, so it does not belong in the return annotation.
    '''
    for cla in classes:
        try:    return driver.find_element(By.CLASS_NAME, cla)
        except NoSuchElementException: pass
        except Exception as e:  print_lg(f'Failed to find element with class "{cla}"!', e)
    raise ValueError("Failed to find an element with given classes")

def company_search_click(driver: WebDriver, actions: ActionChains, companyName: str) -> None:
    '''
    Tries to search and Add the company to company filters list.
    '''
    wait_span_click(driver,"Add a company",1)
    search = driver.find_element(By.XPATH,"(.//input[@placeholder='Add a company'])[1]")
    search.send_keys(Keys.CONTROL + "a")
    human_type(search, companyName)
    buffer(3)
    actions.send_keys(Keys.DOWN).perform()
    actions.send_keys(Keys.ENTER).perform()
    print_lg(f'Tried searching and adding "{companyName}"')

def text_input(actions: ActionChains, textInputEle: WebElement | bool, value: str, textFieldName: str = "Text") -> None | Exception:
    if textInputEle:
        sleep(1)
        # actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        textInputEle.clear()
        human_type(textInputEle, value.strip())
        sleep(2)
        actions.send_keys(Keys.ENTER).perform()
    else:
        print_lg(f'{textFieldName} input was not given!')