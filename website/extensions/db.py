import pymongo
from website.config import MONGO_URL

class Database(object):
    def __init__(self):

        client = pymongo.MongoClient(MONGO_URL, connect=False)
        self.db = client['blog']

    def exists(self, collection, key, value):
        exists = collection.find_one({key: value})
        if exists:
            return True
        return False
    
    def find(self, collection, query):
        return collection.find(query)
    
    def find_one(self, collection, query):
        return collection.find_one(query)
    
    def insert_one(self, collection, data):
        return collection.insert_one(data)
    
    def update_one(self, collection, filter, update):
        return collection.update_one(filter, update)
    
    def delete_one(self, collection, query):
        return collection.delete_one(query)

class DB_Users(Database):

    def __init__(self):
        super().__init__()
        self.collection = self.db['users']

    def exists(self, key, value):
        return super().exists(self.collection, key, value)
    
    def find(self, query):
        return super().find(self.collection, query)
    
    def find_one(self, query):
        return super().find_one(self.collection, query)
    
    def insert_one(self, data):
        return super().insert_one(self.collection, data)
    
    ## own methods    
    def create_user(self, data):
        
        self.collection.insert_one(data)
    
    def update_values(self, username, key, value):
        # pass list to update multiple keys at once
        if isinstance(key, str):
            new_value = {"$set": { key: value}}
            self.collection.update_one({'username': username}, new_value)

        elif isinstance(key, list) and isinstance(value, list):
            new_values = {"$set": {}}
            for i in range(len(key)):
                new_values['$set'][key[i]] = value[i]
            self.collection.update_one({'username': username}, new_values)

class DB_Posts(Database):

    def __init__(self):
        super().__init__()
        self.collection = self.db['posts']

    def find(self, query):
        return super().find(self.collection, query)

    def find_one(self, query):
        return super().find_one(self.collection, query)
    
    def update_one(self, filter, update):
        return super().update_one(self.collection, filter, update)
    
    def delete_one(self, query):
        return super().delete_one(self.collection, query)
    
    ## own methods

    def new_post(self, new_post):

        self.collection.insert_one(new_post)

    def exists(self, key, value):
        return super().exists(self.collection, key, value)
    
    def count_documents(self, query):

        return self.collection.count_documents(query)
    






class DB_Comments(Database):

    def __init__(self):
        super().__init__()
        self.collection = self.db['comments']        




db_users = DB_Users()
db_posts = DB_Posts()
db_comments = DB_Comments()