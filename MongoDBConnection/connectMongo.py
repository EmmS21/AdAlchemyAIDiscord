from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

def connect_to_mongo_and_get_collection(connection_string, db_name, collection_name):
    """
    Establishes a connection to the MongoDB server and retrieves the specified collection
    in a case-insensitive manner.

    Args:
    - connection_string (str): The MongoDB connection string.
    - db_name (str): The name of the database.
    - collection_name (str): The name of the collection to retrieve.

    Returns:
    - Collection: The requested MongoDB collection, or None if authentication failed.
    """
    try:
        client = MongoClient(connection_string)
        client.admin.command('ismaster')
        print("MongoDB connection successful.")
                
        db = client[db_name]
        
        # List all collections and find the case-insensitive match
        collection_names = db.list_collection_names()
        matching_collection_name = None
        
        for name in collection_names:
            if name.lower() == collection_name.lower():
                matching_collection_name = name
                break

        if matching_collection_name:
            collection = db[matching_collection_name]
            print(f"Successfully authenticated to the database '{db_name}' and accessed collection '{matching_collection_name}'.")
            return collection
        else:
            print(f"No collection found matching the name '{collection_name}' (case-insensitive).")
            return None

    except (ConnectionFailure, OperationFailure) as e:
        print(f"MongoDB connection or operation failed: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    
    return None
