#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch
from ..platforms.dexsport import Dexsport, chunks
import json
import websocket
from pyventus import AsyncIOEventEmitter
from .conftest import detect_deadlock

class TestDexsport(unittest.TestCase):
    def setUp(self):
        self.event_emitter = AsyncIOEventEmitter()
        with patch('requests.post') as mock_post:
            mock_post.return_value.json.return_value = {"token": "test_token"}
            with patch('websocket.WebSocketApp'):
                self.dexsport = Dexsport(self.event_emitter)


    def tearDown(self):
        self.dexsport.stop()


    def test_chunks_function(self):
        """Test the chunks helper function"""
        test_list = [1, 2, 3, 4, 5]
        # Test with chunk size 2
        result = list(chunks(test_list, 2))
        self.assertEqual(result, [[1, 2], [3, 4], [5]])
        # Test with chunk size larger than list
        result = list(chunks(test_list, 6))
        self.assertEqual(result, [[1, 2, 3, 4, 5]])
        # Test with empty list
        result = list(chunks([], 2))
        self.assertEqual(result, [])


    @patch('requests.post')
    def test_get_token(self, mock_post):
        """Test token retrieval"""
        mock_post.return_value.json.return_value = {"token": "test_token"}
        token = self.dexsport.get_token()
        self.assertEqual(token, "test_token")
        mock_post.assert_called_once()


    def test_add_discipline(self):
        """Test adding a sport discipline"""
        self.dexsport.send = Mock()
        sport = "football"
        self.dexsport.add_discipline(sport)
        self.dexsport.send.assert_called_with(["join", "discipline", [f"2.{sport}", f"1.{sport}"]])


    def test_add_event(self):
        """Test adding an event"""
        self.dexsport.send = Mock()
        event_id = 12345
        self.dexsport.add_event(event_id)
        self.dexsport.send.assert_called_with(["join", "event", [event_id]])
        self.assertIn(event_id, self.dexsport.tracked_events)


    def test_remove_event(self):
        """Test removing an event"""
        self.dexsport.send = Mock()
        event_id = 12345
        # First add the event
        self.dexsport.tracked_events.append(event_id)
        # Then remove it
        self.dexsport.remove_event(event_id)
        self.dexsport.send.assert_called_with(["leave", "event", [f"2.{event_id}", f"1.{event_id}"]])
        self.assertNotIn(event_id, self.dexsport.tracked_events)


    def test_analysis_match_winner(self):
        """Test analysis of a match winner market message"""
        self.event_emitter.emit = Mock()
        test_message = [
            "market",
            "123",
            None,
            {
                "name": "Match Winner",
                "outcomes": [
                    {"name": "Team A", "price": 2.0},
                    {"name": "Team B", "price": 1.8},
                    {"name": "Draw", "price": 3.5}
                ]
            }
        ]
        self.dexsport.analysis(test_message)
        # Verify that newodd event was emitted
        self.event_emitter.emit.assert_called_once()
        # Get the bet argument from the emit call
        bet = self.event_emitter.emit.call_args[1]['odd']
        # Verify bet properties
        self.assertEqual(bet.platform, "dexsport")
        self.assertEqual(bet.id, "dexsport123")
        self.assertEqual(bet.optionA, "Team A")
        self.assertEqual(bet.optionB, "Team B")
        self.assertEqual(bet.probaA, 2.0)
        self.assertEqual(bet.probaB, 1.8)
        self.assertEqual(bet.probaDraw, 3.5)


    def test_analysis_invalid_market(self):
        """Test analysis of an invalid market message"""
        self.event_emitter.emit = Mock()
        test_message = [
            "market",
            "123",
            None,
            {
                "name": "Total Goals",  # Not a match winner market
                "outcomes": [
                    {"name": "Over 2.5", "price": 1.8},
                    {"name": "Under 2.5", "price": 2.0}
                ]
            }
        ]
        self.dexsport.analysis(test_message)
        # Verify that no event was emitted
        self.event_emitter.emit.assert_not_called()


    def test_analysis_discipline(self):
        """Test analysis of a discipline message"""
        self.dexsport.send = Mock()
        test_message = [
            "discipline",
            None,
            None,
            {"tournamentIds": [1, 2, 3]}
        ]
        self.dexsport.analysis(test_message)
        self.dexsport.send.assert_called_with(["join", "tournament", [1, 2, 3]])


    def test_analysis_tournament(self):
        """Test analysis of a tournament message"""
        self.dexsport.add_event = Mock()
        test_message = [
            "tournament",
            None,
            None,
            {
                "eventRefs": [
                    {"lid": 123},
                    {"lid": 456}
                ]
            }
        ]
        self.dexsport.analysis(test_message)
        # Verify that add_event was called for each event ID
        self.assertEqual(self.dexsport.add_event.call_count, 2)
        self.dexsport.add_event.assert_any_call(123)
        self.dexsport.add_event.assert_any_call(456)

if __name__ == '__main__':
    unittest.main()