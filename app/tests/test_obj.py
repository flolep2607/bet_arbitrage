#!/usr/bin/env python3

import unittest
from datetime import date, datetime, timedelta
from ..obj import BetOption

class TestBetOption(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.valid_bet = BetOption(
            platform="TestPlatform",
            id="test1",
            optionA="Team A",
            optionB="Team B",
            probaA=1.5,
            probaB=2.5,
            probaDraw=3.0,
            title="Test Match",
            sport="Football",
            league="Test League",
            event_date=date.today() + timedelta(days=1)
        )

    def test_valid_bet_creation(self):
        """Test creating a valid bet option"""
        self.assertEqual(self.valid_bet.platform, "TestPlatform")
        self.assertEqual(self.valid_bet.id, "test1")
        self.assertEqual(self.valid_bet.optionA, "Team A")
        self.assertEqual(self.valid_bet.optionB, "Team B")
        self.assertEqual(self.valid_bet.probaA, 1.5)
        self.assertEqual(self.valid_bet.probaB, 2.5)
        self.assertEqual(self.valid_bet.probaDraw, 3.0)
        self.assertEqual(self.valid_bet.title, "Test Match")
        self.assertEqual(self.valid_bet.sport, "Football")
        self.assertEqual(self.valid_bet.league, "Test League")
        self.assertIsInstance(self.valid_bet.timestamp, datetime)

    def test_garbage_detection_probabilities(self):
        """Test garbage detection for invalid probabilities"""
        # Test extremely low probability
        low_prob_bet = BetOption(
            platform="Test",
            id="test2",
            optionA="Team A",
            optionB="Team B",
            probaA=0.009,  # Below 0.01
            probaB=1.5,
            probaDraw=None
        )
        self.assertTrue(low_prob_bet.is_garbage())

        # Test extremely high probability
        high_prob_bet = BetOption(
            platform="Test",
            id="test3",
            optionA="Team A",
            optionB="Team B",
            probaA=101,  # Above 100
            probaB=1.5,
            probaDraw=None
        )
        self.assertTrue(high_prob_bet.is_garbage())

    def test_garbage_detection_yes_no(self):
        """Test garbage detection for yes/no options"""
        yes_no_bet = BetOption(
            platform="Test",
            id="test4",
            optionA="Yes",
            optionB="Team B",
            probaA=1.5,
            probaB=2.5,
            probaDraw=None
        )
        self.assertTrue(yes_no_bet.is_garbage())

        no_yes_bet = BetOption(
            platform="Test",
            id="test5",
            optionA="Team A",
            optionB="No",
            probaA=1.5,
            probaB=2.5,
            probaDraw=None
        )
        self.assertTrue(no_yes_bet.is_garbage())

    def test_garbage_detection_same_teams(self):
        """Test garbage detection for same team names"""
        same_team_bet = BetOption(
            platform="Test",
            id="test6",
            optionA="Team A",
            optionB="Team A",
            probaA=1.5,
            probaB=2.5,
            probaDraw=None
        )
        self.assertTrue(same_team_bet.is_garbage())

    def test_garbage_detection_past_date(self):
        """Test garbage detection for past event dates"""
        past_date_bet = BetOption(
            platform="Test",
            id="test7",
            optionA="Team A",
            optionB="Team B",
            probaA=1.5,
            probaB=2.5,
            probaDraw=None,
            event_date=date.today() - timedelta(days=1)  # Yesterday
        )
        self.assertTrue(past_date_bet.is_garbage())

    def test_valid_bet_not_garbage(self):
        """Test that a valid bet is not marked as garbage"""
        self.assertFalse(self.valid_bet.is_garbage())

    def test_optional_fields(self):
        """Test creation with optional fields omitted"""
        minimal_bet = BetOption(
            platform="Test",
            id="test8",
            optionA="Team A",
            optionB="Team B",
            probaA=1.5,
            probaB=2.5,
            probaDraw=None
        )
        self.assertIsNone(minimal_bet.title)
        self.assertIsNone(minimal_bet.sport)
        self.assertIsNone(minimal_bet.league)
        self.assertIsNone(minimal_bet.event_date)
        self.assertIsInstance(minimal_bet.timestamp, datetime)
        self.assertFalse(minimal_bet.is_garbage())

if __name__ == '__main__':
    unittest.main()