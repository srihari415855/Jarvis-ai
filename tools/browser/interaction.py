"""Browser interaction utilities for JARVIS Phase 3.

Provides structured Playwright element location, actions, and safety validation.
Prefers accessibility selectors (roles, accessible names, text) over raw coordinates.
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("jarvis.tools.browser.interaction")


class ElementTarget(BaseModel):
    """Structured locator specification for a webpage element."""
    role: Optional[str] = Field(default=None, description="Accessible role, e.g. 'button', 'textbox', 'link'")
    name: Optional[str] = Field(default=None, description="Accessible name or label, e.g. 'Search', 'Submit'")
    text: Optional[str] = Field(default=None, description="Visible text content")
    selector: Optional[str] = Field(default=None, description="CSS selector or locator string")
    placeholder: Optional[str] = Field(default=None, description="Input placeholder text")
    label: Optional[str] = Field(default=None, description="Associated label text")

    def has_criteria(self) -> bool:
        return any(
            v is not None and str(v).strip() != ""
            for v in (self.role, self.name, self.text, self.selector, self.placeholder, self.label)
        )


class BrowserActionError(Exception):
    """Exception raised when an interaction fails."""
    pass


def resolve_locator(page: Any, target: ElementTarget) -> Any:
    """Resolve a Playwright Locator from structured ElementTarget.
    
    Prefers accessible roles and names, then labels, then text, then CSS selectors.
    """
    if not target.has_criteria():
        raise BrowserActionError("ElementTarget must specify at least one criteria (role, name, text, selector, label).")

    # 1. Role + Name
    if target.role:
        role_kwargs: Dict[str, Any] = {}
        if target.name:
            role_kwargs["name"] = target.name
        return page.get_by_role(target.role, **role_kwargs)

    # 2. Label
    if target.label:
        return page.get_by_label(target.label)

    # 3. Placeholder
    if target.placeholder:
        return page.get_by_placeholder(target.placeholder)

    # 4. Text
    if target.text:
        return page.get_by_text(target.text)

    # 5. CSS / XPath Selector
    if target.selector:
        return page.locator(target.selector)

    raise BrowserActionError(f"Unable to resolve locator for target: {target}")


def _resolve_visible_element(locator: Any) -> Any:
    """Select the first visible element among matching candidates."""
    try:
        count = locator.count()
        if count <= 1:
            return locator.first
        for i in range(count):
            candidate = locator.nth(i)
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
    except Exception:
        pass
    return locator.first


def perform_click(
    page: Any,
    target: ElementTarget,
    timeout_ms: int = 5000,
) -> Dict[str, Any]:
    """Safely click an element identified by structured target."""
    locator = resolve_locator(page, target)
    count = locator.count()
    if count == 0:
        raise BrowserActionError(f"Element not found on page for target: {target.model_dump(exclude_none=True)}")

    target_el = _resolve_visible_element(locator)
    target_el.click(timeout=timeout_ms)
    logger.info(f"Clicked element matching target: {target.model_dump(exclude_none=True)}")
    return {
        "action": "click",
        "target": target.model_dump(exclude_none=True),
        "status": "clicked",
    }


def perform_fill(
    page: Any,
    target: ElementTarget,
    value: str,
    press_enter: bool = False,
    timeout_ms: int = 5000,
) -> Dict[str, Any]:
    """Safely fill/type into an input element and optionally press Enter."""
    locator = resolve_locator(page, target)
    count = locator.count()
    if count == 0:
        raise BrowserActionError(f"Input element not found on page for target: {target.model_dump(exclude_none=True)}")

    target_el = _resolve_visible_element(locator)
    target_el.fill(value, timeout=timeout_ms)
    logger.info(f"Filled value into target: {target.model_dump(exclude_none=True)}")

    if press_enter:
        target_el.press("Enter")
        logger.info("Pressed Enter after filling value")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass

    return {
        "action": "fill",
        "target": target.model_dump(exclude_none=True),
        "value": value,
        "pressed_enter": press_enter,
        "status": "filled",
    }


def perform_press(
    page: Any,
    key: str,
    target: Optional[ElementTarget] = None,
    timeout_ms: int = 5000,
) -> Dict[str, Any]:
    """Press a keyboard key, optionally focused on target element."""
    if target and target.has_criteria():
        locator = resolve_locator(page, target)
        locator.first.press(key, timeout=timeout_ms)
    else:
        page.keyboard.press(key)

    logger.info(f"Pressed key: '{key}'")
    return {
        "action": "press",
        "key": key,
        "status": "pressed",
    }


def perform_scroll(
    page: Any,
    direction: str = "down",
    amount: int = 500,
) -> Dict[str, Any]:
    """Scroll the page in the specified direction."""
    delta_y = amount if direction.lower() == "down" else -amount
    page.mouse.wheel(0, delta_y)
    logger.info(f"Scrolled page {direction} by {amount}px")
    return {
        "action": "scroll",
        "direction": direction,
        "amount": amount,
        "status": "scrolled",
    }
