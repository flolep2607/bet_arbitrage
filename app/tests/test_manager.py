#!/usr/bin/env python3

import unittest
from datetime import datetime
from ..obj import BetOption
from ..manager import Manager
from rich.console import Console
from .conftest import detect_deadlock

class TestManager(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.manager = Manager(self.console)
        self.manager.clear()


    def test_add_odd(self):
        """Test adding a valid bet option"""
        odd = BetOption(
            id="test1",
            platform="TestPlatform",
            optionA="Team A",
            optionB="Team B",
            probaA=2.0,
            probaB=2.0
        )
        self.manager.add_odd(odd)
        print("self.manager.database",self.manager.database)
        self.assertEqual(self.manager.size(), 1)
        self.assertIn(odd.id, self.manager.database)


    def test_add_garbage_odd(self):
        """Test adding an invalid bet option"""
        odd = BetOption(
            id="garbage",
            platform="TestPlatform",
            optionA="",  # Empty team name should be considered garbage
            optionB="Team B",
            probaA=2.0,
            probaB=2.0
        )
        self.manager.add_odd(odd)
        self.assertEqual(self.manager.size(), 0)  # Should not be added


    def test_arbitrage_detection(self):
        """Test arbitrage detection between two platforms"""
        odd1 = BetOption(
            id="test1",
            platform="Platform1",
            optionA="Team A",
            optionB="Team B",
            probaA=2.0,  # 50% implied probability
            probaB=2.0,  # 50% implied probability
        )
        odd2 = BetOption(
            id="test2",
            platform="Platform2",
            optionA="Team A",
            optionB="Team B",
            probaA=2.5,  # 40% implied probability
            probaB=2.0,  # 50% implied probability
        )
        
        self.manager.add_odd(odd1)
        self.manager.add_odd(odd2)
        
        # Sum of best odds: 1/2.5 + 1/2.0 = 0.4 + 0.5 = 0.9
        # This should be detected as an arbitrage opportunity (sum < 1)
        self.assertGreater(self.manager.arbitrage_count(), 0)

    def test_team_name_similarity(self):
        """Test team name similarity matching"""
        self.assertTrue(self.manager.are_similar("Team A", "team a"))
        self.assertTrue(self.manager.are_similar("Team A", "Team A"))
        self.assertTrue(self.manager.are_similar("Manchester United", "Man United"))
        self.assertFalse(self.manager.are_similar("Team A", "Team B"))


    def test_reversed_match_detection(self):
        """Test detection of reversed team order matches"""
        odd1 = BetOption(
            id="test1",
            platform="Platform1",
            optionA="Team A",
            optionB="Team B",
            probaA=2.0,
            probaB=2.0
        )
        odd2 = BetOption(
            id="test2",
            platform="Platform2",
            optionA="Team B",  # Note: Teams are in reversed order
            optionB="Team A",
            probaA=2.0,
            probaB=2.0,
        )
        
        self.manager.add_odd(odd1)
        self.manager.add_odd(odd2)
        
        # Should detect the match despite reversed order
        self.assertTrue(self.manager.database["test2"].reversed_match or self.manager.database["test1"].reversed_match)


    def test_invalid_bet_option(self):
        """Test handling of invalid input type"""
        with self.assertRaises(AttributeError):
            self.manager.add_odd("not a BetOption object")

if __name__ == '__main__':
    unittest.main()