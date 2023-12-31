from pymongo.mongo_client import MongoClient
from pymongo.collection import Collection
from pymongo.cursor import Cursor
from pymongo.database import Database
from application.config import MONGO_URL


class ExtendedCollection(Collection):
    def __init__(self, database: Database, name: str, create=False):
        super().__init__(database, name, create)

    def exists(self, key: str, value: str) -> bool:
        """check if the values exists for this key in this collection

        Args:
            key (str): the key to search from
            value (any): the value to look for

        Returns:
            bool: return True if exists
        """
        if self.find_one({key: value}):
            return True
        return False

    def find(self, *args, **kwargs):
        return ExtendedCursor(self, *args, **kwargs)

    # this application usually does not consider the case where records not found
    def find_one(self, filter, *args, **kwargs) -> dict:
        result = super().find_one(filter, *args, **kwargs)
        if result is None:
            return result
        return dict(result)

    def update_one(self, filter, update, upsert=False):
        return super().update_one(filter, update, upsert=upsert)

    def update_values(self, filter: dict, update: dict):
        """This method wraps up the pymongo update_one method with "$set" operator.

        Args:
            filter (dict): A query that matches the document to update.
            update (dict): The modified fields. No need to pass "$set".

        """
        return self.update_one(filter=filter, update={"$set": update})

    def make_increments(self, filter: dict, increments: dict, upsert=False):
        """This method wraps up the pymongo update_one method with "$inc" operator.

        Args:
            filter (dict): A query that matches the document to update.
            increments (dict): The values of these fields will be add by the values passed in this argument.

        """
        return self.update_one(filter=filter, update={"$inc": increments}, upsert=upsert)


class ExtendedCursor(Cursor):
    def __init__(self, collection: ExtendedCollection, filter=None):
        super().__init__(collection, filter)

    def __check_okay_to_chain(self):
        return super(ExtendedCursor, self)._Cursor__check_okay_to_chain()

    def sort(self, key_or_list, direction):
        super().sort(key_or_list, direction)
        return self

    def skip(self, skip: int):
        super().skip(skip)
        return self

    def limit(self, limit: int):
        super().limit(limit)
        return self

    def as_list(self):
        self.__check_okay_to_chain()
        return list(self)


###################################################################

# my database handler
# the "interface" for mongo db

###################################################################


class MyDatabase:
    def __init__(self) -> None:
        client = MongoClient(MONGO_URL, connect=False)
        users_db = Database(client=client, name="users")
        posts_db = Database(client=client, name="posts")
        comments_db = Database(client=client, name="comments")
        metrics_db = Database(client=client, name="metrics")

        self._user_login = ExtendedCollection(users_db, "user-login")
        self._user_info = ExtendedCollection(users_db, "user-info")
        self._user_about = ExtendedCollection(users_db, "user-about")
        self._user_views = ExtendedCollection(users_db, "user-views")
        self._post_info = ExtendedCollection(posts_db, "post-info")
        self._post_content = ExtendedCollection(posts_db, "post-content")
        self._post_view_sources = ExtendedCollection(posts_db, "post-view-sources")
        self._comment = ExtendedCollection(comments_db, "comment")
        self._metrics_log = ExtendedCollection(metrics_db, "metrics-log")

    @property
    def user_login(self):
        return self._user_login

    @property
    def user_info(self):
        return self._user_info

    @property
    def user_about(self):
        return self._user_about

    @property
    def user_views(self):
        return self._user_views

    @property
    def post_info(self):
        return self._post_info

    @property
    def post_content(self):
        return self._post_content

    @property
    def post_view_sources(self):
        return self._post_view_sources

    @property
    def comment(self):
        return self._comment

    @property
    def metrics_log(self):
        return self._metrics_log


my_database = MyDatabase()
