import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("PetstoreServer")

PETSTORE_BASE_URL = "https://petstore.swagger.io/v2"

@mcp.tool()
def get_store_inventory() -> str:
    """
    Returns a map of status codes to quantities from the store inventory.
    """
    url = f"{PETSTORE_BASE_URL}/store/inventory"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return f"Error retrieving store inventory: {e}"

@mcp.tool()
def find_pets_by_status(status: str) -> str:
    """
    Finds pets by their status.
    
    Args:
        status: The status of the pet to find. Valid values are 'available', 'pending', 'sold'.
    """
    url = f"{PETSTORE_BASE_URL}/pet/findByStatus"
    params = {"status": status}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return f"Error finding pets by status '{status}': {e}"

@mcp.tool()
def get_pet_by_id(pet_id: int) -> str:
    """
    Finds a single pet by its numeric ID.
    
    Args:
        pet_id: The ID of the pet to fetch.
    """
    url = f"{PETSTORE_BASE_URL}/pet/{pet_id}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 404:
            return f"Pet with ID {pet_id} not found."
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return f"Error retrieving pet with ID {pet_id}: {e}"

@mcp.tool()
def add_pet(name: str, status: str = "available", photo_urls: list[str] = None) -> str:
    """
    Adds a new pet to the store inventory.
    
    Args:
        name: The name of the pet to add.
        status: The status of the pet ('available', 'pending', 'sold').
        photo_urls: Optional list of URLs with photos of the pet.
    """
    url = f"{PETSTORE_BASE_URL}/pet"
    data = {
        "name": name,
        "status": status,
        "photoUrls": photo_urls or []
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return f"Pet successfully added: {response.text}"
    except requests.RequestException as e:
        return f"Error adding pet '{name}': {e}"

@mcp.tool()
def delete_pet(pet_id: int) -> str:
    """
    Deletes a pet from the store inventory by its ID.
    
    Args:
        pet_id: The ID of the pet to delete.
    """
    url = f"{PETSTORE_BASE_URL}/pet/{pet_id}"
    try:
        response = requests.delete(url, timeout=10)
        if response.status_code == 404:
            return f"Pet with ID {pet_id} not found for deletion."
        response.raise_for_status()
        return f"Pet with ID {pet_id} successfully deleted."
    except requests.RequestException as e:
        return f"Error deleting pet with ID {pet_id}: {e}"

if __name__ == "__main__":
    # Run the FastMCP server, listening for tool calls via stdio.
    mcp.run()
