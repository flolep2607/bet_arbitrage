from dataclasses import dataclass
from typing import List, Optional
from datetime import date, datetime

@dataclass
class BetOption:
    id: str
    platform: str
    title: Optional[str]
    sport: Optional[str]
    league: Optional[str]
    event_date: Optional[date]

    optionA: str
    probaA: float

    optionB: str
    probaB: float

    probaDraw: Optional[float]
    
    timestamp: Optional[datetime] = None

    def __init__(
        self,
        platform: str,
        id: str,
        optionA: str,
        optionB: str,
        probaA: float,
        probaB: float,
        probaDraw: Optional[float],
        title: Optional[str] = None,
        sport: Optional[str] = None,
        league: Optional[str] = None,
        event_date: Optional[date] = None,
    ):
        self.platform = platform
        self.id = id
        self.title = title
        self.sport = sport
        self.league = league
        self.event_date = event_date
        self.optionA = optionA
        self.probaA = probaA
        self.optionB = optionB
        self.probaB = probaB
        self.probaDraw = probaDraw
        self.timestamp = datetime.now()

    def is_garbage(self):
        if (self.probaA < 0.01 or self.probaB < 0.01) or \
            (self.probaA > 100 or self.probaB > 100):
            return True
        
        if self.optionA.lower() in ("yes", "no"):
            return True
        if self.optionB.lower() in ("yes", "no"):
            return True
        if self.optionA.lower() == self.optionB.lower():
            return True
        
        if self.event_date and self.event_date < date.today():
            return True
        
        return False