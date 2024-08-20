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
    Retrieves the last inserted document from the given collection.

    Args:
    - collection: MongoDB collection object

    Returns:
    - dict: The last inserted document, or None if no documents exist
    """
    cursor = collection.find().sort('$natural', -1).limit(1)
    try:
        return next(cursor)
    except StopIteration:
        return None  