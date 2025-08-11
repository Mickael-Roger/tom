import requests
import json
import time
import webbrowser
import os

# --- Configuration ---
# This script generates an OAuth2 token for the Home-Connect API

# --- Constantes ---
API_BASE_URL = "https://api.home-connect.com"
# Extended scopes for appliance control
SCOPES = "IdentifyAppliance Monitor Settings Control"

def get_new_token_device_flow():
    """Starts the OAuth2 Device Flow to obtain a new token."""
    print("=== Home-Connect OAuth2 Token Generator ===\n")
    print("1. Go to https://developer.home-connect.com/")
    print("2. Create an application configured to use the 'Device Flow'")
    print("3. Copy your Client ID from your application\n")
    
    client_id = input("Enter your Client ID: ").strip()
    if not client_id:
        print("Client ID required.")
        return

    auth_url = f"{API_BASE_URL}/security/oauth/device_authorization"
    payload = {
        'client_id': client_id,
        'scope': SCOPES
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    try:
        response = requests.post(auth_url, data=payload, headers=headers)
        response.raise_for_status()
        device_auth_data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error during device authorization request: {e}")
        return

    verification_uri = device_auth_data['verification_uri']
    user_code = device_auth_data['user_code']
    device_code = device_auth_data['device_code']
    interval = device_auth_data['interval']
    expires_in = device_auth_data['expires_in']

    print("\n--- Action required ---")
    print(f"1. Open this URL in your browser: {verification_uri}")
    print(f"2. Enter the following code: {user_code}")
    print("3. Login and authorize the application with the requested permissions.")
    print(f"You have approximately {expires_in // 60} minutes to do this.\n")
    webbrowser.open(verification_uri)

    token_url = f"{API_BASE_URL}/security/oauth/token"
    polling_payload = {
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
        'device_code': device_code,
        'client_id': client_id
    }

    start_time = time.time()
    while time.time() - start_time < expires_in:
        print("Waiting for authorization...")
        time.sleep(interval)
        
        response = requests.post(token_url, data=polling_payload, headers=headers)
        token_data = response.json()

        if response.status_code == 200 and 'access_token' in token_data:
            print("\nAuthorization successful!")
            token_data['created_at'] = time.time()
            
            access_token = token_data['access_token']
            refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 86400)
            
            print("\n=== GENERATED TOKENS ===")
            print("Access Token:", access_token)
            if refresh_token:
                print("Refresh Token:", refresh_token)
                print(f"Token expires in: {expires_in} seconds ({expires_in/3600:.1f} hours)")
            else:
                print("Warning: No refresh token provided by Home Connect API")
            print("\n=== END OF TOKENS ===\n")
            
            print("RECOMMENDED: Add this configuration to your config.yml:")
            print("services:")
            print("  homeconnect:")
            if refresh_token:
                print("    token:")
                print(f"      access_token: \"{access_token}\"")
                print(f"      refresh_token: \"{refresh_token}\"")
            else:
                print(f"    token: \"{access_token}\"")
            
            print("\nNOTE: The new token format with refresh_token enables automatic")
            print("token renewal. The module will refresh the token 12 hours before")
            print("expiration to ensure continuous service.")
            return
        
        elif token_data.get('error') == 'authorization_pending':
            continue
        elif token_data.get('error') == 'slow_down':
            interval += 5
            continue
        else:
            print("Error obtaining token:", token_data.get('error_description', 'Unknown error'))
            return

    print("Authorization timeout has expired.")

if __name__ == "__main__":
    get_new_token_device_flow()
