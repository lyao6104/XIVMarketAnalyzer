from datetime import datetime
import json
import pathlib
import sqlite3
import time
import urllib.request as urllib
from urllib.error import HTTPError

from ratelimit import limits, sleep_and_retry
from tabulate import tabulate

from src.util import *
import src.variables as variables

# Constants
WEIGHT_AVG_LISTING_PRICE = 25
WEIGHT_AVG_SALE_PRICE = 60
WEIGHT_SALE_VELOCITY = 40
WEIGHT_MIN_AVG_PRICE_DIFF = 25

def dict_factory(cursor, row):
# From the sqlite3 documentation
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

@sleep_and_retry
@limits(20, 1)
def query_universalis(item_id, world_name):
# Query Universalis at a maximum of 20 calls per second
    print(f"Querying Item {item_id}...")

    # Get item name from XIVAPI
    try:
        xiv_request = urllib.Request(
            f"https://xivapi.com/item/{item_id}?columns=Name")
        xiv_request.add_header('User-Agent', '&lt;User-Agent&gt;')
        xiv_data = json.loads(urllib.urlopen(xiv_request).read())
        print(f"- Found Item {item_id}: {xiv_data['Name']} from XIVAPI...")
    except HTTPError:
        print("- Item not found on XIVAPI. Skipping...")
        return {}

    # Get listing data from Universalis
    univ_request = urllib.Request(
        f"https://universalis.app/api/{world_name}/{item_id}")
    univ_request.add_header('User-Agent', '&lt;User-Agent&gt;')
    entry_data = json.loads(urllib.urlopen(univ_request).read())
    print("- Successfully obtained Universalis data.")

    # Add item name from XIVAPI and return
    entry_data["item_name"] = xiv_data["Name"]
    return entry_data

sqlite3.register_adapter(datetime, lambda ts: time.mktime(ts.timetuple()))
con = sqlite3.connect("market_analyzer.db")
con.row_factory = dict_factory
cur = con.cursor()

# Update last DB update time
variables.init(pathlib.Path("./variables.json").resolve())
last_update_time = variables.get_variable("lastUpdateTime")
if last_update_time is None:
    last_update_time = str(datetime.now())
flag_update_db = input(f"Item database was last updated at {last_update_time}. Update database (y/N)? ").lower() == "y"
if flag_update_db:
    last_update_time = str(datetime.now())
variables.set_variable("lastUpdateTime", last_update_time)

# Check whether database exists
if cur.execute("select count(name) as count from gathering_items").fetchone()['count'] < 1:
    print("Error: Gathering item database is empty. Exiting...")
    exit()
else:
    print("Successfully connected to database.")

# Get min and max gathering level for filtering items.
min_level = 1
try:
    level = int(input("Enter minimum gathering level (Default: 1): "))
    min_level = clamp(level, 1, 90)
except ValueError:
    pass

max_level = 90
try:
    level = int(input("Enter maximum gathering level (Default: 90): "))
    max_level = clamp(level, 1, 90)
except ValueError:
    pass

if min_level > max_level:
    min_level, max_level = max_level, min_level
    print("Automatically swapped minimum and maximum level.")

items = cur.execute(
    "select item_id from gathering_items where gathering_level >= ? and gathering_level <= ?",
    (min_level,
     max_level)).fetchall()
print(f"Found {len(items)} items between Level {min_level} and Level {max_level}")

world_name = input("Enter name of World or Data Centre (Default: Faerie): ")
if len(world_name) < 1:
    world_name = "Faerie"

# Gathering items don't have high-quality versions anymore, so a lot of those are going to be commented out.
# I might still use this for other stuff though, so it's not going to be removed entirely.

print("Making Universalis requests...")
univ_entries = []
entry_minmaxes = {
    "listing_price_nq": MinMax(),
    "sale_price_nq": MinMax(),
    "velocity_nq": MinMax(),
    "difference_nq": MinMax(),
    "listing_price_hq": MinMax(),
    "sale_price_hq": MinMax(),
    "velocity_hq": MinMax(),
    "difference_hq": MinMax()}
for item in items:
    entry = query_universalis(item["item_id"], world_name)
    if entry == {}:
        continue
    univ_entries.append(entry)
    entry = univ_entries[len(univ_entries) - 1]

    entry_minmaxes["listing_price_nq"].add_value(
        entry["currentAveragePriceNQ"])
    entry_minmaxes["sale_price_nq"].add_value(entry["averagePriceNQ"])
    entry_minmaxes["velocity_nq"].add_value(entry["nqSaleVelocity"])
    entry_minmaxes["difference_nq"].add_value(
        entry["currentAveragePriceNQ"] - entry["minPriceNQ"])

    # entry_minmaxes["listing_price_hq"].add_value(
    #     entry["currentAveragePriceHQ"])
    # entry_minmaxes["sale_price_hq"].add_value(entry["averagePriceHQ"])
    # entry_minmaxes["velocity_hq"].add_value(entry["hqSaleVelocity"])
    # entry_minmaxes["difference_hq"].add_value(
    #     entry["currentAveragePriceHQ"] - entry["minPriceHQ"])

if len(univ_entries) < 1:
    print("Error: No results found. Exiting...")
    exit()
else:
    print(f"Successfully found results for {len(univ_entries)} items.")

num_recommendations = 5
try:
    num_recommendations = int(input("Enter number of desired recommendations (Default: 5): "))
except ValueError:
    pass

for entry in univ_entries:
    entry["score_nq"] = entry_minmaxes["listing_price_nq"].get_t(
        entry["currentAveragePriceNQ"]) * WEIGHT_AVG_LISTING_PRICE + entry_minmaxes["sale_price_nq"].get_t(
        entry["averagePriceNQ"]) * WEIGHT_AVG_SALE_PRICE + entry_minmaxes["velocity_nq"].get_t(
            entry["nqSaleVelocity"]) * WEIGHT_SALE_VELOCITY + WEIGHT_MIN_AVG_PRICE_DIFF - (entry_minmaxes["difference_nq"].get_t(
                entry["currentAveragePriceNQ"] - entry["minPriceNQ"]) * WEIGHT_MIN_AVG_PRICE_DIFF)
    # entry["score_hq"] = entry_minmaxes["listing_price_hq"].get_t(
    #     entry["currentAveragePriceHQ"]) * WEIGHT_AVG_LISTING_PRICE + entry_minmaxes["sale_price_hq"].get_t(
    #     entry["averagePriceHQ"]) * WEIGHT_AVG_SALE_PRICE + entry_minmaxes["velocity_hq"].get_t(
    #         entry["hqSaleVelocity"]) * WEIGHT_SALE_VELOCITY + entry_minmaxes["difference_hq"].get_t(
    #             entry["currentAveragePriceHQ"] - entry["minPriceHQ"]) * WEIGHT_MIN_AVG_PRICE_DIFF

sorted_nq_raw = sorted(univ_entries, key=lambda entry: entry["score_nq"], reverse=True)[:num_recommendations]
# sorted_hq_raw = sorted(univ_entries, key=lambda entry: entry["score_hq"])[:5]

# Formatted for the tabulate library
sorted_nq = {"Name": [], "Avg. Listing Price": [], "Avg. Sale Price": [], "Sales Per Day": [], "Avg - Min Listing Price": []}
for entry in sorted_nq_raw:
    sorted_nq["Name"].append(entry["item_name"])
    sorted_nq["Avg. Listing Price"].append(entry["currentAveragePriceNQ"])
    sorted_nq["Avg. Sale Price"].append(entry["averagePriceNQ"])
    sorted_nq["Sales Per Day"].append(entry["nqSaleVelocity"])
    sorted_nq["Avg - Min Listing Price"].append(entry["currentAveragePriceNQ"] - entry["minPriceNQ"])

# sorted_hq = {"Name": [], "Avg. Listing Price": [], "Avg. Sale Price": [], "Sales Per Day": [], "Avg - Min Listing Price": []}
# for entry in sorted_nq_raw:
#     sorted_hq["Name"].append(entry["item_name"])
#     sorted_hq["Avg. Listing Price"].append(entry["currentAveragePriceHQ"])
#     sorted_hq["Avg. Sale Price"].append(entry["averagePriceHQ"])
#     sorted_hq["Sales Per Day"].append(entry["hqSaleVelocity"])
#     sorted_hq["Avg - Min Listing Price"].append(entry["currentAveragePriceHQ"] - entry["minPriceHQ"])

print("\nRecommended NQ Items:")
print(tabulate(sorted_nq, headers="keys", tablefmt="fancy_grid"))
# print("\nRecommended HQ Items:")
# print(tabulate(sorted_hq, headers="keys", tablefmt="fancy_grid"))

variables.close()
con.close()
