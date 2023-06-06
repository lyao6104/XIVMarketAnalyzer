import json
import sqlite3
import urllib.request as urllib
from typing import List
from urllib.error import HTTPError

from ratelimit import limits, sleep_and_retry

from .util import get_user_agent


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
    request.add_header("User-Agent", get_user_agent())
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
def query_gathering_items(ids, batch_size=20):
    batches = []
    entries = []
    while len(ids) > 0:
        batches.append(ids[:batch_size])
        ids = ids[batch_size:]
    print(f"Querying {len(batches)} batches of {batch_size} items each...")

    for i in range(0, len(batches)):
        id_batch = batches[i]
        print(f"- Querying XIVAPI for Batch {i + 1}...")

        request = urllib.Request(
            # TODO Could probably format "columns" in a better way
            f"https://xivapi.com/gatheringitem?limit={batch_size}&ids={','.join(map(str, id_batch))}&columns=Item.Name,Item.ID,GatheringItemLevel.GatheringItemLevel"
        )
        request.add_header("User-Agent", get_user_agent())
        try:
            response = json.loads(urllib.urlopen(request).read())
        except HTTPError:
            print("  - Request failed. Skipping batch...")
            continue
        if False in response["Results"]:
            print(
                f"  - Failed to retrieve data for {response['Results'].count(False)} items."
            )
        else:
            print("  - Successfully found item data for all items in batch:")

        for item in response["Results"]:
            if not item:
                continue

            entry_data = {
                "item_id": item["Item"]["ID"],
                "name": item["Item"]["Name"],
                "gathering_level": item["GatheringItemLevel"]["GatheringItemLevel"],
            }
            entries.append(entry_data)
            print(
                f"    - Found data for Item {entry_data['item_id']}: {entry_data['name']}, {entry_data['gathering_level']}"
            )
    return entries


@sleep_and_retry
@limits(20, 1)
def query_regular_item(id):
    request = urllib.Request(f"https://xivapi.com/item/{id}?columns=Name,ID")
    request.add_header("User-Agent", get_user_agent())
    data = json.loads(urllib.urlopen(request).read())

    try:
        out_data = {}
        out_data["name"] = data["Name"]
        out_data["item_id"] = data["ID"]
        return out_data
    except TypeError:
        return {}


@sleep_and_retry
@limits(20, 1)
def query_regular_items(ids, batch_size=20):
    # Note that querying items in batches can only retrieve name and item id.
    # Shouldn't be an issue since those are the only columns needed currently.

    batches = []
    entries = []
    while len(ids) > 0:
        batches.append(ids[:batch_size])
        ids = ids[batch_size:]
    print(f"Querying {len(batches)} batches of {batch_size} items each...")

    for i in range(0, len(batches)):
        id_batch = batches[i]
        print(f"- Querying XIVAPI for Batch {i + 1}...")

        request = urllib.Request(
            f"https://xivapi.com/item?limit={batch_size}&ids={','.join(map(str, id_batch))}"
        )
        request.add_header("User-Agent", get_user_agent())
        try:
            response = json.loads(urllib.urlopen(request).read())
        except HTTPError:
            print("  - Request failed. Skipping batch...")
            continue
        if False in response["Results"]:
            print(
                f"  - Failed to retrieve data for {response['Results'].count(False)} items."
            )
        else:
            print("  - Successfully found item data for all items in batch:")

        for item in response["Results"]:
            if not item:
                continue

            entry_data = {
                "item_id": item["ID"],
                "name": item["Name"],
            }
            entries.append(entry_data)
            print(
                f"    - Found data for Item {entry_data['item_id']}: {entry_data['name']}"
            )
    return entries


def get_item_ids(base_url: str, params: List[str], name: str) -> List[int]:
    params = "&".join(params)
    cur_page = 1
    ids = []
    print(f"Attempting to retrieve {name}s from XIVAPI")
    while cur_page is not None:
        request = urllib.Request(f"{base_url}?{params}&limit=3000?page={cur_page}")
        request.add_header("User-Agent", get_user_agent())
        data = json.loads(urllib.urlopen(request).read())
        if len(data) < 1:
            print(f"Error: Failed to get {name}s from XIVAPI. Exiting...")
        else:
            print(f"Successfully retrieved {name}s on Page {cur_page} from XIVAPI.")

        ids.extend(map(lambda x: x["ID"], data["Results"]))
        # print(data)
        if data["Pagination"]["PageNext"] != cur_page:
            cur_page = data["Pagination"]["PageNext"]
        else:
            break
    return ids


def update_db() -> None:
    # Used to check which items are actually marketable from Universalis
    univ_request = urllib.Request("https://universalis.app/api/marketable")
    univ_request.add_header("User-Agent", get_user_agent())
    univ_data = set(json.loads(urllib.urlopen(univ_request).read()))

    con = sqlite3.connect("market_analyzer.db")
    con.row_factory = dict_factory
    cur = con.cursor()

    if input("Update GatheringItem database (Y/n)? ").lower() != "n":
        print("Building GatheringItem database...")
        gi_ids = set(
            get_item_ids("https://xivapi.com/gatheringitem", [], "GatheringItem")
        )

        cur.execute("drop table if exists gathering_items")
        cur.execute(
            "create table gathering_items (name text, item_id integer primary key, gathering_level integer)"
        )
        gis = query_gathering_items(list(gi_ids))
        for gi in gis:
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
        cur.execute(
            "create table painting_items (name text, item_id integer primary key)"
        )
        painting_items = query_regular_items(list(painting_ids))
        for painting in painting_items:
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

    if input("Update Orchestrion Roll database (Y/n)? ").lower() != "n":
        print("Building Orchestrion Roll database...")
        orchestrion_roll_ids = set(
            get_item_ids(
                "https://xivapi.com/search",
                ["filters=ItemUICategory.ID=94"],
                "Orchestrion Roll",
            )
        )

        cur.execute("drop table if exists orchestrion_roll_items")
        cur.execute(
            "create table orchestrion_roll_items (name text, item_id integer primary key)"
        )
        orchestrion_roll_items = query_regular_items(list(orchestrion_roll_ids))
        for orchestrion_roll in orchestrion_roll_items:
            if not "name" in orchestrion_roll or not "item_id" in orchestrion_roll:
                continue
            if not orchestrion_roll["item_id"] in univ_data:
                continue
            try:
                cur.execute(
                    "insert into orchestrion_roll_items values (?, ?)",
                    (orchestrion_roll["name"], orchestrion_roll["item_id"]),
                )
            except sqlite3.IntegrityError:
                print(
                    f"- Skipping Item {orchestrion_roll['item_id']}: {orchestrion_roll['name']} as ID is taken."
                )
            else:
                print(
                    f"- Successfully added Item {orchestrion_roll['item_id']}: {orchestrion_roll['name']}."
                )

        con.commit()

    print("Finished setting up database.")
