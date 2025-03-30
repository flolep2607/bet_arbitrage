from fastapi import FastAPI, WebSocket
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import HTMLResponse
import uvicorn
import logging

logging.getLogger("asyncio").setLevel(logging.WARNING)
import asyncio
from datetime import datetime
from worker import manager
from logs import log_queue


def format_log_record(record: logging.LogRecord) -> dict:
    """Format log record into the structure expected by the web interface"""
    return {
        "time": (
            record.asctime.split()[1]
            if hasattr(record, "asctime")
            else datetime.now().strftime("%H:%M:%S")
        ),
        "level": record.levelname,
        "message": record.getMessage(),
        "color": {
            "ERROR": "danger",
            "WARNING": "warning",
            "INFO": "info",
            "DEBUG": "secondary",
            "success": "success",  # Pour le niveau personnalisé 'success'
            "trace": "info",  # Pour le niveau personnalisé 'trace'
        }.get(record.levelname, "info"),
    }


# Store connected websocket clients
# Use a thread-safe set for websocket connections
from threading import Lock

websocket_connections: set[WebSocket] = set()
websocket_lock = Lock()


async def broadcast_stats():
    """Broadcast stats to all connected clients"""
    while True:
        if websocket_connections:
            # Get recent logs
            logs: list[dict] = []
            logs_count = 0
            try:
                while not log_queue.empty() and logs_count < 100:
                    # Convert log record to the format expected by frontend
                    formatted_log = format_log_record(log_queue.get_nowait())
                    logs.append(formatted_log)
                    logs_count += 1
            except Exception as e:
                print(f"Error retrieving logs: {e}")

            # Get detailed stats
            detailed_stats = manager.get_detailed_stats()
            # arbitrage_stats = manager.get_stats()

            stats_data = {
                "runtime": manager.get_runtime(),
                "odds_count": manager.size(),
                "collection_rate": manager.get_collection_rate(),
                "matches_found": manager.matches_found,
                "platform_breakdown": manager.get_platform_breakdown(),
                "arbitrages": manager.get_active_arbitrages(),
                "logs": logs,
                "timestamp": datetime.now().isoformat(),
                # Add the new detailed statistics
                "stats": detailed_stats,
                # "arbitrage_stats": arbitrage_stats,
                # Add hourly summary for the last 24 hours
                "hourly_summary": manager.get_hourly_summary(24),
            }

            # Broadcast to all connected clients
            for connection in websocket_connections.copy():
                try:
                    await connection.send_json(stats_data)
                except Exception as e:
                    print(f"Error sending data to websocket: {e}")
                    websocket_connections.remove(connection)
        await asyncio.sleep(0.5)  # Update every second


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting lifespan context manager")
    # Start the stats broadcasting task
    loop = asyncio.get_event_loop()
    loop.create_task(broadcast_stats())
    yield
    print("Stopping lifespan context manager")
    # Clean up resources if needed


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    with websocket_lock:
        websocket_connections.add(websocket)
    try:
        while True:
            # Keep connection alive and wait for any client messages
            await websocket.receive_text()
    except Exception as e:
        # Clean up on any error
        with websocket_lock:
            if websocket in websocket_connections:
                websocket_connections.remove(websocket)
    finally:
        # Make sure we always clean up
        with websocket_lock:
            if websocket in websocket_connections:
                websocket_connections.remove(websocket)


@app.get("/", response_class=HTMLResponse)
async def get():
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Arbitrage Odds Monitor</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                .arbitrage-card {
                    margin-bottom: 1rem;
                    border-left: 4px solid #28a745;
                }
                .profit-high {
                    color: #28a745;
                    font-weight: bold;
                }
                .stats-card {
                    margin-bottom: 1rem;
                }
                .update-time {
                    font-size: 0.8rem;
                    color: #6c757d;
                }
            </style>
        </head>
        <body>
            <div class="container mt-4">
                <h1>Arbitrage Odds Monitor</h1>
                <div class="row">
                    <div class="col-md-4">
                        <div class="card stats-card">
                            <div class="card-body">
                                <h5 class="card-title">Statistics</h5>
                                <p>Runtime: <span id="runtime">-</span></p>
                                <p>Odds Collected: <span id="odds_count">-</span></p>
                                <p>Collection Rate: <span id="collection_rate">-</span> odds/min</p>
                                <p>Matches Found: <span id="matches_found">-</span></p>
                            </div>
                        </div>
                        <div class="card stats-card">
                            <div class="card-body">
                                <h5 class="card-title">Platform Breakdown</h5>
                                <div id="platform_breakdown"></div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-8">
                        <h3>Active Arbitrage Opportunities</h3>
                        <div id="arbitrages"></div>
                        <p class="update-time">Last update: <span id="last_update">-</span></p>
                    </div>
                </div>
                <div class="row mt-4">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-body">
                                <h5 class="card-title d-flex justify-content-between align-items-center">
                                    Live Logs
                                    <button id="scroll-to-bottom" class="btn btn-sm btn-outline-secondary" style="display: none;">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-arrow-down" viewBox="0 0 16 16">
                                            <path fill-rule="evenodd" d="M8 1a.5.5 0 0 1 .5.5v11.793l3.146-3.147a.5.5 0 0 1 .708.708l-4 4a.5.5 0 0 1-.708 0l-4-4a.5.5 0 0 1 .708-.708L7.5 13.293V1.5A.5.5 0 0 1 8 1z"/>
                                        </svg>
                                        Scroll to bottom
                                    </button>
                                </h5>
                                <div class="border rounded p-2" style="height: 300px; overflow-y: auto;" id="logs-container">
                                    <div id="logs" class="small"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <script>
                const logsContainer = document.getElementById('logs-container');
                const logsDiv = document.getElementById('logs');
                const scrollButton = document.getElementById('scroll-to-bottom');
                let userHasScrolled = false;

                // Function to check if scrolled to bottom
                function isScrolledToBottom() {
                    const threshold = 50; // pixels from bottom to consider "at bottom"
                    return logsContainer.scrollHeight - logsContainer.clientHeight <= logsContainer.scrollTop + threshold;
                }

                // Function to scroll to bottom
                function scrollToBottom() {
                    logsContainer.scrollTop = logsContainer.scrollHeight;
                    scrollButton.style.display = 'none';
                    userHasScrolled = false;
                }

                // Scroll button click handler
                scrollButton.addEventListener('click', scrollToBottom);

                // Track scroll position
                logsContainer.addEventListener('scroll', function() {
                    if (isScrolledToBottom()) {
                        scrollButton.style.display = 'none';
                        userHasScrolled = false;
                    } else {
                        scrollButton.style.display = 'block';
                        userHasScrolled = true;
                    }
                });

                function appendLogs(logs) {
                    const shouldScroll = !userHasScrolled;

                    logs.forEach(log => {
                        const logEntry = document.createElement('div');
                        logEntry.innerHTML = `
                            <span class="text-muted">${log.time}</span>
                            <span class="badge bg-${log.color}">${log.level}</span>
                            <span>${log.message}</span>
                        `;
                        logsDiv.appendChild(logEntry);
                    });

                    // Keep only last 500 log entries
                    while (logsDiv.children.length > 500) {
                        logsDiv.removeChild(logsDiv.firstChild);
                    }

                    // Auto-scroll to bottom only if user hasn't scrolled up
                    if (shouldScroll) {
                        logsContainer.scrollTop = logsContainer.scrollHeight;
                    }
                }
                const ws = new WebSocket(`ws://${window.location.host}/ws`);

                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);

                    // Update stats
                    document.getElementById('runtime').textContent = data.runtime;
                    document.getElementById('odds_count').textContent = data.odds_count;
                    document.getElementById('collection_rate').textContent = data.collection_rate.toFixed(1);
                    document.getElementById('matches_found').textContent = data.matches_found;

                    // Update platform breakdown
                    document.getElementById('platform_breakdown').innerHTML = Object.entries(data.platform_breakdown).map(([key, value])=>`${key}: ${value}`).join('<br>');

                    // Update arbitrages
                    const arbitragesHtml = data.arbitrages.map(arb => `
                        <div class="card arbitrage-card">
                            <div class="card-body">
                                <h5 class="card-title">${arb.match}</h5>
                                <p class="profit-high">Profit: ${arb.profit.toFixed(2)}%</p>
                                <ul class="list-unstyled">
                                    ${arb.bets.map(bet => `<li>• ${bet}</li>`).join('')}
                                </ul>
                            </div>
                        </div>
                    `).join('');
                    document.getElementById('arbitrages').innerHTML = arbitragesHtml;

                    // Update logs if any new ones
                    if (data.logs && data.logs.length > 0) {
                        appendLogs(data.logs);
                    }

                    // Update timestamp
                    const updateTime = new Date(data.timestamp).toLocaleTimeString();
                    document.getElementById('last_update').textContent = updateTime;
                };

                ws.onclose = function() {
                    // Try to reconnect
                    setTimeout(() => {
                        window.location.reload();
                    }, 1000);
                };
            </script>
        </body>
    </html>
    """


def run_webapp():
    uvicorn.run(app, host="0.0.0.0", port=8000)
