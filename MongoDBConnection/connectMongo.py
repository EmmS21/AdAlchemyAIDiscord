from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from urllib.parse import quote_plus
from datetime import datetime

load_dotenv()


def connect_to_mongo_and_get_collection(connection_string, db_name, collection_name):
    """
    Establishes a connection to the MongoDB server and retrieves the specified collection.

    Args:
    - connection_string (str): The MongoDB connection string.
    - db_name (str): The name of the database.
    - collection_name (str): The name of the collection.

    Returns:
    - Collection: The requested MongoDB collection, or None if authentication failed.
    """
    try:
        client = MongoClient(connection_string)
        client.admin.command('ismaster') 
        print("MongoDB connection successful.")
                
        db = client[db_name]
        collection = db[collection_name]
        print(f"Successfully authenticated to the database '{db_name}' and accessed collection '{collection_name}'.")
        return collection
    except (ConnectionFailure, OperationFailure) as e:
        print(f"MongoDB connection or operation failed: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return None
    