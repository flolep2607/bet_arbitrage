from typing import Optional
from pyventus import EventLinker, EventEmitter, AsyncIOEventEmitter
from obj import BetOption
from platforms import *
import atexit
from loguru import logger
from rich import print
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
import dataclasses
import json
from datetime import date, datetime, timedelta
from threading import Lock, Timer
import sys
import os
import time
from collections import Counter, defaultdict

# Setup enhanced logging
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"arbitrage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# Remove default logger and set up console and file loggers
logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
logger.add(log_file, rotation="10 MB", retention="1 week", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}")

logger.info(f"Starting arbitrage odds system. Logs will be saved to {log_file}")

# Stats tracking
stats = {
    "start_time": datetime.now(),
    "odds_count": 0,
    "platform_counts": Counter(),
    "recent_odds_rate": 0,
    "matches_found": 0,
    "potential_arbitrages": 0,
    "last_odds": []  # Keep track of last 10 odds for display
}

stats_lock = Lock()
console = Console()

def generate_stats_table():
    """Generate a rich table with current scraping statistics"""
    table = Table(title="Arbitrage Odds Scraper - Live Progress")
    
    # Add columns
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    # Runtime
    runtime = datetime.now() - stats["start_time"]
    hours, remainder = divmod(runtime.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    runtime_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    table.add_row("Runtime", runtime_str)
    
    # Odds count and rate
    table.add_row("Total Odds Collected", str(stats["odds_count"]))
    table.add_row("Collection Rate", f"{stats['recent_odds_rate']:.1f} odds/min")
    
    # Platform breakdown
    platforms_str = ""
    for platform, count in stats["platform_counts"].most_common():
        platforms_str += f"{platform}: {count}\n"
    table.add_row("Platform Breakdown", platforms_str.strip())
    
    # Matches and arbitrages
    table.add_row("Potential Matches Found", str(stats["matches_found"]))
    table.add_row("Arbitrage Opportunities", str(stats["potential_arbitrages"]))
    
    # Recent odds
    recent_odds = ""
    for odd in reversed(stats["last_odds"]):
        recent_odds += f"{odd.platform} - {odd.optionA} vs {odd.optionB}\n"
    if recent_odds:
        table.add_row("Recent Odds", recent_odds.strip())
    
    return table

def update_progress():
    """Update the progress stats and schedule the next update"""
    global stats
    
    with stats_lock:
        # Calculate odds collection rate (per minute)
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        recent_odds = [odd for odd in stats["last_odds"] if odd.timestamp > one_minute_ago]
        stats["recent_odds_rate"] = len(recent_odds) * (60 / max(1, (now - one_minute_ago).total_seconds()))
    
    # Display progress in console
    console.print(generate_stats_table())
    
    # Schedule next update
    Timer(5.0, update_progress).start()

# Start the progress tracking after a short delay to allow initialization
Timer(3.0, update_progress).start()

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        elif isinstance(o, date):
            return o.isoformat()
        return super().default(o)

database: dict[str, BetOption] = {}
database_lock = Lock()

import difflib

import os
import json

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

def normalize_team_name(team_name: str, sport: Optional[str] = None) -> str:
    """Normalise le nom d'une équipe en utilisant les alias connus"""
    team_lower = team_name.lower().strip()
    aliases = load_team_aliases()
    
    # Si le sport est spécifié, chercher uniquement dans ce sport
    if sport and sport in aliases:
        sport_aliases = aliases[sport]
        for main_name, team_aliases in sport_aliases.items():
            if team_lower == main_name.lower() or team_lower in [alias.lower() for alias in team_aliases]:
                return main_name
    else:
        # Si pas de sport spécifié, chercher dans tous les sports
        for sport_aliases in aliases.values():
            for main_name, team_aliases in sport_aliases.items():
                if team_lower == main_name.lower() or team_lower in [alias.lower() for alias in team_aliases]:
                    return main_name
                    
    return team_lower

def are_similar(str1:str, str2:str, threshold=0.9):
    # D'abord essayer avec la normalisation des noms d'équipes
    norm1 = normalize_team_name(str1)
    norm2 = normalize_team_name(str2)
    
    # Si les noms normalisés sont identiques, c'est un match
    if norm1 == norm2:
        logger.debug(f"Teams matched by normalization: '{str1}' and '{str2}'")
        return True
        
    # Sinon, utiliser la comparaison par similarité comme avant
    similarity = difflib.SequenceMatcher(None, norm1, norm2).ratio()
    is_similar = similarity >= threshold
    
    if is_similar:
        logger.debug(f"Teams matched by similarity: '{str1}' and '{str2}' (similarity: {similarity:.2f})")
    
    return is_similar


@EventLinker.on("newodd")
def add_odd(odd: BetOption):
    global database, stats
    
    # Set timestamp if not already set
    if not odd.timestamp:
        odd.timestamp = datetime.now()
    
    with database_lock:
        database[odd.id] = odd
        logger.debug(f"Added new odd: {odd.platform} - {odd.title or 'Untitled'} - {odd.optionA} vs {odd.optionB}")
    
    # Update stats
    with stats_lock:
        stats["odds_count"] += 1
        stats["platform_counts"][odd.platform] += 1
        stats["last_odds"] = (stats["last_odds"] + [odd])[-10:]  # Keep last 10
    
    # find another odd with same options names, but different platform
    odds = [odd]
    matches_found = 0
    
    with database_lock:
        for other in database.values():
            if other.id == odd.id:
                continue
            if odd.platform != other.platform:
                continue
            if are_similar(odd.optionA.lower(), other.optionA.lower()) and are_similar(
                odd.optionB.lower(), other.optionB.lower()
            ):
                if odd.platform != other.platform:
                    logger.info(
                        f"Match found: '{odd.optionA} vs {odd.optionB}' on {odd.platform} matches with {other.platform}"
                    )
                    matches_found += 1
                    odds.append(other)
    
    if matches_found > 0:
        with stats_lock:
            stats["matches_found"] += matches_found
    
    if matches_found > 0:
        logger.debug(f"Found {matches_found} matching odds across different platforms")
    
    if len(odds) > 1:
        # take max of each odd
        bestA = max(odd.probaA for odd in odds)
        bestB = max(odd.probaB for odd in odds)
        bestDraw = (
            max(odd.probaDraw for odd in odds if odd.probaDraw)
            if any(odd.probaDraw for odd in odds)
            else None
        )
        
        # calculate sum of inverse odds
        sum_inverse_odds = 1 / bestA + 1 / bestB + (1 / bestDraw if bestDraw else 0)
        
        # Log detailed odds information
        platforms = ", ".join(sorted(set(o.platform for o in odds)))
        logger.info(f"Comparing odds across {len(odds)} platforms ({platforms})")
        logger.info(f"Best odds: {odd.optionA}={bestA:.2f}, {odd.optionB}={bestB:.2f}, Draw={bestDraw if bestDraw else 'N/A'}")
        logger.info(f"Sum of inverse odds: {sum_inverse_odds:.4f} (< 1.0 indicates arbitrage opportunity)")
        
        # check for arbitrage opportunity
        if sum_inverse_odds < 1:
            with stats_lock:
                stats["potential_arbitrages"] += 1
                
            profit_percentage = (1 - sum_inverse_odds) * 100
            logger.success(f"🔥 ARBITRAGE OPPORTUNITY DETECTED! Potential profit: {profit_percentage:.2f}% 🔥")
            
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
            
            # Rich console output for visual notification
            print(f"\n[bold green]🔔 ARBITRAGE OPPORTUNITY FOUND![/bold green]")
            for o in odds:
                print(f"[cyan]Platform:[/cyan] [yellow]{o.platform}[/yellow] - [white]{o.optionA} vs {o.optionB}[/white]")
            print(f"[cyan]Potential profit:[/cyan] [bold green]{profit_percentage:.2f}%[/bold green]\n")


event_emitter: EventEmitter = AsyncIOEventEmitter()

markets = [
    Polymarket(event_emitter),
    Dexsport(event_emitter),
]

logger.info(f"Initialized {len(markets)} market platforms: {', '.join(m.__class__.__name__ for m in markets)}")

# on exit call stop on all markets
def stop_all():
    logger.warning("Shutting down arbitrage system - stopping all market connections")
    
    # Print final stats
    with stats_lock:
        runtime = datetime.now() - stats["start_time"]
        hours, remainder = divmod(runtime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        logger.info(f"Session Summary:")
        logger.info(f"Total runtime: {int(hours)}h {int(minutes)}m {int(seconds)}s")
        logger.info(f"Total odds collected: {stats['odds_count']}")
        logger.info(f"Matches found: {stats['matches_found']}")
        logger.info(f"Arbitrage opportunities: {stats['potential_arbitrages']}")
        
        # Platform breakdown
        for platform, count in stats["platform_counts"].most_common():
            logger.info(f"  {platform}: {count} odds")
    
    for market in markets:
        try:
            market.stop()
            logger.info(f"Successfully stopped {market.__class__.__name__}")
        except Exception as e:
            logger.error(f"Error stopping {market.__class__.__name__}: {str(e)}")
    
    logger.info(f"Processed {len(database)} odds in this session")
    logger.info("Shutdown complete")
    exit(0)


atexit.register(stop_all)
# json.dumps(database, cls=EnhancedJSONEncoder)