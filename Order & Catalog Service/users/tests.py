from django.test import TestCase

# Create your tests here.
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from .models import CustomUser

@pytest.mark.django_db
def test_user_registration():
    client = APIClient() # This acts like our web browser/React app
    url = reverse('users:register') # Dynamically finds the /api/users/register/ URL
    
    data = {
        'email': 'testbuyer@gmail.com',
        'password': 'SecurePassword123!',
        'first_name': 'Test',
        'last_name': 'Buyer'
    }
    
    # 1. Action: Send the POST request
    response = client.post(url, data)
    
    # 2. Assertions: Prove the API behaved correctly
    assert response.status_code == 201 # 201 means "Created successfully"
    assert CustomUser.objects.count() == 1 # Proves it actually saved to the DB
    assert CustomUser.objects.get().email == 'testbuyer@gmail.com'