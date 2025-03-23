#!/usr/bin/env python3

import json
import os
import sys
import argparse
from datetime import datetime
from typing import Dict, List
from loguru import logger
import glob
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

# Import the matcher function from worker.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from worker import are_similar, normalize_team_name, BetOption, EnhancedJSONEncoder
except ImportError:
    logger.error("Could not import functions from worker.py")
    sys.exit(1)

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO", format="[{name}.py:{line}] <green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>")

console = Console()

def load_json_data(filename: str) -> Dict:
    """Load data from a JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON from {filename}")
        return {}
    except FileNotFoundError:
        logger.error(f"File not found: {filename}")
        return {}

def find_matches_in_data(data: Dict, threshold: float = 0.9) -> List:
    """Find matching odds across different platforms"""
    matches = []
    items = list(data.values())
    
    # Group by similar team names
    for i in tqdm(range(len(items)), desc="Finding matches", total=len(items)):
        for j in tqdm(range(i + 1, len(items)), desc="Comparing", leave=False):
            item1 = items[i]
            item2 = items[j]
            
            # Skip if from the same platform
            if item1['platform'] == item2['platform']:
                continue
            
            # Try to match both team combinations:
            # Standard order: A1 vs B1 matches A2 vs B2
            standard_match = (
                are_similar(item1['optionA'], item2['optionA'], threshold) and 
                are_similar(item1['optionB'], item2['optionB'], threshold)
            )
            # Reversed order: A1 vs B1 matches B2 vs A2
            reversed_match = (
                are_similar(item1['optionA'], item2['optionB'], threshold) and 
                are_similar(item1['optionB'], item2['optionA'], threshold)
            )
            
            # Check if either match pattern works
            if standard_match or reversed_match:
                logger.info(f"Found potential match: {standard_match} {reversed_match}")
                # If they match in reversed order, swap optionA/B in item2 for consistency
                if reversed_match and not standard_match:
                    logger.info(f"Detected reversed team order between platforms:")
                    logger.info(f"  {item1['platform']}: {item1['optionA']} vs {item1['optionB']}")
                    logger.info(f"  {item2['platform']}: {item2['optionB']} vs {item2['optionA']} (reversed)")
                    
                    # For odds calculation, we'll swap the team order and probabilities in item2
                    # Create temporary objects for calculation to avoid modifying original data
                    calc_item2 = item2.copy()
                    calc_item2['optionA'], calc_item2['optionB'] = calc_item2['optionB'], calc_item2['optionA']
                    calc_item2['probaA'], calc_item2['probaB'] = calc_item2['probaB'], calc_item2['probaA']
                else:
                    logger.info(f"Detected standard team order between platforms:")
                    calc_item2 = item2
                
                # Calculate potential arbitrage
                bestA = max(item1['probaA'], calc_item2['probaA'])
                bestB = max(item1['probaB'], calc_item2['probaB'])
                
                # Handle draw probabilities if they exist
                bestDraw = None
                if item1.get('probaDraw') and calc_item2.get('probaDraw'):
                    bestDraw = max(item1['probaDraw'], calc_item2['probaDraw'])
                elif item1.get('probaDraw'):
                    bestDraw = item1['probaDraw']
                elif calc_item2.get('probaDraw'):
                    bestDraw = calc_item2['probaDraw']
                
                # Sum of inverse odds
                sum_inverse = 1/bestA + 1/bestB
                if bestDraw:
                    sum_inverse += 1/bestDraw
                
                matches.append({
                    'item1': item1,
                    'item2': item2,
                    'reversed': reversed_match and not standard_match,
                    'sum_inverse': sum_inverse,
                    'profit_percentage': (1 - sum_inverse) * 100 if sum_inverse < 1 else 0
                })

    # Sort by potential profit
    matches.sort(key=lambda x: x['profit_percentage'], reverse=True)
    return matches

def display_matches(matches: List):
    """Display matches in a rich table"""
    if not matches:
        console.print("[yellow]No matches found[/yellow]")
        return
    
    # Table for arbitrage opportunities
    arb_table = Table(title="Arbitrage Opportunities")
    arb_table.add_column("Teams", style="cyan")
    arb_table.add_column("Platforms", style="magenta")
    arb_table.add_column("Best Odds A", style="green")
    arb_table.add_column("Best Odds B", style="green")
    arb_table.add_column("Best Draw", style="green")
    arb_table.add_column("Sum Inverse", style="blue")
    arb_table.add_column("Profit %", style="bold red")
    
    # Table for potential matches without arbitrage
    match_table = Table(title="Other Matches (No Arbitrage)")
    match_table.add_column("Teams", style="cyan")
    match_table.add_column("Platforms", style="magenta")
    match_table.add_column("Sum Inverse", style="blue")
    match_table.add_column("Notes", style="yellow")
    
    for match in matches:
        item1 = match['item1']
        item2 = match['item2']
        
        # Handle the display based on whether teams were matched in reversed order
        if match['reversed']:
            teams = f"{item1['optionA']} vs {item1['optionB']}"
            platforms = f"{item1['platform']} & {item2['platform']} (reversed order)"
            note = f"Teams reversed: {item2['optionB']} vs {item2['optionA']}"
            
            # For calculation purposes, get the correct order
            bestA = max(item1['probaA'], item2['probaB'])
            bestB = max(item1['probaB'], item2['probaA'])
        else:
            teams = f"{item1['optionA']} vs {item1['optionB']}"
            platforms = f"{item1['platform']} & {item2['platform']}"
            note = ""
            
            bestA = max(item1['probaA'], item2['probaA'])
            bestB = max(item1['probaB'], item2['probaB'])
        
        # Handle draw probabilities if they exist
        bestDraw = None
        if item1.get('probaDraw') and item2.get('probaDraw'):
            bestDraw = max(item1['probaDraw'], item2['probaDraw'])
        elif item1.get('probaDraw'):
            bestDraw = item1['probaDraw']
        elif item2.get('probaDraw'):
            bestDraw = item2['probaDraw']
        
        # If it's an arbitrage opportunity
        if match['profit_percentage'] > 0:
            arb_table.add_row(
                teams,
                platforms,
                f"{bestA:.2f}",
                f"{bestB:.2f}",
                f"{bestDraw:.2f}" if bestDraw else "N/A",
                f"{match['sum_inverse']:.4f}",
                f"{match['profit_percentage']:.2f}%"
            )
        else:
            match_table.add_row(
                teams,
                platforms,
                f"{match['sum_inverse']:.4f}",
                note
            )
    
    # Print tables
    if any(match['profit_percentage'] > 0 for match in matches):
        console.print(arb_table)
    else:
        console.print("[yellow]No arbitrage opportunities found[/yellow]")
        
    if any(match['profit_percentage'] <= 0 for match in matches):
        console.print(match_table)

def main():
    parser = argparse.ArgumentParser(description="Find matches and arbitrage opportunities in saved odds data")
    parser.add_argument("file", nargs="?", help="JSON file to analyze (default: latest file in current directory)")
    parser.add_argument("--threshold", type=float, default=0.9, help="Similarity threshold for team name matching (default: 0.9)")
    args = parser.parse_args()
    
    # If no file specified, find the latest JSON file
    filename = args.file
    if not filename:
        json_files = glob.glob("odds_data_*.json")
        if not json_files:
            logger.error("No JSON files found. Please specify a file.")
            sys.exit(1)
        latest_file = max(json_files, key=os.path.getctime)
        filename = latest_file
        logger.info(f"Using latest file: {filename}")
    
    # Load data from JSON file
    data = load_json_data(filename)
    if not data:
        logger.error("No data found or could not load file.")
        sys.exit(1)
    
    logger.info(f"Loaded {len(data)} odds from {filename}")
    
    # Find matches
    matches = find_matches_in_data(data, args.threshold)
    logger.info(f"Found {len(matches)} potential matches")
    
    # Display results
    display_matches(matches)
    
    # Count arbitrage opportunities
    arb_count = sum(1 for match in matches if match['profit_percentage'] > 0)
    if arb_count > 0:
        logger.success(f"Found {arb_count} arbitrage opportunities!")
    else:
        logger.info("No arbitrage opportunities found")

if __name__ == "__main__":
    main()
