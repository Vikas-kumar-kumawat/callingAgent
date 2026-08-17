import requests

url = "https://6e33-103-137-84-230.ngrok-free.app/api/call"

data = {
    "phone": "+919057262630",
    "name": "Vikas"
}

try:
    response = requests.post(url, json=data, timeout=30)
    print("Status:", response.status_code)
    print("Response:")
    print(response.text)
except Exception as e:
    print("Error calling endpoint:", e)