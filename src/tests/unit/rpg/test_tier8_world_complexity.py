"""Tests for TIER 8: World Complexity Layer.

Tests for:
    - EconomySystem: Market supply/demand, price simulation, trade flows
    - DynamicQuestGenerator: Quest generation from world state
    - PoliticalSystem: Leadership, coups, political events
"""
from __future__ import annotations

import os
import sys

# Add app directory to path (same as other test files)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

import random
from unittest.mock import MagicMock, patch

import pytest
from rpg.story.dynamic_quest_generator import DynamicQuestGenerator
from rpg.world.economy_system import EconomySystem, Market
from rpg.world.faction_system import Faction, FactionSystem
from rpg.world.political_system import Leader, PoliticalSystem


class TestMarket:
    """Tests for the Market class."""

    def test_market_creation(self):
        """Test market can be created with goods."""
        m = Market("town")
        m.add_good("food", supply=1.0, demand=1.0, price=1.0)

        assert m.location_id == "town"
        assert "food" in m.goods
        assert m.goods["food"]["supply"] == 1.0
        assert m.goods["food"]["demand"] == 1.0
        assert m.goods["food"]["price"] == 1.0

    def test_market_price_increases_when_supply_low(self):
        """Test that low supply causes price spike."""
        m = Market("town")
        m.goods["food"] = {"supply": 0.1, "demand": 1.0, "price": 1.0}

        m.update_prices()

        assert m.goods["food"]["price"] > 1.0

    def test_market_price_decreases_when_oversupply(self):
        """Test that high supply causes price drop."""
        m = Market("town")
        m.goods["iron"] = {"supply": 2.0, "demand": 0.5, "price": 1.0}

        m.update_prices()

        assert m.goods["iron"]["price"] < 1.0

    def test_market_price_spikes_on_zero_supply(self):
        """Test that zero supply causes 50% price spike."""
        m = Market("town")
        m.goods["herbs"] = {"supply": 0.0, "demand": 1.0, "price": 1.0}

        m.update_prices()

        assert m.goods["herbs"]["price"] == 1.5

    def test_shortage_event_generated(self):
        """Test that shortage event is generated when supply < 0.2."""
        m = Market("town")
        m.goods["food"] = {"supply": 0.1, "demand": 1.0, "price": 1.0}

        events = m.update_prices()

        shortage_events = [e for e in events if e["type"] == "shortage"]
        assert len(shortage_events) > 0
        assert shortage_events[0]["good"] == "food"
        assert shortage_events[0]["location"] == "town"

    def test_supply_adjustment(self):
        """Test supply can be adjusted."""
        m = Market("town")
        m.add_good("food", supply=0.5, demand=1.0, price=1.0)

        m.adjust_supply("food", -0.3)

        assert m.goods["food"]["supply"] == pytest.approx(0.2)

    def test_demand_adjustment(self):
        """Test demand can be adjusted."""
        m = Market("town")
        m.add_good("food", supply=1.0, demand=0.5, price=1.0)

        m.adjust_demand("food", 0.5)

        assert m.goods["food"]["demand"] == pytest.approx(1.0)

    def test_price_clamped_to_range(self):
        """Test that price is clamped to reasonable range."""
        m = Market("town")
        # Create extreme demand/supply ratio
        m.goods["gold"] = {"supply": 0.01, "demand": 10.0, "price": 5.0}

        # Multiple updates should eventually clamp
        for _ in range(20):
            m.update_prices()

        assert m.goods["gold"]["price"] <= 10.0
        assert m.goods["gold"]["price"] >= 0.01


class TestEconomySystem:
    """Tests for the EconomySystem class."""

    def test_add_and_remove_market(self):
        """Test market management."""
        economy = EconomySystem()
        market = Market("town")
        economy.add_market(market)

        assert "town" in economy.markets

        removed = economy.remove_market("town")
        assert removed is market
        assert "town" not in economy.markets

    def test_trade_route_management(self):
        """Test trade route add/remove."""
        economy = EconomySystem()
        economy.add_trade_route("mine", "town", "iron")

        assert ("mine", "town", "iron") in economy.trade_routes

        assert True is economy.remove_trade_route("mine", "town", "iron")
        assert ("mine", "town", "iron") not in economy.trade_routes

    def test_trade_flow_events(self):
        """Test that trade flows generate events when price diff is significant."""
        economy = EconomySystem()

        mine = Market("mine")
        mine.add_good("iron", supply=1.0, demand=0.2, price=0.5)
        economy.add_market(mine)

        town = Market("town")
        town.add_good("iron", supply=0.1, demand=1.0, price=2.0)
        economy.add_market(town)

        economy.add_trade_route("mine", "town", "iron")

        events = economy.update()

        trade_events = [e for e in events if e["type"] == "trade_flow"]
        assert len(trade_events) > 0
        assert trade_events[0]["from"] == "mine"
        assert trade_events[0]["to"] == "town"
        assert trade_events[0]["good"] == "iron"

    def test_no_trade_when_markets_missing(self):
        """Test that missing markets don't cause crashes."""
        economy = EconomySystem()
        economy.add_trade_route("a", "b", "food")

        events = economy.update()
        assert len(events) == 0

    def test_reset_clears_all(self):
        """Test reset clears markets and routes."""
        economy = EconomySystem()
        economy.add_market(Market("town"))
        economy.add_trade_route("a", "b", "food")

        economy.reset()

        assert len(economy.markets) == 0
        assert len(economy.trade_routes) == 0


class TestPoliticalSystem:
    """Tests for the PoliticalSystem class."""

    def test_set_and_get_leader(self):
        """Test leader assignment."""
        ps = PoliticalSystem()
        leader = Leader("King Arthur", ["diplomatic"])
        ps.set_leader("knights", leader)

        assert ps.get_leader("knights") is leader

    def test_remove_leader(self):
        """Test leader removal."""
        ps = PoliticalSystem()
        leader = Leader("Queen Guinevere", ["aggressive"])
        ps.set_leader("camelot", leader)

        removed = ps.remove_leader("camelot")
        assert removed is leader
        assert ps.get_leader("camelot") is None

    def test_coup_possible(self):
        """Test that coups can occur when morale is low."""
        # Use deterministic random for testing
        class DeterministicRandom:
            def __init__(self):
                self.calls = 0

            def random(self):
                self.calls += 1
                return 0.05  # Always triggers coup (0.05 < 0.1)

            def randint(self, a, b):
                return 1

            def sample(self, population, k):
                return list(population)[:k]

            def choice(self, seq):
                return seq[0] if seq else "Aldric"

        ps = PoliticalSystem(random_module=DeterministicRandom())
        fs = FactionSystem()

        f = Faction("rebels", "Rebel Alliance")
        f.morale = 0.1  # Very low morale → high instability
        fs.add_faction(f)

        events = ps.update(fs)

        # With low morale (0.1), instability is 0.9 > 0.7 threshold
        # And our deterministic random returns 0.05 < 0.1 probability
        coup_events = [e for e in events if e["type"] == "coup"]
        assert len(coup_events) == 1
        assert coup_events[0]["faction"] == "rebels"
        assert coup_events[0]["new_leader"] is not None

    def test_no_coup_when_stable(self):
        """Test that stable factions don't have coups."""
        class DeterministicRandom:
            def random(self):
                return 0.5  # Always > 0.1, so no coup

        ps = PoliticalSystem(random_module=DeterministicRandom())
        fs = FactionSystem()

        f = Faction("empire", "Galactic Empire")
        f.morale = 0.8  # High morale → low instability
        fs.add_faction(f)

        events = ps.update(fs)

        coup_events = [e for e in events if e["type"] == "coup"]
        assert len(coup_events) == 0

    def test_leader_has_relation_modifier(self):
        """Test that leader traits affect relations."""
        aggressive = Leader("Warlord Krull", ["aggressive"])
        diplomatic = Leader("Ambassador Lee", ["diplomatic"])

        # Aggressive should have negative relation modifier
        assert aggressive.get_relation_modifier() < 0

        # Diplomatic should have positive relation modifier
        assert diplomatic.get_relation_modifier() > 0

    def test_reset_clears_leaders(self):
        """Test reset clears all leadership data."""
        ps = PoliticalSystem()
        ps.set_leader("a", Leader("Test", ["diplomatic"]))

        ps.reset()

        assert len(ps.leaders) == 0


class TestDynamicQuestGenerator:
    """Tests for the DynamicQuestGenerator class."""

    def test_generates_conflict_quest(self):
        """Test that hostile factions generate war quests."""
        fs = FactionSystem()
        a = Faction("a", "Alpha Faction")
        b = Faction("b", "Beta Faction")
        a.set_relation("b", -0.8)

        fs.add_faction(a)
        fs.add_faction(b)

        gen = DynamicQuestGenerator()
        quests = gen.generate(faction_system=fs)

        war_quests = [q for q in quests if q["type"] == "war"]
        assert len(war_quests) > 0
        assert any(q["faction"] == "a" for q in war_quests)

    def test_generates_supply_quest(self):
        """Test that shortages generate supply quests."""
        economy = EconomySystem()
        market = Market("village")
        market.add_good("food", supply=0.1, demand=1.0, price=1.0)
        economy.add_market(market)

        gen = DynamicQuestGenerator()
        quests = gen.generate(economy_system=economy)

        supply_quests = [q for q in quests if q["type"] in ("supply", "crisis")]
        assert len(supply_quests) > 0
        assert supply_quests[0]["location"] == "village"
        assert supply_quests[0]["good"] == "food"

    def test_no_duplicate_quests(self):
        """Test that the same quest is not generated twice."""
        fs = FactionSystem()
        a = Faction("a", "Alpha")
        a.set_relation("b", -0.8)
        fs.add_faction(a)
        fs.add_faction(Faction("b", "Beta"))

        gen = DynamicQuestGenerator()

        # Generate twice
        quests1 = gen.generate(faction_system=fs)
        quests2 = gen.generate(faction_system=fs)

        # Second generation should return no new quests (already generated)
        war_quests2 = [q for q in quests2 if q["type"] == "war"]
        assert len(war_quests2) == 0

    def test_generates_trade_quest(self):
        """Test that price differences generate trade quests."""
        economy = EconomySystem()

        src = Market("mine")
        src.add_good("iron", supply=1.0, demand=0.2, price=0.3)
        economy.add_market(src)

        dst = Market("city")
        dst.add_good("iron", supply=0.2, demand=1.0, price=1.0)
        economy.add_market(dst)

        economy.add_trade_route("mine", "city", "iron")

        gen = DynamicQuestGenerator()
        quests = gen.generate(economy_system=economy)

        trade_quests = [q for q in quests if q["type"] == "trade"]
        assert len(trade_quests) > 0
        assert trade_quests[0]["from"] == "mine"
        assert trade_quests[0]["to"] == "city"

    def test_generates_political_quest(self):
        """Test that political events generate quests."""
        gen = DynamicQuestGenerator()
        events = [{"type": "coup", "faction": "rebels", "old_leader": "Old King", "new_leader": "New King"}]

        quests = gen.generate(political_events=events)

        rebellion_quests = [q for q in quests if q["type"] == "rebellion"]
        assert len(rebellion_quests) > 0
        assert rebellion_quests[0]["faction"] == "rebels"

    def test_clear_generated_allows_regeneration(self):
        """Test that clearing generated IDs allows regeneration."""
        fs = FactionSystem()
        a = Faction("a", "Alpha")
        a.set_relation("b", -0.8)
        fs.add_faction(a)
        fs.add_faction(Faction("b", "Beta"))

        gen = DynamicQuestGenerator()

        # Generate first time
        quests1 = gen.generate(faction_system=fs)
        assert len(quests1) > 0

        # Generate again - should be empty
        quests2 = gen.generate(faction_system=fs)
        assert len(quests2) == 0

        # Clear and regenerate
        gen.clear_generated()
        quests3 = gen.generate(faction_system=fs)
        assert len(quests3) > 0


class TestTier8Integration:
    """Integration tests for Tier 8 systems working together."""

    def test_economy_faction_quest_chain(self):
        """Test that economy shortage → faction conflict → quest chain works."""
        # Setup economy with shortage
        economy = EconomySystem()
        market = Market("border_town")
        market.add_good("food", supply=0.1, demand=1.0, price=1.0)
        economy.add_market(market)

        # Setup factions with tension over the town
        fs = FactionSystem()
        kingdom = Faction("kingdom", "Kingdom of Light")
        barbarians = Faction("barbarians", "Barbarian Horde")
        kingdom.set_relation("barbarians", -0.8)
        fs.add_faction(kingdom)
        fs.add_faction(barbarians)
        fs.factions["barbarians"].set_relation("kingdom", -0.8)

        # Generate quests
        gen = DynamicQuestGenerator()
        quests = gen.generate(fs, economy)

        # Should have both war and supply quests
        war_quests = [q for q in quests if q["type"] == "war"]
        supply_quests = [q for q in quests if q["type"] in ("supply", "crisis")]

        assert len(war_quests) > 0
        assert len(supply_quests) > 0

    def test_political_instability_causes_quest(self):
        """Test that political coups generate rebellion quests."""
        class DeterministicRandom:
            def random(self):
                return 0.05  # Triggers coup
            def randint(self, a, b):
                return 1
            def sample(self, population, k):
                return list(population)[:k]
            def choice(self, seq):
                return seq[0] if seq else "Aldric"

        fs = FactionSystem()
        faction = Faction("empire", "Empire")
        faction.morale = 0.1  # Very unstable
        fs.add_faction(faction)

        politics = PoliticalSystem(random_module=DeterministicRandom())
        politics.set_leader("empire", Leader("Emperor Palpatine", ["ruthless"]))

        # Get political events
        political_events = politics.update(fs)

        gen = DynamicQuestGenerator()
        quests = gen.generate(political_events=political_events)

        rebellion_quests = [q for q in quests if q["type"] == "rebellion"]
        assert len(rebellion_quests) > 0

    def test_full_tier8_simulation(self):
        """Test complete Tier 8 simulation with all systems."""
        # Full setup
        fs = FactionSystem()
        economy = EconomySystem()
        politics = PoliticalSystem()
        gen = DynamicQuestGenerator()

        # Add factions
        mages = Faction("mages", "Mage Council")
        warriors = Faction("warriors", "Warrior Guild")
        mages.set_relation("warriors", -0.75)
        warriors.set_relation("mages", -0.75)
        fs.add_faction(mages)
        fs.add_faction(warriors)

        # Add markets with shortages
        mage_town = Market("mage_district")
        mage_town.add_good("mana_crystals", supply=0.05, demand=1.0, price=2.0)
        economy.add_market(mage_town)

        warrior_camp = Market("warrior_camp")
        warrior_camp.add_good("weaponry", supply=0.1, demand=0.8, price=1.5)
        economy.add_market(warrior_camp)

        # Add trade route
        economy.add_trade_route("mage_district", "warrior_camp", "mana_crystals")

        # Add unstable leader
        politics.set_leader("warriors", Leader("War Chief Thokk", ["aggressive"]))

        # Run simulation
        economy_events = economy.update()
        political_events = politics.update(fs)
        quests = gen.generate(fs, economy, political_events)

        # Should generate multiple quest types
        quest_types = {q["type"] for q in quests}

        # At minimum should have conflict quests
        assert len(quests) > 0