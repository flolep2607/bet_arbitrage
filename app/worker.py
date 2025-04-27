from pyventus import EventLinker, EventEmitter, AsyncIOEventEmitter
import atexit
from rich.live import Live
from rich.table import Table
import json
from datetime import date, datetime, timedelta
from threading import Lock, Timer
import logging
from .logs import console
from .config import *
from .manager import Manager

logger = logging.getLogger(__name__)

# Define log format with file:line for better debugging
# LOG_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file}</cyan>:<cyan>{line:<4}</cyan> | <level>{message}</level>"

# Remove default logger and set up console and file loggers
# logger.add(sys.stdout, level="INFO", format=LOG_FORMAT)

manager = Manager(console=console)

@EventLinker.on("update_date")
def update_date(event_id:str, start_time:date):
    """Update the date for the event"""
    manager.update_date(event_id, start_time)

@EventLinker.on("newodd")
def truc(odd):
    manager.add_odd(odd)

def generate_stats_table():
    """Generate a rich table with current scraping statistics"""
    table = Table(title="Arbitrage Odds Scraper - Live Progress")

    # Add columns
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    # Runtime
    table.add_row("Runtime", manager.get_runtime())

    # Odds count and rate
    table.add_row("Total Odds Collected", str(manager.size()))
    table.add_row("Collection Rate", f"{manager.get_collection_rate():.1f} odds/min")

    # Platform breakdown
    table.add_row("Platform Breakdown", manager.get_platform_breakdown_print())

    # Matches and arbitrages
    table.add_row("Potential Matches Found", str(manager.matches_found))

    # Active arbitrage opportunities
    active_arb_str = ""
    for arb in manager.get_active_arbitrages():
        active_arb_str += f"📈 {arb['match']}\n"
        active_arb_str += f"Profit: {arb['profit']:.2f}%\n"
        for bet in arb["bets"]:
            active_arb_str += f"  • {bet}\n"
        active_arb_str += "---\n"
    if active_arb_str:
        table.add_row("Active Arbitrages", active_arb_str.strip())
    table.add_row("Total Active Arbitrages", str(manager.arbitrage_count()))

    # Recent odds
    recent_odds = ""
    for odd in manager.get_recent_odds(10):
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
    Timer(STATS_UPDATE_INTERVAL, update_progress).start()

# on exit call stop on all markets
def stop_all():
    logger.warning("Shutting down arbitrage system - stopping all market connections")

    # Print final stats
    logger.info(f"Session Summary:")
    logger.info(f"Total runtime: {manager.get_runtime()}")
    logger.info(f"Total odds collected: {manager.size()}")
    logger.info(f"Matches found: {manager.matches_found}")
    logger.info(f"Current arbitrage opportunities: {manager.arbitrage_count()}")

    # Platform breakdown
    logger.info("Platform breakdown:")
    for platform, count in manager.platform_counts.most_common():
        logger.info(f"  {platform}: {count} odds")

    for market in markets:
        try:
            market.stop()
            logger.info(f"Successfully stopped {market.__class__.__name__}")
        except Exception as e:
            logger.error(f"Error stopping {market.__class__.__name__}: {str(e)}")

    logger.info(f"Processed {manager.size()} odds in this session")
    logger.info("Shutdown complete")


def end():
    logger.warning("Keyboard interrupt detected")
    # save_prompt = input("Do you want to save the current database to a JSON file? (y/n): ").strip().lower()
    # if save_prompt == 'y':
    #     save_database_to_json()
    stop_all()
    exit(0)


if __name__ == "__main__":
    from .platforms import Polymarket, Dexsport

    event_emitter: EventEmitter = AsyncIOEventEmitter()
    markets = []
    for platform in [Polymarket, Dexsport]:
        try:
            markets.append(platform(event_emitter))
        except Exception as e:
            logger.error(f"{e}")

    logger.info(
        f"Initialized {len(markets)} market platforms: {', '.join(m.__class__.__name__ for m in markets)}"
    )
    if len(markets) < 2:
        logger.error("Not enought markets")
        end()
    # Start the web interface
    from .webapp import run_webapp
    import threading

    webapp_thread = threading.Thread(target=run_webapp, daemon=True)
    webapp_thread.start()
    logger.info(f"Web interface started at http://localhost:{WEBAPP_PORT}")

    atexit.register(end)
