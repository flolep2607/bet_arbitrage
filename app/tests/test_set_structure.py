import unittest
from ..manager import SetStructure, Graph
from ..obj import BetOption
from datetime import datetime
from .conftest import detect_deadlock


class TestSetStructure(unittest.TestCase):

    def test_basic_set_operations(self):
        """Test basic set operations and value storage"""
        ss = SetStructure()

        # Add a simple set with value
        ss.add_set({"a", "b", "c"}, 10.5)

        # Verify the set is stored correctly
        self.assertEqual(ss.get_set_value("a"), 10.5)
        self.assertEqual(ss.get_set_value("b"), 10.5)
        self.assertEqual(ss.get_set_value("c"), 10.5)

        # Verify retrieval with frozenset works
        self.assertEqual(ss.get_set_value(frozenset({"a", "b", "c"})), 10.5)


    def test_set_merging(self):
        """Test that sets are merged correctly"""
        ss = SetStructure()

        # Add first set
        ss.add_set({"a", "b"}, 5.0)

        # Add overlapping set
        ss.add_set({"b", "c"}, 7.5)

        # Verify sets were merged
        found_set = ss.find_set("a")
        self.assertEqual(found_set, {"a", "b", "c"})

        # Verify all elements point to the same set
        self.assertEqual(ss.find_set("a"), ss.find_set("b"))
        self.assertEqual(ss.find_set("b"), ss.find_set("c"))

        # Verify value was updated to the new one
        self.assertEqual(ss.get_set_value("a"), 7.5)


    def test_value_retrieval(self):
        """Test explicit value retrieval with different key formats"""
        ss = SetStructure()

        # Add a set
        test_set = {"x", "y", "z"}
        ss.add_set(test_set, 42.0)

        # Test finding via element
        self.assertEqual(ss.get_set_value("x"), 42.0)

        # Test finding via frozenset
        frozen = frozenset(test_set)
        self.assertEqual(ss.get_set_value(frozen), 42.0)

        # Test finding via different order frozenset
        different_order = frozenset({"z", "y", "x"})
        self.assertEqual(ss.get_set_value(different_order), 42.0)


class TestGraph(unittest.TestCase):

    def create_bet_option(self, id, platform, optionA, optionB):
        bet = BetOption(
            id=id,
            platform=platform,
            title=f"{optionA} vs {optionB}",
            optionA=optionA,
            optionB=optionB,
            probaA=2.0,
            probaB=1.8,
            probaDraw=0,
        )
        # Set calculated properties that would normally be set in __post_init__
        bet.probaA = 1 / bet.probaA
        bet.probaB = 1 / bet.probaB
        bet.probaDraw = None
        return bet


    def test_graph_operations(self):
        """Test Graph node addition and group operations"""
        graph = Graph()

        # Create some bet options
        bet1 = self.create_bet_option("1", "Platform1", "Team A", "Team B")
        bet2 = self.create_bet_option("2", "Platform2", "Team A", "Team B")
        bet3 = self.create_bet_option("3", "Platform3", "Team A", "Team B")

        # Add nodes
        graph.add_node(bet1)
        graph.add_node(bet2)

        # Add group
        graph.add_group([bet1, bet2, bet3], 5.5)

        # Test items method
        items = list(graph.items())
        self.assertEqual(len(items), 1)

        bets, value = items[0]
        self.assertEqual(len(bets), 3)
        self.assertEqual(value, 5.5)


if __name__ == "__main__":
    unittest.main()
