def website_exists_in_db(db, website_link):
    if db is None:
        raise ValueError("Database connection is not established.")
    for collection_name in db.list_collection_names():
        collection = db[collection_name]
        if collection.find_one({"website": website_link}):
            return True
    return False

