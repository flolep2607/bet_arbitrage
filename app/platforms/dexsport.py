import datetime
from pyventus import EventEmitter
import requests
import json
import threading
import websocket
import time
from ..obj import BetOption
from ..config import TOKEN_REFRESH_INTERVAL, API_REQUEST_TIMEOUT, WEBSOCKET_MESSAGE_RATE, WEBSOCKET_RETRY_MAX, WEBSOCKET_RETRY_DELAY, WEBSOCKET_CONNECT_TIMEOUT
from rich import print
from queue import SimpleQueue
import queue
import logging

logger = logging.getLogger(__name__)


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class Dexsport:
    running = False
    messageQueue: SimpleQueue[str] = SimpleQueue()
    RATELIMIT = WEBSOCKET_MESSAGE_RATE

    def __init__(self, event_emitter: EventEmitter):
        self.event_emitter = event_emitter
        self.token = self.get_token()
        self.tracked_events: list[str] = []
        self.ws = None
        self.token_refresh_interval = TOKEN_REFRESH_INTERVAL
        self.timer = threading.Timer(self.token_refresh_interval, self.refresh_token)
        self.timer.start()
        threading.Thread(target=self.sender, daemon=True).start()
        self.connect()

    def send(self, data):
        self.messageQueue.put(data)

    def sender(self):
        while True:
            message = self.messageQueue.get()
            if (
                isinstance(message, list)
                and len(message) == 3
                and message[0] == "join"
                and message[1] == "event"
                and isinstance(message[2], list)
            ):
                combined_events = message[2]
                while len(combined_events) < 5:
                    try:
                        next_msg = self.messageQueue.get_nowait()
                        if (
                            isinstance(next_msg, list)
                            and len(next_msg) == 3
                            and next_msg[0] == "join"
                            and next_msg[1] == "event"
                            and isinstance(next_msg[2], list)
                        ):
                            combined_events.extend(next_msg[2])
                            if len(combined_events) >= 5:
                                break
                        else:
                            self.messageQueue.put(next_msg)
                            break
                    except queue.Empty:
                        break
                combined_message = ["join", "event", combined_events]
                logger.debug(f"Sending combined message: {combined_message}")
                self.ws.send(json.dumps(combined_message))
            else:
                logger.debug(f"Sending message: {message}")
                self.ws.send(json.dumps(message))
            time.sleep(1 / self.RATELIMIT)

    def get_token(self):
        headers = {
            "content-type": "application/json;charset=UTF-8",
        }
        json_data = {
            "apiKey": "DexSport",
            "guest": True,
        }
        try:
            response = requests.post(
                "https://prod.dexsport.work/public/api/profile",
                headers=headers,
                json=json_data,
                timeout=API_REQUEST_TIMEOUT,
            )
            response.raise_for_status()  # Raise exception for HTTP errors
            data = response.json()
            if "token" not in data:
                logger.error(f"Invalid token response: {data}")
                raise ValueError("No token in response")
            return data["token"]
        except requests.RequestException as e:
            logger.error(f"Failed to get token: {e}")
            time.sleep(5)
            return self.get_token()  # Retry recursively, but with caution
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse token response: {e}")
            time.sleep(5)
            return self.get_token()  # Retry recursively, but with caution

    def connect(self):
        retry_count = 0
        
        while retry_count < WEBSOCKET_RETRY_MAX:
            try:
                url = f"wss://prod.dexsport.work/ws?cid=DexSport&lang=en&timestamp=eyJub3ciOiIyMDI0LTExLTA1VDE5OjQzOjMxLjgyOFoiLCJleHBpcmVkIjpmYWxzZSwiZXhwIjoiMjAyNC0xMS0wNVQxOTo1MzozMS44MjdaIiwicmN2IjoiMjAyNC0xMS0wNVQxOTo0MzozMS44MjdaIn0&token={self.token}&format=short"
                headers = {"Authorization": f"Bearer {self.token}"}
                
                self.ws = websocket.WebSocketApp(
                    url,
                    header=headers,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )
                threading.Thread(target=self.ws.run_forever, daemon=True).start()
                
                timeout = WEBSOCKET_CONNECT_TIMEOUT
                start_time = time.time()
                while not self.running and time.time() - start_time < timeout:
                    time.sleep(0.5)
                    
                if self.running:
                    logger.info("WebSocket connection established successfully")
                    threading.Thread(target=self.ask_all).start()
                    return
                else:
                    logger.warning(f"Failed to establish WebSocket connection (attempt {retry_count + 1}/{WEBSOCKET_RETRY_MAX})")
                    retry_count += 1
                    time.sleep(WEBSOCKET_RETRY_DELAY * retry_count)
            except Exception as e:
                logger.error(f"Error during WebSocket connection: {e}")
                retry_count += 1
                time.sleep(WEBSOCKET_RETRY_DELAY * retry_count)
        
        logger.error(f"Failed to establish WebSocket connection after {WEBSOCKET_RETRY_MAX} attempts")

    def add_discipline(self, sport: str):
        self.send(["join", "discipline", [f"2.{sport}", f"1.{sport}"]])

    def ask_all(self):
        while not self.running:
            time.sleep(0.1)
        sports = [
            "football",
            "tennis",
            "basketball",
            "hockey",
            "american-football",
            "cricket",
            "rugby",
            "mma",
            "boxing",
            "horse-racing",
            "harness-racing",
            "greyhound-racing",
            "golf",
            "formula1",
            "efootball",
            "ebasketball",
            "csgo",
            "dota2",
            "lol",
            "ehockey",
            "ecricket",
            "pubg",
            "rainbow6",
        ]
        for sport in sports:
            self.add_discipline(sport)
            time.sleep(2)
        return
        response = requests.get(
            f"https://prod.dexsport.work/api/sportsbook/express?disciplineIds={','.join(sports)}&limit=100",
            headers={"authorization": f"Bearer {self.token}"},
        ).json()
        event_ids = [20716672]
        for event in response["data"]:
            for sub_event in event:
                event_ids.append(sub_event["eventId"])
        for chunk in chunks(event_ids, 1):
            self.add_events(chunk)
            time.sleep(0.5)

    def on_open(self, ws):
        logger.debug("WebSocket connection opened")
        self.running = True

    def on_close(self, ws, *args):
        previous_state = self.running
        self.running = False
        logger.debug(f"WebSocket connection closed with args: {args}")
        
        if previous_state:
            logger.info("Connection closed unexpectedly, reconnecting...")
            time.sleep(5)
            self.connect()

    def on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
        if not self.running:
            logger.info("Attempting to reconnect...")
            time.sleep(5)
            self.connect()

    def on_message(self, ws, message):
        data = json.loads(message)
        name = data.pop(0)
        rest = data[1:]
        data = data[0]
        if name == "event":
            self.analysis(data)
        elif name == "batch":
            for msg in data:
                self.analysis(msg)
        elif name in ("config", "error", "leave"):
            return
        else:
            logger.error(f"Unhandled message type:{name}##{data}|{rest}")

    def analysis(self, msg):
        if msg[0] == "market":
            logger.debug(f"Market: {msg}")
            market_id = msg[1]
            data = msg[3]
            if data["name"] in ("Match Winner", "Fight Winner", "Winner. With overtime"):
                optionA, optionB = None, None
                probaDraw = None
                for outcome in data["outcomes"]:
                    if not "name" in outcome:
                        logger.warning(f"!!!! not 'name' {market_id} => {outcome}")
                    else:
                        if "draw" in outcome["name"].lower():
                            probaDraw = outcome["price"]
                        elif optionA is None:
                            optionA = outcome["name"]
                            probaA = outcome["price"]
                        else:
                            optionB = outcome["name"]
                            probaB = outcome["price"]
                if optionA and optionB:
                    bet = BetOption(
                        platform="dexsport",
                        id=f"dexsport{market_id}",
                        optionB=optionB,
                        optionA=optionA,
                        probaA=probaA,
                        probaB=probaB,
                        probaDraw=probaDraw,
                    )
                    if self.event_emitter:
                        self.event_emitter.emit("newodd", odd=bet)
                    else:
                        logger.info(f"Bet: {bet}")
                else:
                    logger.warning(f"Skipping market {data}")
            else:
                pass
        elif msg[0] == "event":
            if len(msg) >= 4:
                data = msg[3]
                if "startTime" in data:
                    # logger.debug(f"Event: {msg}")
                    start_time = datetime.datetime.fromtimestamp(data["startTime"]).date()
                    for part_event_id in data.get('marketIds', []):
                        event_id = f"dexsport{part_event_id}"
                        self.event_emitter.emit("update_date", event_id=event_id, start_time=start_time)

                    event_id = f"dexsport{data['lid']}"
                    self.event_emitter.emit("update_date", event_id=event_id, start_time=start_time)
            return
        elif msg[0] == "discipline":
            self.send(["join", "tournament", msg[3]["tournamentIds"]])
        elif msg[0] == "tournament":
            for event in msg[3].get("eventRefs", []):
                self.add_event(event["lid"])
        elif msg[0] == "leave":
            logger.error(f"leave: {json.dumps(msg)}")
        elif msg[0] == "error":
            logger.error(f"error: {json.dumps(msg)}")
        else:
            logger.error(f"{msg}")

    def refresh_token(self):
        self.token = self.get_token()
        self.ws.close()
        self.connect()

    def add_event_id(self, event):
        logger.debug(f"Adding event {event}")
        if event not in self.tracked_events:
            self.send(["join", "event", [f"2.{event}", f"1.{event}"]])
            self.tracked_events.append(event)
            logger.debug(f"Event added: {event}")

    def add_event(self, event):
        if event not in self.tracked_events:
            self.send(["join", "event", [event]])
            self.tracked_events.append(event)

    def add_events(self, events: list[int]):
        logger.debug(f"Adding {len(events)} events")
        events_ids = []
        for event in events:
            events_ids.extend([f"2.{event}", f"1.{event}"])

        self.send(["join", "event", [f"2.{event}", f"1.{event}"]])
        self.tracked_events.extend(events)

    def remove_event(self, event):
        if event in self.tracked_events:
            self.send(["leave", "event", [f"2.{event}", f"1.{event}"]])
            self.tracked_events.remove(event)
            logger.warning(f"Event removed: {event}")

    def stop(self):
        self.timer.cancel()
        if self.ws:
            self.ws.close()


if __name__ == "__main__":
    dexsport = Dexsport(None)
