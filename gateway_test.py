import urllib.request
import urllib.error
import json
import time

# Target the Kong Gateway port 8080
BASE_URL = "http://127.0.0.1:8080"
EMAIL = f"test_{int(time.time())}@test.com"
PASSWORD = "P@ssword"

def make_request(path, method="GET", headers=None, data=None):
    url = f"{BASE_URL}{path}"
    headers = headers or {}
    req_data = None
    if data is not None:
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            body = json.loads(body)
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return 0, str(e)

print("--- 1. Testing Registration via Kong ---")
status, res = make_request("/api/auth/register", "POST", data={"email": EMAIL, "password": PASSWORD})
print(f"Status: {status}, Response: {res}\n")

print("--- 2. Testing Login via Kong ---")
status, res = make_request("/api/auth/login", "POST", data={"email": EMAIL, "password": PASSWORD})
print(f"Status: {status}, Response: {res}")
assert status == 200, "Login failed!"
token = res["access_token"]
print("Token acquired successfully.\n")

print("--- 2.5. Testing Public Product Catalog (Anonymous) ---")
status, res = make_request("/api/products/items/", "GET")
# Print a snippet of the product list to verify it succeeded
print(f"Status: {status}, Products found: {len(res)} items")
assert status == 200, "Failed to fetch public product catalog!"
print("Verified: Public products catalog is accessible anonymously.\n")

print("--- 3. Testing Protected Route /api/orders/ WITHOUT Token ---")
status, res = make_request("/api/orders/", "GET")
print(f"Status: {status}, Response: {res}")
assert status == 401, "Protected route allowed request without token!"
print("Verified: Kong correctly blocked unauthorized request with 401.\n")

print("--- 4. Testing Protected Route /api/orders/ WITH Token ---")
headers = {"Authorization": f"Bearer {token}"}
# First create an order
status, res = make_request("/api/orders/", "POST", headers=headers, data={
    "items": [{"product": 1, "quantity": 1}]
})
print(f"Status: {status}, Response: {res}")
assert status in [200, 201], "Order creation failed!"
order_id = res["id"]
print("Order created successfully.\n")

print("--- 5. Testing Legacy Checkout Path WITH Token ---")
# Verifies path rewriting and JWT validation on the /orders/ path matching the API spec
status, res = make_request(f"/orders/{order_id}/create-checkout-session/", "POST", headers=headers, data={})
print(f"Status: {status}, Response: {res}")
assert status == 200, "Checkout session creation failed!"
print("Legacy checkout path path-rewriting and verification works perfectly!\n")

print("--- ALL INTEGRATION TESTS PASSED SUCCESSFULLY! ---")
