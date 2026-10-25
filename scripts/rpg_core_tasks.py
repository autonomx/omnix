"""The play screen's core tasks in a real browser (RQ-7.7), at a phone's 360 x 740 and a desktop's 1,440 x 900.

A player starts a campaign in a bundled world (Aurelia), takes a quest, travels, buys, undoes the purchase, buys
again and sells from the pack, takes off and puts on what they wear, finishes the quest, rests, names a save point
and returns to it, fights on the grid, and comes back after time away. Each task is driven through the play screen
only; whether it happened is read from the campaign itself (``GET /api/rpg/sessions/{id}``), never from the page's
wording. Each viewport also gets an axe pass (serious or critical issues fail) and a check that nothing scrolls
sideways.

It needs a running gateway (PostgreSQL, sign-in off) and the web app pointed at it, for example::

    OMNIX_AUTH_MODE=disabled OMNIX_GATEWAY_PORT=8765 python -m app.composition.gateway.main
    VITE_GATEWAY_ORIGIN=http://127.0.0.1:8765 npm --prefix web run dev -- --port 5180 --strictPort
    python scripts/rpg_core_tasks.py --web http://127.0.0.1:5180 --gateway http://127.0.0.1:8765 --out report.json

The storyteller need not be configured: the outcome of a turn is the game's own, and its prose may come later or not
at all. Python Playwright drives Chromium (``--chrome`` names a browser build when Playwright's own is older).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
AXE = ROOT / "node_modules" / "axe-core" / "axe.min.js"
VIEWPORTS = {"phone": (360, 740), "desktop": (1440, 900)}
WORLD = "Aurelia: Echoes Beyond the Gate"
TURN_SECONDS = 120.0


@dataclass
class Task:
    name: str
    ok: bool = False
    seconds: float = 0.0
    detail: str = ""


@dataclass
class Run:
    viewport: str
    tasks: list[Task] = field(default_factory=list)
    session_id: str = ""
    axe: list[dict[str, Any]] = field(default_factory=list)
    overflow_px: int = 0
    errors: list[str] = field(default_factory=list)


class Campaign:
    """The campaign as the gateway stores it: what each task is checked against."""

    def __init__(self, gateway: str, session_id: str) -> None:
        self.gateway, self.session_id = gateway.rstrip("/"), session_id

    def session(self) -> dict[str, Any]:
        with urllib.request.urlopen(f"{self.gateway}/api/rpg/sessions/{self.session_id}", timeout=30) as response:
            return json.load(response)["session"]

    def state(self) -> dict[str, Any]:
        return dict(self.session().get("state") or {})

    def inventory(self) -> dict[str, int]:
        items: dict[str, int] = {}
        for item in self.state().get("player", {}).get("inventory") or ():
            items[str(item.get("name"))] = items.get(str(item.get("name")), 0) + int(item.get("quantity") or 0)
        return items

    def purse(self) -> int:
        currency = self.state().get("player", {}).get("currency") or {}
        return sum(int(currency.get(coin) or 0) * rate for coin, rate in (("gold", 100), ("silver", 10), ("copper", 1)))

    def quest(self, title: str) -> str:
        return next((str(quest.get("status")) for quest in self.state().get("quests") or () if quest.get("title") == title), "")

    def turn_count(self) -> int:
        return int(self.state().get("turn_count") or 0)

    def location(self) -> str:
        simulation = dict(self.session().get("simulation_state") or {})
        return str((simulation.get("player_state") or {}).get("location_id") or "")

    def combat(self) -> dict[str, Any]:
        return dict((self.session().get("simulation_state") or {}).get("combat_state") or {})

    def equipped(self, name: str) -> bool:
        return any(entry.get("name") == name for entry in self.state().get("player", {}).get("equipment") or ())


class Screen:
    """The play screen, used the way a player would."""

    def __init__(self, page: Any) -> None:
        self.page = page

    def button(self, name: str) -> Any:
        return self.page.get_by_role("button", name=name, exact=True)

    def log(self) -> str:
        return self.page.locator("[role=log]").first.inner_text()

    def idle(self, timeout: float = TURN_SECONDS) -> None:
        """Until the turn on its way has its outcome: the submit button is back."""
        self.page.get_by_role("button", name="Submit RPG turn", exact=True).wait_for(state="visible", timeout=timeout * 1000)
        self.page.wait_for_function(
            "() => ![...document.querySelectorAll('[role=log] p')].some(p => p.innerText.includes('Considering the scene'))",
            timeout=timeout * 1000,
        )

    def play(self, command: str) -> None:
        self.page.get_by_placeholder("What do you want to do?").fill(command)
        self.button("Submit RPG turn").click()
        self.page.wait_for_timeout(300)
        self.idle()

    def session_id(self) -> str:
        return self.page.locator("select[name=sessionId]").input_value()

    def scene(self) -> str:
        return self.page.locator("#rpg-story-scene-title").inner_text()

    def open_menu(self, card: str = "") -> None:
        """The Campaign Menu, and one of its cards (named by its title; a card's name goes on with what it does)."""
        self.button("Campaign Menu").click()
        if card:
            self.page.get_by_role("dialog").get_by_role("button", name=re.compile(f"^{re.escape(card)}")).first.click()

    def inventory_item(self, name: str) -> list[str]:
        """Selects a carried item; the actions its toolbar offers."""
        self.page.get_by_role("tab", name="Inventory", exact=True).click()
        self.page.get_by_role("group", name="Inventory item slots").get_by_role("button", name=name, exact=True).click()
        self.page.wait_for_timeout(500)
        return [button.get_attribute("aria-label") or "" for button in self.item_actions().get_by_role("button").all()]

    def item_actions(self) -> Any:
        return self.page.get_by_role("toolbar", name="Selected item contextual actions")


def until(check: Callable[[], bool], timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.5)
    return check()


def run_viewport(browser: Any, args: argparse.Namespace, viewport: str, out_dir: Path) -> Run:
    width, height = VIEWPORTS[viewport]
    result = Run(viewport=viewport)
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.clock.install()
    page.on("pageerror", lambda exc: result.errors.append(f"pageerror: {exc}"))
    page.on("response", lambda r: result.errors.append(f"http {r.status} {r.request.method} {r.url}")
            if r.status >= 500 else None)
    page.on("dialog", lambda dialog: dialog.accept())
    screen = Screen(page)
    campaign: Campaign | None = None

    def task(name: str, body: Callable[[], str]) -> None:
        started = time.monotonic()
        entry = Task(name)
        try:
            entry.detail = body() or ""
            entry.ok = True
        except Exception as error:  # a task that fails is reported, and the next one still runs
            entry.detail = f"{type(error).__name__}: {str(error).splitlines()[0][:300]}"
            page.screenshot(path=str(out_dir / f"core-{viewport}-{name}.png"))
        entry.seconds = round(time.monotonic() - started, 1)
        result.tasks.append(entry)

    def check(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    page.goto(f"{args.web}/rpg", wait_until="networkidle")

    def start() -> str:
        nonlocal campaign
        screen.button("Worlds & Campaigns").click()
        card = page.locator("article, li, section").filter(has=page.get_by_role("heading", name=WORLD, exact=True)).last
        card.get_by_role("button", name="Play", exact=True).click()
        page.get_by_label("Name", exact=True).first.fill(f"Core {viewport}")
        screen.button("Launch Campaign").click()
        page.locator("[role=dialog]").wait_for(state="detached", timeout=120_000)
        screen.idle()
        result.session_id = screen.session_id()
        campaign = Campaign(args.gateway, result.session_id)
        check(campaign.location().endswith("arrival-grove"), f"opened at {campaign.location()}")
        return result.session_id

    def take_quest() -> str:
        screen.play("I accept the quest Voices in the Phone.")
        check(campaign.quest("Voices in the Phone") == "active", "the quest is not active")
        return "Voices in the Phone active"

    def travel() -> str:
        screen.play("go to Starfall Village")
        check(campaign.location().endswith("starfall-village"), f"at {campaign.location()}")
        check(until(lambda: "Starfall Village" in screen.scene(), 15), f"the scene says {screen.scene()!r}")
        return campaign.location()

    def buy_and_undo() -> str:
        purse, potions = campaign.purse(), campaign.inventory().get("Healing Potion", 0)
        screen.play("I buy a Healing Potion from Brindle Gearwing.")
        check(campaign.inventory().get("Healing Potion", 0) == potions + 1, "no potion bought")
        paid = purse - campaign.purse()
        check(paid > 0, "nothing paid")
        screen.button("Undo last turn").click()
        page.wait_for_timeout(300)
        screen.idle()
        check(until(lambda: campaign.purse() == purse), f"the purse is {campaign.purse()} after undo, not {purse}")
        check(campaign.inventory().get("Healing Potion", 0) == potions, "the potion stayed after undo")
        return f"paid {paid} copper, undone"

    def buy_and_sell() -> str:
        screen.play("I buy a Healing Potion from Brindle Gearwing.")
        bought = campaign.inventory().get("Healing Potion", 0)
        check(bought >= 1, "no potion bought")
        purse = campaign.purse()
        offered = screen.inventory_item("Healing Potion")
        check("Sell" in offered, f"the potion offers {offered}")
        screen.item_actions().get_by_role("button", name="Sell", exact=True).click()  # a typed turn
        page.wait_for_timeout(300)
        screen.idle()
        check(until(lambda: campaign.inventory().get("Healing Potion", 0) == bought - 1), "the potion was not sold")
        check(campaign.purse() > purse, "nothing earned")
        return f"sold for {campaign.purse() - purse} copper"

    def equip() -> str:
        name = "Travel Cloak"
        check(campaign.equipped(name), f"{name} is not worn at the start")
        offered = screen.inventory_item(name)
        check("Unequip" in offered, f"{name} offers {offered}")
        screen.item_actions().get_by_role("button", name="Unequip", exact=True).click()
        check(until(lambda: not campaign.equipped(name)), f"{name} still worn")
        offered = screen.inventory_item(name)
        check("Equip" in offered, f"{name} offers {offered}")
        screen.item_actions().get_by_role("button", name="Equip", exact=True).click()
        check(until(lambda: campaign.equipped(name)), f"{name} not worn again")
        return f"{name} off and on"

    def finish_quest() -> str:
        screen.play("go to Wayfarers' Guild")
        check(campaign.quest("First Night in Aurelia") == "completed", "First Night in Aurelia is not complete")
        check(campaign.inventory().get("Wayfarer Sigil", 0) >= 1, "no reward")
        return "First Night in Aurelia completed"

    def rest() -> str:
        turns = campaign.turn_count()
        screen.button("Rest").click()  # it prepares the command; the player sends it
        check("rest" in page.get_by_placeholder("What do you want to do?").input_value().lower(), "Rest wrote no command")
        screen.button("Submit RPG turn").click()
        page.wait_for_timeout(300)
        screen.idle()
        check(until(lambda: campaign.turn_count() > turns), "resting was no turn")
        return f"turn {campaign.turn_count()}"

    def save_point() -> str:
        location = campaign.location()
        screen.open_menu("Save points")
        page.get_by_label("Name this moment").fill("At the guild")
        screen.button("Save here").click()
        page.get_by_role("list", name="Your save points").get_by_text("At the guild").wait_for(timeout=15_000)
        screen.button("Close").click()
        screen.play("go to Starfall Village")
        check(campaign.location() != location, "did not leave")
        screen.open_menu("Save points")
        screen.button("Return here").first.click()
        page.wait_for_timeout(300)
        screen.idle()
        check(until(lambda: campaign.location() == location), f"returned to {campaign.location()}, not {location}")
        return f"back at {location}"

    def fight_on_grid() -> str:
        screen.play("go to Starfall Grove")
        screen.play("I attack the Echo Wolf.")
        check(campaign.combat().get("active") is True, "no fight began")
        screen.button("Open interactive map").click()
        grid = page.get_by_role("region", name="Local tactical map")
        grid.wait_for(timeout=30_000)
        moved = False
        for cell in grid.locator(".rpg-grid-reachable").all()[:6]:
            cell.click(force=True)
            move = page.get_by_role("button", name="Move here")
            if move.count():
                before = campaign.session().get("runtime_state", {}).get("state_revision")
                move.first.click()
                moved = until(lambda: campaign.session().get("runtime_state", {}).get("state_revision") != before, 20)
                break
        attack = grid.get_by_role("button", name=re.compile("^Attack .*Echo Wolf"))
        check(attack.count() > 0, "no Echo Wolf to attack on the grid")
        attack.first.click()
        page.wait_for_timeout(1500)
        screen.button("Close map").click()
        for _ in range(30):
            if not campaign.combat().get("active"):
                break
            screen.play("I attack the Echo Wolf.")
        check(not campaign.combat().get("active"), "the fight did not end")
        return f"moved on the grid: {moved}; {campaign.combat().get('ended_reason')}"

    def resume_after_away() -> str:
        turns_before = campaign.session().get("runtime_state", {}).get("state_revision")
        page.evaluate("""() => {
            Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        page.clock.fast_forward("15:00")
        page.evaluate("""() => {
            Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        check(until(lambda: campaign.session().get("runtime_state", {}).get("state_revision") != turns_before, 60),
              "coming back ran no turn")
        until(lambda: "while you were away" in screen.log(), 30)
        check("while you were away" in screen.log(), "the story log does not say the world went on")
        return "the world went on"

    for name, body in (("start", start), ("take_quest", take_quest), ("travel", travel),
                       ("buy_and_undo", buy_and_undo), ("buy_and_sell", buy_and_sell), ("equip", equip),
                       ("finish_quest", finish_quest), ("rest", rest), ("save_point", save_point),
                       ("fight_on_grid", fight_on_grid), ("resume_after_away", resume_after_away)):
        if name != "start" and campaign is None:
            result.tasks.append(Task(name, detail="skipped: no campaign"))
            continue
        task(name, body)

    page.screenshot(path=str(out_dir / f"core-{viewport}.png"))
    page.add_script_tag(content=AXE.read_text(encoding="utf-8"))
    result.axe = page.evaluate("""async () => (await axe.run()).violations
        .map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help }))""")
    result.overflow_px = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    context.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--web", default="http://127.0.0.1:5180")
    parser.add_argument("--gateway", default="http://127.0.0.1:8765")
    parser.add_argument("--viewport", choices=[*VIEWPORTS, "both"], default="both")
    parser.add_argument("--chrome", default="", help="a Chromium executable, when Playwright's own build is older")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--out", default="", help="write the report here (JSON); screenshots go beside it")
    args = parser.parse_args(argv)
    from playwright.sync_api import sync_playwright

    out_dir = Path(args.out).parent if args.out else ROOT / "output" / "rpg-core-tasks"
    out_dir.mkdir(parents=True, exist_ok=True)
    viewports = list(VIEWPORTS) if args.viewport == "both" else [args.viewport]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed, executable_path=args.chrome or None)
        runs = [run_viewport(browser, args, viewport, out_dir) for viewport in viewports]
        browser.close()

    report = {
        "measured_on": time.strftime("%Y-%m-%d", time.gmtime()),
        "runs": [{
            "viewport": run.viewport, "size": VIEWPORTS[run.viewport], "session_id": run.session_id,
            "tasks": [vars(task) for task in run.tasks],
            "passed": sum(task.ok for task in run.tasks), "total": len(run.tasks),
            "axe_serious_or_critical": [v for v in run.axe if v["impact"] in ("serious", "critical")],
            "axe_other": [v["id"] for v in run.axe if v["impact"] not in ("serious", "critical")],
            "horizontal_overflow_px": run.overflow_px, "errors": run.errors[:20],
        } for run in runs],
    }
    report["all_pass"] = all(
        run["passed"] == run["total"] and not run["axe_serious_or_critical"] and run["horizontal_overflow_px"] <= 0
        for run in report["runs"]
    )
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
