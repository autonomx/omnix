"""The play screen's core tasks in a real browser (RQ-7.7), at a phone's 360 x 740 and a desktop's 1,440 x 900.

A player starts a campaign in a bundled world (Aurelia), takes a quest, travels, buys, undoes the purchase, buys
again and sells from the pack, takes off and puts on what they wear, finishes the quest, rests, names a save point
and returns to it, fights on the grid, and comes back after time away. Each task is driven through the play screen
only; whether it happened is read from the campaign itself (``GET /api/rpg/sessions/{id}``), never from the page's
wording. Each viewport also gets an axe pass, with each of the play bar's panels open as well (serious or critical
issues fail), and a check that the page scrolls neither sideways nor down: the story and composer stay on screen.

It needs a running gateway (PostgreSQL, sign-in off, the web app's origin allowed) and the web app pointed at it::

    OMNIX_AUTH_MODE=disabled OMNIX_GATEWAY_PORT=8765 OMNIX_ALLOWED_ORIGINS=http://127.0.0.1:5180 python -m app.composition.gateway.main
    VITE_GATEWAY_ORIGIN=http://127.0.0.1:8765 npm --prefix web run dev -- --port 5180 --strictPort
    python scripts/rpg_core_tasks.py --web http://127.0.0.1:5180 --gateway http://127.0.0.1:8765 --out report.json

RPG's model route must answer, on the owner's gate model (Haiku, effort low): a typed turn is read by it, and an
unread one is "Nothing comes of that". The outcome of a turn is still the game's own, and its prose may come later or
not at all. A database without the bundled world gets it installed and adopted first. Python Playwright drives Chromium (``--chrome`` names a browser build when Playwright's own is older).
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
WORLD_ID = "world:aurelia-echoes-beyond-the-gate"
BUNDLE = ROOT / "resources" / "examples" / "rpg" / "world-bundles" / "aurelia-echoes-beyond-the-gate.omnix-world.zip"
PANELS = ("Pack", "Character", "Journal", "World")
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
    page_scroll_px: int = 0
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
        self.close_panel()
        self.page.get_by_placeholder("What do you want to do?").fill(command)
        self.button("Submit RPG turn").click()
        self.page.wait_for_timeout(300)
        self.idle()

    def session_id(self) -> str:
        return self.page.locator("input[name=sessionId]").input_value()

    def scene(self) -> str:
        return self.page.locator("#rpg-story-scene-title").inner_text()

    def open_menu(self, card: str = "") -> None:
        """The Campaign Menu, and one of its cards (named by its title; a card's name goes on with what it does)."""
        self.button("Campaign Menu").click()
        if card:
            self.page.get_by_role("dialog").get_by_role("button", name=re.compile(f"^{re.escape(card)}")).first.click()

    def bar_button(self, name: str) -> Any:
        return self.page.get_by_role("navigation", name="Play panels").get_by_role("button", name=name, exact=True)

    def open_panel(self, name: str) -> Any:
        """A panel of the play bar, open; what it holds."""
        button = self.bar_button(name)
        if button.get_attribute("aria-expanded") != "true":
            button.click()
        return self.page.locator("#rpg-play-panel")

    def close_panel(self) -> None:
        close = self.page.get_by_role("button", name="Close panel", exact=True)
        if close.count():
            close.click()

    def inventory_item(self, name: str) -> list[str]:
        """Selects a carried item; the actions its toolbar offers."""
        self.open_panel("Pack")
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


def install_world(gateway: str) -> None:
    """The bundled world, imported and adopted, on a database that does not have it yet."""
    base = gateway.rstrip("/")
    with urllib.request.urlopen(f"{base}/api/rpg/worlds", timeout=30) as response:
        if any(world.get("id") == WORLD_ID for world in json.load(response).get("worlds") or ()):
            return

    def post(path: str, body: bytes, content_type: str) -> dict[str, Any]:
        request = urllib.request.Request(f"{base}{path}", data=body, method="POST",
                                         headers={"Content-Type": content_type, "X-Omnix-Client": "rpg-core-tasks"})
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)

    imported = post("/api/rpg/worlds/import", BUNDLE.read_bytes(), "application/zip")
    post(f"/api/rpg/worlds/{WORLD_ID}/adopt", json.dumps({"bundle_sha256": imported["bundle_sha256"]}).encode(),
         "application/json")


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
        screen.play("I ask Miri Kestrel to register me with the guild.")  # the quest's steps: reach, register, a companion
        screen.play("I ask Miri Kestrel to join my party as my companion.")
        check(campaign.quest("First Night in Aurelia") == "completed", "First Night in Aurelia is not complete")
        check(campaign.inventory().get("Wayfarer Sigil", 0) >= 1, "no reward")
        return "First Night in Aurelia completed"

    def rest() -> str:
        turns = campaign.turn_count()
        # It prepares the command and closes the panel; the player sends it.
        screen.open_panel("Character").get_by_role("button", name="Rest", exact=True).click()
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
        screen.play("go to Starfall Village")
        screen.play("go to Skybridge Pass")  # where no one lives: the world's creatures are met there
        check(campaign.location().endswith("skybridge-pass"), f"at {campaign.location()}")
        if not campaign.combat().get("active"):  # nothing barred the way: seek a wolf out
            screen.play("I attack the Echo Wolf.")
        check(campaign.combat().get("active") is True, "no fight began")
        foe = next(str(row.get("name")) for row in campaign.combat()["participants"].values() if row.get("side") == "enemy")
        grid = page.get_by_role("region", name="Local tactical map")
        attack = grid.get_by_role("button", name=re.compile(f"^Attack {re.escape(foe)}$"))
        attack.wait_for(timeout=30_000)
        check(grid.get_by_text(f"{foe} · hostile").count() > 0, f"the {foe} is not listed on the grid")
        log = len(campaign.combat().get("combat_log") or ())
        attack.click()
        check(until(lambda: len(campaign.combat().get("combat_log") or ()) > log or not campaign.combat().get("active")),
              "the grid attack was no blow")
        for _ in range(30):
            if not campaign.combat().get("active"):
                break
            screen.play(f"I attack the {foe}.")
        check(not campaign.combat().get("active"), "the fight did not end")
        return f"{foe} struck from the grid; {campaign.combat().get('ended_reason')}"

    def here_and_map() -> str:
        """Who is here and where the paths lead, and the map: beside the story, or in the World panel on a phone."""
        screen.close_panel()
        paths = page.get_by_role("group", name="Paths from here")
        if not paths.is_visible():
            screen.open_panel("World")
        check(paths.get_by_role("button").count() > 0, "no paths are offered from here")
        target = paths.get_by_role("button").first
        place = target.inner_text()
        target.click()  # it prepares the command and closes the panel; the player sends it or not
        check(place in page.get_by_placeholder("What do you want to do?").input_value(), f"{place} wrote no command")
        page.get_by_placeholder("What do you want to do?").fill("")
        if not screen.button("Open interactive map").is_visible():
            screen.open_panel("World")
        screen.button("Open interactive map").click()
        page.get_by_role("region", name="Local tactical map").wait_for(timeout=30_000)
        screen.button("Close map").click()
        screen.close_panel()
        return f"a path to {place}; the map opens"

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
                       ("here_and_map", here_and_map), ("buy_and_undo", buy_and_undo), ("buy_and_sell", buy_and_sell), ("equip", equip),
                       ("finish_quest", finish_quest), ("rest", rest), ("save_point", save_point),
                       ("fight_on_grid", fight_on_grid), ("resume_after_away", resume_after_away)):
        if name != "start" and campaign is None:
            result.tasks.append(Task(name, detail="skipped: no campaign"))
            continue
        task(name, body)

    page.screenshot(path=str(out_dir / f"core-{viewport}.png"))
    page.add_script_tag(content=AXE.read_text(encoding="utf-8"))

    def audit(where: str) -> None:
        found = page.evaluate("""async () => (await axe.run()).violations
            .map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help }))""")
        result.axe.extend({**row, "where": where} for row in found)
        result.overflow_px = max(result.overflow_px, page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"))
        result.page_scroll_px = max(result.page_scroll_px, page.evaluate(
            "() => document.documentElement.scrollHeight - document.documentElement.clientHeight"))

    screen.close_panel()
    audit("play")
    for panel in PANELS:
        screen.open_panel(panel)
        page.wait_for_timeout(500)
        page.screenshot(path=str(out_dir / f"core-{viewport}-{panel.lower()}.png"))
        audit(panel)
        screen.close_panel()
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
    install_world(args.gateway)
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
            "horizontal_overflow_px": run.overflow_px, "page_scroll_px": run.page_scroll_px, "errors": run.errors[:20],
        } for run in runs],
    }
    report["all_pass"] = all(
        run["passed"] == run["total"] and not run["axe_serious_or_critical"] and run["horizontal_overflow_px"] <= 0
        and run["page_scroll_px"] <= 0
        for run in report["runs"]
    )
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
