import json
import pathlib
import sqlite3
import time
import urllib.request as urllib
from datetime import datetime
from select import select
from urllib.error import HTTPError

from ratelimit import limits, sleep_and_retry
from tabulate import tabulate

import src.variables as variables
from src.util import *

#####
# Constants
#####

WEIGHT_AVG_LISTING_PRICE = 25
WEIGHT_AVG_SALE_PRICE = 50
WEIGHT_SALE_VELOCITY = 50
WEIGHT_MIN_AVG_PRICE_DIFF = 25
ITEM_TYPES = [
    "Gatherable",
    "Painting",
]

#####
# Utility Functions
#####


def dict_factory(cursor, row):
    # From the sqlite3 documentation
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


@sleep_and_retry
@limits(20, 1)
def query_items(item_tuples, world_name, batch_size=20):
    # Query Universalis for multiple items at once at a maximum of 20 calls per second
    batches = []
    entries = []  # [ { "item_name": item_name } for item_id, item_name in item_tuples ]
    while len(item_tuples) > 0:
        batches.append(item_tuples[:batch_size])
        item_tuples = item_tuples[batch_size:]
    print(f"Querying {len(batches)} batches of {batch_size} items each...")

    # Get listing data from Universalis
    for i in range(0, len(batches)):
        batch = {item_id: item_name for item_id, item_name in batches[i]}
        print(f"Querying Universalis for Batch {i + 1}...")
        listings_request = urllib.Request(
            f"https://universalis.app/api/{world_name}/{','.join((map(str, batch.keys())))}?entries=100"
        )
        listings_request.add_header("User-Agent", "&lt;User-Agent&gt;")
        try:
            listings_response = json.loads(urllib.urlopen(listings_request).read())
        except HTTPError:
            print("- Listings request failed. Skipping batch...")
            continue
        failed_items = listings_response["unresolvedItems"]
        if len(failed_items) > 0:
            print(f"- Failed to retrieve data for {len(failed_items)} items:")
            for item in failed_items:
                print(f"  - Item {item}: {batch[item]}")
        else:
            print("- Successfully found listing data for all items in batch:")

        for listing_data in listings_response["items"]:
            entry_data = {
                "item_id": listing_data["itemID"],
                "item_name": batch[listing_data["itemID"]],
            }
            entry_data["currentAveragePriceNQ"] = listing_data["currentAveragePriceNQ"]
            entry_data["averagePriceNQ"] = listing_data["averagePriceNQ"]
            entry_data["currentPriceDifferenceNQ"] = (
                listing_data["currentAveragePriceNQ"] - listing_data["minPriceNQ"]
            )
            entry_data["currentAveragePriceHQ"] = listing_data["currentAveragePriceHQ"]
            entry_data["averagePriceHQ"] = listing_data["averagePriceHQ"]
            entry_data["currentPriceDifferenceHQ"] = (
                listing_data["currentAveragePriceHQ"] - listing_data["minPriceHQ"]
            )
            entries.append(entry_data)
            print(
                f"  - Found listing data for Item {entry_data['item_id']}: {entry_data['item_name']}"
            )

        # Sale velocities are kind of weird, so we need to make a separate request for historical data.
        sale_request = urllib.Request(
            f"https://universalis.app/api/history/{world_name}/{','.join((map(str, batch.keys())))}"
        )
        sale_request.add_header("User-Agent", "&lt;User-Agent&gt;")
        try:
            sale_response = json.loads(urllib.urlopen(sale_request).read())
        # A 404 response should only happen if the world name is wrong
        except HTTPError:
            for i in range(0, len(entries)):
                entries[i]["nqSaleVelocity"] = 0
                entries[i]["hqSaleVelocity"] = 0
            print("- Warning: Failed to obtain sale data from Universalis.")
            continue
        # Set velocities to zero for all failed items
        failed_items = set(sale_response["unresolvedItems"])
        if len(failed_items) > 0:
            print(f"- Failed to retrieve sales data for {len(failed_items)} items:")
            for item in failed_items:
                print(f"  - Item {item}: {batch[item]}")
            for i in range(0, len(entries)):
                if entries[i]["item_id"] in failed_items:
                    entries[i]["nqSaleVelocity"] = 0
                    entries[i]["hqSaleVelocity"] = 0
        else:
            print("- Successfully found sales data for all items in batch.")

        # Annotate entries with sales data
        sale_data = {
            item_data["itemID"]: {
                "nqSaleVelocity": item_data["nqSaleVelocity"],
                "hqSaleVelocity": item_data["hqSaleVelocity"],
            }
            for item_data in sale_response["items"]
        }
        for i in range(0, len(entries)):
            if entries[i].get("nqSaleVelocity") is None:
                entries[i]["nqSaleVelocity"] = sale_data[entries[i]["item_id"]][
                    "nqSaleVelocity"
                ]
            if entries[i].get("hqSaleVelocity") is None:
                entries[i]["hqSaleVelocity"] = sale_data[entries[i]["item_id"]][
                    "hqSaleVelocity"
                ]

    return entries


@sleep_and_retry
@limits(20, 1)
def query_item(item_tuple, world_name):
    # Query Universalis at a maximum of 20 calls per second
    item_id, item_name = item_tuple
    print(f"Querying Item {item_id}: {item_name}...")
    entry_data = {"item_name": item_name}

    # Get listing data from Universalis
    listing_request = urllib.Request(
        f"https://universalis.app/api/{world_name}/{item_id}?entries=100"
    )
    listing_request.add_header("User-Agent", "&lt;User-Agent&gt;")
    try:
        listing_data = json.loads(urllib.urlopen(listing_request).read())
    except HTTPError:
        print("- Listing data not found on Universalis. Skipping...")
        return {}
    entry_data["currentAveragePriceNQ"] = listing_data["currentAveragePriceNQ"]
    entry_data["averagePriceNQ"] = listing_data["averagePriceNQ"]
    entry_data["currentPriceDifferenceNQ"] = (
        listing_data["currentAveragePriceNQ"] - listing_data["minPriceNQ"]
    )
    entry_data["currentAveragePriceHQ"] = listing_data["currentAveragePriceHQ"]
    entry_data["averagePriceHQ"] = listing_data["averagePriceHQ"]
    entry_data["currentPriceDifferenceHQ"] = (
        listing_data["currentAveragePriceHQ"] - listing_data["minPriceHQ"]
    )
    print("- Successfully obtained listing data from Universalis.")

    # Sale velocities are kind of weird, so we need to make a separate request for historical data.
    sale_request = urllib.Request(
        f"https://universalis.app/api/history/{world_name}/{item_id}"
    )
    sale_request.add_header("User-Agent", "&lt;User-Agent&gt;")
    try:
        sale_data = json.loads(urllib.urlopen(sale_request).read())
    except HTTPError:
        entry_data["nqSaleVelocity"] = 0
        entry_data["hqSaleVelocity"] = 0
        print("- Warning: Failed to obtain sale data from Universalis.")
    else:
        entry_data["nqSaleVelocity"] = sale_data["nqSaleVelocity"]
        entry_data["hqSaleVelocity"] = sale_data["hqSaleVelocity"]
        print("- Successfully obtained historical sale data from Universalis.")

    return entry_data


#####
# Main Program
#####

sqlite3.register_adapter(datetime, lambda ts: time.mktime(ts.timetuple()))
con = sqlite3.connect("market_analyzer.db")
con.row_factory = dict_factory
cur = con.cursor()

# Update last DB update time
variables.init(pathlib.Path("./variables.json").resolve())
last_update_time = variables.get_variable("lastUpdateTime")
if last_update_time is None:
    last_update_time = str(datetime.now())
flag_update_db = (
    input(
        f"Item database was last updated at {last_update_time}. Update database (y/N)? "
    ).lower()
    == "y"
)
if flag_update_db:
    last_update_time = str(datetime.now())
variables.set_variable("lastUpdateTime", last_update_time)

selected_item_type = -1
while selected_item_type < 0 or selected_item_type >= len(ITEM_TYPES):
    print("Please select an item category from the following:")
    for i in range(1, len(ITEM_TYPES) + 1):
        print(f"  {i}. {ITEM_TYPES[i - 1]}")
    try:
        selected_item_type = (
            int(input(f"Enter your selection (1 to {len(ITEM_TYPES)}): ")) - 1
        )
    except ValueError:
        print("Please enter a number.")
items = []

# Gathering
if selected_item_type == 0:
    # Check whether gathering database exists
    if (
        cur.execute("select count(name) as count from gathering_items").fetchone()[
            "count"
        ]
        < 1
    ):
        print("Error: Gathering item database is empty. Exiting...")
        exit()
    else:
        print("Successfully connected to gathering items database.")

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
        "select item_id, name from gathering_items where gathering_level >= ? and gathering_level <= ?",
        (min_level, max_level),
    ).fetchall()
    items = list(map(lambda item: (item["item_id"], item["name"]), items))
    print(
        f"Found {len(items)} gatherable items between Level {min_level} and Level {max_level}"
    )
# Paintings
elif selected_item_type == 1:
    # Check whether paintings database exists
    if (
        cur.execute("select count(name) as count from painting_items").fetchone()[
            "count"
        ]
        < 1
    ):
        print("Error: Paintings database is empty. Exiting...")
        exit()
    else:
        print("Successfully connected to paintings database.")

    items = cur.execute("select item_id, name from painting_items").fetchall()
    items = list(map(lambda item: (item["item_id"], item["name"]), items))
    print(f"Found {len(items)} paintings.")

world_name = input("Enter name of World or Data Centre (Default: Faerie): ")
if len(world_name) < 1:
    world_name = "Faerie"

num_recommendations = 5
try:
    num_recommendations = int(
        input("Enter number of desired recommendations (Default: 5): ")
    )
except ValueError:
    pass

# Gathering items don't have high-quality versions anymore, so a lot of those are going to be commented out.
# I might still use this for other stuff though, so it's not going to be removed entirely.

print("\nMaking Universalis requests...\n")
univ_entries = []
entry_minmaxes = {
    "listing_price_nq": MinMax(),
    "sale_price_nq": MinMax(),
    "velocity_nq": MinMax(),
    "difference_nq": MinMax(),
    "listing_price_hq": MinMax(),
    "sale_price_hq": MinMax(),
    "velocity_hq": MinMax(),
    "difference_hq": MinMax(),
}
entries = query_items(items, world_name)
for entry in entries:
    if entry == {}:
        continue
    univ_entries.append(entry)
    entry = univ_entries[len(univ_entries) - 1]

    entry_minmaxes["listing_price_nq"].add_value(entry["currentAveragePriceNQ"])
    entry_minmaxes["sale_price_nq"].add_value(entry["averagePriceNQ"])
    entry_minmaxes["velocity_nq"].add_value(entry["nqSaleVelocity"])
    entry_minmaxes["difference_nq"].add_value(entry["currentPriceDifferenceNQ"])

    # entry_minmaxes["listing_price_hq"].add_value(
    #     entry["currentAveragePriceHQ"])
    # entry_minmaxes["sale_price_hq"].add_value(entry["averagePriceHQ"])
    # entry_minmaxes["velocity_hq"].add_value(entry["hqSaleVelocity"])
    # entry_minmaxes["difference_hq"].add_value(entry["currentPriceDifferenceHQ"])

if len(univ_entries) < 1:
    print("\nError: No results found. Exiting...")
    exit()
else:
    print(f"\nSuccessfully found results for {len(univ_entries)} items.")

for entry in univ_entries:
    entry["score_nq"] = (
        entry_minmaxes["listing_price_nq"].get_t(entry["currentAveragePriceNQ"])
        * WEIGHT_AVG_LISTING_PRICE
        + entry_minmaxes["sale_price_nq"].get_t(entry["averagePriceNQ"])
        * WEIGHT_AVG_SALE_PRICE
        + entry_minmaxes["velocity_nq"].get_t(entry["nqSaleVelocity"])
        * WEIGHT_SALE_VELOCITY
        + WEIGHT_MIN_AVG_PRICE_DIFF
        - (
            entry_minmaxes["difference_nq"].get_t(entry["currentPriceDifferenceNQ"])
            * WEIGHT_MIN_AVG_PRICE_DIFF
        )
    )
    # entry["score_hq"] = entry_minmaxes["listing_price_hq"].get_t(
    #     entry["currentAveragePriceHQ"]) * WEIGHT_AVG_LISTING_PRICE + entry_minmaxes["sale_price_hq"].get_t(
    #     entry["averagePriceHQ"]) * WEIGHT_AVG_SALE_PRICE + entry_minmaxes["velocity_hq"].get_t(
    #         entry["hqSaleVelocity"]) * WEIGHT_SALE_VELOCITY + entry_minmaxes["difference_hq"].get_t(
    #             entry["currentPriceDifferenceHQ"]) * WEIGHT_MIN_AVG_PRICE_DIFF

sorted_nq_raw = sorted(univ_entries, key=lambda entry: entry["score_nq"], reverse=True)[
    :num_recommendations
]
# sorted_hq_raw = sorted(univ_entries, key=lambda entry: entry["score_hq"])[:5]

# Formatted for the tabulate library
sorted_nq = {
    "Name": [],
    "Avg. Listing Price": [],
    "Avg. Sale Price": [],
    "Sales Per Day": [],
    "Avg - Min Listing Price": [],
}
for entry in sorted_nq_raw:
    sorted_nq["Name"].append(entry["item_name"])
    sorted_nq["Avg. Listing Price"].append(entry["currentAveragePriceNQ"])
    sorted_nq["Avg. Sale Price"].append(entry["averagePriceNQ"])
    sorted_nq["Sales Per Day"].append(entry["nqSaleVelocity"])
    sorted_nq["Avg - Min Listing Price"].append(entry["currentPriceDifferenceNQ"])

# sorted_hq = {"Name": [], "Avg. Listing Price": [], "Avg. Sale Price": [], "Sales Per Day": [], "Avg - Min Listing Price": []}
# for entry in sorted_nq_raw:
#     sorted_hq["Name"].append(entry["item_name"])
#     sorted_hq["Avg. Listing Price"].append(entry["currentAveragePriceHQ"])
#     sorted_hq["Avg. Sale Price"].append(entry["averagePriceHQ"])
#     sorted_hq["Sales Per Day"].append(entry["hqSaleVelocity"])
#     sorted_hq["Avg - Min Listing Price"].append(entry["currentPriceDifferenceHQ"])

print("\nRecommended NQ Items:")
print(tabulate(sorted_nq, headers="keys", tablefmt="fancy_grid", floatfmt=".2f"))
# print("\nRecommended HQ Items:")
# print(tabulate(sorted_hq, headers="keys", tablefmt="fancy_grid"))

variables.close()
con.close()
