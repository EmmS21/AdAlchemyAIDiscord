from pymongo import DESCENDING

def website_exists_in_db(db, website_link):
    if db is None:
        raise ValueError("Database connection is not established.")
    for collection_name in db.list_collection_names():
        collection = db[collection_name]
        if collection.find_one({"website": website_link}):
            return True
    return False

def get_latest_document(collection):
    """
    Retrieves the most recent document from the given collection.

    Args:
    - collection: MongoDB collection object

    Returns:
    - dict: The most recent document, or None if no documents exist
    """
    return collection.find_one(sort=[("timestamp", DESCENDING)])