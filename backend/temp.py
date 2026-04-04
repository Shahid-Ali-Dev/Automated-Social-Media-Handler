import os
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# This is the master permission scope for managing a Business Profile
SCOPES = ['https://www.googleapis.com/auth/business.manage']

def fetch_business_ids():
    print("Initiating Google Login...")
    
    # 1. Boot up the local auth server using your downloaded secret file
    # This will open a browser window asking you to log in to Google
    flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
    creds = flow.run_local_server(port=8080)

    print("Login successful! Fetching data...\n")

    # 2. Connect to the Account Management API
    account_api = build('mybusinessaccountmanagement', 'v1', credentials=creds)
    accounts_result = account_api.accounts().list().execute()
    
    accounts = accounts_result.get('accounts', [])
    if not accounts:
        print("No accounts found. Make sure the Google account you logged in with is an Owner/Manager of the Maps listing.")
        return

    print("=========================================")
    print("        GOOGLE BUSINESS PROFILE IDs      ")
    print("=========================================\n")

    for acc in accounts:
        account_name = acc.get('name') # Formatted as 'accounts/123456789'
        print(f"🏢 ACCOUNT LEVEL")
        print(f"Account Name:  {acc.get('accountName')}")
        print(f"Account ID:    {account_name}  <-- Save this to .env as GOOGLE_ACCOUNT_ID")
        print("-" * 40)
        
        # 3. Connect to the Business Information API to get the specific storefronts
        location_api = build('mybusinessbusinessinformation', 'v1', credentials=creds)
        
        try:
            # We fetch the locations belonging to the parent account
            locations_result = location_api.accounts().locations().list(
                parent=account_name,
                readMask="name,title" # We only need the ID and the display name
            ).execute()
            
            locations = locations_result.get('locations', [])
            if locations:
                for loc in locations:
                    print(f"📍 LOCATION LEVEL")
                    print(f"Business Title: {loc.get('title')}")
                    print(f"Location ID:    {loc.get('name')}  <-- Save this to .env as GOOGLE_LOCATION_ID")
                    print("\n")
            else:
                print("  No verified locations found under this account.")
        except Exception as e:
            print(f"  Error fetching locations: {e}")

if __name__ == '__main__':
    fetch_business_ids()