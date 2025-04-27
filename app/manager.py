import dataclasses
from functools import lru_cache
import json
import os
import re
import time
from datetime import date, datetime, timedelta
import hashlib
import logging
from collections import Counter, defaultdict
from threading import Lock
from typing import Optional, Tuple
from rapidfuzz import fuzz
from rapidfuzz import process as fuzz_process
from rapidfuzz import utils as fuzz_utils
from .obj import BetOption
from .config import *
from typing import Set, Dict, Optional, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


def load_team_aliases():
    try:
        aliases_path = os.path.join(os.path.dirname(__file__), "teams_aliases.json")
        with open(aliases_path, "r", encoding="utf-8") as f:
            ALIASES = json.load(f)
        # set everything to lower in aliases, even main_name
        for sport_aliases in list(ALIASES.values())[:]:
            for main_name, team_aliases in list(sport_aliases.items())[:]:
                sport_aliases[main_name.lower()] = [
                    alias.lower() for alias in team_aliases
                ]
                if main_name.lower() != main_name:
                    del sport_aliases[main_name]

        ALL_NAMES = set()
        for sport_aliases in ALIASES.values():
            for main_name, team_aliases in sport_aliases.items():
                ALL_NAMES.add(main_name.lower())
                ALL_NAMES.update(alias.lower() for alias in team_aliases)
        return ALIASES, ALL_NAMES
    except FileNotFoundError:
        logger.warning("teams_aliases.json not found, using default empty dictionary")
    except json.JSONDecodeError:
        logger.error("Error parsing teams_aliases.json")
    return ({}, set())


ALIASES, ALL_NAMES = load_team_aliases()


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]



T = TypeVar('T')
V = TypeVar('V')  # Type pour la valeur associée

class SetStructure:
    def __init__(self):
        self.data: Dict[T, Set[T]] = {}
        self.set_values: Dict[frozenset[T], V] = {}  # Use frozenset hash as key

    def add_set(self, new_set: Set[T], value: V) -> None:
        # Convert to frozenset for hashing
        new_frozen = frozenset(new_set)
        
        # Check if any element already exists in a set
        existing_set = None
        for element in new_set:
            if element in self.data:
                existing_set = self.data[element]
                break

        if existing_set:
            # Merge sets
            merged_set = existing_set | new_set
            merged_frozen = frozenset(merged_set)

            # Update data dictionary with merged set
            for element in merged_set:
                self.data[element] = merged_set

            # Update value - always use the new value for merged sets
            self.set_values[merged_frozen] = value
            
            # Clean up old values if present
            old_frozen = frozenset(existing_set)
            if old_frozen in self.set_values and old_frozen != merged_frozen:
                del self.set_values[old_frozen]
        else:
            # Add new set
            for element in new_set:
                self.data[element] = new_set
            self.set_values[new_frozen] = value

    def find_set(self, element: T) -> Optional[Set[T]]:
        return self.data.get(element)

    def get_set_value(self, element: T) -> Optional[V]:
        # If element is already a set or frozenset, use it directly
        if isinstance(element, (set, frozenset)):
            key = frozenset(element)
            value = self.set_values.get(key)
            if value is not None:
                return value
            
            # Try to find a matching set with the same elements
            for k, v in self.set_values.items():
                if set(k) == set(element):
                    return v
            return None
            
        # Otherwise look up the set containing the element
        found_set = self.find_set(element)
        if found_set:
            key = frozenset(found_set)
            value = self.set_values.get(key)
            if value is not None:
                return value
                
            # Try to find a matching set with the same elements
            for k, v in self.set_values.items():
                if set(k) == set(found_set):
                    return v
                    
        return None

    def delete_set(self, element: T) -> bool:
        found_set = self.find_set(element)
        if found_set:
            for elem in found_set:
                if elem in self.data:
                    del self.data[elem]
            if found_set in self.set_values:
                del self.set_values[found_set]
            return True
        return False

    def delete_key(self, element: T) -> bool:
        if element in self.data:
            found_set = self.find_set(element)
            del self.data[element]
            # Si c'était le dernier élément du set, on supprime aussi la valeur associée
            if found_set and all(e not in self.data for e in found_set):
                del self.set_values[found_set]
            return True
        return False

class Graph:
    def __init__(self):
        self.lock = Lock()
        self.groups: SetStructure[str,float] = SetStructure()
        self.values: dict[str, BetOption] = {}

    def add_node(self, node: BetOption):
        with self.lock:
            self.values[node.id] = node
            self.groups.add_set({node.id}, 0.0)
    
    def add_group(self, odds_list: list[BetOption], value: float):
        with self.lock:
            group_ids = set()
            for odd in odds_list:
                self.values[odd.id] = odd
                group_ids.add(odd.id)
            self.groups.add_set(group_ids, value)
    
    def count_groups(self):
        with self.lock:
            return len(self.groups.data)
    
    def items(self):
        with self.lock:
            # Debug: print all keys and values in set_values
            # logger.debug(f"GRAPH ITEMS - Available keys in set_values: {list(self.groups.set_values.keys())}")
            # logger.debug(f"GRAPH ITEMS - Values count: {len(self.groups.set_values)}")
            
            # Use frozenset to store sets of IDs
            groups_ids = {frozenset(s) for s in self.groups.data.values()}
            # logger.debug(f"GRAPH ITEMS - Groups count: {len(groups_ids)}")
            
            for ids in groups_ids:
                if len(ids)==1:continue
                bets = [self.values[i] for i in ids if i in self.values]
                value = self.groups.get_set_value(frozenset(ids))
                
                # Debug info about the value lookup
                # logger.debug(f"GRAPH ITEMS - Looking for key: {frozenset(ids)}")
                # logger.debug(f"GRAPH ITEMS - Found value: {value}")
                
                # if value is None:
                #     # Check if there's a similar key that contains the same elements
                #     for key in self.groups.set_values.keys():
                #         if set(key) == set(ids):
                #             logger.debug(f"GRAPH ITEMS - Found similar key with different order: {key}")
                #             value = self.groups.set_values[key]
                #             break
                if value and value > 0:
                    yield bets, value



class Manager(metaclass=Singleton):
    def __init__(self, console):
        # ArbitrageManager attributes
        self.graph = Graph()
        self.expiration_timer = 300  # 5 minutes default
        self.history = []  # Store historical arbitrage opportunities
        self.max_history = 1000
        self.min_profit_threshold = 1.0  # 1% minimum profit

        # StatsManager attributes
        self.start_time = datetime.now()
        self.platform_counts = Counter()
        self.matches_found = 0
        self.db_update_date: dict[str, date] = {}
        self.database: dict[str, BetOption] = {}  # key: odd.id, value: BetOption
        self.database_lock = Lock()
        self.stats_lock = Lock()
        self.console = console

        # Additional statistics tracking
        self.hourly_stats = defaultdict(
            lambda: {
                "odds_count": 0,
                "matches_found": 0,
                "collection_rates": [],
                "platform_counts": Counter(),
            }
        )
        self.error_counts = Counter()
        self.performance_metrics = {
            "avg_processing_time": 0,
            "total_processing_time": 0,
            "processed_items": 0,
        }
        self.max_odds_rate = 0
        self.min_odds_rate = float("inf")

    def update_date(self,event_id:str, start_time:date):
        """Update the date for the event"""
        with self.database_lock:
            self.db_update_date[event_id] = start_time
            if event_id in self.database:
                self.database[event_id].event_date = start_time
                logger.debug(f"Updated date for event {event_id} to {start_time}")
            

    def clear(self):
        """Cleanup resources and close connections if needed"""
        self.database.clear()
        self.graph = Graph()
        self.history.clear()
        self.platform_counts.clear()
        self.matches_found = 0
        self.hourly_stats.clear()
    
    # Arbitrage Methods
    def _get_match_key(self, odds: list[BetOption]) -> set[str]:
        """Generate a unique key for a match based on platform IDs"""
        match_ids = {f"{odd.platform}:{odd.id}" for odd in odds}
        logger.debug(f"Match key generated: {match_ids}")
        return match_ids

    def _is_expired(self, timestamp: datetime) -> bool:
        """Check if an arbitrage opportunity has expired"""
        return (datetime.now() - timestamp).total_seconds() > self.expiration_timer

    def add_arbitrage(
        self, 
        profit: float,
        odds_list: list[BetOption],
    ) -> bool:
        self._clean_expired()
        match = f"{odds_list[0].optionA} vs {odds_list[0].optionB}"
        bet_strings = []  # We should calculate bet strings here if needed
        match_key = self._get_match_key(odds_list)
        arb_hash = hashlib.md5(str(match_key).encode()).hexdigest()
        
        # Add group to graph
        self.graph.add_group(odds_list, profit)
        
        # Create and update arbitrage info
        arb_info = self._create_arbitrage_info(
            match=match,
            profit=profit,
            bets=bet_strings,
            match_key=match_key,
            arb_hash=arb_hash,
            odds_list=odds_list
        )
        self._update_history(arb_info)
        
        logger.debug(f"Added arbitrage opportunity with profit {profit:.2f}%")
        return True

    def _create_arbitrage_info(
        self,
        match: str,
        profit: float,
        bets: list[str],
        match_key: set,
        arb_hash: str,
        odds_list: list[BetOption],
    ) -> dict:
        """Create a standardized arbitrage info dictionary"""
        return {
            "match": match,
            "profit": profit,
            "bets": bets,
            "timestamp": datetime.now(),
            "hash": arb_hash,
            "match_key": match_key,
            "platforms": [odd.platform for odd in odds_list],
            "bet_count": len(bets),
            "max_profit": profit,
        }

    def _update_history(self, arb_info: dict):
        """Update arbitrage history"""
        history_entry = {
            "timestamp": arb_info["timestamp"],
            "match": arb_info["match"],
            "profit": arb_info["profit"],
            "platforms": arb_info["platforms"],
        }
        self.history.append(history_entry)

        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

    def _clean_expired(self):
        """Remove expired arbitrage opportunities"""
        return
        with self.graph_lock:
            expired = [
                h for h, a in self.graph.items() if self._is_expired(a["timestamp"])
            ]
            for h in expired:
                del self.graph[h]

    def get_active_arbitrages(self) -> list[dict]:
        """Get list of active arbitrage opportunities sorted by profit"""
        self._clean_expired()
        # Filter out items with None values and provide a default of 0.0
        arbitrages = []
        for bets, profit in self.graph.items():
            if profit is not None:
                match = f"{bets[0].optionA} vs {bets[0].optionB}" if bets else "Unknown Match"
                
                # Récupérer la date du match si disponible
                match_date = None
                for bet in bets:
                    if bet.event_date:
                        match_date = bet.event_date
                        break
                
                arb_info = {
                    "match": match,
                    "profit": profit,
                    "date": match_date.strftime("%Y-%m-%d") if match_date else "Unknown date",
                    "bets": [f"{bet.platform}: {bet.optionA} vs {bet.optionB}" for bet in bets],
                    "platforms": [bet.platform for bet in bets],
                }
                arbitrages.append(arb_info)
        
        # Sort by profit
        return sorted(arbitrages, key=lambda x: x["profit"], reverse=True)

    def add_match(self):
        """Record a new match found"""
        with self.stats_lock:
            self.matches_found += 1
            hour_key = datetime.now().strftime("%Y-%m-%d %H:00")
            self.hourly_stats[hour_key]["matches_found"] += 1

    def add_error(self, error_type: str):
        """Record an error occurrence"""
        with self.stats_lock:
            self.error_counts[error_type] += 1

    def _update_performance_metrics(self, processing_time: float):
        """Update performance tracking metrics"""
        metrics = self.performance_metrics
        metrics["total_processing_time"] += processing_time
        metrics["processed_items"] += 1
        metrics["avg_processing_time"] = (
            metrics["total_processing_time"] / metrics["processed_items"]
        )

    def get_collection_rate(self, window_minutes: int = 1) -> float:
        """Calculate current odds collection rate per minute"""
        now = datetime.now()
        window_ago = now - timedelta(minutes=window_minutes)

        with self.database_lock:
            recent_odds = [
                odd for odd in self.database.values() if odd.timestamp > window_ago
            ]
            rate = len(recent_odds) * (60 / max(1, (now - window_ago).total_seconds()))

            if rate > self.max_odds_rate:
                self.max_odds_rate = rate
            if rate < self.min_odds_rate and rate > 0:
                self.min_odds_rate = rate

            return rate

    def get_runtime(self) -> str:
        """Get formatted runtime string"""
        runtime = datetime.now() - self.start_time
        hours, remainder = divmod(runtime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

    def get_platform_breakdown(self) -> dict:
        """Get formatted platform breakdown"""
        with self.stats_lock:
            return {
                platform: count
                for platform, count in self.platform_counts.most_common()
            }

    def get_platform_breakdown_print(self) -> str:
        """Get formatted platform breakdown string"""
        with self.stats_lock:
            return "\n".join(
                f"{platform}:{count}"
                for platform, count in self.platform_counts.most_common()
            )

    def get_recent_odds(self, limit: int = 10) -> list[BetOption]:
        """Get most recent odds with limit"""
        with self.database_lock:
            # Sort by timestamp and return most recent
            sorted_odds = sorted(
                self.database.values(), key=lambda x: x.timestamp, reverse=True
            )
            return sorted_odds[:limit]

    def get_detailed_stats(self) -> dict:
        """Get comprehensive statistics"""
        with self.stats_lock:
            current_rate = self.get_collection_rate()
            return {
                "runtime": self.get_runtime(),
                "total_odds": self.size(),
                "total_matches": self.matches_found,
                "current_rate": current_rate,
                "max_rate": self.max_odds_rate,
                "min_rate": (
                    self.min_odds_rate if self.min_odds_rate != float("inf") else 0
                ),
                "platform_stats": dict(self.platform_counts),
                "hourly_stats": dict(self.hourly_stats),
                "error_stats": dict(self.error_counts),
                "performance": {
                    "avg_processing_time": self.performance_metrics[
                        "avg_processing_time"
                    ],
                    "total_processed": self.performance_metrics["processed_items"],
                },
            }

    def get_hourly_summary(self, hours: int = 24) -> dict:
        """Get summary of the last N hours of operation"""
        with self.stats_lock:
            now = datetime.now()
            cutoff = now - timedelta(hours=hours)
            relevant_hours = {
                hour: stats
                for hour, stats in self.hourly_stats.items()
                if datetime.strptime(hour, "%Y-%m-%d %H:00") >= cutoff
            }
            return {
                "hours_analyzed": len(relevant_hours),
                "total_odds": sum(
                    stats["odds_count"] for stats in relevant_hours.values()
                ),
                "total_matches": sum(
                    stats["matches_found"] for stats in relevant_hours.values()
                ),
                "hourly_breakdown": relevant_hours,
            }

    def arbitrage_count(self):
        """Get count of currently active arbitrage opportunities"""
        return self.graph.count_groups()

    def size(self) -> int:
        """Get size of the database"""
        with self.database_lock:
            return len(self.database)

    def add_odd(self, odd: BetOption):
        if odd.is_garbage():
            return

        logger.debug(
            f"Added new odd: {odd.platform} - {odd.title or 'Untitled'} - {odd.optionA} vs {odd.optionB}"
        )
        odd.event_date = odd.event_date or self.db_update_date.get(odd.id)

        if not odd.id in self.database:
            # Add new odd to the database
            with self.database_lock:
                self.platform_counts[odd.platform] += 1

        self.graph.add_node(odd)
        self.database[odd.id] = odd
        # find another odd with same options names, but different platform
        odds = [odd]
        matches_found = 0

        with self.database_lock:
            for other in self.database.values():
                if other.id == odd.id:
                    continue
                if odd.platform == other.platform:
                    continue

                # Vérifier d'abord si les dates correspondent (si elles sont définies)
                # Accepter un match seulement si les dates sont nulles ou égales +/- 1 jour
                if odd.event_date and other.event_date:
                    # Si les deux ont des dates, elles doivent être identiques ou au maximum à 1 jour d'écart
                    date_diff = abs((odd.event_date - other.event_date).days) if isinstance(odd.event_date, date) else None
                    if date_diff is not None and date_diff > 1:
                        # Dates trop éloignées, ce ne peut pas être le même match
                        # logger.debug(
                        #     f"Date mismatch: '{odd.optionA} vs {odd.optionB}' on {odd.event_date} vs "
                        #     f"'{other.optionA} vs {other.optionB}' on {other.event_date}"
                        # )
                        continue
                logger.debug(
                    f"Date match: '{odd.optionA} vs {odd.optionB}' on {odd.event_date} vs "
                    f"'{other.optionA} vs {other.optionB}' on {other.event_date}"
                )
                # Check both standard and reversed order matches
                standard_match = self.are_similar(
                    odd.optionA.lower(), other.optionA.lower()
                ) and self.are_similar(odd.optionB.lower(), other.optionB.lower())

                reversed_match = self.are_similar(
                    odd.optionA.lower(), other.optionB.lower()
                ) and self.are_similar(odd.optionB.lower(), other.optionA.lower())

                if standard_match or reversed_match:
                    if reversed_match and not standard_match:
                        logger.info(
                            f"Reversed match found: '{odd.optionA} vs {odd.optionB}' on {odd.platform} matches "
                            f"with '{other.optionB} vs {other.optionA}' on {other.platform}"
                            f"{' - Match date: ' + str(odd.event_date) if odd.event_date else ''}"
                        )
                    else:
                        logger.info(
                            f"Match found: '{odd.optionA} vs {odd.optionB}' on {odd.platform} matches "
                            f"with '{other.optionA} vs {other.optionB}' on {other.platform}"
                            f"{' - Match date: ' + str(odd.event_date) if odd.event_date else ''}"
                        )
                    matches_found += 1
                    # Store match type with the odd for later use
                    other.reversed_match = reversed_match and not standard_match
                    odds.append(other)

        if matches_found > 0:
            self.add_match()

        if matches_found > 0:
            logger.debug(
                f"Found {matches_found} matching odds across different platforms"
            )

        if len(odds) > 1:
            # Calculate best odds considering reversed matches
            bestA = odd.probaA  # Start with current odd
            bestB = odd.probaB
            bestDraw = odd.probaDraw

            # Compare with other odds, accounting for reversed matches
            for o in odds[1:]:  # Skip the first one (current odd)
                if hasattr(o, "reversed_match") and o.reversed_match:
                    # For reversed matches, swap A and B
                    bestA = max(bestA, o.probaB)
                    bestB = max(bestB, o.probaA)
                    # Draw stays the same for reversed matches
                else:
                    bestA = max(bestA, o.probaA)
                    bestB = max(bestB, o.probaB)

                bestDraw = (
                    max(bestDraw, o.probaDraw)
                    if bestDraw and o.probaDraw
                    else (bestDraw or o.probaDraw)
                )

            # calculate sum of inverse odds
            sum_inverse_odds = 1 / bestA + 1 / bestB + (1 / bestDraw if bestDraw else 0)

            # Log detailed odds information
            platforms = ", ".join(sorted(set(o.platform for o in odds)))
            logger.info(f"Comparing odds across {len(odds)} platforms ({platforms})")
            logger.info(
                f"Best odds: {odd.optionA}={bestA:.2f}, {odd.optionB}={bestB:.2f}, Draw={bestDraw if bestDraw else 'N/A'}"
            )
            logger.info(
                f"Sum of inverse odds: {sum_inverse_odds:.4f} (< 1.0 indicates arbitrage opportunity)"
            )

            # check for arbitrage opportunity
            if sum_inverse_odds < 1:
                profit_percentage = (1 - sum_inverse_odds) * 100
                logger.log(
                    25,
                    f"ARBITRAGE OPPORTUNITY DETECTED! Potential profit: {profit_percentage:.2f}% 🔥",
                )

                # Calculate optimal bet distribution for 100 unit investment
                total_investment = 100
                optimalA = (total_investment / bestA) / sum_inverse_odds
                optimalB = (total_investment / bestB) / sum_inverse_odds
                optimalDraw = (
                    (total_investment / bestDraw) / sum_inverse_odds if bestDraw else 0
                )

                # print the optimal bets and expected profit
                logger.info(f"Optimal bet distribution for {total_investment} units:")
                logger.info(
                    f"Bet {optimalA:.2f} units on '{odd.optionA}' at odds {bestA:.2f}"
                )
                logger.info(
                    f"Bet {optimalB:.2f} units on '{odd.optionB}' at odds {bestB:.2f}"
                )
                if bestDraw:
                    logger.info(
                        f"Bet {optimalDraw:.2f} units on 'Draw' at odds {bestDraw:.2f}"
                    )
                logger.info(
                    f"Expected return: {total_investment/sum_inverse_odds:.2f} units (Profit: {profit_percentage:.2f}%)"
                )

                # Create formatted strings for bets
                bet_strings = []
                bet_strings.append(
                    f"Bet {optimalA:.2f} units on '{odd.optionA}' at odds {bestA:.2f}"
                )
                bet_strings.append(
                    f"Bet {optimalB:.2f} units on '{odd.optionB}' at odds {bestB:.2f}"
                )
                if bestDraw:
                    bet_strings.append(
                        f"Bet {optimalDraw:.2f} units on 'Draw' at odds {bestDraw:.2f}"
                    )

                # Try to add to arbitrage manager using all odds involved
                is_new = self.add_arbitrage(
                    # match=f"{odd.optionA} vs {odd.optionB}",
                    profit=profit_percentage,
                    # bets=bet_strings,
                    odds_list=odds
                )

                if not is_new:
                    # If this exact arbitrage was already tracked, skip the notification
                    return

                # Rich console output for visual notification
                self.console.print(
                    f"\n[bold green]🔔 ARBITRAGE OPPORTUNITY FOUND![/bold green]"
                )
                for o in odds:
                    if hasattr(o, "reversed_match") and o.reversed_match:
                        self.console.print(
                            f"[cyan]Platform:[/cyan] [yellow]{o.platform}[/yellow] - [white]{o.optionB} vs {o.optionA}[/white] [magenta](reversed)[/magenta]"
                        )
                    else:
                        self.console.print(
                            f"[cyan]Platform:[/cyan] [yellow]{o.platform}[/yellow] - [white]{o.optionA} vs {o.optionB}[/white]"
                        )
                self.console.print(
                    f"[cyan]Potential profit:[/cyan] [bold green]{profit_percentage:.2f}%[/bold green]"
                )
                self.console.print(f"[cyan]Details:[/cyan] {odds}\n")

    @staticmethod
    @lru_cache(maxsize=None)
    def normalize_team_name(
        team_name: str, sport: Optional[str] = None
    ) -> Tuple[str, bool]:
        """Normalise le nom d'une équipe en utilisant les alias connus"""
        RATIO = TEAM_NAME_MATCH_RATIO

        # Si le sport est spécifié, chercher uniquement dans ce sport
        if sport and sport in ALIASES:
            sport_aliases = ALIASES[sport]
            for main_name, team_aliases in sport_aliases.items():
                if team_name == main_name.lower() or team_name in team_aliases:
                    return main_name, True
            # try fuzzy matching
            ALL_NAMES_SPORT = set()
            for main_name, team_aliases in sport_aliases.items():
                ALL_NAMES_SPORT.add(main_name.lower())
                ALL_NAMES_SPORT.update(team_aliases)
            best_match = fuzz_process.extractOne(
                team_name,
                ALL_NAMES_SPORT,
                score_cutoff=RATIO,
                processor=fuzz_utils.default_process,
            )
            if best_match:
                logger.debug(
                    f"Fuzzy matched team name: '{team_name}' -> '{best_match}'"
                )
                return Manager.normalize_team_name(best_match[0], sport=sport)
        else:
            # Si pas de sport spécifié, chercher dans tous les sports
            for sport_aliases in ALIASES.values():
                for main_name, team_aliases in sport_aliases.items():
                    if team_name == main_name.lower() or team_name in team_aliases:
                        return main_name, True
            # try fuzzy matching
            best_match = fuzz_process.extractOne(
                team_name,
                ALL_NAMES,
                score_cutoff=RATIO,
                processor=fuzz_utils.default_process,
            )
            if best_match:
                logger.debug(
                    f"Fuzzy matched1 team name: '{team_name}' -> ({best_match})"
                )
                return Manager.normalize_team_name(best_match[0])
        return team_name, False

    @staticmethod
    def are_similar(str1: str, str2: str, threshold=SIMILAR_STRINGS_THRESHOLD):
        str1 = str1.lower().strip()
        str2 = str2.lower().strip()
        # D'abord essayer avec la normalisation des noms d'équipes
        transform = [
            ("st", "state"),
            ("st", "saint"),
        ]

        norm1, fixed1 = Manager.normalize_team_name(str1)
        norm2, fixed2 = Manager.normalize_team_name(str2)

        # Apply transformations to both strings
        for old, new in transform:
            regex = re.compile(rf"\b{old}\b", re.IGNORECASE)
            if not fixed1 and regex.search(str1):
                transformed_str1 = regex.sub(new, str1).strip()
                norm1, fixed1 = Manager.normalize_team_name(transformed_str1)

            if not fixed2 and regex.search(str2):
                transformed_str2 = regex.sub(new, str2).strip()
                norm2, fixed2 = Manager.normalize_team_name(transformed_str2)

        # logger.debug(f"Normalized: {str1}=>{norm1} | {str2}=>{norm2}")

        # Si les noms normalisés sont identiques, c'est un match
        if norm1 == norm2:
            # logger.info(f"Teams matched by normalization: '{str1}' and '{str2}'")
            return True

        # Essayer avec la similarité de texte
        similarity = fuzz.ratio(str1, str2) / 100
        is_similar = similarity >= threshold

        # if is_similar:
        #     logger.info(f"Teams matched by similarity: '{str1}' and '{str2}' (similarity: {similarity:.2f})")

        return is_similar

    class EnhancedJSONEncoder(json.JSONEncoder):
        def default(self, o):
            if dataclasses.is_dataclass(o):
                return dataclasses.asdict(o)
            elif isinstance(o, date):
                return o.isoformat()
            return super().default(o)

    def save_database_to_json(self, filename: Optional[str] = None):
        """Save the current database to a JSON file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(
                os.path.dirname(__file__), f"odds_data_{timestamp}.json"
            )

        with self.database_lock:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(self.database, f, cls=self.EnhancedJSONEncoder, indent=2)
                logger.log(25, f"Successfully saved database to {filename}")
                return True
            except Exception as e:
                logger.error(f"Failed to save database: {str(e)}")
                return False
