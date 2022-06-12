# XIVMarketAnalyzer

Analyzes market board data from Final Fantasy XIV using Universalis and XIVAPI, then makes recommendations on what to sell.
The script does **not** interact with the actual game in any way.

Currently works for gatherable items, paintings, and orchestrion rolls.

To use, run `UpdateDB.py`, then the main file, `MarketAnalyzer.py`, assuming you have the required
dependencies and Python 3 installed. You can also run the script using Pipenv or the provided Makefile.

## Dependencies

This project requires the `ratelimit` and `tabulate` libraries for Python 3.
