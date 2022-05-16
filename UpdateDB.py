import urllib.request as urllib
import json
import sqlite3
from ratelimit import limits, sleep_and_retry
from typing import List


def dict_factory(cursor, row):
    # From the sqlite3 documentation
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


@sleep_and_retry
@limits(20, 1)
def query_gathering_item(id):
    request = urllib.Request(
        f"https://xivapi.com/gatheringitem/{id}?columns=Item.Name,Item.ID,GatheringItemLevel.GatheringItemLevel"
    )
    request.add_header("User-Agent", "&lt;User-Agent&gt;")
    data = json.loads(urllib.urlopen(request).read())

    try:
        out_data = {}
        out_data["name"] = data["Item"]["Name"]
        out_data["item_id"] = data["Item"]["ID"]
        out_data["gathering_level"] = data["GatheringItemLevel"]["GatheringItemLevel"]
        return out_data
    except TypeError:
        return {}


@sleep_and_retry
@limits(20, 1)
def query_regular_item(id):
    request = urllib.Request(f"https://xivapi.com/item/{id}?columns=Name,ID")
    request.add_header("User-Agent", "&lt;User-Agent&gt;")
    data = json.loads(urllib.urlopen(request).read())

    try:
        out_data = {}
        out_data["name"] = data["Name"]
        out_data["item_id"] = data["ID"]
        return out_data
    except TypeError:
        return {}


def get_item_ids(base_url: str, params: List[str], name: str) -> List[int]:
    params = "&".join(params)
    cur_page = 1
    ids = []
    print(f"Attempting to retrieve {name}s from XIVAPI")
    while cur_page is not None:
        request = urllib.Request(f"{base_url}?{params}&limit=3000?page={cur_page}")
        request.add_header("User-Agent", "&lt;User-Agent&gt;")
        data = json.loads(urllib.urlopen(request).read())
        if len(data) < 1:
            print(f"Error: Failed to get {name}s from XIVAPI. Exiting...")
        else:
            print(f"Successfully retrieved {name}s from XIVAPI.")

        ids.extend(map(lambda x: x["ID"], data["Results"]))
        # print(data)
        if data["Pagination"]["PageNext"] != cur_page:
            cur_page = data["Pagination"]["PageNext"]
        else:
            break
    return ids


gi_ids = set(get_item_ids("https://xivapi.com/gatheringitem", [], "GatheringItem"))

# Used to check which items are actually marketable from Universalis
univ_request = urllib.Request("https://universalis.app/api/marketable")
univ_request.add_header("User-Agent", "&lt;User-Agent&gt;")
univ_data = set(json.loads(urllib.urlopen(univ_request).read()))

con = sqlite3.connect("market_analyzer.db")
con.row_factory = dict_factory
cur = con.cursor()

if input("Update GatheringItem database (Y/n)? ").lower() != "n":
    print("Building GatheringItem database...")

    cur.execute("drop table if exists gathering_items")
    cur.execute(
        "create table gathering_items (name text, item_id integer primary key, gathering_level integer)"
    )
    for gi_id in gi_ids:
        gi = query_gathering_item(gi_id)
        if not "name" in gi or not "item_id" in gi or not "gathering_level" in gi:
            continue
        if not gi["item_id"] in univ_data:
            continue
        try:
            cur.execute(
                "insert into gathering_items values (?, ?, ?)",
                (gi["name"], gi["item_id"], gi["gathering_level"]),
            )
        except sqlite3.IntegrityError:
            print(f"- Skipping Item {gi['item_id']}: {gi['name']} as ID is taken.")
        else:
            print(f"- Successfully added Item {gi['item_id']}: {gi['name']}.")

    con.commit()

if input("Update Paintings database (Y/n)? ").lower() != "n":
    print("Building Paintings database...")
    painting_ids = set(
        get_item_ids(
            "https://xivapi.com/search",
            ["filters=ItemSearchCategory.ID=82"],
            "Painting",
        )
    )

    cur.execute("drop table if exists painting_items")
    cur.execute("create table painting_items (name text, item_id integer primary key)")
    for painting_id in painting_ids:
        painting = query_regular_item(painting_id)
        if not "name" in painting or not "item_id" in painting:
            continue
        if not painting["item_id"] in univ_data:
            continue
        try:
            cur.execute(
                "insert into painting_items values (?, ?)",
                (painting["name"], painting["item_id"]),
            )
        except sqlite3.IntegrityError:
            print(
                f"- Skipping Item {painting['item_id']}: {painting['name']} as ID is taken."
            )
        else:
            print(
                f"- Successfully added Item {painting['item_id']}: {painting['name']}."
            )

    con.commit()

print("Finished setting up database.")
