from logs import console
import re
from typing import Optional, Tuple
from pyventus import EventLinker, EventEmitter, AsyncIOEventEmitter
import atexit
from rich import print
from rich.live import Live
from rich.table import Table
import dataclasses
import json
from datetime import date, datetime, timedelta
from threading import Lock, Timer
import os
from collections import Counter, defaultdict
from rapidfuzz import fuzz
from rapidfuzz import process as fuzz_process
from rapidfuzz import utils as fuzz_utils
from functools import lru_cache
import hashlib
import logging
from obj import BetOption

logger = logging.getLogger(__name__)

# Define log format with file:line for better debugging
# LOG_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file}</cyan>:<cyan>{line:<4}</cyan> | <level>{message}</level>"

# Remove default logger and set up console and file loggers
# logger.add(sys.stdout, level="INFO", format=LOG_FORMAT)

class ArbitrageManager:
    def __init__(self):
        self.active_arbitrages = {}  # key: hash, value: arbitrage info
        self.lock = Lock()
        self.expiration_timer = 30 * 60  # 30 minutes in seconds

    def _get_match_key(self, odds: list[BetOption]) -> set[str]:
        """
        Generate a unique key for a match based on platform IDs
        Returns a set of 'platform:id' strings
        """
        match_ids = {f"{odd.platform}:{odd.id}" for odd in odds}
        logger.debug(f"Match key generated: {match_ids}")
        return match_ids

    def _match_exists(self, match_key: set[str]) -> bool:
        """Check if this match combination already exists"""
        with self.lock:
            for arb in self.active_arbitrages.values():
                if arb.get('match_key', set()) == match_key:
                    return True
        return False

    def _generate_hash(self, teams: list[str]) -> str:
        """Generate a unique hash for an arbitrage based on normalized team names"""
        normalized_teams = self._normalize_teams(teams)
        key = '|'.join(normalized_teams)
        return hashlib.md5(key.encode()).hexdigest()

    def _is_expired(self, timestamp: datetime) -> bool:
        """Check if an arbitrage opportunity has expired"""
        return (datetime.now() - timestamp).total_seconds() > self.expiration_timer

    def add_arbitrage(self, match: str, profit: float, bets: list[str], odds_list: list[BetOption]) -> bool:
        """
        Add a new arbitrage opportunity if it doesn't exist or update if better profit
        Returns True if added/updated, False if ignored
        """
        with self.lock:
            # Clean expired opportunities first
            self._clean_expired()

            # Generate match key from odds
            match_key = self._get_match_key(odds_list)
            
            # Check if we already have this arbitrage
            for arb_hash, existing_arb in self.active_arbitrages.items():
                if existing_arb.get('match_key', set()) == match_key:
                    # Found existing arbitrage
                    if profit > existing_arb["profit"]:
                        # Update with better profit
                        logger.info(f"Updated arbitrage {match} with better profit: {profit:.2f}% (was: {existing_arb['profit']:.2f}%)")
                        arb_info = {
                            "match": match,
                            "profit": profit,
                            "bets": bets,
                            "timestamp": datetime.now(),
                            "hash": arb_hash,
                            "match_key": match_key
                        }
                        self.active_arbitrages[arb_hash] = arb_info
                        return True
                    return False

            # New arbitrage opportunity
            arb_hash = hashlib.md5(str(sorted(match_key)).encode()).hexdigest()
            arb_info = {
                "match": match,
                "profit": profit,
                "bets": bets,
                "timestamp": datetime.now(),
                "hash": arb_hash,
                "match_key": match_key
            }
            self.active_arbitrages[arb_hash] = arb_info
            return True

    def _clean_expired(self):
        """Remove expired arbitrage opportunities"""
        current_time = datetime.now()
        expired = [h for h, a in self.active_arbitrages.items() if self._is_expired(a["timestamp"])]
        for h in expired:
            del self.active_arbitrages[h]

    def get_active_arbitrages(self) -> list[dict]:
        """Get list of active arbitrage opportunities sorted by profit"""
        with self.lock:
            self._clean_expired()
            return sorted(
                self.active_arbitrages.values(),
                key=lambda x: x["profit"],
                reverse=True
            )

    def get_count(self) -> int:
        """Get count of currently active arbitrage opportunities"""
        with self.lock:
            self._clean_expired()
            return len(self.active_arbitrages)


class StatsManager:
    def __init__(self):
        self.start_time = datetime.now()
        self.odds_count = 0
        self.platform_counts = Counter()
        self.matches_found = 0
        self.last_odds = []  # Keep track of last 1000 odds for rate calculation
        self.lock = Lock()

    def add_odd(self, odd: BetOption):
        """Record a new odd"""
        with self.lock:
            self.odds_count += 1
            self.platform_counts[odd.platform] += 1
            self.last_odds = [*self.last_odds, odd][-1_000:]

    def add_match(self):
        """Record a new match found"""
        with self.lock:
            self.matches_found += 1

    def get_collection_rate(self) -> float:
        """Calculate current odds collection rate per minute"""
        with self.lock:
            now = datetime.now()
            one_minute_ago = now - timedelta(minutes=1)
            recent_odds = [odd for odd in self.last_odds if odd.timestamp > one_minute_ago]
            return len(recent_odds) * (60 / max(1, (now - one_minute_ago).total_seconds()))

    def get_runtime(self) -> str:
        """Get formatted runtime string"""
        runtime = datetime.now() - self.start_time
        hours, remainder = divmod(runtime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

    def get_platform_breakdown(self) -> str:
        """Get formatted platform breakdown string"""
        with self.lock:
            return "\n".join(f"{platform}: {count}" for platform, count in self.platform_counts.most_common())

    def get_recent_odds(self, limit: int = 10) -> list[BetOption]:
        """Get most recent odds with limit"""
        with self.lock:
            return list(reversed(self.last_odds))[:limit]


# Global arbitrage manager instance
arbitrage_manager = ArbitrageManager()
# Global managers
stats_manager = StatsManager()
database: dict[str, BetOption] = {}
database_lock = Lock()

def generate_stats_table():
    """Generate a rich table with current scraping statistics"""
    table = Table(title="Arbitrage Odds Scraper - Live Progress")
    
    # Add columns
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    # Runtime
    table.add_row("Runtime", stats_manager.get_runtime())
    
    # Odds count and rate
    table.add_row("Total Odds Collected", str(stats_manager.odds_count))
    table.add_row("Collection Rate", f"{stats_manager.get_collection_rate():.1f} odds/min")
    
    # Platform breakdown
    table.add_row("Platform Breakdown", stats_manager.get_platform_breakdown())
    
    # Matches and arbitrages
    table.add_row("Potential Matches Found", str(stats_manager.matches_found))
    
    # Active arbitrage opportunities
    active_arb_str = ""
    for arb in arbitrage_manager.get_active_arbitrages():
        active_arb_str += f"📈 {arb['match']}\n"
        active_arb_str += f"Profit: {arb['profit']:.2f}%\n"
        for bet in arb['bets']:
            active_arb_str += f"  • {bet}\n"
        active_arb_str += "---\n"
    if active_arb_str:
        table.add_row("Active Arbitrages", active_arb_str.strip())
    table.add_row("Total Active Arbitrages", str(arbitrage_manager.get_count()))
    
    # Recent odds
    recent_odds = ""
    for odd in stats_manager.get_recent_odds(10):
        recent_odds += f"{odd.platform} - {odd.optionA} vs {odd.optionB}\n"
    if recent_odds:
        table.add_row("Recent Odds", recent_odds.strip())
    
    return table

# Global live display
live = Live(generate_stats_table(), refresh_per_second=0.2, console=console)

def update_progress():
    """Update the progress stats and schedule the next update"""    
    # Update the live table
    live.update(generate_stats_table())
    
    # Schedule next update
    Timer(5.0, update_progress).start()

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        elif isinstance(o, date):
            return o.isoformat()
        return super().default(o)

def load_team_aliases():
    try:
        aliases_path = os.path.join(os.path.dirname(__file__), "teams_aliases.json")
        with open(aliases_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("teams_aliases.json not found, using default empty dictionary")
        return {}
    except json.JSONDecodeError:
        logger.error("Error parsing teams_aliases.json")
        return {}

ALIASES = load_team_aliases()
# set everything to lower in aliases, even main_name
for sport_aliases in list(ALIASES.values())[:]:
    for main_name, team_aliases in list(sport_aliases.items())[:]:
        sport_aliases[main_name.lower()] = [alias.lower() for alias in team_aliases]
        if main_name.lower() != main_name:
            del sport_aliases[main_name]

ALL_NAMES = set()
for sport_aliases in ALIASES.values():
    for main_name, team_aliases in sport_aliases.items():
        ALL_NAMES.add(main_name.lower())
        ALL_NAMES.update(alias.lower() for alias in team_aliases)

@lru_cache(maxsize=None)
def normalize_team_name(team_name: str, sport: Optional[str] = None) -> Tuple[str,bool]:
    """Normalise le nom d'une équipe en utilisant les alias connus"""
    RATIO = 95
    
    # Si le sport est spécifié, chercher uniquement dans ce sport
    if sport and sport in ALIASES:
        sport_aliases = ALIASES[sport]
        for main_name, team_aliases in sport_aliases.items():
            if team_name == main_name.lower() or team_name in team_aliases:
                return main_name,True
        # try fuzzy matching
        ALL_NAMES_SPORT = set()
        for main_name, team_aliases in sport_aliases.items():
            ALL_NAMES_SPORT.add(main_name.lower())
            ALL_NAMES_SPORT.update(team_aliases)
        best_match = fuzz_process.extractOne(team_name, ALL_NAMES_SPORT, score_cutoff=RATIO,processor=fuzz_utils.default_process)
        if best_match:
            logger.debug(f"Fuzzy matched team name: '{team_name}' -> '{best_match}'")
            return normalize_team_name(best_match[0],sport=sport)
    else:
        # Si pas de sport spécifié, chercher dans tous les sports
        for sport_aliases in ALIASES.values():
            for main_name, team_aliases in sport_aliases.items():
                if team_name == main_name.lower() or team_name in team_aliases:
                    return main_name,True
        # try fuzzy matching
        best_match = fuzz_process.extractOne(team_name, ALL_NAMES, score_cutoff=RATIO,processor=fuzz_utils.default_process)
        if best_match:
            logger.debug(f"Fuzzy matched1 team name: '{team_name}' -> ({best_match})")
            return normalize_team_name(best_match[0])
    return team_name,False

def are_similar(str1:str, str2:str, threshold=0.9):
    str1 = str1.lower().strip()
    str2 = str2.lower().strip()
    # D'abord essayer avec la normalisation des noms d'équipes
    transform = [
        ("st","state"),
        ("st","saint"),
    ]
    
    norm1, fixed1 = normalize_team_name(str1)
    norm2, fixed2 = normalize_team_name(str2)
    
    # Apply transformations to both strings
    for old, new in transform:
        regex = re.compile(rf"\b{old}\b", re.IGNORECASE)
        if not fixed1 and regex.search(str1):
            transformed_str1 = regex.sub(new, str1).strip()
            norm1, fixed1 = normalize_team_name(transformed_str1)
        
        if not fixed2 and regex.search(str2):
            transformed_str2 = regex.sub(new, str2).strip()
            norm2, fixed2 = normalize_team_name(transformed_str2)
    
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

@EventLinker.on("newodd")
def add_odd(odd: BetOption):
    global database
    if odd.is_garbage():
        return
    # Set timestamp if not already set
    if not odd.timestamp:
        odd.timestamp = datetime.now()
    
    with database_lock:
        database[odd.id] = odd
        logger.debug(f"Added new odd: {odd.platform} - {odd.title or 'Untitled'} - {odd.optionA} vs {odd.optionB}")
    
    # Update stats
    stats_manager.add_odd(odd)
    
    # find another odd with same options names, but different platform
    odds = [odd]
    matches_found = 0
    
    with database_lock:
        for other in database.values():
            if other.id == odd.id:
                continue
            if odd.platform == other.platform:
                continue
                
            # Check both standard and reversed order matches
            standard_match = (are_similar(odd.optionA.lower(), other.optionA.lower()) and 
                              are_similar(odd.optionB.lower(), other.optionB.lower()))
            
            reversed_match = (are_similar(odd.optionA.lower(), other.optionB.lower()) and 
                              are_similar(odd.optionB.lower(), other.optionA.lower()))
            
            if standard_match or reversed_match:
                if reversed_match and not standard_match:
                    logger.info(
                        f"Reversed match found: '{odd.optionA} vs {odd.optionB}' on {odd.platform} matches "
                        f"with '{other.optionB} vs {other.optionA}' on {other.platform}"
                    )
                else:
                    logger.info(
                        f"Match found: '{odd.optionA} vs {odd.optionB}' on {odd.platform} matches "
                        f"with '{other.optionA} vs {other.optionB}' on {other.platform}"
                    )
                matches_found += 1
                # Store match type with the odd for later use
                other.reversed_match = reversed_match and not standard_match
                odds.append(other)
    
    if matches_found > 0:
        stats_manager.add_match()
    
    if matches_found > 0:
        logger.debug(f"Found {matches_found} matching odds across different platforms")
    
    if len(odds) > 1:
        # Calculate best odds considering reversed matches
        bestA = odd.probaA  # Start with current odd
        bestB = odd.probaB
        bestDraw = odd.probaDraw
        
        # Compare with other odds, accounting for reversed matches
        for o in odds[1:]:  # Skip the first one (current odd)
            if hasattr(o, 'reversed_match') and o.reversed_match:
                # For reversed matches, swap A and B
                bestA = max(bestA, o.probaB)
                bestB = max(bestB, o.probaA)
                # Draw stays the same for reversed matches
            else:
                bestA = max(bestA, o.probaA)
                bestB = max(bestB, o.probaB)
            
            bestDraw = max(bestDraw, o.probaDraw) if bestDraw and o.probaDraw else (bestDraw or o.probaDraw)
        
        # calculate sum of inverse odds
        sum_inverse_odds = 1 / bestA + 1 / bestB + (1 / bestDraw if bestDraw else 0)
        
        # Log detailed odds information
        platforms = ", ".join(sorted(set(o.platform for o in odds)))
        logger.info(f"Comparing odds across {len(odds)} platforms ({platforms})")
        logger.info(f"Best odds: {odd.optionA}={bestA:.2f}, {odd.optionB}={bestB:.2f}, Draw={bestDraw if bestDraw else 'N/A'}")
        logger.info(f"Sum of inverse odds: {sum_inverse_odds:.4f} (< 1.0 indicates arbitrage opportunity)")
        
        # check for arbitrage opportunity
        if sum_inverse_odds < 1:
            profit_percentage = (1 - sum_inverse_odds) * 100
            logger.log(25,"BITRAGE OPPORTUNITY DETECTED! Potential profit: {profit_percentage:.2f}% 🔥")
            
            # Calculate optimal bet distribution for 100 unit investment
            total_investment = 100
            optimalA = (total_investment / bestA) / sum_inverse_odds
            optimalB = (total_investment / bestB) / sum_inverse_odds
            optimalDraw = (total_investment / bestDraw) / sum_inverse_odds if bestDraw else 0
            
            # print the optimal bets and expected profit
            logger.info(f"Optimal bet distribution for {total_investment} units:")
            logger.info(f"Bet {optimalA:.2f} units on '{odd.optionA}' at odds {bestA:.2f}")
            logger.info(f"Bet {optimalB:.2f} units on '{odd.optionB}' at odds {bestB:.2f}")
            if bestDraw:
                logger.info(f"Bet {optimalDraw:.2f} units on 'Draw' at odds {bestDraw:.2f}")
            logger.info(f"Expected return: {total_investment/sum_inverse_odds:.2f} units (Profit: {profit_percentage:.2f}%)")
            
            # Create formatted strings for bets
            bet_strings = []
            bet_strings.append(f"Bet {optimalA:.2f} units on '{odd.optionA}' at odds {bestA:.2f}")
            bet_strings.append(f"Bet {optimalB:.2f} units on '{odd.optionB}' at odds {bestB:.2f}")
            if bestDraw:
                bet_strings.append(f"Bet {optimalDraw:.2f} units on 'Draw' at odds {bestDraw:.2f}")

            # Try to add to arbitrage manager using all odds involved
            is_new = arbitrage_manager.add_arbitrage(
                match=f"{odd.optionA} vs {odd.optionB}",
                profit=profit_percentage,
                bets=bet_strings,
                odds_list=odds
            )

            if not is_new:
                # If this exact arbitrage was already tracked, skip the notification
                return

            # Rich console output for visual notification
            print(f"\n[bold green]🔔 ARBITRAGE OPPORTUNITY FOUND![/bold green]")
            for o in odds:
                if hasattr(o, 'reversed_match') and o.reversed_match:
                    print(f"[cyan]Platform:[/cyan] [yellow]{o.platform}[/yellow] - [white]{o.optionB} vs {o.optionA}[/white] [magenta](reversed)[/magenta]")
                else:
                    print(f"[cyan]Platform:[/cyan] [yellow]{o.platform}[/yellow] - [white]{o.optionA} vs {o.optionB}[/white]")
            print(f"[cyan]Potential profit:[/cyan] [bold green]{profit_percentage:.2f}%[/bold green]\n")

# on exit call stop on all markets
def stop_all():
    logger.warning("Shutting down arbitrage system - stopping all market connections")
    
    # Print final stats
    logger.info(f"Session Summary:")
    logger.info(f"Total runtime: {stats_manager.get_runtime()}")
    logger.info(f"Total odds collected: {stats_manager.odds_count}")
    logger.info(f"Matches found: {stats_manager.matches_found}")
    logger.info(f"Current arbitrage opportunities: {arbitrage_manager.get_count()}")
    
    # Platform breakdown
    logger.info("Platform breakdown:")
    for platform, count in stats_manager.platform_counts.most_common():
        logger.info(f"  {platform}: {count} odds")
    
    for market in markets:
        try:
            market.stop()
            logger.info(f"Successfully stopped {market.__class__.__name__}")
        except Exception as e:
            logger.error(f"Error stopping {market.__class__.__name__}: {str(e)}")
    
    logger.info(f"Processed {len(database)} odds in this session")
    logger.info("Shutdown complete")

def save_database_to_json(filename:Optional[str]=None):
    """Save the current database to a JSON file"""
    if not filename:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(os.path.dirname(__file__), f"odds_data_{timestamp}.json")
    
    with database_lock:
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(database, f, cls=EnhancedJSONEncoder, indent=2)
            logger.log(25,f"Successfully saved database to {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to save database: {str(e)}")
            return False


def end():
    logger.warning("Keyboard interrupt detected")
    # save_prompt = input("Do you want to save the current database to a JSON file? (y/n): ").strip().lower()
    # if save_prompt == 'y':
    #     save_database_to_json()
    stop_all()
    exit(0)


if __name__ == "__main__":
    # Format with file name and line number for all logs

    event_emitter: EventEmitter = AsyncIOEventEmitter()

    from platforms import Polymarket,Dexsport
    markets = [
        Polymarket(event_emitter),
        Dexsport(event_emitter),
    ]

    logger.info(f"Initialized {len(markets)} market platforms: {', '.join(m.__class__.__name__ for m in markets)}")

    # Start the web interface
    from webapp import run_webapp
    import threading
    webapp_thread = threading.Thread(target=run_webapp, daemon=True)
    webapp_thread.start()
    logger.info("Web interface started at http://localhost:8000")

    atexit.register(end)
