# Module defines a class for representing XIVAPI ElasticSearch Queries (https://xivapi.com/docs/Search#advanced)


class Query(object):
    def __init__(self) -> None:
        self.indexes = ["Item"]
