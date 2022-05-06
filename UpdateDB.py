from dataclasses import dataclass
from urllib.error import HTTPError
import urllib.request as urllib
import json
import sqlite3
from ratelimit import limits, sleep_and_retry

def dict_factory(cursor, row):
# From the sqlite3 documentation
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

@sleep_and_retry
@limits(20, 1)
def query_gathering_item(id):
    request = urllib.Request(f"https://xivapi.com/gatheringitem/{id}?columns=Item.Name,Item.ID,GatheringItemLevel.GatheringItemLevel")
    request.add_header('User-Agent', '&lt;User-Agent&gt;')
    data = json.loads(urllib.urlopen(request).read())

    try:
        out_data = {}
        out_data["name"] = data["Item"]["Name"]
        out_data["item_id"] = data["Item"]["ID"]
        out_data["gathering_level"] = data["GatheringItemLevel"]["GatheringItemLevel"]
        return out_data
    except TypeError:
        return {}

# Limit of 3000 per page, but there's only one page currently.
# Probably going to have to refactor this in the future though.
gi_request = urllib.Request("https://xivapi.com/gatheringitem?limit=3000")
gi_request.add_header('User-Agent', '&lt;User-Agent&gt;')
gi_data = json.loads(urllib.urlopen(gi_request).read())
if len(gi_data) < 1:
    print("Error: Failed to get GatheringItems from XIVAPI. Exiting...")
    exit()
else:
    print("Successfully retrieved GatheringItems from XIVAPI.")

gi_ids = list(map(lambda x: x["ID"], gi_data["Results"]))

print("Building GatheringItem database...")
con = sqlite3.connect("market_analyzer.db")
con.row_factory = dict_factory
cur = con.cursor()

cur.execute("drop table if exists gathering_items")
cur.execute("create table gathering_items (name text, item_id integer primary key, gathering_level integer)")
for gi_id in gi_ids:
    gi = query_gathering_item(gi_id)
    if not "name" in gi or not "item_id" in gi or not "gathering_level" in gi:
        continue
    cur.execute("insert into gathering_items values (?, ?, ?)", (gi["name"], gi["item_id"], gi["gathering_level"]))
    print(f"- Successfully added Item {gi['item_id']}: {gi['name']}.")

con.commit()

print("Finished setting up database.")