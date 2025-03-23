from py_clob_client.client import ClobClient, BookParams
import threading
import requests
from obj import BetOption
import json
from datetime import date, datetime
from loguru import logger
import time

client = ClobClient("https://clob.polymarket.com/")


class Polymarket:
    def __init__(self, event_emitter):
        self.event_emitter = event_emitter
        self.timer=threading.Timer(60, self.get_list)
        self.timer.start()
        self.get_list()

    def get_list(self):
        options = []
        # TODO add: end_date_max = +1j
        url = "https://gamma-api.polymarket.com/events?active=true&closed=false&liquidity_num_min=10000&limit=100&order=endDate&tag_id=1&related_tags=true"
        response = requests.get(url).json()
        for possibility in response:
            if not possibility.get("enableOrderBook"):
                continue
            league = possibility.get("seriesSlug")
            sport = {
                "nba": "Basketball",
                "nfl": "American Football",
                "epl": "Soccer",
                "mlb": "Baseball",
                "uel": "Soccer",
                "cfb": "American Football",
                "nhl": "Hockey",
            }.get(league, league)
            if possibility.get("markets"):
                markets = possibility.get("markets")
                id = possibility.get("id")
                optionA = None
                optionB = None
                try:
                    if len(markets) == 1:
                        market = markets[0]
                        if not market.get("enableOrderBook"):
                            continue
                        priceA = market.get("bestAsk")
                        priceB = 1 - market.get("bestBid",0)
                        # "outcomes": "["Yes", "No"]"
                        optionA = json.loads(market.get("outcomes"))[0]
                        optionB = json.loads(market.get("outcomes"))[1]
                        priceDraw = None
                    elif len(markets) == 3:
                        for market in markets:
                            qst = market.get("question")
                            if any(
                                i in qst
                                for i in ("draw", "tie", "no official winner", "no winner")
                            ):
                                priceDraw = market.get("bestAsk")
                            else:
                                if "beat" in qst:
                                    option = (
                                        qst.split("beat")[0].replace("Will", "").strip()
                                    )
                                elif "win" in qst:
                                    option = qst.split("win")[0].replace("Will", "").strip()
                                else:
                                    continue
                                price = market.get("bestAsk")
                                # if optionA doesn't exist set it
                                if optionA is None:
                                    optionA = option
                                    priceA = price
                                else:
                                    optionB = option
                                    priceB = price
                    else:
                        continue
                    if optionA is None or optionB is None:
                        logger.info("Skipping possibility: {}", possibility)
                        continue
                    options.append(
                        BetOption(
                            platform="polymarket",
                            id=f"polymarket{id}",
                            title=possibility.get("title"),
                            sport=sport,
                            league=league,
                            date=datetime.strptime(
                                possibility.get("endDate"), "%Y-%m-%dT%H:%M:%SZ"
                            ).date(),
                            probaA=1 / priceA,
                            probaB=1 / priceB,
                            probaDraw=1 / priceDraw if priceDraw else None,
                            optionA=optionA,
                            optionB=optionB,
                        )
                    )
                    self.event_emitter.emit("newodd", options[-1])
                except Exception as e:
                    logger.error(f"{e} => {json.dumps(possibility, indent=2)}")
        return options

    def stop(self):
        # kill the timer
        self.timer.cancel()

# client.get_simplified_markets()
# resp = client.get_prices(
#     params=[
#         BookParams(
#             token_id="71321045679252212594626385532706912750332728571942532289631379312455583992563",
#             side="BUY",
#         ),
#         BookParams(
#             token_id="71321045679252212594626385532706912750332728571942532289631379312455583992563",
#             side="SELL",
#         ),
#         BookParams(
#             token_id="52114319501245915516055106046884209969926127482827954674443846427813813222426",
#             side="BUY",
#         ),
#         BookParams(
#             token_id="52114319501245915516055106046884209969926127482827954674443846427813813222426",
#             side="SELL",
#         ),
#     ]
# )
