import os
import requests
from dotenv import load_dotenv

# Load your new tokens from the .env file
load_dotenv()

access_token = os.environ.get("PINTEREST_INITIAL_ACCESS_TOKEN")

if not access_token:
    print("Error: Could not find PINTEREST_INITIAL_ACCESS_TOKEN in your .env file.")
    exit()

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

print("Fetching your boards...\n")
response = requests.get("https://api.pinterest.com/v5/boards", headers=headers)

if response.status_code == 200:
    data = response.json()
    boards = data.get("items", [])
    
    if not boards:
        print("Success, but your account has NO boards! Go to Pinterest.com and create one first.")
    else:
        for board in boards:
            print(f"Board Name: {board['name']}")
            print(f"Board ID:   {board['id']}")
            print("-" * 30)
else:
    print(f"Failed to fetch boards: {response.text}")