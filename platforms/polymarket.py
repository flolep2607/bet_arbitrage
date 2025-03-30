from typing import List, Optional, Dict
from py_clob_client.client import ClobClient, BookParams
import threading
from pyventus import EventEmitter
import requests
from obj import BetOption
import json
from datetime import date, datetime
import logging
from functools import lru_cache
from ratelimit import limits, sleep_and_retry

logger = logging.getLogger(__name__)


# Constants
API_BASE_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com/"
CALLS_PER_MINUTE = 30
ONE_MINUTE = 60

# Sport mapping dictionary
SPORT_MAPPING = {
    "nba": "Basketball",
    "nfl": "American Football",
    "epl": "Soccer",
    "mlb": "Baseball",
    "uel": "Soccer",
    "cfb": "American Football",
    "nhl": "Hockey",
}


class Polymarket:
    """Main Polymarket class for handling betting events and odds."""
    
    def __init__(self, event_emitter: EventEmitter):
        """
        Initialize Polymarket instance.
        
        Args:
            event_emitter: Event emitter for notifications
        """
        self.event_emitter = event_emitter
        # self.client = ClobClient(CLOB_URL)
        self.timer = threading.Timer(60, self.get_list)
        self.timer.start()
        self.get_list()

    @sleep_and_retry
    @limits(calls=CALLS_PER_MINUTE, period=ONE_MINUTE)
    def get_events(self, params: dict) -> dict:
        """
        Get events from Polymarket API with rate limiting.
        
        Args:
            params: Query parameters for the API
            
        Returns:
            JSON response from the API
        """
        url = f"{API_BASE_URL}/events"
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()

    @lru_cache(maxsize=128)
    def _get_sport(self, league: str) -> str:
        """
        Get sport name from league with caching.
        
        Args:
            league: League identifier
            
        Returns:
            Sport name
        """
        return SPORT_MAPPING.get(league, league)

    def _parse_market_outcomes(self, market: dict) -> tuple:
        """
        Parse market outcomes and prices.
        
        Args:
            market: Market data dictionary
            
        Returns:
            Tuple of (optionA, optionB, priceA, priceB, priceDraw)
        """
        if not market.get("enableOrderBook"):
            return None
            
        outcomes = json.loads(market.get("outcomes", "[]"))
        if len(outcomes) != 2:
            return None
            
        return (
            outcomes[0],
            outcomes[1],
            market.get("bestAsk"),
            1 - market.get("bestBid", 0),
            None
        )

    def _parse_three_way_market(self, markets: List[dict]) -> tuple:
        """
        Parse three-way market outcomes and prices.
        
        Args:
            markets: List of market dictionaries
            
        Returns:
            Tuple of (optionA, optionB, priceA, priceB, priceDraw)
        """
        optionA = optionB = priceA = priceB = priceDraw = None
        
        for market in markets:
            qst = market.get("question", "").lower()
            
            if any(term in qst for term in ("draw", "tie", "no official winner", "no winner")):
                priceDraw = market.get("bestAsk")
                continue
                
            option = None
            if "beat" in qst:
                option = qst.split("beat")[0].replace("will", "").strip()
            elif "win" in qst:
                option = qst.split("win")[0].replace("will", "").strip()
                
            if option:
                price = market.get("bestAsk")
                if optionA is None:
                    optionA, priceA = option, price
                else:
                    optionB, priceB = option, price
                    
        return optionA, optionB, priceA, priceB, priceDraw

    def get_list(self) -> List[BetOption]:
        """
        Get list of betting options.
        
        Returns:
            List of BetOption objects
        """
        options = []
        try:
            params = {
                "active": True,
                "closed": False,
                "liquidity_num_min": 10000,
                "limit": 100,
                "order": "endDate",
                "tag_id": 1,
                "related_tags": True
            }
            
            response = self.get_events(params)
            
            for possibility in response:
                if not possibility.get("enableOrderBook"):
                    continue
                    
                markets = possibility.get("markets", [])
                if not markets or len(markets) not in (1, 3):
                    continue
                    
                try:
                    if len(markets) == 1:
                        parsed = self._parse_market_outcomes(markets[0])
                    else:
                        parsed = self._parse_three_way_market(markets)
                        
                    if not parsed:
                        continue
                        
                    optionA, optionB, priceA, priceB, priceDraw = parsed
                    
                    if not all([optionA, optionB, priceA, priceB]):
                        logger.debug(f"Skipping incomplete market: {possibility.get('id')}")
                        continue
                    
                    bet_option = BetOption(
                        platform="polymarket",
                        id=f"polymarket{possibility.get('id')}",
                        title=possibility.get("title"),
                        sport=self._get_sport(possibility.get("seriesSlug")),
                        league=possibility.get("seriesSlug"),
                        event_date=datetime.strptime(
                            possibility.get("endDate"), 
                            "%Y-%m-%dT%H:%M:%SZ"
                        ).date(),
                        probaA=1 / priceA,
                        probaB=1 / priceB,
                        probaDraw=1 / priceDraw if priceDraw else None,
                        optionA=optionA,
                        optionB=optionB,
                    )
                    
                    options.append(bet_option)
                    self.event_emitter.emit("newodd", odd=bet_option)
                    
                except Exception as e:
                    logger.error(f"Error processing market: {e}", extra={"market": possibility.get("id")},exc_info=True)
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        
        return options

    def stop(self):
        """Stop the polling timer."""
        if self.timer:
            self.timer.cancel()