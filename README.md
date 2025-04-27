# Arbitrage Odds Finder

A system for detecting arbitrage opportunities across multiple sports betting platforms in real-time.

## Overview

This project monitors different sports betting platforms, collects odds data, and automatically identifies arbitrage opportunities - situations where the combined odds from different platforms allow for guaranteed profit by betting on all possible outcomes of an event.

### Features

- Real-time monitoring of multiple betting platforms
- Automatic matching of equivalent events across platforms
- Detection of arbitrage opportunities
- Web interface for monitoring system status and opportunities
- Console-based visualization with real-time updates
- Fuzzy matching of team names for improved event correlation
- Historical arbitrage opportunity tracking

## Installation

### Prerequisites

- Python 3.10+
- pip

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd arbitrage_odds
   ```

2. Install the package in development mode:
   ```bash
   pip install -e .
   ```

3. Install additional dependencies for testing:
   ```bash
   pip install -e ".[test]"
   ```

## Configuration

Configuration options are defined in `app/config.py`:

- `ARBITRAGE_EXPIRATION_TIMER`: How long arbitrage opportunities are considered valid (default: 30 minutes)
- `MAX_HISTORY_ENTRIES`: Maximum number of historical arbitrage opportunities to store (default: 1000)
- `MIN_PROFIT_THRESHOLD`: Minimum profit percentage to consider as an arbitrage opportunity (default: 0.5%)
- `STATS_UPDATE_INTERVAL`: How often to update stats display in seconds (default: 5.0)
- `TEAM_NAME_MATCH_RATIO`: Minimum ratio for fuzzy team name matching (default: 95)
- `SIMILAR_STRINGS_THRESHOLD`: Threshold for string similarity comparison (default: 0.9)
- `WEBAPP_PORT`: Port for the web interface (default: 8000)

## Usage

### Running the System

To start the arbitrage monitoring system:

```bash
python -m app.worker
```

This will:
1. Connect to all configured betting platforms
2. Start collecting odds data
3. Begin monitoring for arbitrage opportunities
4. Launch the web interface for monitoring

### Web Interface

Once the system is running, access the web interface at:

```
http://localhost:8000
```

The web interface provides:
- Current system statistics
- Active arbitrage opportunities
- Platform breakdown
- Live logs

### Analyzing Saved Data

To analyze previously saved odds data for arbitrage opportunities:

```bash
python -m app.tests.test_find [path/to/odds_data.json] [--threshold 0.9]
```

If no file is specified, the script will use the most recent odds data file in the current directory.

### Saving Odds Data

The system automatically logs odds data. To manually save the current database to a JSON file:

```python
from app.worker import manager
manager.save_database_to_json('filename.json')  # Optional filename
```

## Development

### Project Structure

```
arbitrage_odds/
├── app/                      # Main package
│   ├── __init__.py
│   ├── config.py             # Configuration options
│   ├── logs.py               # Logging configuration
│   ├── manager.py            # Core arbitrage detection logic
│   ├── obj.py                # Data models
│   ├── webapp.py             # Web interface
│   ├── worker.py             # Main application entry point
│   ├── logs/                 # Log files
│   ├── platforms/            # Platform-specific connectors
│   │   ├── __init__.py
│   │   ├── dexsport.py
│   │   ├── polymarket.py
│   │   └── polymarket_old.py
│   └── tests/                # Unit tests
│       ├── __init__.py
│       ├── test_dexsport.py
│       ├── test_find.py
│       ├── test_manager.py
│       ├── test_obj.py
│       └── test_set_structure.py
├── odds_data_*.json          # Saved odds data
├── setup.py                  # Package setup
└── README.md                 # This file
```

### Running Tests

To run all tests:

```bash
pytest
```

To run specific test modules:

```bash
pytest app/tests/test_obj.py
```

To run tests with coverage:

```bash
pytest --cov=app
```

### Adding a New Betting Platform

To add a new betting platform:

1. Create a new file in the `app/platforms` directory (e.g., `newplatform.py`)
2. Implement a class that connects to the platform and emits "newodd" events with BetOption objects
3. Add your platform to the imports in `app/platforms/__init__.py`
4. Add your platform to the list in `app/worker.py`

Example structure for a new platform class:

```python
from pyventus import EventEmitter
from ..obj import BetOption

class NewPlatform:
    def __init__(self, event_emitter: EventEmitter):
        self.event_emitter = event_emitter
        # Initialize connection to platform
        # Start data collection

    def get_odds(self):
        # Logic to get odds from the platform
        # For each betting opportunity found:
        bet = BetOption(
            platform="newplatform",
            id=f"newplatform{event_id}",
            optionA="Team A",
            optionB="Team B",
            probaA=2.0,  # Odds for Team A
            probaB=1.8,  # Odds for Team B
            probaDraw=3.5,  # Optional odds for a draw
            title="Match Title",  # Optional
            sport="Sport Name",   # Optional
            league="League Name"  # Optional
        )
        self.event_emitter.emit("newodd", bet)

    def stop(self):
        # Cleanup logic when shutting down
        pass
```

## Technical Details

### Arbitrage Detection Algorithm

1. Odds from different platforms are collected as `BetOption` objects
2. For each new odd, the system attempts to match it with existing odds from different platforms using:
   - Exact team name matching
   - Fuzzy matching for similar team names
   - Team name aliases from a predefined list
3. When matching odds are found, the system:
   - Identifies the best odds for each outcome
   - Calculates the sum of inverse odds (1/oddsA + 1/oddsB + 1/oddsDraw)
   - If this sum is less than 1, an arbitrage opportunity exists
4. The profit percentage is calculated as: (1 - sum_inverse_odds) * 100
5. For identified arbitrage opportunities, the system calculates optimal bet distribution

### Data Structures

- `SetStructure`: Custom data structure for efficiently managing related sets
- `Graph`: Structure for tracking odds relationships and arbitrage opportunities
- `BetOption`: Class representing a betting option with platform-specific details

## Troubleshooting

### Common Issues

1. **Connection failures to betting platforms**
   - Check network connectivity
   - Verify that the betting platform APIs haven't changed

2. **No arbitrage opportunities detected**
   - Lower the `MIN_PROFIT_THRESHOLD` in config.py
   - Check that odds are being collected properly from platforms
   - Verify that team name matching is working correctly

3. **High CPU usage**
   - Reduce polling frequency in platform connectors
   - Optimize team name matching for large datasets

## License

[Specify your license here]